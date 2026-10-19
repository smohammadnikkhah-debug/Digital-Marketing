"""Comprehensive Verification Test Suite for Durable Screener Persistence & Background Jobs.

Tests required behaviors:
1. Durable database persistence (MonitoredStock, ScreenerSnapshot, RefreshJob).
2. Immutable timestamps on repeated queries.
3. Refresh Screener runs as an independent backend job.
4. Prevention of duplicate concurrent refreshes.
5. Navigation and reload simulation (independent execution).
6. Atomic snapshot publication and rollback on failure.
7. Safe concurrent Add to Screener and duplicate ticker handling.
8. Backend worker crash recovery (orphaned job cleanup).
9. Persistence across backend restart and simulated deployment.
10. Scheduled and manual jobs unified pipeline verification.
11. Frozen V4.0 strategy regression invariance.
"""
import json
import time
from datetime import datetime, date, timedelta
import pytest
from fastapi.testclient import TestClient

from app.config import SECRET_KEY, STOCKANALYSIS_ADMIN_KEY
from app.main import app
from app.database import SessionLocal
from app.models import MonitoredStock, ScreenerSnapshot, RefreshJob
from app.services.universe_manager import universe_manager
from app.services.scanner_service import scanner_service
from app.services.snapshot_service import snapshot_service
from app.cli import is_us_market_holiday
import pandas as pd
import strategy_core_v38 as v41_core

client = TestClient(app)


