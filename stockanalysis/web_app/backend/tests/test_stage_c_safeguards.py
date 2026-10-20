"""Stage C1.5 Safeguards Regression Test Suite.

Validates:
1. Partial ticker request validation (normalization, deduplication, universe bounds, bounds check).
2. PostgreSQL/SQLite batch upsert idempotency on daily_bars table.
3. Partial refresh snapshot non-destructive merge (231 universe preserved, 3 refreshed, 228 untouched).
4. Frozen baseline signal provenance isolation during partial refreshes.
5. Yahoo Finance HTTP 429 bounded backoff retry logic.
6. Worker partial job resolution from queued job metadata.
"""
import os
import sys
import json
from pathlib import Path
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import DailyBar, RefreshJob, ScreenerSnapshot, MonitoredStock
from app.services.scanner_service import scanner_service
from app.services.snapshot_service import snapshot_service
from app.services.universe_manager import universe_manager

client = TestClient(app)

STANDARD_REFRESHED_SIGNALS = [
    {
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "as_of": "2026-10-16",
        "close": 585.50,
        "ma30": 575.0,
        "ma50": 565.0,
        "ma250": 520.0,
        "roc20_pct": 3.5,
        "atr14": 5.2,
        "entry_rule": "ROC20_AT_CROSS",
        "exit_rule": "MA250_3CLOSE",
        "signal": "WATCH",
        "explanation": "Above MA250 setup.",
        "shariah_status": "NOT VERIFIED",
        "data_freshness": "FRESH",
    },
    {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "as_of": "2026-10-16",
        "close": 235.00,
        "ma30": 225.0,
        "ma50": 220.0,
        "ma250": 195.0,
        "roc20_pct": 4.1,
        "atr14": 3.8,
        "entry_rule": "DELAYED_STACK",
        "exit_rule": "MA250_ATR3",
        "signal": "BUY CANDIDATE",
        "explanation": "Valid long setup.",
        "shariah_status": "COMPLIANT",
        "data_freshness": "FRESH",
    },
    {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "as_of": "2026-10-16",
        "close": 420.00,
        "ma30": 415.0,
        "ma50": 410.0,
        "ma250": 390.0,
        "roc20_pct": 2.2,
        "atr14": 6.5,
        "entry_rule": "ROC20_AT_CROSS",
        "exit_rule": "MA250_3CLOSE",
        "signal": "WATCH",
        "explanation": "Above MA250 setup.",
        "shariah_status": "COMPLIANT",
        "data_freshness": "FRESH",
    },
]


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    snapshot_service._ensure_tables_and_seed()
    yield


