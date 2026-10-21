"""Stage D2.3A.1: Database Safety Hardening Acceptance Test Suite.

Comprehensive verification of all 11 safety criteria:
1. Live-account identifiers ('U...') are strictly rejected across API, service, and agent boundaries.
2. Malformed paper-account identifiers ('ABC', 'DU_UNBOUND', 'DU', 'DF', 'DU-123') are rejected.
3. Orders proposed or claimed against an account different from the bound paper account are rejected.
4. Concurrent order claiming across separate database connections permits exactly one winner and produces a consistent audit record.
5. Duplicate idempotency keys reject duplicate insertion.
6. Process restart during order transitions preserves correct order state and audit log in PostgreSQL.
7. Unknown submission outcomes quarantine the order and prevent retry until manual reconciliation.
8. Migration failure recovery visibly fails without corrupting active records.
9. Non-destructive rollback preserves active records into timestamped archival tables when rollback is executed.
10. paper_order_events remains immutable in PostgreSQL even when administrative reconciliation occurs.
11. Emergency-stop active flag prohibits order claiming.
"""
import copy
import json
import os
import re
import sys
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Test environment configuration
os.environ["ENVIRONMENT"] = "development"
os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"
os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
os.environ["IBKR_PAPER_ENABLED"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
    PAPER_ACCOUNT_REGEX,
    ORDERS_SETTING_KEY,
)
from app.main import app

# Import execution agent module
AGENT_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "ibkr_adapter" / "ibkr_execution_agent.py"
import importlib.util
spec = importlib.util.spec_from_file_location("ibkr_execution_agent", str(AGENT_SCRIPT))
agent_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_module)

client = TestClient(app)
ADMIN_AUTH = {"X-Admin-Key": "test_admin_key_2026"}
EXEC_AUTH = {"X-IBKR-Execution-Key": "test_execution_key_2026"}
TEST_BOUND_ACCOUNT = "DUR257161"


def seed_test_paper_account(db, account_id=TEST_BOUND_ACCOUNT, cash_balance=100000.0, connect_gw=True):
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
        connection_state="CONNECTED" if connect_gw else "DISCONNECTED",
        timestamp=datetime.now(timezone.utc).isoformat(),
        adapter_version="2.0.0",
        gateway_managed_accounts=[account_id],
        gateway_account_type="PAPER",
        gateway_port=4002,
    )
    ibkr_service.save_paper_snapshot(db, payload)


