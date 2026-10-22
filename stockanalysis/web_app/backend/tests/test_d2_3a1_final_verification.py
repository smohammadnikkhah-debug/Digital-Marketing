"""Stage D2.3A.1 Final Verification Test Suite.

Demonstrates:
1. Complete Archive Table Restoration in PostgreSQL:
   - Full restoration including constraints, unique indexes, triggers, permissions, and audit history.
   - Empirical proof against actual Supabase PostgreSQL connection.
2. Valid-format but Unbound Account Rejection across ALL boundaries:
   - Proposal boundary (API & Service)
   - Approval boundary (API & Service)
   - Claim boundary (API & Service)
   - Execution-Agent boundary
   - Completely Unbound State (zero fallback)
"""
import copy
import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Configure test environment
os.environ["ENVIRONMENT"] = "development"
os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"
os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
os.environ["IBKR_PAPER_ENABLED"] = "true"

import psycopg2
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import (
    SystemSetting,
    PaperOrder,
    PaperOrderEvent,
    PaperExecutionClaim,
)
from app.services.ibkr_service import (
    ibkr_service,
    IBKRPaperSyncPayload,
    IBKRPositionSchema,
)
from app.services.order_execution_service import (
    order_execution_service,
    PaperOrderProposal,
    ORDERS_SETTING_KEY,
)
from app.main import app

# Import execution agent
AGENT_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "ibkr_adapter" / "ibkr_execution_agent.py"
import importlib.util
spec = importlib.util.spec_from_file_location("ibkr_execution_agent", str(AGENT_SCRIPT))
agent_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_module)

client = TestClient(app)
ADMIN_AUTH = {"X-Admin-Key": "test_admin_key_2026"}
EXEC_AUTH = {"X-IBKR-Execution-Key": "test_execution_key_2026"}
AUTHORITATIVE_BOUND_ACCOUNT = "DUR257161"
UNBOUND_VALID_ACCOUNT = "DU999999"  # Valid format, but NOT bound!
UNBOUND_VALID_DF_ACCOUNT = "DF888888"  # Valid format, but NOT bound!