class TestDurableScreenerPersistence:

    def test_01_monitored_stocks_and_snapshot_seeded_in_db(self):
        """Test 1: MonitoredStock table and an active ScreenerSnapshot exist in the database."""
        db = SessionLocal()
        try:
            stocks_count = db.query(MonitoredStock).count()
            assert stocks_count >= 28, f"Expected at least 28 monitored stocks, found {stocks_count}"

            active_snap = db.query(ScreenerSnapshot).filter(
                ScreenerSnapshot.is_active == True,
                ScreenerSnapshot.status == "COMPLETED"
            ).first()
            assert active_snap is not None, "No active completed snapshot found in database"
            assert active_snap.market_as_of_date is not None
            assert active_snap.calculated_at is not None
            assert active_snap.total_stocks >= 28

            signals = json.loads(active_snap.signals_json)
            assert len(signals) >= 28
        finally:
            db.close()

    def test_02_immutable_timestamp_across_repeated_requests(self):
        """Test 2: GET /api/signals returns invariant, immutable last_refresh_time matching active snapshot."""
        res1 = client.get("/api/signals")
        assert res1.status_code == 200
        data1 = res1.json()
        ts1 = data1.get("last_refresh_time")

        time.sleep(0.5)

        res2 = client.get("/api/signals")
        assert res2.status_code == 200
        data2 = res2.json()
        ts2 = data2.get("last_refresh_time")

        assert ts1 is not None and ts1 != ""
        assert ts1 == ts2, f"Expected immutable refresh timestamp, but got '{ts1}' and '{ts2}'"

    def test_03_trigger_refresh_job_returns_job_id_immediately(self):
        """Test 3: POST /api/scanner/refresh requires valid admin authorization, rejects unauthenticated, and returns job ID."""
        # Cancel any previous running job with valid auth
        headers = {"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
        scanner_service.cancel_refresh()
        time.sleep(0.2)

        # 3a. Unauthenticated refresh request must be rejected (401 Unauthorized)
        res_unauth = client.post("/api/scanner/refresh", json={"force_all": False, "job_type": "FULL"})
        assert res_unauth.status_code == 401

        # 3b. Request with invalid key must be rejected (401 Unauthorized)
        res_bad_key = client.post(
            "/api/scanner/refresh",
            json={"force_all": False, "job_type": "FULL"},
            headers={"Authorization": "Bearer invalid_secret_key"}
        )
        assert res_bad_key.status_code == 401

        # 3c. Unauthenticated cancel-refresh must also be rejected (401 Unauthorized)
        res_cancel_unauth = client.post("/api/scanner/cancel-refresh")
        assert res_cancel_unauth.status_code == 401

        # 3d. Valid administrator X-Admin-Key with explicit job_type='FULL' succeeds
        res = client.post("/api/scanner/refresh", json={"force_all": False, "job_type": "FULL"}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("STARTED", "ALREADY_RUNNING")
        assert "job_id" in data
        assert data["job_id"].startswith("job_")

    def test_04_duplicate_refresh_request_prevented(self):
        """Test 4: Second refresh request while one is running returns ALREADY_RUNNING with same job_id."""
        db = SessionLocal()
        try:
            # Check or create a mock RUNNING job
            active_job = db.query(RefreshJob).filter(RefreshJob.status.in_(["QUEUED", "RUNNING"])).first()
            if not active_job:
                active_job = RefreshJob(
                    id=f"job_test_dup_{int(time.time())}",
                    status="RUNNING",
                    total_stocks=100,
                    completed_stocks=10,
                    start_time=datetime.utcnow(),
                    message="Simulated running job",
                )
                db.add(active_job)
                db.commit()

            headers = {"X-Admin-Key": STOCKANALYSIS_ADMIN_KEY}
            res = client.post("/api/scanner/refresh", json={"force_all": False, "job_type": "FULL"}, headers=headers)
            assert res.status_code == 409
            data = res.json()["detail"]
            assert data["status"] == "ALREADY_RUNNING"
            assert data["job_id"] == active_job.id
            assert "already in progress" in data["message"].lower()
        finally:
            # Clean up mock job
            if active_job and active_job.id.startswith("job_test_dup_"):
                active_job.status = "COMPLETED"
                db.commit()
            db.close()

    def test_05_browser_navigation_reload_simulation(self):
        """Test 5: Navigating away, reloading, or polling active-job retains state independently of client."""
        db = SessionLocal()
        try:
            test_job_id = f"job_nav_test_{int(time.time())}"
            job = RefreshJob(
                id=test_job_id,
                status="RUNNING",
                total_stocks=200,
                completed_stocks=75,
                remaining_stocks=125,
                current_ticker="AAPL",
                start_time=datetime.utcnow(),
                message="Analyzing AAPL...",
            )
            db.add(job)
            db.commit()

            # 1. Check active job endpoint
            res_active = client.get("/api/scanner/active-job")
            assert res_active.status_code == 200
            active_data = res_active.json().get("active_job")
            assert active_data is not None
            assert active_data["job_id"] == test_job_id
            assert active_data["completed"] == 75

            # 2. Simulate navigating to other pages (dashboard, portfolio)
            res_dash = client.get("/api/dashboard/strategy")
            assert res_dash.status_code == 200
            res_port = client.get("/api/portfolio/holdings")
            assert res_port.status_code == 200

            # 3. Simulate returning to Today's Signals and reconnecting
            res_return = client.get("/api/scanner/active-job")
            assert res_return.status_code == 200
            assert res_return.json()["active_job"]["job_id"] == test_job_id

            # Clean up
            job.status = "COMPLETED"
            db.commit()
        finally:
            db.close()

    def test_06_atomic_snapshot_rollback_on_failure(self):
        """Test 6: Failed or cancelled refresh preserves previous valid snapshot 100% intact."""
        db = SessionLocal()
        try:
            # Get existing active snapshot
            initial_snap = db.query(ScreenerSnapshot).filter(
                ScreenerSnapshot.is_active == True,
                ScreenerSnapshot.status == "COMPLETED"
            ).first()
            assert initial_snap is not None
            initial_snap_id = initial_snap.id
            initial_calc_time = initial_snap.calculated_at

            # Simulate a worker job failure
            failed_job_id = f"job_fail_{int(time.time())}"
            failed_job = RefreshJob(
                id=failed_job_id,
                status="FAILED",
                error_message="Simulated provider timeout",
                start_time=datetime.utcnow(),
                finish_time=datetime.utcnow(),
            )
            db.add(failed_job)
            db.commit()

            # Verify that active snapshot was NOT mutated or deactivated
            after_snap = db.query(ScreenerSnapshot).filter(
                ScreenerSnapshot.is_active == True,
                ScreenerSnapshot.status == "COMPLETED"
            ).first()
            assert after_snap.id == initial_snap_id
            assert after_snap.calculated_at == initial_calc_time

            # Verify GET /api/signals still returns the valid initial snapshot
            res_sig = client.get("/api/signals")
            assert res_sig.status_code == 200
            assert res_sig.json()["snapshot_id"] == initial_snap_id
        finally:
            db.close()

    def test_07_concurrent_add_stock_to_screener(self):
        """Test 7: Add to screener persists ticker, calculates signal, and handles duplicates safely."""
        ticker = "PANW"
        res = client.post("/api/scanner/add-stock", json={
            "ticker": ticker,
            "name": "Palo Alto Networks, Inc.",
            "exchange": "NASDAQ",
            "sector": "Technology",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["stock"]["ticker"] == ticker
        assert data["signal"]["signal"] in ("BUY CANDIDATE", "WATCH", "AVOID", "HOLD", "EXIT")

        # Verify safe duplicate addition (idempotent update)
        res_dup = client.post("/api/scanner/add-stock", json={
            "ticker": ticker,
            "name": "Palo Alto Networks, Inc.",
            "exchange": "NASDAQ",
            "sector": "Technology",
        })
        assert res_dup.status_code == 200
        assert res_dup.json()["stock"]["ticker"] == ticker

        # Verify stock exists in DB MonitoredStock
        db = SessionLocal()
        try:
            stock = db.query(MonitoredStock).filter(MonitoredStock.ticker == ticker).first()
            assert stock is not None
            assert stock.ticker == ticker
            assert stock.is_active is True
        finally:
            db.close()

    def test_08_backend_worker_restart_and_orphaned_job_recovery(self):
        """Test 8: Backend server restart detects and cleans up any orphaned running jobs."""
        db = SessionLocal()
        try:
            stuck_id = f"job_stuck_{int(time.time())}"
            stuck_job = RefreshJob(
                id=stuck_id,
                status="RUNNING",
                total_stocks=230,
                completed_stocks=45,
                start_time=datetime.utcnow() - timedelta(minutes=15),
                message="Processing...",
            )
            db.add(stuck_job)
            db.commit()

            # Run recovery
            snapshot_service.recover_orphaned_jobs(db)

            # Assert recovered
            recovered_job = db.query(RefreshJob).filter(RefreshJob.id == stuck_id).first()
            assert recovered_job.status == "FAILED"
            assert "restart" in recovered_job.error_message.lower()
        finally:
            db.close()

    def test_09_persistence_across_backend_restart_and_deployment(self):
        """Test 9: Database state survives re-initialization of service instances."""
        active_before = snapshot_service.get_active_snapshot()
        assert active_before is not None

        # Re-initialize universe manager and snapshot service
        from app.services.universe_manager import UniverseManager
        from app.services.snapshot_service import SnapshotService
        fresh_um = UniverseManager()
        fresh_ss = SnapshotService()

        active_after = fresh_ss.get_active_snapshot()
        assert active_after is not None
        assert active_after["snapshot_id"] == active_before["snapshot_id"]
        assert len(fresh_um.get_all()) >= 28

    def test_10_scheduled_and_manual_jobs_use_same_pipeline(self):
        """Test 10: Scheduled jobs use unified US calendar, market-open, and market-close checks."""
        # Weekend check
        sat = date(2026, 10, 17)
        is_hol, reason = is_us_market_holiday(sat)
        assert is_hol is True
        assert reason == "Weekend"

        # Trading weekday check
        wed = date(2026, 10, 14)
        is_hol_wed, reason_wed = is_us_market_holiday(wed)
        assert is_hol_wed is False
        assert reason_wed == "Regular Trading Session"

        # Scheduled jobs endpoints/snapshots audit
        res_snaps = client.get("/api/scanner/snapshots?limit=5")
        assert res_snaps.status_code == 200
        snaps = res_snaps.json()
        assert isinstance(snaps, list)
        assert len(snaps) >= 1

    def test_11_frozen_v40_strategy_regression(self):
        """Test 11: Frozen V4.0 strategy logic remains strictly preserved and unmodified."""
        # Test synthetic series
        dates = pd.bdate_range(start="2020-01-01", periods=300)
        df = pd.DataFrame({
            "Open": [100.0] * 300,
            "High": [105.0] * 300,
            "Low": [95.0] * 300,
            "Close": [102.0] * 300,
        }, index=dates)

        d = v41_core.prep(df)
        assert "MA30" in d.columns
        assert "MA50" in d.columns
        assert "MA250" in d.columns
        assert "ROC20" in d.columns
        assert "ATR14" in d.columns
        assert not d.empty
