"""Read-only metadata check for stockanalysis.paper_* tables.

Usage (PowerShell):
  $env:STOCKANALYSIS_READONLY_DATABASE_URL = 'postgresql://...'
  python scratch/readonly_paper_schema_check.py

Or set STOCKANALYSIS_PG_* discrete variables.
Does not create/alter/drop objects. Does not print secrets.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

try:
    import psycopg2
except ImportError:
    print("RESULT: FAIL (psycopg2 not installed)")
    sys.exit(1)


def connect():
    url = (
        os.getenv("STOCKANALYSIS_READONLY_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if url.startswith("postgres"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
        # Redacted host for report only
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        conn = psycopg2.connect(url)
        return conn, host

    host = os.getenv("STOCKANALYSIS_PG_HOST", "").strip()
    user = os.getenv("STOCKANALYSIS_PG_USER", "").strip()
    password = os.getenv("STOCKANALYSIS_PG_PASSWORD", "").strip()
    dbname = os.getenv("STOCKANALYSIS_PG_DATABASE", "").strip()
    port = int(os.getenv("STOCKANALYSIS_PG_PORT", "5432") or "5432")
    if not (host and user and password and dbname):
        print("RESULT: SKIP (no PostgreSQL URL/env configured)")
        sys.exit(0)
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        sslmode=os.getenv("STOCKANALYSIS_PG_SSLMODE", "require"),
    )
    return conn, host


def main():
    conn, host = connect()
    # Never print credentials; host may be shown at high level
    print(f"CONNECTED_HOST_CLASS: {'supabase' if 'supabase' in host else 'other'}")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'stockanalysis'
          AND table_name IN (
            'paper_orders',
            'paper_order_events',
            'paper_execution_claims'
          )
        ORDER BY table_name
        """
    )
    tables = [r[0] for r in cur.fetchall()]
    expected = ["paper_execution_claims", "paper_order_events", "paper_orders"]
    present = {t: (t in tables) for t in expected}
    print("TABLE_PRESENCE:")
    for t, ok in present.items():
        print(f"  {t}: {'PRESENT' if ok else 'MISSING'}")

    if all(present.values()):
        cur.execute(
            """
            SELECT c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'stockanalysis'
              AND t.relname = 'paper_orders'
              AND c.conname = 'chk_paper_orders_account'
            """
        )
        row = cur.fetchone()
        if row:
            cdef = row[1]
            print("ACCOUNT_CONSTRAINT: PRESENT")
            print(f"  includes_alpaca: {'alpaca' in cdef.lower()}")
            print(f"  includes_ibkr_prefix: {'DU' in cdef or 'DF' in cdef}")
        else:
            print("ACCOUNT_CONSTRAINT: MISSING")
        print("RESULT: MIGRATION_APPLIED")
        code = 0
    else:
        print("RESULT: MIGRATION_NOT_APPLIED_OR_INCOMPLETE")
        code = 3

    cur.close()
    conn.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