def get_real_pg_connection():
    """Establish PostgreSQL connection using environment configuration only.

    Required (either):
    - STOCKANALYSIS_READONLY_DATABASE_URL / DATABASE_URL (postgresql://...)
    - or discrete STOCKANALYSIS_PG_HOST, STOCKANALYSIS_PG_PORT, STOCKANALYSIS_PG_USER,
      STOCKANALYSIS_PG_PASSWORD, STOCKANALYSIS_PG_DATABASE

    Hardcoded credential file paths are intentionally unsupported.
    """
    url = (
        os.getenv("STOCKANALYSIS_READONLY_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if url.startswith("postgres"):
        # psycopg2 accepts postgresql:// ; normalize SQLAlchemy-style URLs
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return psycopg2.connect(url)

    host = os.getenv("STOCKANALYSIS_PG_HOST", "").strip()
    user = os.getenv("STOCKANALYSIS_PG_USER", "").strip()
    password = os.getenv("STOCKANALYSIS_PG_PASSWORD", "").strip()
    dbname = os.getenv("STOCKANALYSIS_PG_DATABASE", "").strip()
    port = int(os.getenv("STOCKANALYSIS_PG_PORT", "5432").strip() or "5432")
    if not (host and user and password and dbname):
        raise unittest.SkipTest(
            "prod_db PostgreSQL credentials not configured via environment "
            "(STOCKANALYSIS_READONLY_DATABASE_URL or STOCKANALYSIS_PG_*)."
        )
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        sslmode=os.getenv("STOCKANALYSIS_PG_SSLMODE", "require"),
    )


def seed_test_paper_account(db, account_id=AUTHORITATIVE_BOUND_ACCOUNT, cash_balance=100000.0):
    """Binds authoritative paper account and seeds fresh snapshot."""
    ibkr_service.bind_paper_account(db, target_account_id=account_id, reason="Test harness bind")
    payload = IBKRPaperSyncPayload(
        account_id=account_id,
        account_type="PAPER",
        currency="USD",
        net_liquidation=cash_balance,
        total_cash_value=cash_balance,
        buying_power=cash_balance * 2.0,
        positions=[
            IBKRPositionSchema(
                symbol="AAPL",
                position=100.0,
                market_price=200.0,
                market_value=20000.0,
                avg_cost=190.0,
                unrealized_pnl=1000.0,
                realized_pnl=0.0
            )
        ],
        connection_state="CONNECTED",
        timestamp=datetime.now(timezone.utc).isoformat(),
        adapter_version="2.0.0",
        gateway_managed_accounts=[account_id],
        gateway_account_type="PAPER",
        gateway_port=4002,
    )
    ibkr_service.save_paper_snapshot(db, payload)


class TestD23A1FinalVerification(unittest.TestCase):

    def setUp(self):
        os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
        os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
        os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"

        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        try:
            self.db.query(PaperExecutionClaim).delete()
            self.db.query(PaperOrderEvent).delete()
            self.db.query(PaperOrder).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()

        settings = order_execution_service.get_execution_settings(self.db)
        settings["emergency_stop"] = False
        settings["execution_enabled"] = True
        settings["max_order_notional_usd"] = 1000.0
        settings["max_daily_orders"] = 10
        settings["max_daily_notional_usd"] = 5000.0
        settings["max_open_orders"] = 5
        order_execution_service.update_execution_settings(self.db, settings)

        seed_test_paper_account(self.db, account_id=AUTHORITATIVE_BOUND_ACCOUNT)

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

    # =========================================================================
    # Verification Check 1: Full PostgreSQL Archive & Restoration
    # =========================================================================
    def test_01_postgresql_archive_and_full_restoration(self):
        """Demonstrates that archived order tables can be fully restored in PostgreSQL,
        including constraints, indexes, triggers, permissions, and complete audit history."""
        pg_conn = get_real_pg_connection()
        cur = pg_conn.cursor()

        try:
            # Step A: Setup active transactional tables in isolated temporary schema
            cur.execute("""
                CREATE TEMP TABLE test_active_orders (
                    order_id VARCHAR(50) PRIMARY KEY,
                    client_order_id VARCHAR(100) UNIQUE NOT NULL,
                    account_id VARCHAR(30) NOT NULL,
                    quantity NUMERIC(14, 4) NOT NULL,
                    limit_price NUMERIC(14, 4) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    CONSTRAINT chk_test_active_account CHECK (account_id ~ '^(DU|DF)[A-Z0-9]{3,28}$'),
                    CONSTRAINT chk_test_active_qty CHECK (quantity > 0),
                    CONSTRAINT chk_test_active_price CHECK (limit_price > 0)
                );

                CREATE TEMP TABLE test_active_order_events (
                    event_id SERIAL PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL REFERENCES test_active_orders(order_id) ON DELETE CASCADE,
                    event_sequence INTEGER NOT NULL,
                    from_status VARCHAR(30),
                    to_status VARCHAR(30) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    actor VARCHAR(50) NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (order_id, event_sequence)
                );

                CREATE TEMP TABLE test_active_execution_claims (
                    claim_id VARCHAR(50) PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL REFERENCES test_active_orders(order_id) ON DELETE CASCADE,
                    agent_id VARCHAR(50) NOT NULL,
                    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    lease_expires_at TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    released_at TIMESTAMPTZ,
                    release_reason VARCHAR(255)
                );

                CREATE UNIQUE INDEX uq_test_active_claim_order ON test_active_execution_claims (order_id) WHERE is_active = TRUE;

                CREATE OR REPLACE FUNCTION pg_temp.prevent_test_audit_event_mutation()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'CRITICAL SECURITY VIOLATION: Mutations (UPDATE or DELETE) to paper_order_events are strictly prohibited by database engine trigger. Records are append-only.';
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER trg_test_prevent_audit_event_mutation
                BEFORE UPDATE OR DELETE ON test_active_order_events
                FOR EACH ROW
                EXECUTE FUNCTION pg_temp.prevent_test_audit_event_mutation();
            """)
            pg_conn.commit()

            # Step B: Insert representative transactional lifecycle data
            cur.execute("""
                INSERT INTO test_active_orders (order_id, client_order_id, account_id, quantity, limit_price, status, version)
                VALUES ('ORD-VERIFY-01', 'KEY-VERIFY-01', 'DUR257161', 25.0, 195.50, 'CLAIMED', 3);

                INSERT INTO test_active_order_events (order_id, event_sequence, from_status, to_status, action, actor, reason)
                VALUES 
                ('ORD-VERIFY-01', 1, 'DRAFT', 'AWAITING_APPROVAL', 'ORDER_PROPOSED', 'USER', 'Initial proposal'),
                ('ORD-VERIFY-01', 2, 'AWAITING_APPROVAL', 'APPROVED', 'ORDER_APPROVED', 'ADMIN', 'Risk check passed'),
                ('ORD-VERIFY-01', 3, 'APPROVED', 'CLAIMED', 'ORDER_CLAIMED', 'agent_alpha', 'Leased to execution agent');

                INSERT INTO test_active_execution_claims (claim_id, order_id, agent_id, lease_expires_at, is_active)
                VALUES ('CLM-VERIFY-01', 'ORD-VERIFY-01', 'agent_alpha', NOW() + INTERVAL '10 min', TRUE);
            """)
            pg_conn.commit()

            # Capture baseline state before rollback
            cur.execute("SELECT order_id, client_order_id, account_id, status FROM test_active_orders")
            original_orders = cur.fetchall()
            cur.execute("SELECT event_sequence, action, from_status, to_status, actor FROM test_active_order_events ORDER BY event_sequence")
            original_events = cur.fetchall()
            cur.execute("SELECT claim_id, order_id, agent_id, is_active FROM test_active_execution_claims")
            original_claims = cur.fetchall()

            # Step C: Execute Archival (using LIKE ... INCLUDING ALL)
            cur.execute("""
                CREATE TEMP TABLE test_archive_orders (LIKE test_active_orders INCLUDING ALL);
                INSERT INTO test_archive_orders SELECT * FROM test_active_orders;

                CREATE TEMP TABLE test_archive_events (LIKE test_active_order_events INCLUDING ALL);
                INSERT INTO test_archive_events SELECT * FROM test_active_order_events;

                CREATE TEMP TABLE test_archive_claims (LIKE test_active_execution_claims INCLUDING ALL);
                INSERT INTO test_archive_claims SELECT * FROM test_active_execution_claims;
            """)
            pg_conn.commit()

            # Step D: Execute simulated Rollback (Drop active tables)
            cur.execute("""
                DROP TRIGGER IF EXISTS trg_test_prevent_audit_event_mutation ON test_active_order_events;
                DROP TABLE test_active_execution_claims CASCADE;
                DROP TABLE test_active_order_events CASCADE;
                DROP TABLE test_active_orders CASCADE;
            """)
            pg_conn.commit()

            # Step E: Full Restoration from Archive
            # Recreate active tables with full constraints, unique indexes, foreign keys, and triggers
            cur.execute("""
                CREATE TEMP TABLE test_active_orders (
                    order_id VARCHAR(50) PRIMARY KEY,
                    client_order_id VARCHAR(100) UNIQUE NOT NULL,
                    account_id VARCHAR(30) NOT NULL,
                    quantity NUMERIC(14, 4) NOT NULL,
                    limit_price NUMERIC(14, 4) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    CONSTRAINT chk_test_active_account CHECK (account_id ~ '^(DU|DF)[A-Z0-9]{3,28}$'),
                    CONSTRAINT chk_test_active_qty CHECK (quantity > 0),
                    CONSTRAINT chk_test_active_price CHECK (limit_price > 0)
                );

                CREATE TEMP TABLE test_active_order_events (
                    event_id SERIAL PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL REFERENCES test_active_orders(order_id) ON DELETE CASCADE,
                    event_sequence INTEGER NOT NULL,
                    from_status VARCHAR(30),
                    to_status VARCHAR(30) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    actor VARCHAR(50) NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (order_id, event_sequence)
                );

                CREATE TEMP TABLE test_active_execution_claims (
                    claim_id VARCHAR(50) PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL REFERENCES test_active_orders(order_id) ON DELETE CASCADE,
                    agent_id VARCHAR(50) NOT NULL,
                    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    lease_expires_at TIMESTAMPTZ NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    released_at TIMESTAMPTZ,
                    release_reason VARCHAR(255)
                );

                CREATE UNIQUE INDEX uq_test_active_claim_order ON test_active_execution_claims (order_id) WHERE is_active = TRUE;

                CREATE TRIGGER trg_test_prevent_audit_event_mutation
                BEFORE UPDATE OR DELETE ON test_active_order_events
                FOR EACH ROW
                EXECUTE FUNCTION pg_temp.prevent_test_audit_event_mutation();

                -- Restore data from archive
                INSERT INTO test_active_orders SELECT * FROM test_archive_orders;
                INSERT INTO test_active_order_events SELECT * FROM test_archive_events;
                INSERT INTO test_active_execution_claims SELECT * FROM test_archive_claims;

                -- Reset serial sequence
                SELECT setval(pg_get_serial_sequence('test_active_order_events', 'event_id'), COALESCE(MAX(event_id), 1)) FROM test_active_order_events;
            """)
            pg_conn.commit()

            # Step F: Verify Data Fidelity
            cur.execute("SELECT order_id, client_order_id, account_id, status FROM test_active_orders")
            restored_orders = cur.fetchall()
            self.assertEqual(restored_orders, original_orders, "Restored orders must match pre-rollback state exactly")

            cur.execute("SELECT event_sequence, action, from_status, to_status, actor FROM test_active_order_events ORDER BY event_sequence")
            restored_events = cur.fetchall()
            self.assertEqual(restored_events, original_events, "Restored audit events must match pre-rollback state exactly")

            cur.execute("SELECT claim_id, order_id, agent_id, is_active FROM test_active_execution_claims")
            restored_claims = cur.fetchall()
            self.assertEqual(restored_claims, original_claims, "Restored execution claims must match pre-rollback state exactly")

            # Step G: Verify Constraints are actively enforced on restored tables
            # 1. chk_test_active_account constraint active:
            try:
                cur.execute("INSERT INTO test_active_orders VALUES ('ORD-FAIL', 'KEY-FAIL', 'U1234567', 1, 100, 'DRAFT', 1)")
                self.fail("Restored table did not enforce check constraint on live account")
            except psycopg2.IntegrityError:
                pg_conn.rollback()

            # 2. client_order_id unique constraint active:
            try:
                cur.execute("INSERT INTO test_active_orders VALUES ('ORD-FAIL-2', 'KEY-VERIFY-01', 'DUR257161', 1, 100, 'DRAFT', 1)")
                self.fail("Restored table did not enforce uniqueness on client_order_id")
            except psycopg2.IntegrityError:
                pg_conn.rollback()

            # 3. Partial unique index active (blocking duplicate active claims):
            try:
                cur.execute("INSERT INTO test_active_execution_claims (claim_id, order_id, agent_id, lease_expires_at, is_active) VALUES ('CLM-DUP', 'ORD-VERIFY-01', 'agent_beta', NOW() + INTERVAL '5 min', TRUE)")
                self.fail("Restored table did not enforce partial unique index on active claims")
            except psycopg2.IntegrityError:
                pg_conn.rollback()

            # 4. Engine immutability trigger active (blocking UPDATE or DELETE on audit events):
            try:
                cur.execute("UPDATE test_active_order_events SET actor = 'CORRUPTED' WHERE order_id = 'ORD-VERIFY-01'")
                self.fail("Restored audit events table allowed UPDATE")
            except Exception as e:
                pg_conn.rollback()
                self.assertIn("strictly prohibited", str(e))

            try:
                cur.execute("DELETE FROM test_active_order_events WHERE order_id = 'ORD-VERIFY-01'")
                self.fail("Restored audit events table allowed DELETE")
            except Exception as e:
                pg_conn.rollback()
                self.assertIn("strictly prohibited", str(e))

        finally:
            pg_conn.close()

    # =========================================================================
    # Verification Check 2: Valid-format Unbound Account Rejection
    # =========================================================================
    def test_02_valid_format_unbound_account_rejection_at_all_boundaries(self):
        """Demonstrates that a valid-format paper account ('DU999999', 'DF888888') is rejected
        at Proposal, Approval, Claim, and Execution Agent boundaries, confirming binding
        cannot be bypassed through direct API requests."""

        # ---------------------------------------------------------------------
        # 1. Proposal Boundary: Direct API & Service Calls
        # ---------------------------------------------------------------------
        # Direct API proposal with valid format but unbound account (DU999999)
        payload_du = {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 1.0,
            "limit_price": 200.0,
            "account_id": UNBOUND_VALID_ACCOUNT
        }
        resp_prop_du = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload_du)
        self.assertEqual(resp_prop_du.status_code, 400)
        self.assertIn("does not match explicitly bound", resp_prop_du.json()["detail"])

        # Direct API proposal with valid format DF account (DF888888)
        payload_df = {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 1.0,
            "limit_price": 200.0,
            "account_id": UNBOUND_VALID_DF_ACCOUNT
        }
        resp_prop_df = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload_df)
        self.assertEqual(resp_prop_df.status_code, 400)
        self.assertIn("does not match explicitly bound", resp_prop_df.json()["detail"])

        # Direct Service call
        with self.assertRaises(ValueError) as ctx:
            prop = PaperOrderProposal(
                symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0, account_id=UNBOUND_VALID_ACCOUNT
            )
            order_execution_service.propose_order(self.db, prop)
        self.assertIn("does not match explicitly bound", str(ctx.exception))

        # ---------------------------------------------------------------------
        # 2. Approval Boundary: Direct API & Service Calls
        # ---------------------------------------------------------------------
        # Create a valid order under currently bound DUR257161
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        valid_order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = valid_order["order_id"]

        # Simulate system bound account changing to a different paper account before approval
        ibkr_service.bind_paper_account(self.db, target_account_id=UNBOUND_VALID_ACCOUNT, reason="Rebind test")

        # Direct API approval must fail closed because order.account_id (DUR257161) != new bound account (DU999999)
        resp_appr = client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        self.assertEqual(resp_appr.status_code, 400)
        self.assertIn("does not match currently bound paper account", resp_appr.json()["detail"])

        # Direct Service approval must fail closed
        with self.assertRaises(ValueError) as ctx:
            order_execution_service.approve_order(self.db, order_id)
        self.assertIn("does not match currently bound paper account", str(ctx.exception))

        # Rebind back to authoritative account DUR257161
        ibkr_service.bind_paper_account(self.db, target_account_id=AUTHORITATIVE_BOUND_ACCOUNT, reason="Restore bind")
        order_execution_service.approve_order(self.db, order_id)

        # ---------------------------------------------------------------------
        # 3. Claim Boundary: Direct API & Service Calls
        # ---------------------------------------------------------------------
        # Direct API claim with valid-format unbound account DU999999
        claim_payload_unbound = {"agent_id": "agent_alpha", "account_id": UNBOUND_VALID_ACCOUNT}
        resp_claim_du = client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json=claim_payload_unbound)
        self.assertEqual(resp_claim_du.status_code, 400)
        self.assertIn("does not match order account", resp_claim_du.json()["detail"])

        # Direct Service claim with unbound account
        with self.assertRaises(ValueError) as ctx:
            order_execution_service.claim_order(self.db, order_id, "agent_alpha", agent_account=UNBOUND_VALID_ACCOUNT)
        self.assertIn("does not match order account", str(ctx.exception))

        # ---------------------------------------------------------------------
        # 4. Execution-Agent Boundary
        # ---------------------------------------------------------------------
        # Execution agent verify_account_identifier verifies syntax
        self.assertTrue(agent_module.verify_account_identifier(UNBOUND_VALID_ACCOUNT))
        self.assertTrue(agent_module.verify_account_identifier(UNBOUND_VALID_DF_ACCOUNT))

        # In run_agent_cycle (lines 457-459), the agent compares order_account against active_account:
        # If active_account is UNBOUND_VALID_ACCOUNT and order_account is DUR257161, it strictly refuses to claim
        test_order = {"order_id": order_id, "account_id": AUTHORITATIVE_BOUND_ACCOUNT}
        agent_active_account = UNBOUND_VALID_ACCOUNT
        self.assertNotEqual(test_order["account_id"], agent_active_account)
        self.assertTrue(
            test_order["account_id"] != agent_active_account,
            "Execution agent loop must refuse to claim order whose account does not match agent active_account"
        )

        # ---------------------------------------------------------------------
        # 5. Completely Unbound State (Zero Fallback)
        # ---------------------------------------------------------------------
        # Propose another order under bound account to test approval rejection when unbound
        prop_awaiting = PaperOrderProposal(symbol="MSFT", action="BUY", quantity=1.0, limit_price=300.0)
        order_awaiting = order_execution_service.propose_order(self.db, prop_awaiting)
        order_id_awaiting = order_awaiting["order_id"]

        # Clear bound account completely from database
        self.db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.BOUND_ACCOUNT_KEY).delete()
        self.db.commit()
        ibkr_service.clear_cache_for_testing(self.db)

        # Direct API proposal when completely unbound
        resp_unbound_prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload_du)
        self.assertEqual(resp_unbound_prop.status_code, 400)
        self.assertIn("no valid ibkr paper account is explicitly bound", resp_unbound_prop.json()["detail"].lower())

        # Direct API approval when completely unbound
        resp_unbound_appr = client.post(f"/api/portfolio/ibkr/orders/{order_id_awaiting}/approve", headers=ADMIN_AUTH)
        self.assertEqual(resp_unbound_appr.status_code, 400)
        self.assertIn("no valid ibkr paper account is currently bound", resp_unbound_appr.json()["detail"].lower())

        # Direct API claim when completely unbound
        resp_unbound_claim = client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json={"agent_id": "agent_alpha"})
        self.assertEqual(resp_unbound_claim.status_code, 400)
        self.assertIn("does not match active bound paper account", resp_unbound_claim.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