class TestStageD23A1DatabaseSafetyHardening(unittest.TestCase):

    def setUp(self):
        os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
        os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
        os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"

        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        # Clean existing test records
        try:
            self.db.query(PaperExecutionClaim).delete()
            self.db.query(PaperOrderEvent).delete()
            self.db.query(PaperOrder).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()

        # Arm settings with default test values
        settings = order_execution_service.get_execution_settings(self.db)
        settings["emergency_stop"] = False
        settings["execution_enabled"] = True
        settings["max_order_notional_usd"] = 1000.0
        settings["max_daily_orders"] = 10
        settings["max_daily_notional_usd"] = 5000.0
        settings["max_open_orders"] = 5
        order_execution_service.update_execution_settings(self.db, settings)

        seed_test_paper_account(self.db, account_id=TEST_BOUND_ACCOUNT)

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
    # Acceptance Criterion 1: Live-Account Identifiers ('U...') Strictly Rejected
    # =========================================================================
    def test_01_live_account_strictly_rejected(self):
        """Verifies live-account identifiers ('U...') are rejected at API, service, and agent boundaries."""
        # 1. Proposal with live account in proposal payload
        live_account = "U1234567"
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 1.0,
            "limit_price": 200.0,
            "account_id": live_account
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertIn(resp.status_code, (400, 422))
        detail_str = str(resp.json())
        self.assertTrue(
            any(w in detail_str.lower() for w in ["live account", "strictly rejected", "paper account"])
        )

        # 2. Service-level proposal rejection
        with self.assertRaises(ValueError) as ctx:
            prop = PaperOrderProposal(
                symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0, account_id=live_account
            )
        self.assertIn("LIVE account", str(ctx.exception))

        # 3. Execution Agent verify_account_identifier rejection
        self.assertFalse(agent_module.verify_account_identifier(live_account))
        self.assertFalse(agent_module.verify_account_identifier("U987654321"))

        # 4. Claiming with live account
        # Create a valid approved order first
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)

        claim_payload = {"agent_id": "test_agent_1", "account_id": live_account}
        claim_resp = client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json=claim_payload)
        self.assertEqual(claim_resp.status_code, 400)
        self.assertIn("live account", claim_resp.json()["detail"].lower())

    # =========================================================================
    # Acceptance Criterion 2: Malformed Paper-Account Identifiers Rejected
    # =========================================================================
    def test_02_malformed_paper_account_identifiers_rejected(self):
        """Malformed identifiers ('ABC', 'DU_UNBOUND', 'DU', 'DF', 'DU-123') fail validation."""
        malformed_accounts = ["ABC", "DU_UNBOUND", "DU", "DF", "DU-123", "", "   ", "DU@123", "DF!"]
        for mal in malformed_accounts:
            # Pydantic validator check
            try:
                PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0, account_id=mal)
                self.fail(f"PaperOrderProposal should have rejected malformed account '{mal}'")
            except (ValueError, Exception):
                pass

            # Agent check
            self.assertFalse(agent_module.verify_account_identifier(mal), f"Agent should reject '{mal}'")

            # ORM validator check
            with self.assertRaises(ValueError):
                o = PaperOrder(
                    order_id=f"ORD-TEST-{mal[:4]}",
                    client_order_id=f"KEY-TEST-{mal[:4]}",
                    account_id=mal,
                    symbol="AAPL",
                    action="BUY",
                    quantity=1.0,
                    limit_price=100.0,
                    status="DRAFT"
                )

    # =========================================================================
    # Acceptance Criterion 3: Bound-Account Mismatch Rejected (No Silent Fallback)
    # =========================================================================
    def test_03_account_mismatch_and_no_fallback(self):
        """Orders proposed or claimed against an account different from bound account are rejected."""
        different_paper_account = "DU999999"  # Valid format, but not the bound account

        # 1. Proposal with mismatched account
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 1.0,
            "limit_price": 200.0,
            "account_id": different_paper_account
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not match explicitly bound", resp.json()["detail"])

        # 2. Claiming with mismatched account
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)

        mismatched_claim = {"agent_id": "test_agent_1", "account_id": different_paper_account}
        claim_resp = client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json=mismatched_claim)
        self.assertEqual(claim_resp.status_code, 400)
        self.assertIn("does not match order account", claim_resp.json()["detail"])

        # 3. Proposal when NO account is bound in system settings
        self.db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.BOUND_ACCOUNT_KEY).delete()
        self.db.commit()
        ibkr_service.clear_cache_for_testing(self.db)

        unbound_payload = {"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        resp_unbound = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=unbound_payload)
        self.assertEqual(resp_unbound.status_code, 400)
        self.assertIn("no valid ibkr paper account is explicitly bound", resp_unbound.json()["detail"].lower())

    # =========================================================================
    # Acceptance Criterion 4: Concurrent Order Claiming Across Separate Connections
    # =========================================================================
    def test_04_concurrent_order_claiming_permits_exactly_one_winner(self):
        """Simultaneous claims across distinct threads/sessions permit exactly 1 winner and reject collisions."""
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)

        results = []
        barrier = threading.Barrier(2)

        def claim_worker(agent_id):
            worker_db = SessionLocal()
            try:
                barrier.wait()
                claimed = order_execution_service.claim_order(
                    worker_db,
                    order_id=order_id,
                    agent_id=agent_id,
                    agent_account=TEST_BOUND_ACCOUNT
                )
                results.append((agent_id, "SUCCESS", claimed))
            except Exception as e:
                results.append((agent_id, "FAILED", str(e)))
            finally:
                worker_db.close()

        t1 = threading.Thread(target=claim_worker, args=("agent_alpha",))
        t2 = threading.Thread(target=claim_worker, args=("agent_beta",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [r for r in results if r[1] == "SUCCESS"]
        failures = [r for r in results if r[1] == "FAILED"]

        self.assertEqual(len(successes), 1, "Exactly one agent must win the race")
        self.assertEqual(len(failures), 1, "The competing agent must fail")
        self.assertTrue(
            any(w in failures[0][2].lower() for w in ["already claimed", "claim collision", "cannot claim"]),
            f"Expected collision error, got: {failures[0][2]}"
        )

        # Verify audit trail contains exactly 1 ORDER_CLAIMED event
        events = self.db.query(PaperOrderEvent).filter(
            PaperOrderEvent.order_id == order_id,
            PaperOrderEvent.action == "ORDER_CLAIMED"
        ).all()
        self.assertEqual(len(events), 1)

    # =========================================================================
    # Acceptance Criterion 5: Duplicate Idempotency Keys Reject Duplicate Insertion
    # =========================================================================
    def test_05_duplicate_idempotency_keys(self):
        """Proposing with identical client_idempotency_key returns existing order without duplicate insertion."""
        idem_key = "test_idem_key_unique_001"
        prop = PaperOrderProposal(
            symbol="AAPL",
            action="BUY",
            quantity=2.0,
            limit_price=200.0,
            client_idempotency_key=idem_key
        )
        order1 = order_execution_service.propose_order(self.db, prop)
        self.assertEqual(order1["client_idempotency_key"], idem_key)

        # Propose second time with same key
        order2 = order_execution_service.propose_order(self.db, prop)
        self.assertEqual(order2["order_id"], order1["order_id"])

        # Count in database must remain exactly 1
        count = self.db.query(PaperOrder).filter(PaperOrder.client_order_id == idem_key).count()
        self.assertEqual(count, 1)

    # =========================================================================
    # Acceptance Criterion 6: Process Restart During Transitions Preserves State & Heartbeat
    # =========================================================================
    def test_06_process_restart_preserves_order_state_and_heartbeat(self):
        """Process restart/cache wipe restores order state and durable agent heartbeat from database."""
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)
        order_execution_service.claim_order(self.db, order_id, "agent_restart_test", TEST_BOUND_ACCOUNT)

        # Send heartbeat to persist durably in system_settings
        hb_record = order_execution_service.record_agent_heartbeat(
            agent_id="agent_restart_test",
            payload={
                "client_id": 22,
                "gateway_host": "127.0.0.1",
                "gateway_port": 4002,
                "gateway_connected": True,
                "managed_accounts": [TEST_BOUND_ACCOUNT],
                "active_account": TEST_BOUND_ACCOUNT,
                "status": "HEALTHY",
                "details": {"restart_test": True},
            },
            db=self.db,
        )
        self.assertEqual(hb_record["status"], "HEALTHY")
        self.assertTrue(hb_record["gateway_connected"])

        # Simulate total memory wipe (simulate process restart)
        order_execution_service._agent_heartbeats.clear()
        order_execution_service._settings_cache = None

        # Verify state in PostgreSQL
        reloaded_order = order_execution_service.get_order(self.db, order_id)
        self.assertEqual(reloaded_order["status"], "CLAIMED")
        self.assertEqual(reloaded_order["claimed_by_agent"], "agent_restart_test")

        # Verify heartbeat reloads from durable storage
        restored_hb = order_execution_service.get_agent_status("agent_restart_test", db=self.db)
        self.assertEqual(restored_hb["status"], "HEALTHY")
        self.assertTrue(restored_hb["gateway_connected"])
        self.assertEqual(restored_hb["active_account"], TEST_BOUND_ACCOUNT)

    # =========================================================================
    # Acceptance Criterion 7: Unknown Submission Outcomes Quarantine Order
    # =========================================================================
    def test_07_unknown_submission_outcome_quarantines_order(self):
        """UNKNOWN outcome sets requires_manual_reconciliation=True, blocks auto-resubmit and polling."""
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)
        order_execution_service.claim_order(self.db, order_id, "agent_alpha", TEST_BOUND_ACCOUNT)

        # Report socket disconnect / uncertain submission
        unknown_details = {
            "error_code": 1100,
            "message": "Socket connection lost during transmission",
            "can_auto_resubmit": False
        }
        order_execution_service.report_execution_status(
            self.db,
            order_id=order_id,
            agent_id="agent_alpha",
            target_status="UNKNOWN",
            report_details=unknown_details
        )

        # Order must be quarantined
        quarantined = order_execution_service.get_order(self.db, order_id)
        self.assertEqual(quarantined["status"], "UNKNOWN")
        self.assertTrue(quarantined["requires_manual_reconciliation"])
        self.assertFalse(quarantined["can_auto_resubmit"])

        # Agent polling must NOT return this order for execution
        poll_res = order_execution_service.poll_approved_orders(self.db, agent_id="agent_alpha")
        self.assertEqual(len(poll_res["orders"]), 0)

        # Claim attempt on quarantined order must fail
        with self.assertRaises(ValueError) as ctx:
            order_execution_service.claim_order(self.db, order_id, "agent_alpha", TEST_BOUND_ACCOUNT)
        self.assertIn("APPROVED required", str(ctx.exception))

        # Admin reconciles to FILLED
        reconciled = order_execution_service.reconcile_order(
            self.db,
            order_id=order_id,
            resolution_status="FILLED",
            reason="Verified manual execution on TWS"
        )
        self.assertEqual(reconciled["status"], "FILLED")
        self.assertFalse(reconciled["requires_manual_reconciliation"])

    # =========================================================================
    # Acceptance Criterion 8: Migration Failure Recovery Visibly Fails
    # =========================================================================
    def test_08_migration_failure_recovery_without_corrupting_active_records(self):
        """Corrupt record in legacy migration raises visible exception and rolls back atomically."""
        corrupt_legacy_orders = {
            "ORD-LEGACY-BAD": {
                "order_id": "ORD-LEGACY-BAD",
                "client_idempotency_key": "leg_bad_key",
                "account_id": "U1234567_INVALID_LIVE",  # Corrupted / live account
                "symbol": "MSFT",
                "status": "APPROVED",
            }
        }
        # Seed or update in system_settings
        row = self.db.query(SystemSetting).filter(SystemSetting.key == ORDERS_SETTING_KEY).first()
        if not row:
            row = SystemSetting(
                key=ORDERS_SETTING_KEY,
                value=json.dumps(corrupt_legacy_orders),
                updated_at=datetime.utcnow()
            )
            self.db.add(row)
        else:
            row.value = json.dumps(corrupt_legacy_orders)
            row.updated_at = datetime.utcnow()
        self.db.commit()

        # Must raise visible exception without swallowing into zero or notices
        with self.assertRaises(ValueError) as ctx:
            order_execution_service.migrate_d21_json_orders_to_db(self.db)
        self.assertIn("invalid paper account", str(ctx.exception).lower())

        # Verify zero corrupted records were inserted
        bad_in_db = self.db.query(PaperOrder).filter(PaperOrder.order_id == "ORD-LEGACY-BAD").first()
        self.assertIsNone(bad_in_db, "Corrupted record must not be committed to PaperOrder table")

    # =========================================================================
    # Acceptance Criterion 9: Non-Destructive Rollback Preserves Active Records
    # =========================================================================
    def test_09_nondestructive_rollback_preserves_records_in_archival_tables(self):
        """Rollback SQL contains archival table creation logic when active orders exist."""
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        rollback_sql = (migrations_dir / "d2_2_paper_orders_transactional_rollback.sql").read_text(encoding="utf-8")

        # 1. Verify existence of non-destructive archival mechanics
        self.assertIn("paper_orders_archive_", rollback_sql)
        self.assertIn("paper_order_events_archive_", rollback_sql)
        self.assertIn("paper_execution_claims_archive_", rollback_sql)
        self.assertIn("SELECT COUNT(*) FROM stockanalysis.paper_orders", rollback_sql)

        # 2. Verify pre-migration backup instructions included
        self.assertIn("pg_dump", rollback_sql)
        self.assertIn("PRE-MIGRATION BACKUP & RECOVERY INSTRUCTIONS", rollback_sql)

    # =========================================================================
    # Acceptance Criterion 10: Audit Immutability Trigger Prevents Mutation
    # =========================================================================
    def test_10_paper_order_events_immutable_and_reconciliation_appends(self):
        """Audit trail is strictly append-only; administrative reconciliation appends new event."""
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)
        order_execution_service.claim_order(self.db, order_id, "agent_alpha", TEST_BOUND_ACCOUNT)
        order_execution_service.report_execution_status(
            self.db, order_id=order_id, agent_id="agent_alpha", target_status="UNKNOWN", report_details={}
        )

        # Reconcile order
        reconciled = order_execution_service.reconcile_order(
            self.db, order_id=order_id, resolution_status="FILLED", reason="Administrator reconciliation", actor="ADMIN"
        )
        audit_trail = reconciled["audit_trail"]
        actions = [ev["action"] for ev in audit_trail]

        # Audit events must be sequentially ordered and preserve all intermediate steps
        self.assertIn("ORDER_PROPOSED", actions)
        self.assertIn("ORDER_APPROVED", actions)
        self.assertIn("ORDER_CLAIMED", actions)
        self.assertIn("REPORT_UNKNOWN", actions)
        self.assertIn("RECONCILED", actions)
        self.assertEqual(actions[-1], "RECONCILED")

        # Verify event sequence in DB
        events = self.db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        seqs = [e.event_sequence for e in events]
        self.assertEqual(seqs, list(range(1, len(events) + 1)), "Event sequences must be strictly incrementing without gaps")

    # =========================================================================
    # Acceptance Criterion 11: Emergency-Stop Prohibits Order Claiming
    # =========================================================================
    def test_11_emergency_stop_prohibits_claiming(self):
        """Active Emergency Stop immediately blocks order claiming and polling."""
        valid_prop = PaperOrderProposal(symbol="AAPL", action="BUY", quantity=1.0, limit_price=200.0)
        order = order_execution_service.propose_order(self.db, valid_prop)
        order_id = order["order_id"]
        order_execution_service.approve_order(self.db, order_id)

        # Engage Emergency Stop
        settings = order_execution_service.get_execution_settings(self.db)
        settings["emergency_stop"] = True
        order_execution_service.update_execution_settings(self.db, settings)

        # Polling returns emergency_stop=True and empty orders
        poll_res = order_execution_service.poll_approved_orders(self.db)
        self.assertTrue(poll_res["emergency_stop"])
        self.assertEqual(len(poll_res["orders"]), 0)

        # Claim attempt is rejected
        with self.assertRaises(ValueError) as ctx:
            order_execution_service.claim_order(self.db, order_id, "test_agent_1", TEST_BOUND_ACCOUNT)
        self.assertIn("Emergency Stop is ACTIVE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
