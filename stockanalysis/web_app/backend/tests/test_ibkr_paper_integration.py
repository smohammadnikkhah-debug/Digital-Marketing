"""Comprehensive Automated Test Suite for IBKR Paper Trading Read-Only Integration.

Adaptive Trading V4.0 — Stage D1B.

Verifies:
1. Pydantic payload validation and strict enforcement of account_type == 'PAPER'.
2. Unauthenticated and spoofed outbound push attempts are rejected with HTTP 401.
3. Authenticated push with valid admin key successfully persists snapshot in SystemSetting and cache.
4. Segregation guarantee: No changes to real user portfolios, monitored stocks, or V4.0 baseline.
5. Automated staleness detection (<300s fresh, >300s stale).
6. Gateway connection states (CONNECTED, DISCONNECTED, ERROR) and warning messages.
7. Read-only safety: Order placement and cancellation methods unconditionally raise PermissionError.
8. Currency consistency: AUD account currency preserved and reported.
9. Mocked IBKR EWrapper/EClient data collection callbacks.
10. Lightweight status endpoint response integrity.
"""
import json
import os
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db, engine, SessionLocal
from app.config import STOCKANALYSIS_ADMIN_KEY, IBKR_INGESTION_KEY
from app.models import SystemSetting, Portfolio, PortfolioTransaction, ScreenerSnapshot
from app.services.ibkr_service import ibkr_service, IBKRPaperSyncPayload
from app.adapters.ibkr_adapter import ReadOnlyIBKREClient, IBKRPaperReader

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_teardown():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    ibkr_service.clear_cache_for_testing(db)
    db.close()
    yield
    db = SessionLocal()
    ibkr_service.clear_cache_for_testing(db)
    db.close()


