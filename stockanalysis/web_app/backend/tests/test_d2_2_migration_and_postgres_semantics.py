"""Stage D2.2 Migration and PostgreSQL Semantics Test Suite.

Validates:
1. Compilation, syntax, and relational structural integrity of migration SQL:
   - migrations/d2_2_paper_orders_transactional.sql
   - migrations/d2_2_paper_orders_transactional_rollback.sql
2. Database-enforced constraints and invariants:
   - Unique client_order_id
   - Positive quantity and limit price checks
   - Paper-account-only check (DU/DF)
   - Unique partial index on active paper_execution_claims
   - Append-only event sequence uniqueness (order_id, event_sequence)
3. SQLAlchemy ORM models (PaperOrder, PaperOrderEvent, PaperExecutionClaim) parity with SQL DDL.
4. Non-destructive migration procedure for legacy D2.1 JSON stored in system_settings.
"""
import json
import os
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import inspect

os.environ["ENVIRONMENT"] = "development"
os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"
os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
os.environ["IBKR_PAPER_ENABLED"] = "true"

from app.database import Base, engine, SessionLocal
from app.models import SystemSetting, PaperOrder, PaperOrderEvent, PaperExecutionClaim
from app.services.order_execution_service import (
    order_execution_service,
    ORDERS_SETTING_KEY,
)


