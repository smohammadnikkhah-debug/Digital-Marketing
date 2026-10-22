"""Isolated PostgreSQL verification of D2.2 migration + rollback (not production).

Requires STOCKANALYSIS_ISOLATED_DATABASE_URL pointing at a disposable Postgres
database. Skips cleanly when unavailable.

Safety: never targets production by default; refuses known Supabase host markers
unless STOCKANALYSIS_ALLOW_ISOLATED_ON_SHARED=1 is set.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
FORWARD_SQL = MIGRATIONS_DIR / "d2_2_paper_orders_transactional.sql"
ROLLBACK_SQL = MIGRATIONS_DIR / "d2_2_paper_orders_transactional_rollback.sql"

BLOCKED_HOST_FRAGMENTS = (
    "supabase.co",
    "pooler.supabase",
)


def _isolated_url() -> str:
    url = os.getenv("STOCKANALYSIS_ISOLATED_DATABASE_URL", "").strip()
    if not url:
        raise unittest.SkipTest(
            "Set STOCKANALYSIS_ISOLATED_DATABASE_URL to a disposable Postgres DSN"
        )
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    allow_shared = os.getenv("STOCKANALYSIS_ALLOW_ISOLATED_ON_SHARED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_shared and any(frag in url.lower() for frag in BLOCKED_HOST_FRAGMENTS):
        raise unittest.SkipTest(
            "Refusing to run isolated migration tests against Supabase/shared host "
            "without STOCKANALYSIS_ALLOW_ISOLATED_ON_SHARED=1"
        )
    return url


@pytest.mark.isolated_postgres
class TestIsolatedPostgresMigrationD22(unittest.TestCase):
    def setUp(self):
        self.url = _isolated_url()
        self.conn = psycopg2.connect(self.url)
        self.conn.autocommit = True
        self.cur = self.conn.cursor()

    def tearDown(self):
        try:
            self.cur.close()
            self.conn.close()
        except Exception:
            pass

    def _table_exists(self, table: str) -> bool:
        self.cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'stockanalysis' AND table_name = %s
            """,
            (table,),
        )
        return self.cur.fetchone() is not None

    def test_01_forward_migration_creates_paper_tables_and_constraints(self):
        forward = FORWARD_SQL.read_text(encoding="utf-8")
        # Clean slate for disposable DB
        self.cur.execute("DROP SCHEMA IF EXISTS stockanalysis CASCADE")
        self.cur.execute(forward)

        for table in ("paper_orders", "paper_order_events", "paper_execution_claims"):
            self.assertTrue(self._table_exists(table), f"missing {table}")

        self.cur.execute(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'stockanalysis'
              AND t.relname = 'paper_orders'
              AND c.conname = 'chk_paper_orders_account'
            """
        )
        row = self.cur.fetchone()
        self.assertIsNotNone(row)
        cdef = row[0]
        self.assertIn("alpaca", cdef.lower())
        self.assertRegex(cdef, r"DU\|DF|DU|DF")

    def test_02_rollback_archives_then_drops_when_rows_exist(self):
        forward = FORWARD_SQL.read_text(encoding="utf-8")
        rollback = ROLLBACK_SQL.read_text(encoding="utf-8")
        self.cur.execute("DROP SCHEMA IF EXISTS stockanalysis CASCADE")
        self.cur.execute(forward)

        # Insert a minimal valid IBKR paper order so archive path triggers
        self.cur.execute(
            """
            INSERT INTO stockanalysis.paper_orders (
                order_id, client_order_id, broker, account_id, symbol, action,
                order_type, quantity, limit_price, estimated_notional, status, version
            ) VALUES (
                'ORD-ISO-1', 'cid-iso-1', 'ibkr', 'DU123456', 'AAPL', 'BUY',
                'LIMIT', 1.0, 100.0, 100.0, 'DRAFT', 1
            )
            """
        )
        self.cur.execute(rollback)
        self.assertFalse(self._table_exists("paper_orders"))

        self.cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'stockanalysis' AND table_name LIKE 'paper_orders_archive_%'
            """
        )
        archives = self.cur.fetchall()
        self.assertTrue(archives, "Expected archival table after non-destructive rollback")


if __name__ == "__main__":
    unittest.main()