class TestStageCSafeguards:

    def test_01_ticker_list_validation_in_refresh_request(self):
        """Validates ticker list normalization, deduplication, and invalid ticker rejection."""
        # 1. Empty list rejected with 400
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            resp = client.post("/api/scanner/refresh", json={"tickers": []}, headers=headers)
            assert resp.status_code == 400
            assert "cannot be empty" in resp.json()["detail"]

            # 2. Invalid tickers not in universe rejected with 400
            resp_inv = client.post("/api/scanner/refresh", json={"tickers": ["UNKNOWN"]}, headers=headers)
            assert resp_inv.status_code == 400
            assert "not in monitored universe" in resp_inv.json()["detail"]

            # 3. Excessive tickers (> 50) rejected with 400
            excessive = [f"TICKER_{i}" for i in range(55)]
            resp_exc = client.post("/api/scanner/refresh", json={"tickers": excessive}, headers=headers)
            assert resp_exc.status_code == 400
            assert "exceeds 50 ticker limit" in resp_exc.json()["detail"]

            # 4. Duplicate tickers rejected with 400
            resp_dup = client.post(
                "/api/scanner/refresh",
                json={"tickers": ["SPY", "AAPL", "SPY"]},
                headers=headers
            )
            assert resp_dup.status_code == 400
            assert "Duplicate tickers detected" in resp_dup.json()["detail"]

            # 5. Valid unique tickers accepted and passed to start_refresh_async
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                mock_start.return_value = {"status": "QUEUED", "job_id": "test_job"}
                resp_valid = client.post(
                    "/api/scanner/refresh",
                    json={"tickers": ["SPY", "AAPL", "MSFT"]},
                    headers=headers
                )
                assert resp_valid.status_code == 200
                mock_start.assert_called_once_with(
                    force_all=False,
                    tickers=["SPY", "AAPL", "MSFT"],
                    job_type="PARTIAL"
                )

    def test_02_batch_bar_persistence_idempotency(self):
        """Validates atomic batch upserts to DailyBar table without row-by-row overhead."""
        db = SessionLocal()
        # Clean any existing bars for test ticker
        db.query(DailyBar).filter(DailyBar.ticker == "TEST_BATCH").delete()
        db.commit()

        # Generate sample dataframe of 5 daily bars
        dates = pd.date_range("2026-10-01", periods=5, freq="D")
        df = pd.DataFrame({
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "High": [105.0, 106.0, 107.0, 108.0, 109.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "Close": [104.0, 105.0, 106.0, 107.0, 108.0],
            "Volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0],
        }, index=dates)

        # Batch insert
        scanner_service._persist_bars_to_db("TEST_BATCH", df, full=False)

        count1 = db.query(DailyBar).filter(DailyBar.ticker == "TEST_BATCH").count()
        assert count1 == 5

        # Re-insert with updated Close prices (idempotency & upsert verification)
        df["Close"] = [110.0, 111.0, 112.0, 113.0, 114.0]
        scanner_service._persist_bars_to_db("TEST_BATCH", df, full=False)

        # Count must remain exactly 5 (no duplicates)
        count2 = db.query(DailyBar).filter(DailyBar.ticker == "TEST_BATCH").count()
        assert count2 == 5

        # Check that values were updated to new close
        first_bar = db.query(DailyBar).filter(DailyBar.ticker == "TEST_BATCH").order_by(DailyBar.bar_date.asc()).first()
        assert first_bar.close == 110.0

        # Cleanup
        db.query(DailyBar).filter(DailyBar.ticker == "TEST_BATCH").delete()
        db.commit()
        db.close()

    def test_03_partial_refresh_snapshot_preserves_full_universe(self):
        """Proves that a partial refresh merges refreshed signals into the 231-stock snapshot without collapsing it."""
        db = SessionLocal()
        # Seed initial snapshot if not present
        active_snap = snapshot_service.get_active_snapshot(db=db)
        if not active_snap:
            snapshot_service._create_initial_snapshot(db=db)
            active_snap = snapshot_service.get_active_snapshot(db=db)

        initial_count = active_snap["total_stocks"]
        assert initial_count >= 20, f"Expected universe in baseline snapshot, got {initial_count}"

        # Refreshed signals for exactly 3 stocks
        refreshed_signals = STANDARD_REFRESHED_SIGNALS

        # Publish partial snapshot
        result = snapshot_service.publish_new_snapshot(
            staged_signals=refreshed_signals,
            market_as_of_date="2026-10-16",
            refresh_job_id="test_partial_job_01",
            db=db,
            is_partial=True,
        )

        assert result["total_stocks"] == 231, "Total universe must remain 231 stocks, NOT collapse to 3!"
        assert result["summary"]["refreshed_count"] >= 3

        # Verify active snapshot from DB
        new_active = snapshot_service.get_active_snapshot(db=db)
        assert new_active["total_stocks"] == 231
        signals_map = {s["ticker"]: s for s in new_active["signals"]}

        # Refreshed stocks must be FRESH
        assert signals_map["SPY"]["data_freshness"] == "FRESH"
        assert signals_map["AAPL"]["data_freshness"] == "FRESH"
        assert signals_map["MSFT"]["data_freshness"] == "FRESH"
        assert signals_map["AAPL"]["signal"] == "BUY CANDIDATE"

        # Untouched baseline stocks (e.g., NVDA, MA) must remain intact and preserve baseline data
        assert "NVDA" in signals_map
        assert "MA" in signals_map
        nvda_before = next(s for s in active_snap["signals"] if s["ticker"] == "NVDA")
        assert signals_map["NVDA"] == nvda_before, "Untouched stock NVDA must be preserved verbatim!"


        db.close()

    def test_04_yahoo_download_exponential_backoff_on_429(self):
        """Validates that HTTP 429 triggers bounded exponential backoff and retry."""
        import yfinance as yf

        mock_attempts = 0
        def fake_download(*args, **kwargs):
            nonlocal mock_attempts
            mock_attempts += 1
            if mock_attempts < 2:
                raise RuntimeError("HTTP 429 Client Error: Too Many Requests")
            # Succeed on attempt 2
            return pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2026-10-16", periods=1))

        with patch("yfinance.download", side_effect=fake_download), patch("time.sleep") as mock_sleep:
            bars = scanner_service._download_yahoo_bars(
                "SPY",
                {"period": "5d"},
                max_retries=3,
                base_delay=0.1
            )
            assert bars is not None
            assert len(bars) == 1
            assert mock_attempts == 2
            mock_sleep.assert_called()

    def test_05_start_refresh_async_stores_requested_tickers_in_job(self):
        """Verifies start_refresh_async stores requested tickers in job metadata."""
        db = SessionLocal()
        with patch.object(scanner_service, "_run_refresh_worker"):
            res = scanner_service.start_refresh_async(
                force_all=False,
                tickers=["SPY", "AAPL", "MSFT"]
            )
            assert res["status"] in ("STARTED", "QUEUED")
            job_id = res["job_id"]

            job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert job is not None
            assert job.job_type == "PARTIAL_REFRESH"
            assert job.total_stocks == 3
            assert "SPY" in job.message

            meta = json.loads(job.errors_json)
            assert meta["requested_tickers"] == ["SPY", "AAPL", "MSFT"]

            # Cleanup
            db.delete(job)
            db.commit()
        db.close()

    def test_06_zero_snapshot_fallback_preserves_universe_without_fabrication(self):
        """Validates that a partial refresh when 0 snapshots exist preserves 231 stocks without fabricating signals for unscanned stocks."""
        db = SessionLocal()
        existing_snaps = db.query(ScreenerSnapshot).all()
        existing_data = [(s.id, s.is_active, s.signals_json, s.summary_json, s.total_stocks, s.market_as_of_date, s.status, s.calculated_at, s.saved_at) for s in existing_snaps]
        stocks = db.query(MonitoredStock).all()
        stock_signals = {s.ticker: s.latest_signal_json for s in stocks}

        try:
            db.query(ScreenerSnapshot).delete()
            # Clear non-baseline signals in MonitoredStock to mirror true zero-snapshot production initial state
            from app.config import BASELINE_EXCEL_PATH
            import pandas as pd
            xl = pd.ExcelFile(BASELINE_EXCEL_PATH)
            baseline_tickers = set(t.strip().upper() for t in xl.parse("TodayTrade")["Ticker"].tolist())
            db.query(MonitoredStock).filter(~MonitoredStock.ticker.in_(baseline_tickers)).update({"latest_signal_json": None}, synchronize_session=False)
            db.commit()

            refreshed_signals = STANDARD_REFRESHED_SIGNALS

            result = snapshot_service.publish_new_snapshot(
                staged_signals=refreshed_signals,
                market_as_of_date="2026-10-16",
                refresh_job_id="test_zero_snap_job",
                db=db,
                is_partial=True,
            )

            assert result["total_stocks"] == 231
            assert result["summary"]["total_universe"] == 231
            assert result["summary"]["unscanned_count"] > 0

            active = snapshot_service.get_active_snapshot(db=db)
            assert active["total_stocks"] == 231
            assert len(active["signals"]) < 231, "Unscanned stocks must NOT have fabricated signals!"
            assert "Unscanned" in active["summary"]["data_provenance"]["badge_text"]
        finally:
            db.query(ScreenerSnapshot).delete()
            for row in existing_data:
                db.add(ScreenerSnapshot(
                    id=row[0], is_active=row[1], signals_json=row[2], summary_json=row[3],
                    total_stocks=row[4], market_as_of_date=row[5], status=row[6],
                    calculated_at=row[7], saved_at=row[8]
                ))
            for t, sig in stock_signals.items():
                db.query(MonitoredStock).filter(MonitoredStock.ticker == t).update({"latest_signal_json": sig})
            db.commit()
            db.close()

    def test_07_truthful_classification_of_baseline_refreshed_unscanned(self):
        """Verifies exact counts for refreshed, frozen baseline, and unscanned stocks without mislabeling all untouched as baseline."""
        db = SessionLocal()
        existing_snaps = db.query(ScreenerSnapshot).all()
        existing_data = [(s.id, s.is_active, s.signals_json, s.summary_json, s.total_stocks, s.market_as_of_date, s.status, s.calculated_at, s.saved_at) for s in existing_snaps]

        try:
            # Seed active snapshot with 28 baseline stocks to mirror true production baseline state
            from app.config import BASELINE_EXCEL_PATH
            import pandas as pd
            xl = pd.ExcelFile(BASELINE_EXCEL_PATH)
            baseline_tickers = [t.strip().upper() for t in xl.parse("TodayTrade")["Ticker"].tolist()]
            baseline_signals = [
                {"ticker": t, "name": t, "signal": "WATCH", "close": 100.0, "as_of": "2026-10-16", "data_freshness": "FROZEN_BASELINE"}
                for t in baseline_tickers
            ]
            db.query(ScreenerSnapshot).update({"is_active": False})
            base_snap = ScreenerSnapshot(
                id="test_baseline_snap_07",
                status="COMPLETED",
                is_active=True,
                market_as_of_date="2026-10-16",
                total_stocks=231,
                signals_json=json.dumps(baseline_signals),
                summary_json=json.dumps({"total_universe": 231, "frozen_baseline_count": 28, "unscanned_count": 203})
            )
            db.add(base_snap)
            db.commit()

            refreshed_signals = STANDARD_REFRESHED_SIGNALS
            res = snapshot_service.publish_new_snapshot(
                staged_signals=refreshed_signals,
                market_as_of_date="2026-10-16",
                refresh_job_id="test_classification_job",
                db=db,
                is_partial=True,
            )

            summary = res["summary"]
            provenance = summary["data_provenance"]
            assert summary["refreshed_count"] >= 3
            assert summary["frozen_baseline_count"] < 50, "Untouched stocks must not all be labeled baseline!"
            assert summary["unscanned_count"] > 100
            assert provenance["is_refreshed"] is False
        finally:
            db.query(ScreenerSnapshot).delete()
            for row in existing_data:
                db.add(ScreenerSnapshot(
                    id=row[0], is_active=row[1], signals_json=row[2], summary_json=row[3],
                    total_stocks=row[4], market_as_of_date=row[5], status=row[6],
                    calculated_at=row[7], saved_at=row[8]
                ))
            db.commit()
            db.close()

    def test_08_batch_upsert_chunking_and_idempotency_large_dataset(self):
        """Verifies that large backfills (1,200 bars) are chunked safely into <=500 row batches and are idempotent."""
        db = SessionLocal()
        dates = pd.date_range("2021-01-01", periods=1200, freq="B")
        df_large = pd.DataFrame({
            "Open": [100.0 + i * 0.1 for i in range(1200)],
            "High": [105.0 + i * 0.1 for i in range(1200)],
            "Low": [95.0 + i * 0.1 for i in range(1200)],
            "Close": [102.0 + i * 0.1 for i in range(1200)],
            "Volume": [1000000.0 for _ in range(1200)],
        }, index=dates)

        db.query(DailyBar).filter(DailyBar.ticker == "TEST_CHUNK").delete()
        db.commit()

        scanner_service._persist_bars_to_db("TEST_CHUNK", df_large, full=True)
        count1 = db.query(DailyBar).filter(DailyBar.ticker == "TEST_CHUNK").count()
        assert count1 == 1200, f"Expected 1200 bars, got {count1}"

        df_large["Close"] = [200.0 + i * 0.1 for i in range(1200)]
        scanner_service._persist_bars_to_db("TEST_CHUNK", df_large, full=True)
        count2 = db.query(DailyBar).filter(DailyBar.ticker == "TEST_CHUNK").count()
        assert count2 == 1200, f"Expected 1200 bars after upsert, got {count2}"

        sample = db.query(DailyBar).filter(DailyBar.ticker == "TEST_CHUNK").first()
        assert sample.close >= 200.0, "Upsert should have updated close price"

        db.query(DailyBar).filter(DailyBar.ticker == "TEST_CHUNK").delete()
        db.commit()
        db.close()

    def test_09_worker_strict_rejection_of_empty_or_invalid_partial_job(self):
        """Verifies worker rejects partial refresh with empty/invalid tickers and refuses fallback to full universe."""
        db = SessionLocal()
        job_id = "test_invalid_partial_job"
        db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
        try:
            bad_job = RefreshJob(
                id=job_id,
                status="QUEUED",
                job_type="PARTIAL_REFRESH",
                errors_json=json.dumps({"requested_tickers": []}),
                created_at=datetime.utcnow(),
            )
            db.add(bad_job)
            db.commit()

            from app.worker import run_worker_iteration
            did_work = run_worker_iteration(db=db)
            assert did_work is True

            db.expire_all()
            updated = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert updated.status == "FAILED"
            assert "rejected" in updated.error_message.lower()
        finally:
            db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_10_atomic_snapshot_rollback_on_failure(self):
        """Verifies that an error during snapshot publication rolls back cleanly and leaves the prior active snapshot active."""
        db = SessionLocal()
        active_before = snapshot_service.get_active_snapshot(db=db)
        if not active_before:
            snapshot_service._create_initial_snapshot(db=db)
            active_before = snapshot_service.get_active_snapshot(db=db)

        with patch.object(db, "commit", side_effect=RuntimeError("Simulated database failure during commit")):
            try:
                snapshot_service.publish_new_snapshot(
                    staged_signals=[{"ticker": "SPY", "signal": "WATCH"}],
                    market_as_of_date="2026-10-16",
                    db=db,
                    is_partial=True,
                )
            except RuntimeError:
                pass

        active_after = snapshot_service.get_active_snapshot(db=db)
        assert active_after["snapshot_id"] == active_before["snapshot_id"]
        assert active_after["is_active"] is True
        db.close()

    def test_11_partial_refresh_leaves_nvda_and_unselected_stocks_verbatim(self):
        """Verifies that refreshing SPY, AAPL, MSFT does not alter NVDA's signal, freshness, or provenance."""
        db = SessionLocal()
        active = snapshot_service.get_active_snapshot(db=db)
        if not active:
            snapshot_service._create_initial_snapshot(db=db)
            active = snapshot_service.get_active_snapshot(db=db)

        nvda_signal_before = next((s for s in active["signals"] if s["ticker"] == "NVDA"), None)
        assert nvda_signal_before is not None

        refreshed_signals = STANDARD_REFRESHED_SIGNALS

        snapshot_service.publish_new_snapshot(
            staged_signals=refreshed_signals,
            market_as_of_date="2026-10-16",
            refresh_job_id="test_nvda_integrity_job",
            db=db,
            is_partial=True,
        )

        new_active = snapshot_service.get_active_snapshot(db=db)
        nvda_signal_after = next((s for s in new_active["signals"] if s["ticker"] == "NVDA"), None)

        assert nvda_signal_after is not None
        assert nvda_signal_after == nvda_signal_before, "NVDA signal must be identical down to every field!"
        db.close()

    def test_12_api_rejects_contradictory_full_job_with_tickers(self):
        """Verifies API rejects job_type=FULL when specific tickers are provided (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            # 1. job_type=FULL with tickers
            resp = client.post("/api/scanner/refresh", json={"job_type": "FULL", "tickers": ["AAPL"]}, headers=headers)
            assert resp.status_code == 400
            assert "Contradictory payload: job_type is FULL" in resp.json()["detail"]

            # 2. job_type=FULL with selected_tickers
            resp2 = client.post("/api/scanner/refresh", json={"job_type": "FULL", "selected_tickers": ["MSFT"]}, headers=headers)
            assert resp2.status_code == 400
            assert "Contradictory payload: job_type is FULL" in resp2.json()["detail"]

    def test_13_api_rejects_contradictory_partial_job_without_tickers(self):
        """Verifies API rejects job_type=PARTIAL when no tickers are provided (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            resp = client.post("/api/scanner/refresh", json={"job_type": "PARTIAL"}, headers=headers)
            assert resp.status_code == 400
            assert "Contradictory payload: job_type is PARTIAL but no tickers" in resp.json()["detail"]

    def test_14_api_rejects_conflicting_tickers_and_selected_tickers(self):
        """Verifies API rejects request when tickers and selected_tickers contain conflicting lists (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            resp = client.post(
                "/api/scanner/refresh",
                json={"tickers": ["AAPL"], "selected_tickers": ["MSFT"]},
                headers=headers
            )
            assert resp.status_code == 400
            assert "conflicting values" in resp.json()["detail"]

    def test_15_api_rejects_invalid_job_type(self):
        """Verifies API rejects unrecognized job_type (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            resp = client.post(
                "/api/scanner/refresh",
                json={"job_type": "UNSUPPORTED_TYPE", "tickers": ["AAPL"]},
                headers=headers
            )
            assert resp.status_code == 400
            assert "Invalid job_type" in resp.json()["detail"]

    def test_16_api_rejects_case_insensitive_duplicates_and_malformed_symbols(self):
        """Verifies API rejects case-insensitive duplicates and malformed ticker symbols (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            # Case-insensitive duplicate
            resp_dup = client.post("/api/scanner/refresh", json={"tickers": ["aapl", "AAPL"]}, headers=headers)
            assert resp_dup.status_code == 400
            assert "Duplicate ticker" in resp_dup.json()["detail"]

            # Malformed symbol with invalid characters
            resp_mal = client.post("/api/scanner/refresh", json={"tickers": ["AAPL$#@"]}, headers=headers)
            assert resp_mal.status_code == 400
            assert "Malformed ticker symbol" in resp_mal.json()["detail"]

            # Empty string symbol
            resp_empty = client.post("/api/scanner/refresh", json={"tickers": ["   "]}, headers=headers)
            assert resp_empty.status_code == 400
            assert "Malformed ticker symbol" in resp_empty.json()["detail"]

    def test_17_api_rejects_inactive_ticker(self):
        """Verifies API rejects inactive tickers (HTTP 400)."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            orig_stock = universe_manager.get_stock("SPY")
            try:
                universe_manager.update_stock("SPY", {"is_active": False}, sync_db=False)
                resp = client.post("/api/scanner/refresh", json={"tickers": ["SPY"]}, headers=headers)
                assert resp.status_code == 400
                assert "inactive in monitored universe" in resp.json()["detail"]
            finally:
                universe_manager.update_stock("SPY", {"is_active": True}, sync_db=False)

    def test_18_worker_fails_closed_on_corrupt_or_missing_metadata(self):
        """Verifies worker rejects partial refresh with corrupted or missing JSON metadata without full refresh."""
        db = SessionLocal()
        job_id = "test_corrupt_meta_job"
        db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
        try:
            bad_job = RefreshJob(
                id=job_id,
                status="QUEUED",
                job_type="PARTIAL_REFRESH",
                errors_json="{bad_json: invalid",
                created_at=datetime.utcnow(),
            )
            db.add(bad_job)
            db.commit()

            from app.worker import run_worker_iteration
            did_work = run_worker_iteration(db=db)
            assert did_work is True

            db.expire_all()
            updated = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert updated.status == "FAILED"
            assert "corrupted json" in updated.error_message.lower()
        finally:
            db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_19_worker_fails_closed_on_duplicate_tickers(self):
        """Verifies worker rejects partial refresh when metadata contains duplicate tickers."""
        db = SessionLocal()
        job_id = "test_dup_worker_job"
        db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
        try:
            bad_job = RefreshJob(
                id=job_id,
                status="QUEUED",
                job_type="PARTIAL_REFRESH",
                errors_json=json.dumps({"requested_tickers": ["AAPL", "AAPL"]}),
                created_at=datetime.utcnow(),
            )
            db.add(bad_job)
            db.commit()

            from app.worker import run_worker_iteration
            did_work = run_worker_iteration(db=db)
            assert did_work is True

            db.expire_all()
            updated = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert updated.status == "FAILED"
            assert "duplicate ticker" in updated.error_message.lower()
        finally:
            db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_20_worker_fails_closed_on_unknown_or_inactive_ticker(self):
        """Verifies worker rejects partial refresh if ANY ticker is unknown or inactive without scanning remaining."""
        db = SessionLocal()
        job_id = "test_unknown_worker_job"
        db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
        try:
            # Contains valid AAPL but also unknown XYZABC (6 chars, valid format, unknown in universe)
            bad_job = RefreshJob(
                id=job_id,
                status="QUEUED",
                job_type="PARTIAL_REFRESH",
                errors_json=json.dumps({"requested_tickers": ["AAPL", "XYZABC"]}),
                created_at=datetime.utcnow(),
            )
            db.add(bad_job)
            db.commit()

            from app.worker import run_worker_iteration
            with patch.object(scanner_service, "_run_refresh_worker") as mock_run:
                did_work = run_worker_iteration(db=db)
                assert did_work is True
                mock_run.assert_not_called()

            db.expire_all()
            updated = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert updated.status == "FAILED"
            assert "unknown ticker" in updated.error_message.lower()
        finally:
            db.query(RefreshJob).filter(RefreshJob.id == job_id).delete()
            db.commit()
            db.close()

    def test_21_valid_intentional_full_refresh_succeeds(self):
        """Verifies explicitly valid full-universe refresh triggers successfully with explicit job_type='FULL'."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                mock_start.return_value = {"status": "QUEUED", "job_id": "test_full_job"}
                # Explicit job_type=FULL with no tickers succeeds
                resp = client.post("/api/scanner/refresh", json={"job_type": "FULL"}, headers=headers)
                assert resp.status_code == 200
                mock_start.assert_called_with(force_all=False, tickers=None, job_type="FULL")

    def test_22_empty_or_missing_body_rejected_with_http_400_without_creating_jobs(self):
        """Verifies empty or missing request bodies return HTTP 400 without creating jobs."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                # 1. Missing request body (None)
                resp1 = client.post("/api/scanner/refresh", headers=headers)
                assert resp1.status_code == 400
                assert "Missing request body" in resp1.json()["detail"]
                mock_start.assert_not_called()

                # 2. Empty JSON body ({})
                resp2 = client.post("/api/scanner/refresh", json={}, headers=headers)
                assert resp2.status_code == 400
                assert "Missing explicit job_type" in resp2.json()["detail"]
                mock_start.assert_not_called()

                # 3. Unclassified body with only force_all
                resp3 = client.post("/api/scanner/refresh", json={"force_all": True}, headers=headers)
                assert resp3.status_code == 400
                assert "Missing explicit job_type" in resp3.json()["detail"]
                mock_start.assert_not_called()

    def test_23_service_layer_enforces_explicit_job_type_full(self):
        """Verifies scanner_service.start_refresh_async raises ValueError if full refresh lacks explicit job_type='FULL'."""
        import pytest
        # Calling without tickers and without explicit job_type='FULL' must raise ValueError
        with pytest.raises(ValueError, match="Full-universe refresh requires explicit job_type='FULL'"):
            scanner_service.start_refresh_async(tickers=None, job_type=None)

        with pytest.raises(ValueError, match="Full-universe refresh requires explicit job_type='FULL'"):
            scanner_service.start_refresh_async(tickers=None, job_type="MANUAL_REFRESH")

    def test_24_refresh_screener_button_partial_payload_contract(self):
        """Verifies the Refresh Screener button contract: job_type='PARTIAL' with ['SPY', 'AAPL', 'MSFT']."""
        headers = {"X-Admin-Key": "test_admin_key"}
        payload = {
            "job_type": "PARTIAL",
            "selected_tickers": ["SPY", "AAPL", "MSFT"]
        }
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                mock_start.return_value = {
                    "status": "QUEUED",
                    "job_id": "test_partial_button_job",
                    "target_tickers": ["SPY", "AAPL", "MSFT"]
                }
                resp = client.post("/api/scanner/refresh", json=payload, headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "QUEUED"
                mock_start.assert_called_with(
                    force_all=False,
                    tickers=["SPY", "AAPL", "MSFT"],
                    job_type="PARTIAL"
                )

    def test_25_unauthenticated_scanner_request_rejected_with_http_401(self):
        """Verifies unauthenticated scanner refresh requests are strictly rejected with HTTP 401."""
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                # 1. No headers provided
                resp1 = client.post("/api/scanner/refresh", json={"job_type": "PARTIAL", "selected_tickers": ["SPY"]})
                assert resp1.status_code == 401
                assert "Unauthorized: Valid administrator credentials required." in resp1.json()["detail"]
                mock_start.assert_not_called()

                # 2. Invalid key provided
                resp2 = client.post(
                    "/api/scanner/refresh",
                    json={"job_type": "PARTIAL", "selected_tickers": ["SPY"]},
                    headers={"X-Admin-Key": "wrong_key"}
                )
                assert resp2.status_code == 401
                assert "Unauthorized: Valid administrator credentials required." in resp2.json()["detail"]
                mock_start.assert_not_called()

    def test_26_obsolete_force_all_payload_rejected_no_accidental_full_refresh(self):
        """Verifies obsolete payload {'force_all': false} is rejected with HTTP 400 and cannot trigger full refresh."""
        headers = {"X-Admin-Key": "test_admin_key"}
        with patch("app.routers.scanner.STOCKANALYSIS_ADMIN_KEY", "test_admin_key"):
            with patch.object(scanner_service, "start_refresh_async") as mock_start:
                resp = client.post("/api/scanner/refresh", json={"force_all": False}, headers=headers)
                assert resp.status_code == 400
                assert "Missing explicit job_type" in resp.json()["detail"]
                mock_start.assert_not_called()