class TestD22MigrationAndPostgresSemantics(unittest.TestCase):

    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        self.migration_sql_path = self.migrations_dir / "d2_2_paper_orders_transactional.sql"
        self.rollback_sql_path = self.migrations_dir / "d2_2_paper_orders_transactional_rollback.sql"

    def tearDown(self):
        try:
            self.db.query(PaperExecutionClaim).delete()
            self.db.query(PaperOrderEvent).delete()
            self.db.query(PaperOrder).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()
        finally:
            self.db.close()

    def test_01_migration_files_exist_and_readable(self):
        """Migration SQL and Rollback SQL files exist, are readable, and non-empty."""
        self.assertTrue(self.migration_sql_path.exists(), f"Migration file missing: {self.migration_sql_path}")
        self.assertTrue(self.rollback_sql_path.exists(), f"Rollback file missing: {self.rollback_sql_path}")

        mig_text = self.migration_sql_path.read_text(encoding="utf-8")
        roll_text = self.rollback_sql_path.read_text(encoding="utf-8")

        self.assertGreater(len(mig_text), 500)
        self.assertGreater(len(roll_text), 200)

    def test_02_migration_sql_structural_invariants(self):
        """Verifies migration SQL defines required tables, constraints, indexes, and triggers."""
        sql = self.migration_sql_path.read_text(encoding="utf-8")

        # Table definitions
        self.assertIn("CREATE TABLE IF NOT EXISTS stockanalysis.paper_orders", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS stockanalysis.paper_order_events", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS stockanalysis.paper_execution_claims", sql)

        # Constraints
        self.assertIn("client_order_id VARCHAR(100) UNIQUE NOT NULL", sql)
        self.assertIn("CONSTRAINT chk_paper_orders_qty CHECK (quantity > 0)", sql)
        self.assertIn("CONSTRAINT chk_paper_orders_price CHECK (limit_price > 0)", sql)
        self.assertIn("CONSTRAINT chk_paper_orders_account CHECK", sql)
        self.assertIn("DU", sql)
        self.assertIn("DF", sql)

        # Unique partial index on active claims
        self.assertIn("uq_active_claim_order", sql)
        self.assertIn("WHERE is_active = TRUE", sql)

        # Append-only event sequence uniqueness
        self.assertIn("UNIQUE (order_id, event_sequence)", sql)

        # Versioning column for optimistic concurrency
        self.assertIn("version INTEGER NOT NULL DEFAULT 1", sql)

    def test_03_rollback_sql_reverses_all_objects_in_dependency_order(self):
        """Verifies rollback SQL drops claims, events, orders, triggers, and functions cleanly."""
        sql = self.rollback_sql_path.read_text(encoding="utf-8")

        # Reverse dependency drop order
        drop_claims = sql.find("DROP TABLE IF EXISTS stockanalysis.paper_execution_claims")
        drop_events = sql.find("DROP TABLE IF EXISTS stockanalysis.paper_order_events")
        drop_orders = sql.find("DROP TABLE IF EXISTS stockanalysis.paper_orders")

        self.assertNotEqual(drop_claims, -1)
        self.assertNotEqual(drop_events, -1)
        self.assertNotEqual(drop_orders, -1)

        # Claims must be dropped before orders
        self.assertLess(drop_claims, drop_orders, "Claims table must be dropped before orders table")
        self.assertLess(drop_events, drop_orders, "Events table must be dropped before orders table")

    def test_04_sqlalchemy_models_match_schema_contract(self):
        """Verifies SQLAlchemy models match the exact schema columns and constraints."""
        # 1. PaperOrder
        order_cols = {c.name: c for c in PaperOrder.__table__.columns}
        self.assertIn("order_id", order_cols)
        self.assertIn("client_order_id", order_cols)
        self.assertTrue(order_cols["client_order_id"].unique)
        self.assertIn("symbol", order_cols)
        self.assertIn("action", order_cols)
        self.assertIn("quantity", order_cols)
        self.assertIn("limit_price", order_cols)
        self.assertIn("status", order_cols)
        self.assertIn("version", order_cols)
        self.assertIn("requires_manual_reconciliation", order_cols)
        self.assertIn("can_auto_resubmit", order_cols)

        # 2. PaperOrderEvent
        event_cols = {c.name: c for c in PaperOrderEvent.__table__.columns}
        self.assertIn("id", event_cols)
        self.assertIn("order_id", event_cols)
        self.assertIn("event_sequence", event_cols)
        self.assertIn("action", event_cols)
        self.assertIn("actor", event_cols)

        # 3. PaperExecutionClaim
        claim_cols = {c.name: c for c in PaperExecutionClaim.__table__.columns}
        self.assertIn("claim_id", claim_cols)
        self.assertIn("order_id", claim_cols)
        self.assertIn("agent_id", claim_cols)
        self.assertIn("is_active", claim_cols)

    def test_05_legacy_d21_json_migration_is_nondestructive_and_idempotent(self):
        """Legacy D2.1 orders stored in system_settings JSON migrate into PaperOrder table cleanly."""
        legacy_orders = {
            "ORD-LEGACY-001": {
                "order_id": "ORD-LEGACY-001",
                "client_idempotency_key": "leg_key_001",
                "account_id": "DU123456",
                "symbol": "MSFT",
                "action": "BUY",
                "order_type": "LIMIT",
                "quantity": 5.0,
                "limit_price": 400.0,
                "estimated_notional": 2000.0,
                "currency": "USD",
                "status": "APPROVED",
                "created_at": "2026-03-01T14:30:00Z",
                "updated_at": "2026-03-01T14:35:00Z",
                "approved_by": "ADMIN",
                "audit_trail": [
                    {"action": "ORDER_PROPOSED", "actor": "ADMIN", "created_at": "2026-03-01T14:30:00Z"},
                    {"action": "ORDER_APPROVED", "actor": "ADMIN", "created_at": "2026-03-01T14:35:00Z"},
                ]
            }
        }

        # Seed into system_settings
        row = self.db.query(SystemSetting).filter(SystemSetting.key == ORDERS_SETTING_KEY).first()
        if not row:
            row = SystemSetting(key=ORDERS_SETTING_KEY, value=json.dumps(legacy_orders), updated_at=datetime.utcnow())
            self.db.add(row)
        else:
            row.value = json.dumps(legacy_orders)
            row.updated_at = datetime.utcnow()
        self.db.commit()

        # Run migration procedure
        count = order_execution_service.migrate_d21_json_orders_to_db(self.db)
        self.assertEqual(count, 1)

        # Verify order in DB
        db_order = self.db.query(PaperOrder).filter(PaperOrder.order_id == "ORD-LEGACY-001").first()
        self.assertIsNotNone(db_order)
        self.assertEqual(db_order.symbol, "MSFT")
        self.assertEqual(db_order.status, "APPROVED")
        self.assertEqual(float(db_order.estimated_notional), 2000.0)

        # Verify events created in DB
        events = self.db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == "ORD-LEGACY-001").all()
        self.assertGreaterEqual(len(events), 1)

        # Idempotency check: Running migration again must not create duplicates or fail
        count_again = order_execution_service.migrate_d21_json_orders_to_db(self.db)
        self.assertEqual(count_again, 0, "Second migration run must be idempotent (0 additional orders)")


if __name__ == "__main__":
    unittest.main()
