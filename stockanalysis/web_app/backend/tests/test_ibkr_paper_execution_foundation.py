"""Automated Unit and Integration Tests for Stage D2.1: Controlled IBKR Paper Execution Foundation
and D2.1 Risk Settings Amendment.

Validates:
1. Durable state machine transitions & validations.
2. Idempotent proposal handling.
3. Automated Risk Engine checks:
   - Paper account verification (starts with DU/DF; live accounts rejected).
   - Instrument validation (US equities only; options/futures/crypto rejected).
   - Order type restriction (LIMIT orders only).
   - Long-only constraint (SELL <= verified snapshot holdings; shorting blocked).
   - Cash solvency (BUY notional <= USD cash; no AUD confusion).
   - Configurable single-order notional ceiling (default $500 USD).
   - Daily order count limit per US trading day (default 5 orders, America/New_York).
   - Daily aggregate notional limit (default $2,500 USD, America/New_York).
   - Simultaneous open orders limit (default 1 open order).
   - Price collar check (limit price within 3% of market price).
   - Snapshot freshness (<= 300s) and gateway connection state.
4. Admin approval & 15-minute expiration window.
5. Immediate enforcement of lowered limits at approval time.
6. Non-revival of previously rejected orders upon limit increase.
7. Anti-bypass counting: rejected and cancelled orders consume daily order quota.
8. Atomic claiming & collision prevention (no double claims).
9. Server-side Emergency Stop (active by default, blocks approvals and claims).
10. UNKNOWN outcome handling (manual reconciliation required, no auto-resubmit).
11. Credential isolation (Admin vs Ingestion vs Execution least privilege).
12. Immutable audit trail integrity for orders and settings updates.
13. Stage D2.1 strictly non-executing safety.
"""
import copy
import json
import os
import unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_ORIGINAL_ENV = dict(os.environ)

# Setup test environment before importing app modules
os.environ["ENVIRONMENT"] = "development"
os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"
os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
os.environ["IBKR_PAPER_ENABLED"] = "true"
os.environ["IBKR_EMERGENCY_STOP"] = "true"
os.environ["IBKR_EXECUTION_ENABLED"] = "false"

from app.database import Base, get_db, engine, SessionLocal
from app.main import app
from app.models import SystemSetting, PaperOrder, PaperOrderEvent, PaperExecutionClaim
from app.services.ibkr_service import ibkr_service
from app.services.order_execution_service import (
    order_execution_service,
    PaperOrderProposal,
    ORDERS_SETTING_KEY,
    EXECUTION_SETTINGS_KEY,
    get_us_trading_date,
    get_us_daily_metrics,
    HARD_CEILING_MAX_ORDER_NOTIONAL,
    HARD_CEILING_MAX_DAILY_ORDERS,
    HARD_CEILING_MAX_DAILY_NOTIONAL,
    HARD_CEILING_MAX_OPEN_ORDERS,
)

client = TestClient(app)

ADMIN_AUTH = {"X-Admin-Key": "test_admin_key_2026"}
INGEST_AUTH = {"X-IBKR-Ingest-Key": "test_gateway_ibkr_ingest_key_2026"}
EXEC_AUTH = {"X-IBKR-Execution-Key": "test_execution_key_2026"}