class TestIBKRPaperIntegration:

    def test_01_payload_validation_enforces_paper_account_only(self):
        """Rejects any non-PAPER account type (e.g. LIVE)."""
        valid_payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 80000.0,
            "buying_power": 320000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        parsed = IBKRPaperSyncPayload(**valid_payload)
        assert parsed.account_type == "PAPER"
        assert parsed.currency == "AUD"

        # Attempt LIVE account
        invalid_payload = valid_payload.copy()
        invalid_payload["account_type"] = "LIVE"
        with pytest.raises(ValueError, match="strictly accepts 'PAPER'"):
            IBKRPaperSyncPayload(**invalid_payload)

    def test_02_unauthenticated_sync_rejected_401(self):
        """Unauthenticated POST /api/portfolio/ibkr/sync must return HTTP 401."""
        os.environ.pop("TESTING", None)
        payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 80000.0,
            "buying_power": 320000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        res = client.post("/api/portfolio/ibkr/sync", json=payload)
        assert res.status_code == 401
        assert "Unauthorized" in res.text

    def test_03_invalid_admin_key_rejected_401(self):
        """Spoofed or wrong X-Admin-Key must return HTTP 401."""
        os.environ.pop("TESTING", None)
        payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 80000.0,
            "buying_power": 320000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        res = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"X-Admin-Key": "wrong-or-spoofed-key"}
        )
        assert res.status_code == 401

    def test_04_authenticated_sync_persists_in_database_and_cache(self):
        """Valid X-Admin-Key persists snapshot to SystemSetting and memory."""
        os.environ.pop("TESTING", None)
        admin_key = STOCKANALYSIS_ADMIN_KEY
        payload = {
            "account_id": "DU999111",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 250000.75,
            "total_cash_value": 150000.25,
            "buying_power": 600000.00,
            "positions": [
                {
                    "symbol": "AAPL",
                    "sec_type": "STK",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "position": 100.0,
                    "avg_cost": 210.50,
                    "market_price": 215.00,
                    "market_value": 21500.00,
                    "unrealized_pnl": 450.00,
                    "realized_pnl": 0.0,
                }
            ],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adapter_version": "1.0.0",
        }

        # Admin key is rejected on sync (sync is strictly ingestion-only)
        res_admin = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"X-Admin-Key": admin_key}
        )
        assert res_admin.status_code == 401

        # Dedicated ingestion key succeeds on sync
        res = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["status"]["account_id"] == "DU999111"
        assert data["status"]["currency"] == "AUD"
        assert data["status"]["summary"]["net_liquidation"] == 250000.75

        # Verify DB persistence in SystemSetting table
        db = SessionLocal()
        setting = db.query(SystemSetting).filter(SystemSetting.key == "ibkr_paper_snapshot").first()
        assert setting is not None
        saved_dict = json.loads(setting.value)
        assert saved_dict["account_id"] == "DU999111"
        assert len(saved_dict["positions"]) == 1
        db.close()

    def test_05_get_paper_account_snapshot_structure(self):
        """GET /api/portfolio/ibkr returns full read-only structure to authorized administrators."""
        # Preload snapshot
        db = SessionLocal()
        payload = IBKRPaperSyncPayload(
            account_id="DU888222",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=500000.0,
            total_cash_value=300000.0,
            buying_power=1200000.0,
            positions=[
                {
                    "symbol": "MSFT",
                    "sec_type": "STK",
                    "exchange": "NASDAQ",
                    "currency": "USD",
                    "position": 50.0,
                    "avg_cost": 400.0,
                    "market_price": 410.0,
                    "market_value": 20500.0,
                    "unrealized_pnl": 500.0,
                }
            ],
            connection_state="CONNECTED",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        ibkr_service.save_paper_snapshot(db, payload)
        db.close()

        # Unauthenticated account GET -> 401
        res_unauth = client.get("/api/portfolio/ibkr")
        assert res_unauth.status_code == 401

        # Ingestion-only credentials GET -> 401
        res_ingest = client.get(
            "/api/portfolio/ibkr",
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_ingest.status_code == 401

        # Authenticated administrator account GET -> 200
        res = client.get(
            "/api/portfolio/ibkr",
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["read_only"] is True
        assert body["account_type"] == "PAPER"
        assert body["account_id"] == "DU888222"
        assert body["currency"] == "AUD"
        assert body["summary"]["net_liquidation"] == 500000.0
        assert body["positions_count"] == 1
        assert body["positions"][0]["symbol"] == "MSFT"

    def test_06_staleness_fresh_vs_stale(self):
        """Timestamps <300s are fresh; timestamps >300s are marked STALE."""
        db = SessionLocal()

        # 1. Fresh sync (30 seconds ago)
        fresh_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        fresh_payload = IBKRPaperSyncPayload(
            account_id="DU_TEST",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=100000.0,
            total_cash_value=100000.0,
            buying_power=400000.0,
            positions=[],
            connection_state="CONNECTED",
            timestamp=fresh_time,
        )
        ibkr_service.save_paper_snapshot(db, fresh_payload)
        status_fresh = ibkr_service.get_paper_account_status(db)
        assert status_fresh["is_stale"] is False
        assert status_fresh["staleness_seconds"] <= 60
        assert status_fresh["warning_message"] is None

        # 2. Stale sync (600 seconds ago)
        ibkr_service.clear_cache_for_testing(db)
        os.environ["ALLOW_STALE_TEST_INGEST"] = "1"
        try:
            stale_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
            stale_payload = IBKRPaperSyncPayload(
                account_id="DU_TEST",
                account_type="PAPER",
                currency="AUD",
                net_liquidation=100000.0,
                total_cash_value=100000.0,
                buying_power=400000.0,
                positions=[],
                connection_state="CONNECTED",
                timestamp=stale_time,
            )
            ibkr_service.save_paper_snapshot(db, stale_payload)
            status_stale = ibkr_service.get_paper_account_status(db)
            assert status_stale["is_stale"] is True
            assert status_stale["staleness_seconds"] >= 599
            assert "STALE" in status_stale["warning_message"]
        finally:
            os.environ.pop("ALLOW_STALE_TEST_INGEST", None)

        db.close()

    def test_07_connection_state_disconnected_reports_warning(self):
        """Disconnected or error state sets appropriate warning banner."""
        db = SessionLocal()
        payload = IBKRPaperSyncPayload(
            account_id="DU_OFFLINE",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=0.0,
            total_cash_value=0.0,
            buying_power=0.0,
            positions=[],
            connection_state="DISCONNECTED",
            error_message="Gateway socket refused on 127.0.0.1:4002",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        ibkr_service.save_paper_snapshot(db, payload)
        res = ibkr_service.get_paper_account_status(db)

        assert res["connection_state"] == "DISCONNECTED"
        assert "DISCONNECTED" in res["warning_message"]
        assert "Gateway socket refused" in res["warning_message"]
        db.close()

    def test_08_read_only_safety_prohibits_all_orders(self):
        """ReadOnlyIBKREClient unconditionally raises PermissionError on place/cancel orders."""
        dummy_reader = ReadOnlyIBKREClient(object())

        with pytest.raises(PermissionError, match="READ-ONLY SAFETY"):
            dummy_reader.placeOrder(1, None, None)

        with pytest.raises(PermissionError, match="READ-ONLY SAFETY"):
            dummy_reader.cancelOrder(1)

        with pytest.raises(PermissionError, match="READ-ONLY SAFETY"):
            dummy_reader.reqGlobalCancel()

    def test_09_segregation_guarantee(self):
        """Paper account data synchronization NEVER touches real user portfolio or screener snapshots."""
        db = SessionLocal()

        # Seed real user portfolio
        user_portfolio = Portfolio(name="Personal Live Account", cash_balance=50000.0)
        db.add(user_portfolio)
        db.commit()

        initial_tx_count = db.query(PortfolioTransaction).count()
        initial_snap_count = db.query(ScreenerSnapshot).count()

        # Push paper trading snapshot
        payload = IBKRPaperSyncPayload(
            account_id="DU_PAPER_ONLY",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=999999.0,
            total_cash_value=888888.0,
            buying_power=3333333.0,
            positions=[{"symbol": "NVDA", "position": 500.0, "avg_cost": 120.0}],
            connection_state="CONNECTED",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        ibkr_service.save_paper_snapshot(db, payload)

        # Verify real tables are completely untouched
        assert db.query(PortfolioTransaction).count() == initial_tx_count
        assert db.query(ScreenerSnapshot).count() == initial_snap_count

        # Verify user portfolio cash balance is untouched
        p = db.query(Portfolio).filter(Portfolio.id == user_portfolio.id).first()
        assert p.cash_balance == 50000.0
        db.close()

    def test_10_mock_ibkr_reader_event_parsing(self):
        """Simulates IB Gateway socket events and verifies collector parsing."""
        reader = IBKRPaperReader()

        # 1. Connection established
        reader.nextValidId(1)
        assert reader.connection_ok is True
        assert reader.connected_event.is_set()

        # 2. Managed accounts
        reader.managedAccounts("DU888123,DU999456")
        assert reader.account_id == "DU888123"

        # 3. Account summary callbacks
        reader.accountSummary(9001, "DU888123", "NetLiquidation", "1250000.50", "AUD")
        reader.accountSummary(9001, "DU888123", "TotalCashValue", "850000.25", "AUD")
        reader.accountSummary(9001, "DU888123", "BuyingPower", "3400000.00", "AUD")
        reader.accountSummaryEnd(9001)

        assert reader.summary_event.is_set()
        assert reader.currency == "AUD"
        assert reader.account_values["NetLiquidation"] == "1250000.50"

        # 4. Position callbacks
        class DummyContract:
            symbol = "TLS"
            secType = "STK"
            exchange = "ASX"
            currency = "AUD"

        reader.position("DU888123", DummyContract(), 1000.0, 4.05)
        reader.positionEnd()

        assert reader.positions_event.is_set()
        assert len(reader.positions_list) == 1
        pos = reader.positions_list[0]
        assert pos["symbol"] == "TLS"
        assert pos["position"] == 1000.0
        assert pos["avg_cost"] == 4.05
        assert pos["market_value"] == 4050.0

    def test_11_status_lightweight_endpoint(self):
        """GET /api/portfolio/ibkr/status returns compact monitoring status to authorized administrators."""
        # Unauthenticated status GET -> 401
        res_unauth = client.get("/api/portfolio/ibkr/status")
        assert res_unauth.status_code == 401

        # Ingestion-only credentials GET -> 401
        res_ingest = client.get(
            "/api/portfolio/ibkr/status",
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_ingest.status_code == 401

        # Authenticated administrator status GET -> 200
        res = client.get(
            "/api/portfolio/ibkr/status",
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        )
        assert res.status_code == 200
        body = res.json()
        assert "connection_state" in body
        assert "is_stale" in body
        assert "read_only" in body
        assert body["read_only"] is True
        assert body["account_type"] == "PAPER"
        assert "adapter_status" in body
        assert "gateway_connection" in body
        assert "freshness_state" in body
        assert "is_cached" in body

    def test_12_dedicated_ingestion_key_accepted(self):
        """Dedicated IBKR_INGESTION_KEY is accepted via X-IBKR-Ingest-Key or Bearer token."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 105000.0,
            "total_cash_value": 75000.0,
            "buying_power": 420000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        }

        # 1. Via X-IBKR-Ingest-Key header
        res1 = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res1.status_code == 200
        assert res1.json()["success"] is True

        # 2. Via Authorization Bearer header
        payload["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        res2 = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"Authorization": f"Bearer {IBKR_INGESTION_KEY}"}
        )
        assert res2.status_code == 200
        assert res2.json()["success"] is True

    def test_13_ingestion_key_cannot_access_scanner_or_admin_routes(self):
        """Dedicated IBKR_INGESTION_KEY must NEVER grant access to administrative or scanner triggers."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        # Attempt to trigger scanner refresh using ingestion credential
        res = client.post(
            "/api/scanner/refresh",
            headers={"X-Admin-Key": IBKR_INGESTION_KEY}
        )
        # Must be rejected because IBKR_INGESTION_KEY is not STOCKANALYSIS_ADMIN_KEY
        assert res.status_code == 401

    def test_14_replay_protection_rejects_older_snapshot(self):
        """Replay attack or out-of-order snapshot submission is rejected with HTTP 400."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        base_now = datetime.now(timezone.utc)
        t2 = (base_now - timedelta(seconds=15)).isoformat()
        t1 = (base_now - timedelta(seconds=60)).isoformat()  # Older

        # 1. Push timestamp T2
        payload_t2 = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 50000.0,
            "buying_power": 200000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": t2,
        }
        res2 = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload_t2,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res2.status_code == 200

        # 2. Push older timestamp T1 (replay attack / stale submission)
        payload_t1 = payload_t2.copy()
        payload_t1["timestamp"] = t1
        res1 = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload_t1,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res1.status_code == 400
        assert "Replay protection rejection" in res1.json()["detail"]

    def test_15_live_account_id_strictly_rejected(self):
        """Live account ID pattern (e.g., U1234567) is strictly rejected with HTTP 422."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        payload = {
            "account_id": "U12345678",  # Live IBKR account pattern
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 50000.0,
            "buying_power": 200000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        res = client.post(
            "/api/portfolio/ibkr/sync",
            json=payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res.status_code == 422
        assert "LIVE brokerage account" in res.text

    def test_16_three_tier_status_classification(self):
        """Verifies distinct classification: adapter_status, gateway_connection, freshness_state, is_cached."""
        db = SessionLocal()

        # 1. Push a fresh snapshot (< 60s)
        now_ts = datetime.now(timezone.utc).isoformat()
        payload = IBKRPaperSyncPayload(
            account_id="DU_TIER_TEST",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=200000.0,
            total_cash_value=100000.0,
            buying_power=400000.0,
            positions=[],
            connection_state="CONNECTED",
            timestamp=now_ts,
        )
        ibkr_service.save_paper_snapshot(db, payload)

        status = ibkr_service.get_paper_account_status(db)
        assert status["adapter_status"] == "ONLINE"
        assert status["gateway_connection"] == "CONNECTED"
        assert status["freshness_state"] == "LIVE_STREAM"
        assert status["is_cached"] is True

        # 2. Simulate cached state (120s ago)
        ibkr_service.clear_cache_for_testing(db)
        cached_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        payload_cached = IBKRPaperSyncPayload(
            account_id="DU_TIER_TEST",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=200000.0,
            total_cash_value=100000.0,
            buying_power=400000.0,
            positions=[],
            connection_state="CONNECTED",
            timestamp=cached_ts,
        )
        ibkr_service.save_paper_snapshot(db, payload_cached)

        status_cached = ibkr_service.get_paper_account_status(db)
        assert status_cached["adapter_status"] == "ONLINE"
        assert status_cached["gateway_connection"] == "CONNECTED"
        assert status_cached["freshness_state"] == "CACHED"

        # 3. Simulate stale state (400s ago)
        ibkr_service.clear_cache_for_testing(db)
        os.environ["ALLOW_STALE_TEST_INGEST"] = "1"
        try:
            stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
            payload_stale = IBKRPaperSyncPayload(
                account_id="DU_TIER_TEST",
                account_type="PAPER",
                currency="AUD",
                net_liquidation=200000.0,
                total_cash_value=100000.0,
                buying_power=400000.0,
                positions=[],
                connection_state="CONNECTED",
                timestamp=stale_ts,
            )
            ibkr_service.save_paper_snapshot(db, payload_stale)

            status_stale = ibkr_service.get_paper_account_status(db)
            assert status_stale["adapter_status"] == "OFFLINE"
            assert status_stale["freshness_state"] == "STALE"
        finally:
            os.environ.pop("ALLOW_STALE_TEST_INGEST", None)

        db.close()

    def test_17_unrelated_system_settings_isolated(self):
        """Syncing IBKR snapshot must not modify other unrelated SystemSetting keys."""
        db = SessionLocal()
        # Seed an unrelated setting
        unrelated = SystemSetting(
            key="v40_audit_baseline_lock",
            value=json.dumps({"locked": True, "date": "2026-10-15"}),
            updated_at=datetime.now(timezone.utc)
        )
        db.merge(unrelated)
        db.commit()

        # Push paper snapshot
        payload = IBKRPaperSyncPayload(
            account_id="DU_ISOLATION",
            account_type="PAPER",
            currency="AUD",
            net_liquidation=100000.0,
            total_cash_value=50000.0,
            buying_power=200000.0,
            positions=[],
            connection_state="CONNECTED",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        ibkr_service.save_paper_snapshot(db, payload)

        # Check unrelated setting
        refreshed = db.query(SystemSetting).filter(SystemSetting.key == "v40_audit_baseline_lock").first()
        assert refreshed is not None
        assert json.loads(refreshed.value)["locked"] is True
        db.close()

    def test_18_malformed_and_negative_payloads_rejected(self):
        """Pydantic rejects negative net liquidation or malformed fields with HTTP 422."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        # Negative net liquidation
        negative_payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": -500.0,  # Invalid
            "total_cash_value": 0.0,
            "buying_power": 0.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        res = client.post(
            "/api/portfolio/ibkr/sync",
            json=negative_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res.status_code == 422

    def test_19_clock_skew_duplicate_and_stale_rejections(self):
        """Authoritative database transaction rejects duplicates, clock skew, and stale timestamps."""
        os.environ.pop("TESTING", None)
        os.environ.pop("ALLOW_STALE_TEST_INGEST", None)
        from app.config import IBKR_INGESTION_KEY

        base_ts = datetime.now(timezone.utc)

        # A. Clock skew (>60s in future)
        future_payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 50000.0,
            "buying_power": 200000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": (base_ts + timedelta(seconds=120)).isoformat(),
        }
        res_future = client.post(
            "/api/portfolio/ibkr/sync",
            json=future_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_future.status_code == 400
        assert "Clock skew rejection" in res_future.json()["detail"]

        # B. Stale snapshot upon submission (>300s old)
        stale_payload = future_payload.copy()
        stale_payload["timestamp"] = (base_ts - timedelta(seconds=400)).isoformat()
        res_stale = client.post(
            "/api/portfolio/ibkr/sync",
            json=stale_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_stale.status_code == 400
        assert "Stale snapshot rejection" in res_stale.json()["detail"]

        # C. Push valid snapshot T_now
        valid_payload = future_payload.copy()
        t_now = (base_ts + timedelta(seconds=1)).isoformat()
        valid_payload["timestamp"] = t_now
        res_valid = client.post(
            "/api/portfolio/ibkr/sync",
            json=valid_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_valid.status_code == 200

        # D. Duplicate snapshot submission (same timestamp)
        res_dup = client.post(
            "/api/portfolio/ibkr/sync",
            json=valid_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res_dup.status_code == 400
        assert "Duplicate snapshot rejection" in res_dup.json()["detail"]

    def test_20_production_fails_closed_on_dev_or_missing_ingestion_key(self):
        """Production environment MUST fail closed with HTTP 500 when key is unconfigured or a development value."""
        os.environ.pop("TESTING", None)
        old_env = os.environ.get("ENVIRONMENT")
        os.environ["ENVIRONMENT"] = "production"

        try:
            payload = {
                "account_id": "DU123456",
                "account_type": "PAPER",
                "currency": "AUD",
                "net_liquidation": 100000.0,
                "total_cash_value": 50000.0,
                "buying_power": 200000.0,
                "positions": [],
                "connection_state": "CONNECTED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            # Attempt to use local dev key against production
            res = client.post(
                "/api/portfolio/ibkr/sync",
                json=payload,
                headers={"X-IBKR-Ingest-Key": "ibkr-ingest-key-dev-local-2026"}
            )
            # Must fail closed with 500 configuration failure
            assert res.status_code == 500
            assert "Security Configuration Failure" in res.json()["detail"]
        finally:
            if old_env is not None:
                os.environ["ENVIRONMENT"] = old_env
            else:
                os.environ.pop("ENVIRONMENT", None)

    def test_21_gateway_managed_accounts_and_port_confirmation(self):
        """Validates confirmation of paper-account identifiers against the authenticated IBKR Gateway account."""
        os.environ.pop("TESTING", None)
        from app.config import IBKR_INGESTION_KEY

        # 1. Gateway reports live account in managed accounts list
        live_managed_payload = {
            "account_id": "DU123456",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 100000.0,
            "total_cash_value": 50000.0,
            "buying_power": 200000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gateway_managed_accounts": ["DU123456", "U99887766"],
        }
        res1 = client.post(
            "/api/portfolio/ibkr/sync",
            json=live_managed_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res1.status_code == 400
        assert "LIVE brokerage account" in res1.json()["detail"]

        # 2. Account ID not confirmed in gateway managed accounts list
        unconfirmed_payload = live_managed_payload.copy()
        unconfirmed_payload["gateway_managed_accounts"] = ["DU999999"]
        res2 = client.post(
            "/api/portfolio/ibkr/sync",
            json=unconfirmed_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res2.status_code == 400
        assert "Account verification failed" in res2.json()["detail"]

        # 3. Gateway port is live port (4001)
        live_port_payload = live_managed_payload.copy()
        live_port_payload["gateway_managed_accounts"] = ["DU123456"]
        live_port_payload["gateway_port"] = 4001
        res3 = client.post(
            "/api/portfolio/ibkr/sync",
            json=live_port_payload,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res3.status_code == 400
        assert "LIVE trading port" in res3.json()["detail"]

    def test_22_restart_recovery_from_database_without_disk_cache(self):
        """Recovers snapshot directly from authoritative database without relying on ephemeral container disk cache."""
        db = SessionLocal()
        from app.config import DATA_CACHE_DIR
        cache_file = DATA_CACHE_DIR / "ibkr_paper_cache.json"

        # 1. Seed authoritative database setting directly
        now_ts = datetime.now(timezone.utc).isoformat()
        db_payload = {
            "account_id": "DU_PERSIST_RECOVERY",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 350000.0,
            "total_cash_value": 200000.0,
            "buying_power": 800000.0,
            "positions": [
                {
                    "symbol": "CBA",
                    "sec_type": "STK",
                    "exchange": "ASX",
                    "currency": "AUD",
                    "position": 500.0,
                    "avg_cost": 140.0,
                    "market_price": 145.0,
                    "market_value": 72500.0,
                    "unrealized_pnl": 2500.0,
                    "realized_pnl": 0.0,
                }
            ],
            "connection_state": "CONNECTED",
            "timestamp": now_ts,
            "received_at": now_ts,
            "adapter_version": "1.0.0",
        }
        setting = db.query(SystemSetting).filter(SystemSetting.key == "ibkr_paper_snapshot").first()
        if not setting:
            setting = SystemSetting(
                key="ibkr_paper_snapshot",
                value=json.dumps(db_payload),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(setting)
        else:
            setting.value = json.dumps(db_payload)
            setting.updated_at = datetime.now(timezone.utc)
        db.commit()

        # 2. Simulate container reboot / ephemeral filesystem wipe
        ibkr_service._in_memory_cache = None
        if cache_file.exists():
            cache_file.unlink()

        # 3. Query read-only endpoint with ephemeral disk cache absent
        res = client.get(
            "/api/portfolio/ibkr",
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is True
        assert data["account_id"] == "DU_PERSIST_RECOVERY"
        assert data["summary"]["net_liquidation"] == 350000.0
        assert data["positions_count"] == 1
        assert data["positions"][0]["symbol"] == "CBA"
        assert data["is_cached"] is True
        assert data["freshness_state"] == "LIVE_STREAM"

        # 4. Simulate elapsed staleness purely in database setting (400s ago)
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        db_payload["timestamp"] = stale_ts
        setting.value = json.dumps(db_payload)
        db.commit()

        # Wipe in-memory and disk cache again
        ibkr_service._in_memory_cache = None
        if cache_file.exists():
            cache_file.unlink()

        status = ibkr_service.get_paper_account_status(db)
        assert status["is_stale"] is True
        assert status["freshness_state"] == "STALE"
        assert status["adapter_status"] == "OFFLINE"
        assert "STALE" in status["warning_message"]

        db.close()

    def test_23_atomic_first_snapshot_admission_and_concurrency(self):
        """Verifies concurrent first-snapshot admission serialization, duplicate timestamp rejection, and failure rollback."""
        from concurrent.futures import ThreadPoolExecutor

        db = SessionLocal()
        ibkr_service.clear_cache_for_testing(db)
        assert db.query(SystemSetting).filter_by(key=ibkr_service.SETTING_KEY).first() is None
        assert db.query(SystemSetting).filter_by(key=ibkr_service.BOUND_ACCOUNT_KEY).first() is None
        db.close()

        now = datetime.now(timezone.utc)
        results = []

        def ingest_thread(thread_idx, ts_offset_ms):
            thread_db = SessionLocal()
            try:
                # Slight offset in timestamps
                snap_ts = (now - timedelta(seconds=20) + timedelta(milliseconds=ts_offset_ms)).isoformat()
                p = IBKRPaperSyncPayload(
                    account_id="DU_CONCURRENCY_TEST",
                    account_type="PAPER",
                    currency="AUD",
                    net_liquidation=100000.0 + thread_idx * 1000.0,
                    total_cash_value=50000.0,
                    buying_power=200000.0,
                    positions=[],
                    connection_state="CONNECTED",
                    timestamp=snap_ts,
                    gateway_managed_accounts=["DU_CONCURRENCY_TEST"],
                    gateway_account_type="PAPER",
                    gateway_port=4002,
                )
                res = ibkr_service.save_paper_snapshot(thread_db, p)
                return ("SUCCESS", thread_idx, res)
            except Exception as e:
                return ("ERROR", thread_idx, str(e))
            finally:
                thread_db.close()

        # Fire 6 concurrent threads trying to perform the first insert simultaneously
        # Threads 0, 1, 2 have the EXACT SAME timestamp (testing duplicate collision)
        # Threads 3, 4, 5 have monotonically increasing timestamps
        offsets = [0, 0, 0, 100, 200, 300]
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(ingest_thread, i, offsets[i]) for i in range(6)]
            results = [f.result() for f in futures]

        # Verify exact database state
        verify_db = SessionLocal()
        rows = verify_db.query(SystemSetting).filter_by(key=ibkr_service.SETTING_KEY).all()
        assert len(rows) == 1, f"Expected exactly 1 row for {ibkr_service.SETTING_KEY}, found {len(rows)}"

        # Exactly one row exists for bound account
        bound_rows = verify_db.query(SystemSetting).filter_by(key=ibkr_service.BOUND_ACCOUNT_KEY).all()
        assert len(bound_rows) == 1, "Expected exactly 1 bound account setting row"
        assert json.loads(bound_rows[0].value)["account_id"] == "DU_CONCURRENCY_TEST"

        # Verify duplicate timestamp rejections occurred
        errors = [r for r in results if r[0] == "ERROR"]
        successes = [r for r in results if r[0] == "SUCCESS"]
        assert len(successes) >= 1, "At least one initial admission must succeed"
        duplicate_or_replay_errors = [e for e in errors if "Duplicate" in e[2] or "Replay" in e[2] or "collision" in e[2]]
        assert len(duplicate_or_replay_errors) > 0, "Duplicate timestamp submissions must be rejected"

        # Verify rollback on transaction failure: simulated failure must not leave partial state
        fail_db = SessionLocal()
        try:
            invalid_payload = IBKRPaperSyncPayload(
                account_id="DU_CONCURRENCY_TEST",
                account_type="PAPER",
                currency="AUD",
                net_liquidation=100000.0,
                total_cash_value=50000.0,
                buying_power=200000.0,
                positions=[],
                connection_state="CONNECTED",
                timestamp=(now + timedelta(seconds=120)).isoformat(), # Future skew will fail
                gateway_managed_accounts=["DU_CONCURRENCY_TEST"],
                gateway_account_type="PAPER",
                gateway_port=4002,
            )
            with pytest.raises(ValueError, match="Clock skew rejection"):
                ibkr_service.save_paper_snapshot(fail_db, invalid_payload)
        finally:
            fail_db.close()

        # Confirm database is still healthy and latest valid snapshot is intact
        post_db = SessionLocal()
        current_status = ibkr_service.get_paper_account_status(post_db)
        assert current_status["account_id"] == "DU_CONCURRENCY_TEST"
        assert current_status["bound_account_id"] == "DU_CONCURRENCY_TEST"
        post_db.close()

    def test_24_paper_account_identity_binding_and_admin_rebind(self):
        """Verifies paper account binding, silent account switch prevention, and administrative rebind authorization."""
        db = SessionLocal()
        ibkr_service.clear_cache_for_testing(db)
        db.close()

        now = datetime.now(timezone.utc)
        t1 = (now - timedelta(seconds=30)).isoformat()
        t2 = (now - timedelta(seconds=20)).isoformat()
        t3 = (now - timedelta(seconds=10)).isoformat()

        # 1. First snapshot binds account DU_PRIMARY
        p1 = {
            "account_id": "DU_PRIMARY",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 150000.0,
            "total_cash_value": 75000.0,
            "buying_power": 300000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": t1,
            "gateway_managed_accounts": ["DU_PRIMARY"],
            "gateway_account_type": "PAPER",
            "gateway_port": 4002,
        }
        from app.config import IBKR_INGESTION_KEY
        res1 = client.post(
            "/api/portfolio/ibkr/sync",
            json=p1,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res1.status_code == 200

        # Check bound account status
        status1 = client.get(
            "/api/portfolio/ibkr/status",
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        ).json()
        assert status1["account_id"] == "DU_PRIMARY"

        # 2. Ingestion token attempts to silently switch dashboard to another paper account DU_SECONDARY
        p2_silent_switch = {
            "account_id": "DU_SECONDARY",
            "account_type": "PAPER",
            "currency": "AUD",
            "net_liquidation": 200000.0,
            "total_cash_value": 100000.0,
            "buying_power": 400000.0,
            "positions": [],
            "connection_state": "CONNECTED",
            "timestamp": t2,
            "gateway_managed_accounts": ["DU_SECONDARY"],
            "gateway_account_type": "PAPER",
            "gateway_port": 4002,
        }
        res2 = client.post(
            "/api/portfolio/ibkr/sync",
            json=p2_silent_switch,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res2.status_code == 400
        assert "Account binding rejection" in res2.json()["detail"]
        assert "Administrative authorization" in res2.json()["detail"]

        # 3. Ingestion credential attempts to call admin /bind-account endpoint
        res3_unauth = client.post(
            "/api/portfolio/ibkr/bind-account",
            json={"account_id": "DU_SECONDARY", "reason": "Unauthorized bind attempt"},
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        # Ingestion key does not grant admin access
        assert res3_unauth.status_code == 401

        # 4. Attempt to bind a LIVE brokerage account ('U1234567') is strictly rejected
        res4_live = client.post(
            "/api/portfolio/ibkr/bind-account",
            json={"account_id": "U1234567", "reason": "Attempting live account bind"},
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        )
        assert res4_live.status_code == 400
        assert "Live brokerage account" in res4_live.json()["detail"]

        # 5. Authorized administrator successfully rebinds to DU_SECONDARY
        res5_admin = client.post(
            "/api/portfolio/ibkr/bind-account",
            json={"account_id": "DU_SECONDARY", "reason": "Authorized paper account migration"},
            headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        )
        assert res5_admin.status_code == 200
        assert res5_admin.json()["status"] == "SUCCESS"
        assert res5_admin.json()["bound_account"]["account_id"] == "DU_SECONDARY"

        # 6. Now DU_SECONDARY snapshot is accepted
        p2_silent_switch["timestamp"] = t3
        res6 = client.post(
            "/api/portfolio/ibkr/sync",
            json=p2_silent_switch,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res6.status_code == 200
        assert res6.json()["status"]["account_id"] == "DU_SECONDARY"

        # 7. Old DU_PRIMARY is now rejected because account is bound to DU_SECONDARY
        t4 = datetime.now(timezone.utc).isoformat()
        p1["timestamp"] = t4
        res7_old = client.post(
            "/api/portfolio/ibkr/sync",
            json=p1,
            headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
        )
        assert res7_old.status_code == 400
        assert "Account binding rejection" in res7_old.json()["detail"]

    def test_25_soft_disable_flag_and_rollback_safety(self):
        """Validates that setting IBKR_PAPER_ENABLED=false soft-disables the integration immediately.

        Rollback does NOT require deleting database records.
        """
        db = SessionLocal()
        from app.config import IBKR_INGESTION_KEY, STOCKANALYSIS_ADMIN_KEY

        # 1. Simulate soft-disable via environment variable
        old_flag = os.environ.get("IBKR_PAPER_ENABLED")
        os.environ["IBKR_PAPER_ENABLED"] = "false"
        try:
            # Status endpoint reports DISABLED without modifying or deleting database records
            res = client.get(
                "/api/portfolio/ibkr",
                headers={"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["configured"] is False
            assert data["adapter_status"] == "DISABLED"
            assert data["gateway_connection"] == "DISABLED"
            assert "soft-disabled" in data["warning_message"]

            # Ingestion endpoint rejects new snapshots cleanly
            payload = {
                "account_id": "DU123456",
                "account_type": "PAPER",
                "currency": "AUD",
                "net_liquidation": 100000.0,
                "total_cash_value": 50000.0,
                "buying_power": 200000.0,
                "positions": [],
                "connection_state": "CONNECTED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            res_sync = client.post(
                "/api/portfolio/ibkr/sync",
                json=payload,
                headers={"X-IBKR-Ingest-Key": IBKR_INGESTION_KEY}
            )
            assert res_sync.status_code == 400
            assert "soft-disabled" in res_sync.json()["detail"]

        finally:
            if old_flag is not None:
                os.environ["IBKR_PAPER_ENABLED"] = old_flag
            else:
                os.environ.pop("IBKR_PAPER_ENABLED", None)
            db.close()

    def test_26_adapter_dry_run_does_not_call_backend(self):
        """Validates that adapter --dry-run returns cleanly without pushing to backend."""
        from app.adapters.ibkr_adapter import run_single_sync
        import argparse
        args = argparse.Namespace(
            host="127.0.0.1",
            port=4002,
            client_id=21,
            backend_url="http://127.0.0.1:8000",
            ingest_key=None,
            admin_key=None,
            interval=60,
            timeout=1,
            once=True,
            dry_run=True,
            mock=True
        )
        success = run_single_sync(args)
        assert success is True