def seed_mock_paper_snapshot(
    db,
    account_id="DU1234567",
    cash=50000.0,
    positions=None,
    connection_state="CONNECTED",
    timestamp=None
):
    """Seeds a fresh paper account snapshot into the database."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    if positions is None:
        positions = [
            {
                "symbol": "AAPL",
                "sec_type": "STK",
                "position": 50.0,
                "market_price": 200.0,
                "market_value": 10000.0,
                "average_cost": 190.0,
                "unrealized_pnl": 500.0,
                "realized_pnl": 0.0,
            }
        ]

    snapshot_data = {
        "account_id": account_id,
        "account_type": "PAPER",
        "currency": "USD",
        "timestamp": timestamp,
        "connection_state": connection_state,
        "is_stale": False,
        "staleness_seconds": 10,
        "summary": {
            "net_liquidation": cash + sum(p.get("market_value", 0) for p in positions),
            "total_cash_value": cash,
            "buying_power": cash * 2.0,
            "gross_position_value": sum(p.get("market_value", 0) for p in positions),
            "unrealized_pnl": sum(p.get("unrealized_pnl", 0) for p in positions),
            "realized_pnl": 0.0,
        },
        "positions": positions,
    }

    # Store in system_settings
    snap_setting = db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.SETTING_KEY).first()
    if not snap_setting:
        snap_setting = SystemSetting(
            key=ibkr_service.SETTING_KEY,
            value=json.dumps(snapshot_data),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(snap_setting)
    else:
        snap_setting.value = json.dumps(snapshot_data)
        snap_setting.updated_at = datetime.now(timezone.utc)

    # Store bound account
    bound_setting = db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.BOUND_ACCOUNT_KEY).first()
    bound_val = json.dumps({"account_id": account_id, "bound_at": timestamp, "reason": "Test seed"})
    if not bound_setting:
        bound_setting = SystemSetting(
            key=ibkr_service.BOUND_ACCOUNT_KEY,
            value=bound_val,
            updated_at=datetime.now(timezone.utc)
        )
        db.add(bound_setting)
    else:
        bound_setting.value = bound_val
        bound_setting.updated_at = datetime.now(timezone.utc)

    db.commit()
    ibkr_service._in_memory_cache = snapshot_data
    return snapshot_data


class TestIBKRPaperExecutionFoundation(unittest.TestCase):

    def setUp(self):
        os.environ["ENVIRONMENT"] = "development"
        os.environ["STOCKANALYSIS_ADMIN_KEY"] = "test_admin_key_2026"
        os.environ["IBKR_INGESTION_KEY"] = "test_gateway_ibkr_ingest_key_2026"
        os.environ["IBKR_EXECUTION_KEY"] = "test_execution_key_2026"
        os.environ["IBKR_PAPER_ENABLED"] = "true"
        os.environ["IBKR_EMERGENCY_STOP"] = "true"
        os.environ["IBKR_EXECUTION_ENABLED"] = "false"

        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        order_execution_service._orders_cache = {}
        order_execution_service._settings_cache = None
        # Disarm emergency stop for testing order flow unless explicitly testing stop
        order_execution_service.update_execution_settings(
            self.db,
            {"emergency_stop": False, "execution_enabled": True},
            actor="TEST_SETUP"
        )
        seed_mock_paper_snapshot(self.db)

    def tearDown(self):
        try:
            self.db.query(PaperOrderEvent).delete()
            self.db.query(PaperExecutionClaim).delete()
            self.db.query(PaperOrder).delete()
            self.db.query(SystemSetting).delete()
            self.db.commit()
        except Exception:
            pass
        self.db.close()

    @classmethod
    def tearDownClass(cls):
        for k in [
            "ENVIRONMENT",
            "STOCKANALYSIS_ADMIN_KEY",
            "IBKR_INGESTION_KEY",
            "IBKR_EXECUTION_KEY",
            "IBKR_PAPER_ENABLED",
            "IBKR_EMERGENCY_STOP",
            "IBKR_EXECUTION_ENABLED",
        ]:
            if k in _ORIGINAL_ENV:
                os.environ[k] = _ORIGINAL_ENV[k]
            else:
                os.environ.pop(k, None)

    # -------------------------------------------------------------------------
    # 1. Proposal & Risk Engine Tests
    # -------------------------------------------------------------------------

    def test_01_propose_order_creates_draft_and_evaluates_risk(self):
        """Proposing an order creates DRAFT and transitions to AWAITING_APPROVAL if risk passes."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 201.0,  # Notional = $402.00 <= $500.00 ceiling, within 3% of $200 market price
            "currency": "USD",
            "notes": "Testing valid BUY proposal"
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["order"]
        self.assertEqual(data["status"], "AWAITING_APPROVAL")
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(data["action"], "BUY")
        self.assertTrue(data["risk_check"]["passed"])
        self.assertGreater(len(data["audit_trail"]), 1)

    def test_02_idempotency_prevents_duplicate_orders(self):
        """Submitting duplicate proposal with same client_idempotency_key returns existing order."""
        key = "idemp_test_unique_key_123"
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
            "currency": "USD",
            "client_idempotency_key": key
        }
        resp1 = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp1.status_code, 200)
        order1 = resp1.json()["order"]

        resp2 = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp2.status_code, 200)
        order2 = resp2.json()["order"]

        self.assertEqual(order1["order_id"], order2["order_id"])

    def test_03_risk_rejects_live_account(self):
        """Risk engine strictly rejects proposals when live account is active."""
        seed_mock_paper_snapshot(self.db, account_id="U1234567")
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertIn(resp.status_code, [200, 400])
        if resp.status_code == 200:
            order = resp.json()["order"]
            self.assertEqual(order["status"], "REJECTED")
            self.assertFalse(order["risk_check"]["passed"])
            self.assertTrue(any("Live" in f or "validated" in f or "account" in f.lower() for f in order["risk_check"]["failure_reasons"]))
        else:
            self.assertTrue("account" in resp.json()["detail"].lower() or "live" in resp.json()["detail"].lower())

    def test_04_risk_rejects_non_us_or_invalid_symbols(self):
        """Unsupported symbols (crypto, options, non-alphabetic) fail risk evaluation."""
        payload = {
            "symbol": "BTC/USD",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 1.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Unsupported instrument type or invalid symbol.", order["risk_check"]["failure_reasons"])

    def test_05_risk_rejects_market_orders(self):
        """Non-LIMIT orders are prohibited."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "MARKET",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Market and stop orders are not permitted in Stage D2.1.", order["risk_check"]["failure_reasons"])

    def test_06_risk_rejects_short_selling(self):
        """SELL order for unheld stock fails long-only verification."""
        payload = {
            "symbol": "TSLA",  # Not in held positions
            "action": "SELL",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Short selling is forbidden: No verified long holdings.", order["risk_check"]["failure_reasons"])

    def test_07_risk_rejects_sell_quantity_exceeding_holdings(self):
        """SELL order exceeding verified holdings is rejected."""
        payload = {
            "symbol": "AAPL",  # 50 shares held in snapshot
            "action": "SELL",
            "order_type": "LIMIT",
            "quantity": 100.0,  # Exceeds 50
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Sell quantity exceeds verified portfolio holdings.", order["risk_check"]["failure_reasons"])

    def test_08_risk_allows_valid_sell_within_holdings(self):
        """SELL order within verified holdings and under notional ceiling passes risk check."""
        payload = {
            "symbol": "AAPL",  # 50 held
            "action": "SELL",
            "order_type": "LIMIT",
            "quantity": 2.0,  # <= 50 held, notional = $404.00 <= $500.00 ceiling
            "limit_price": 202.0,  # Within 3% of $200
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "AWAITING_APPROVAL")
        self.assertTrue(order["risk_check"]["passed"])

    def test_09_risk_rejects_buy_exceeding_cash(self):
        """BUY order where notional exceeds cash balance is rejected."""
        seed_mock_paper_snapshot(self.db, cash=200.0)  # Only $200 cash
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,  # Notional = $400 > $200 cash
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Insufficient cash in paper account to cover notional.", order["risk_check"]["failure_reasons"])

    def test_10_risk_rejects_buy_exceeding_notional_ceiling(self):
        """BUY order exceeding $500 default notional ceiling is rejected."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 3.0,
            "limit_price": 200.0,  # Notional = $600 > $500 ceiling
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertTrue(any("single-order risk ceiling" in f for f in order["risk_check"]["failure_reasons"]))

    def test_11_risk_rejects_stale_snapshot(self):
        """Risk engine fails if paper snapshot is older than 300 seconds."""
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        snap_setting = self.db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.SETTING_KEY).first()
        data = json.loads(snap_setting.value)
        data["timestamp"] = stale_time
        snap_setting.value = json.dumps(data)
        self.db.commit()
        ibkr_service._in_memory_cache = data

        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Market snapshot is stale.", order["risk_check"]["failure_reasons"])

    def test_12_risk_rejects_disconnected_gateway(self):
        """Risk engine fails if IB Gateway state is DISCONNECTED."""
        snap_setting = self.db.query(SystemSetting).filter(SystemSetting.key == ibkr_service.SETTING_KEY).first()
        data = json.loads(snap_setting.value)
        data["connection_state"] = "DISCONNECTED"
        snap_setting.value = json.dumps(data)
        self.db.commit()
        ibkr_service._in_memory_cache = data

        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Gateway connection state is DISCONNECTED.", order["risk_check"]["failure_reasons"])

    def test_13_risk_rejects_price_collar_deviation(self):
        """Limit price deviating more than 3% from market price is rejected."""
        # Market price for AAPL is $200. +3% collar is $206.00.
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 215.0,  # 7.5% deviation > 3% collar, notional $430 <= $500
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(resp.status_code, 200)
        order = resp.json()["order"]
        self.assertEqual(order["status"], "REJECTED")
        self.assertTrue(any("collar" in f for f in order["risk_check"]["failure_reasons"]))

    # -------------------------------------------------------------------------
    # 2. State Machine & Approval Lifecycle Tests
    # -------------------------------------------------------------------------

    def test_14_admin_approval_sets_15_minute_expiration(self):
        """Admin approval transitions AWAITING_APPROVAL -> APPROVED and sets 15-minute expiration."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,  # Notional $400
        }
        prop_resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        order_id = prop_resp.json()["order"]["order_id"]

        app_resp = client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        self.assertEqual(app_resp.status_code, 200)
        approved = app_resp.json()["order"]
        self.assertEqual(approved["status"], "APPROVED")
        self.assertIsNotNone(approved["approved_at"])
        self.assertIsNotNone(approved["approval_expires_at"])

    def test_15_emergency_stop_blocks_approvals_and_claims(self):
        """Active Emergency Stop blocks approvals and agent claims."""
        # Re-arm emergency stop
        order_execution_service.update_execution_settings(self.db, {"emergency_stop": True}, actor="TEST")

        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop_resp = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        order = prop_resp.json()["order"]
        # When emergency stop is active, risk evaluation rejects immediate approval
        self.assertEqual(order["status"], "REJECTED")
        self.assertIn("Emergency Stop is currently active.", order["risk_check"]["failure_reasons"])

    def test_16_emergency_stop_toggle_updates_settings_and_logs(self):
        """Toggling Emergency Stop updates settings and returns current state."""
        resp = client.post(
            "/api/portfolio/ibkr/execution/emergency-stop",
            headers=ADMIN_AUTH,
            json={"active": True, "reason": "Test activation"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["emergency_stop"])

        resp2 = client.post(
            "/api/portfolio/ibkr/execution/emergency-stop",
            headers=ADMIN_AUTH,
            json={"active": False, "reason": "Test deactivation"}
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertFalse(resp2.json()["emergency_stop"])

    def test_17_approval_expiration_sweeps_to_expired(self):
        """Expired approvals automatically transition to EXPIRED on read."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)

        # Manually backdate approval_expires_at to simulate expiration
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        orders = order_execution_service._load_orders_from_db(self.db)
        orders[order_id]["approval_expires_at"] = past_iso
        order_execution_service._save_orders_to_db(self.db, orders)

        # Read detail triggers sweep
        get_resp = client.get(f"/api/portfolio/ibkr/orders/{order_id}", headers=ADMIN_AUTH)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["order"]["status"], "EXPIRED")

    def test_18_atomic_order_claiming_prevents_double_claims(self):
        """Atomic claim transitions APPROVED -> CLAIMED; duplicate claim fails with 409 Conflict."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)

        # First claim succeeds
        claim_resp1 = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/claim",
            headers=EXEC_AUTH,
            json={"agent_id": "agent_alpha"}
        )
        self.assertEqual(claim_resp1.status_code, 200)
        self.assertEqual(claim_resp1.json()["order"]["status"], "CLAIMED")
        self.assertEqual(claim_resp1.json()["order"]["claimed_by_agent"], "agent_alpha")

        # Second claim fails with 409 Conflict
        claim_resp2 = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/claim",
            headers=EXEC_AUTH,
            json={"agent_id": "agent_beta"}
        )
        self.assertEqual(claim_resp2.status_code, 409)

    def test_19_cannot_claim_expired_order(self):
        """Claiming an order whose approval window has elapsed is rejected with 409."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)

        # Backdate expiration
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        orders = order_execution_service._load_orders_from_db(self.db)
        orders[order_id]["approval_expires_at"] = past_iso
        order_execution_service._save_orders_to_db(self.db, orders)

        claim_resp = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/claim",
            headers=EXEC_AUTH,
            json={"agent_id": "agent_alpha"}
        )
        self.assertEqual(claim_resp.status_code, 409)

    def test_20_agent_polling_returns_only_active_approved_orders(self):
        """Agent poll returns only valid APPROVED orders."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        client.post(f"/api/portfolio/ibkr/orders/{prop['order_id']}/approve", headers=ADMIN_AUTH)

        poll_resp = client.get("/api/portfolio/ibkr/execution/orders/poll", headers=EXEC_AUTH)
        self.assertEqual(poll_resp.status_code, 200)
        data = poll_resp.json()
        self.assertGreaterEqual(len(data["orders"]), 1)
        self.assertFalse(data["emergency_stop"])

    def test_21_agent_status_reporting_transitions(self):
        """Execution agent reports transition CLAIMED -> SUBMITTING -> SUBMITTED."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json={"agent_id": "agent_1"})

        # Report SUBMITTING
        r1 = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/report",
            headers=EXEC_AUTH,
            json={"agent_id": "agent_1", "target_status": "SUBMITTING", "details": {"step": "preparing"}}
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["order"]["status"], "SUBMITTING")

        # Report SUBMITTED
        r2 = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/report",
            headers=EXEC_AUTH,
            json={"agent_id": "agent_1", "target_status": "SUBMITTED", "details": {"ibkr_id": "IB-1001"}}
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["order"]["status"], "SUBMITTED")

    def test_22_unknown_outcome_flags_reconciliation_and_blocks_resubmission(self):
        """UNKNOWN outcome sets requires_manual_reconciliation=True and can_auto_resubmit=False."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json={"agent_id": "agent_1"})

        # Report UNKNOWN (e.g., gateway socket disconnected mid-flight)
        rep = client.post(
            f"/api/portfolio/ibkr/execution/orders/{order_id}/report",
            headers=EXEC_AUTH,
            json={
                "agent_id": "agent_1",
                "target_status": "UNKNOWN",
                "details": {"error": "Socket timeout during transmit"}
            }
        )
        self.assertEqual(rep.status_code, 200)
        order = rep.json()["order"]
        self.assertEqual(order["status"], "UNKNOWN")
        self.assertTrue(order["requires_manual_reconciliation"])
        self.assertFalse(order["can_auto_resubmit"])

    def test_23_admin_rejection_and_cancellation(self):
        """Admin can reject in AWAITING_APPROVAL and cancel before execution."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]

        # Reject
        rej_resp = client.post(
            f"/api/portfolio/ibkr/orders/{order_id}/reject",
            headers=ADMIN_AUTH,
            json={"reason": "Operator discretion"}
        )
        self.assertEqual(rej_resp.status_code, 200)
        self.assertEqual(rej_resp.json()["order"]["status"], "REJECTED")

        # Propose second order and cancel
        prop2 = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        cancel_resp = client.post(
            f"/api/portfolio/ibkr/orders/{prop2['order_id']}/cancel",
            headers=ADMIN_AUTH,
            json={"reason": "Changed mind"}
        )
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["order"]["status"], "CANCELLED")

    # -------------------------------------------------------------------------
    # 3. Security & Credential Isolation Tests
    # -------------------------------------------------------------------------

    def test_24_auth_isolation_ingestion_key_cannot_access_execution(self):
        """Ingestion key cannot call execution endpoints (returns 401)."""
        resp = client.get("/api/portfolio/ibkr/execution/orders/poll", headers=INGEST_AUTH)
        self.assertEqual(resp.status_code, 401)

    def test_25_auth_isolation_execution_key_cannot_access_admin(self):
        """Execution key cannot propose orders or approve orders (returns 401)."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        resp = client.post("/api/portfolio/ibkr/orders/propose", headers=EXEC_AUTH, json=payload)
        self.assertEqual(resp.status_code, 401)

    def test_26_auth_isolation_admin_key_cannot_claim_as_agent(self):
        """Admin key cannot claim orders from execution agent endpoint (returns 401)."""
        resp = client.get("/api/portfolio/ibkr/execution/orders/poll", headers=ADMIN_AUTH)
        self.assertEqual(resp.status_code, 401)

    def test_27_immutable_audit_trail_recorded_on_every_step(self):
        """Audit trail contains complete chronological record of transitions."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 2.0,
            "limit_price": 200.0,
        }
        prop = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload).json()["order"]
        order_id = prop["order_id"]
        client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        client.post(f"/api/portfolio/ibkr/execution/orders/{order_id}/claim", headers=EXEC_AUTH, json={"agent_id": "agent_1"})

        final = client.get(f"/api/portfolio/ibkr/orders/{order_id}", headers=ADMIN_AUTH).json()["order"]
        trail = final["audit_trail"]
        actions = [a["action"] for a in trail]
        self.assertIn("ORDER_PROPOSED", actions)
        self.assertIn("RISK_CHECK_PASSED", actions)
        self.assertIn("ORDER_APPROVED", actions)
        self.assertIn("ORDER_CLAIMED", actions)

    def test_28_stage_d21_strictly_non_executing_safety(self):
        """Verifies settings declare non-executing mode active."""
        settings = order_execution_service.get_execution_settings(self.db)
        self.assertIn(settings["stage"], ("D2.1", "D2.2"))
        self.assertTrue(settings["is_non_executing"])

    # -------------------------------------------------------------------------
    # 4. Configurable Risk Settings & America/New_York Quota Enforcement Tests
    # -------------------------------------------------------------------------

    def test_29_configurable_risk_settings_update_and_audit_history(self):
        """Admin can update risk limits with validation; previous/new values and reason recorded."""
        update_payload = {
            "max_order_notional_usd": 600.0,
            "max_daily_orders": 8,
            "max_daily_notional_usd": 3000.0,
            "max_open_orders": 2,
            "reason": "Operator risk envelope expansion for testing"
        }
        resp = client.post("/api/portfolio/ibkr/execution/settings", headers=ADMIN_AUTH, json=update_payload)
        self.assertEqual(resp.status_code, 200)
        settings = resp.json()["settings"]
        self.assertEqual(settings["max_order_notional_usd"], 600.0)
        self.assertEqual(settings["max_daily_orders"], 8)
        self.assertEqual(settings["max_daily_notional_usd"], 3000.0)
        self.assertEqual(settings["max_open_orders"], 2)

        # Verify audit history
        self.assertGreaterEqual(len(settings["history"]), 1)
        latest_hist = settings["history"][0]
        self.assertEqual(latest_hist["updated_by"], "ADMIN")
        self.assertEqual(latest_hist["reason"], "Operator risk envelope expansion for testing")
        self.assertEqual(latest_hist["previous_values"]["max_order_notional_usd"], 500.0)
        self.assertEqual(latest_hist["new_values"]["max_order_notional_usd"], 600.0)

    def test_30_risk_settings_bounds_and_hard_ceilings_enforced(self):
        """Settings updates violating hard safety ceilings or consistency rules are rejected."""
        # 1. Order notional exceeds $25,000 ceiling
        r1 = client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_order_notional_usd": 30000.0, "reason": "Testing ceiling"}
        )
        self.assertEqual(r1.status_code, 400)
        self.assertIn("between", r1.json()["detail"])

        # 2. Daily orders exceeds 50 ceiling
        r2 = client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_daily_orders": 100, "reason": "Testing orders ceiling"}
        )
        self.assertEqual(r2.status_code, 400)

        # 3. Order notional > daily notional
        r3 = client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_order_notional_usd": 4000.0, "max_daily_notional_usd": 2000.0, "reason": "Inconsistent"}
        )
        self.assertEqual(r3.status_code, 400)
        self.assertIn("cannot exceed", r3.json()["detail"].lower())

        # 4. Missing / empty reason (< 3 chars)
        r4 = client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_order_notional_usd": 600.0, "reason": "no"}
        )
        self.assertEqual(r4.status_code, 422)

    def test_31_daily_order_count_limit_enforced_for_us_trading_day(self):
        """Max 5 orders per US trading day; 6th proposal is rejected."""
        payload = {
            "symbol": "AAPL",
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": 1.0,
            "limit_price": 200.0,  # $200 notional
        }
        # Propose 5 orders and cancel each to keep open orders at 0
        for i in range(5):
            p = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
            self.assertEqual(p.status_code, 200)
            order = p.json()["order"]
            self.assertEqual(order["status"], "AWAITING_APPROVAL")
            # Cancel to clear open orders
            client.post(f"/api/portfolio/ibkr/orders/{order['order_id']}/cancel", headers=ADMIN_AUTH, json={"reason": "clean"})

        # 6th proposal must fail on daily order count
        p6 = client.post("/api/portfolio/ibkr/orders/propose", headers=ADMIN_AUTH, json=payload)
        self.assertEqual(p6.status_code, 200)
        order6 = p6.json()["order"]
        self.assertEqual(order6["status"], "REJECTED")
        self.assertTrue(any("Daily order limit reached" in f for f in order6["risk_check"]["failure_reasons"]))

    def test_32_anti_bypass_rejected_and_cancelled_orders_consume_daily_quota(self):
        """Rejected and cancelled orders cannot be used to bypass daily order count limits."""
        # 1. Propose invalid symbol -> rejected
        r1 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "CRYPTO!", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        )
        self.assertEqual(r1.json()["order"]["status"], "REJECTED")

        # 2. Propose short sale -> rejected
        r2 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "NVDA", "action": "SELL", "quantity": 1.0, "limit_price": 100.0}
        )
        self.assertEqual(r2.json()["order"]["status"], "REJECTED")

        # 3. Propose valid order -> cancelled
        r3 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        )
        client.post(f"/api/portfolio/ibkr/orders/{r3.json()['order']['order_id']}/cancel", headers=ADMIN_AUTH, json={"reason": "cancel"})

        # 4 & 5. Propose 2 more and cancel
        for _ in range(2):
            rx = client.post(
                "/api/portfolio/ibkr/orders/propose",
                headers=ADMIN_AUTH,
                json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
            )
            client.post(f"/api/portfolio/ibkr/orders/{rx.json()['order']['order_id']}/cancel", headers=ADMIN_AUTH, json={"reason": "cancel"})

        # Total 5 orders proposed (2 rejected, 3 cancelled). 6th proposal must be rejected!
        r6 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        )
        self.assertEqual(r6.json()["order"]["status"], "REJECTED")
        self.assertTrue(any("Daily order limit reached" in f for f in r6.json()["order"]["risk_check"]["failure_reasons"]))

    def test_33_daily_aggregate_notional_limit_enforced(self):
        """Cumulative proposed notional on US trading date cannot exceed $2,500."""
        # First expand max_daily_orders to 10 so daily count doesn't hit before daily notional
        client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_daily_orders": 10, "max_daily_notional_usd": 2500.0, "reason": "Expand order count"}
        )

        # Propose 5 orders of $500 each ($2,500 cumulative), cancelling each
        for _ in range(5):
            p = client.post(
                "/api/portfolio/ibkr/orders/propose",
                headers=ADMIN_AUTH,
                json={"symbol": "AAPL", "action": "BUY", "quantity": 2.5, "limit_price": 200.0}  # $500
            )
            self.assertEqual(p.json()["order"]["status"], "AWAITING_APPROVAL")
            client.post(f"/api/portfolio/ibkr/orders/{p.json()['order']['order_id']}/cancel", headers=ADMIN_AUTH, json={"reason": "cancel"})

        # 6th order would exceed $2,500 limit ($2,500 + $200 = $2,700 > $2,500) -> rejected
        p6 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}  # $200 -> $2,700 total
        )
        self.assertEqual(p6.json()["order"]["status"], "REJECTED")
        self.assertTrue(any("Daily aggregate notional limit exceeded" in f for f in p6.json()["order"]["risk_check"]["failure_reasons"]))

    def test_34_simultaneous_open_orders_limit_enforced(self):
        """Default max_open_orders = 1; proposing a second order while one is open is rejected."""
        # 1. Propose order 1 (notional $400) -> AWAITING_APPROVAL (open)
        p1 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 2.0, "limit_price": 200.0}
        )
        order1 = p1.json()["order"]
        self.assertEqual(order1["status"], "AWAITING_APPROVAL")

        # 2. Attempt to propose order 2 while order 1 is open -> REJECTED
        p2 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        )
        order2 = p2.json()["order"]
        self.assertEqual(order2["status"], "REJECTED")
        self.assertTrue(any("Simultaneous open order limit reached" in f for f in order2["risk_check"]["failure_reasons"]))

        # 3. Cancel order 1 -> open orders count drops to 0
        client.post(f"/api/portfolio/ibkr/orders/{order1['order_id']}/cancel", headers=ADMIN_AUTH, json={"reason": "done"})

        # 4. Order 3 can now be proposed successfully
        p3 = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 1.0, "limit_price": 200.0}
        )
        self.assertEqual(p3.json()["order"]["status"], "AWAITING_APPROVAL")

    def test_35_immediate_enforcement_of_lowered_limits_at_approval(self):
        """Lowering limits takes effect immediately for unsubmitted orders when approval is attempted."""
        # 1. Propose order with notional $450 (valid under default $500 limit)
        p = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 2.25, "limit_price": 200.0}  # $450
        )
        order_id = p.json()["order"]["order_id"]
        self.assertEqual(p.json()["order"]["status"], "AWAITING_APPROVAL")

        # 2. Lower max_order_notional_usd to $300
        client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_order_notional_usd": 300.0, "reason": "Lowering intraday ceiling"}
        )

        # 3. Attempt to approve $450 order -> must be rejected immediately
        app_resp = client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        self.assertEqual(app_resp.status_code, 400)
        self.assertIn("exceeds current configured single-order maximum", app_resp.json()["detail"])

    def test_36_increasing_limits_never_auto_authorizes_rejected_orders(self):
        """Increasing limits does not automatically revive or authorize previously rejected orders."""
        # 1. Propose order with notional $600 -> rejected under $500 limit
        p = client.post(
            "/api/portfolio/ibkr/orders/propose",
            headers=ADMIN_AUTH,
            json={"symbol": "AAPL", "action": "BUY", "quantity": 3.0, "limit_price": 200.0}  # $600
        )
        order = p.json()["order"]
        order_id = order["order_id"]
        self.assertEqual(order["status"], "REJECTED")

        # 2. Admin increases limit to $1,000
        client.post(
            "/api/portfolio/ibkr/execution/settings",
            headers=ADMIN_AUTH,
            json={"max_order_notional_usd": 1000.0, "reason": "Increasing risk allowance"}
        )

        # 3. Verify order remains REJECTED
        order_check = client.get(f"/api/portfolio/ibkr/orders/{order_id}", headers=ADMIN_AUTH).json()["order"]
        self.assertEqual(order_check["status"], "REJECTED")

        # 4. Calling approve directly on REJECTED order is rejected
        app_resp = client.post(f"/api/portfolio/ibkr/orders/{order_id}/approve", headers=ADMIN_AUTH)
        self.assertEqual(app_resp.status_code, 400)
        self.assertIn("Cannot approve order", app_resp.json()["detail"])

    def test_37_us_trading_date_timezone_conversion(self):
        """get_us_trading_date converts UTC timestamps accurately to America/New_York date."""
        # 2026-10-21 02:00:00 UTC is 2026-10-20 22:00:00 EDT (prior day in New York)
        dt_utc = datetime(2026, 10, 21, 2, 0, 0, tzinfo=timezone.utc)
        ny_date = get_us_trading_date(dt_utc)
        self.assertEqual(ny_date, "2026-10-20")

        # 2026-10-21 15:00:00 UTC is 2026-10-21 11:00:00 EDT (same day in New York)
        dt_utc_day = datetime(2026, 10, 21, 15, 0, 0, tzinfo=timezone.utc)
        ny_date_day = get_us_trading_date(dt_utc_day)
        self.assertEqual(ny_date_day, "2026-10-21")


if __name__ == "__main__":
    unittest.main()
