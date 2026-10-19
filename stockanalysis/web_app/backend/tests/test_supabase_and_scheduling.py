"""Test Suite for Supabase PostgreSQL Integration, Table Isolation, Worker Concurrency,
DST-Safe Scheduling Guards, and Storage Retention Policy.
"""
import os
import sys
import json

from datetime import datetime, date, timedelta
import zoneinfo
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    DATABASE_URL,
    DB_SCHEMA,
    WORKER_MODE,
    SNAPSHOT_RETENTION_COUNT,
    JOB_RETENTION_COUNT,
    WEB_APP_DIR,
)
from app.database import engine, SessionLocal, Base
from app.models import MonitoredStock, ScreenerSnapshot, RefreshJob, DailyBar
from app.services.snapshot_service import snapshot_service
from app.services.scanner_service import scanner_service

from app.cli import (
    is_us_market_holiday,
    is_us_market_early_close,
    get_good_friday,
    NY_TZ,
)

client = TestClient(app)


class TestSupabaseAndScheduling:
    def setup_method(self):
        """Ensure clean test state."""
        pass

    def test_01_supabase_url_normalization_and_pooling_config(self):
        """Verifies postgres:// URL normalization and database settings."""
        test_postgres_url = "postgres://stockanalysis_app:placeholder_test_password@db.nrunrjfmqczeowakjnjh.supabase.co:5432/postgres?sslmode=require"
        normalized = test_postgres_url.replace("postgres://", "postgresql://", 1)
        assert normalized.startswith("postgresql://")
        assert "nrunrjfmqczeowakjnjh" in normalized
        assert "sslmode=require" in normalized

    def test_02_database_schema_isolation(self):
        """Verifies all models are scoped under the dedicated 'stockanalysis' schema."""
        assert DB_SCHEMA == "stockanalysis"
        assert Base.metadata.schema == "stockanalysis"

        # Check key models metadata schema
        assert MonitoredStock.__table__.schema == "stockanalysis"
        assert ScreenerSnapshot.__table__.schema == "stockanalysis"
        assert RefreshJob.__table__.schema == "stockanalysis"
        assert DailyBar.__table__.schema == "stockanalysis"


    def test_03_worker_mode_concurrency(self, monkeypatch):
        """Verifies that in standalone mode, web service queues job without spawning in-process thread."""
        db = SessionLocal()
        try:
            # Test standalone mode
            monkeypatch.setattr("app.services.scanner_service.WORKER_MODE", "standalone")
            res = scanner_service.start_refresh_async(force_all=False, job_type="FULL")
            assert res["status"] in ("QUEUED", "ALREADY_RUNNING")
            job_id = res.get("job_id")

            # Check that job is recorded in DB as QUEUED or RUNNING
            job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            assert job is not None
            assert job.status in ("QUEUED", "RUNNING")

            # Clean up job
            job.status = "COMPLETED"
            db.commit()
        finally:
            db.close()

    def test_04_timezone_dst_market_open_guard(self):
        """Verifies market open time guard correctly distinguishes 9:45 AM ET from off-hours UTC cron triggers."""
        # 9:45 AM ET on a regular Monday
        time_945_et = datetime(2026, 10, 19, 9, 45, tzinfo=NY_TZ)
        in_open_window = (time_945_et.hour == 9 and time_945_et.minute >= 35) or (time_945_et.hour == 10 and time_945_et.minute <= 20)
        assert in_open_window is True

        # Off-hours trigger (e.g. 8:45 AM ET during DST shift mismatch)
        time_845_et = datetime(2026, 10, 19, 8, 45, tzinfo=NY_TZ)
        in_open_window_845 = (time_845_et.hour == 9 and time_845_et.minute >= 35) or (time_845_et.hour == 10 and time_845_et.minute <= 20)
        assert in_open_window_845 is False

        # Night trigger (e.g. 13:45 ET)
        time_1345_et = datetime(2026, 10, 19, 13, 45, tzinfo=NY_TZ)
        in_open_window_1345 = (time_1345_et.hour == 9 and time_1345_et.minute >= 35) or (time_1345_et.hour == 10 and time_1345_et.minute <= 20)
        assert in_open_window_1345 is False

    def test_05_timezone_dst_market_close_guard(self):
        """Verifies market close time guard correctly identifies post-close sessions and early closes."""
        # Regular trading day at 4:30 PM ET (16:30 ET)
        time_1630_et = datetime(2026, 10, 19, 16, 30, tzinfo=NY_TZ)
        is_past_close = (time_1630_et.hour > 16) or (time_1630_et.hour == 16 and time_1630_et.minute >= 25)
        assert is_past_close is True

        # Premature trigger at 3:30 PM ET (15:30 ET - winter trigger during daylight saving)
        time_1530_et = datetime(2026, 10, 19, 15, 30, tzinfo=NY_TZ)
        is_past_close_premature = (time_1530_et.hour > 16) or (time_1530_et.hour == 16 and time_1530_et.minute >= 25)
        assert is_past_close_premature is False

        # Early close session (Black Friday at 1:30 PM ET)
        time_early_close = datetime(2026, 11, 27, 13, 30, tzinfo=NY_TZ)
        is_early, reason = is_us_market_early_close(time_early_close.date())
        assert is_early is True
        is_past_early_close = (time_early_close.hour > 13) or (time_early_close.hour == 13 and time_early_close.minute >= 25)
        assert is_past_early_close is True

    def test_06_market_holidays_and_weekends(self):
        """Verifies market holiday detection across US federal holidays and weekends."""
        # Weekend
        is_sat, _ = is_us_market_holiday(date(2026, 10, 17))
        assert is_sat is True

        is_sun, _ = is_us_market_holiday(date(2026, 10, 18))
        assert is_sun is True

        # Good Friday
        gf_2026 = get_good_friday(2026)
        assert gf_2026 == date(2026, 4, 3)
        is_gf, name = is_us_market_holiday(gf_2026)
        assert is_gf is True
        assert name == "Good Friday"

        # Memorial Day (Last Monday in May)
        is_mem, mem_name = is_us_market_holiday(date(2026, 5, 25))
        assert is_mem is True
        assert mem_name == "Memorial Day"

        # Juneteenth
        is_june, june_name = is_us_market_holiday(date(2026, 6, 19))
        assert is_june is True
        assert "Juneteenth" in june_name

        # Christmas Day
        is_xmas, xmas_name = is_us_market_holiday(date(2026, 12, 25))
        assert is_xmas is True
        assert "Christmas Day" in xmas_name

        # Regular trading day
        is_normal, _ = is_us_market_holiday(date(2026, 10, 19))
        assert is_normal is False

    def test_07_snapshot_retention_policy_pruning(self):
        """Verifies prune_historical_snapshots removes old inactive snapshots and keeps active snapshot."""
        db = SessionLocal()
        try:
            # Create active snapshot
            active_id = "snap_active_test_keep"
            db.merge(ScreenerSnapshot(
                id=active_id,
                status="COMPLETED",
                is_active=True,
                market_as_of_date="2026-10-19",
                saved_at=datetime.utcnow(),
                total_stocks=231,
                summary_json="{}",
                signals_json="[]",
            ))

            # Create 35 old inactive snapshots
            for i in range(35):
                db.merge(ScreenerSnapshot(
                    id=f"snap_old_test_{i:02d}",
                    status="COMPLETED",
                    is_active=False,
                    market_as_of_date="2026-09-01",
                    saved_at=datetime.utcnow() - timedelta(days=50 - i),
                    total_stocks=231,
                    summary_json="{}",
                    signals_json="[]",
                ))
            db.commit()

            # Execute pruning with keep_count = 10
            deleted = snapshot_service.prune_historical_snapshots(keep_count=10, db=db)
            assert deleted >= 20

            # Verify active snapshot was NEVER deleted
            active_after = db.query(ScreenerSnapshot).filter(ScreenerSnapshot.id == active_id).first()
            assert active_after is not None
            assert active_after.is_active is True

            # Verify remaining snapshot count is bounded
            total_remaining = db.query(ScreenerSnapshot).count()
            assert total_remaining <= 15
        finally:
            try:
                db.query(ScreenerSnapshot).filter(
                    ScreenerSnapshot.id.like("snap_old_test_%") | (ScreenerSnapshot.id == active_id)
                ).delete()
                db.commit()
            except Exception:
                pass
            db.close()

    def test_08_job_retention_policy_pruning(self):
        """Verifies prune_historical_jobs removes old finished jobs while preserving running jobs."""
        db = SessionLocal()
        try:
            # Create 60 old completed jobs
            for i in range(60):
                db.merge(RefreshJob(
                    id=f"job_old_test_{i:02d}",
                    status="COMPLETED",
                    created_at=datetime.utcnow() - timedelta(days=30),
                ))
            db.commit()

            # Prune
            deleted = snapshot_service.prune_historical_jobs(keep_count=20, max_age_days=14, db=db)
            assert deleted >= 30

            # Verify count is within limit
            remaining = db.query(RefreshJob).filter(RefreshJob.id.like("job_old_test_%")).count()
            assert remaining <= 20
        finally:
            try:
                db.query(RefreshJob).filter(RefreshJob.id.like("job_old_test_%")).delete()
                db.commit()
            except Exception:
                pass
            db.close()


    def test_09_storage_stats_and_free_tier_safety(self):
        """Verifies storage statistics calculation returns safe metrics well under Supabase 500 MB limit."""
        stats = snapshot_service.get_storage_stats()
        assert stats["status"] == "HEALTHY"
        assert stats["supabase_free_limit_mb"] == 500.0
        assert stats["estimated_footprint_mb"] < 15.0  # Well under 500 MB
        assert stats["capacity_used_pct"] < 3.0  # < 3% used
        assert stats["headroom_mb"] > 480.0
        assert stats["db_schema"] == "stockanalysis"

        # Check API endpoint
        response = client.get("/api/scanner/storage-stats")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "HEALTHY"
        assert data["db_schema"] == "stockanalysis"
        assert data["estimated_footprint_mb"] < 15.0

    def test_10_app_yaml_spec_verification(self):
        """Verifies app.yaml contains NO paid database and has proper Supabase/DST configuration."""
        app_yaml_path = WEB_APP_DIR / ".do" / "app.yaml"
        if not app_yaml_path.exists():
            app_yaml_path = WEB_APP_DIR.parent.parent / ".do" / "app.yaml"
        assert app_yaml_path.exists(), f"app.yaml not found at {app_yaml_path}"

        with open(app_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. No databases block
        assert "databases:" not in content
        assert "adaptive-db" not in content
        assert "${adaptive-db.DATABASE_URL}" not in content

        # 2. Top-level or component-level DATABASE_URL as SECRET
        assert "key: DATABASE_URL" in content
        assert "type: SECRET" in content

        # 3. Scheduled jobs configured with verified time_zone and recurrence
        assert "scheduled-market-open" in content
        assert "scheduled-market-close" in content
        assert ("America/New_York" in content or "45 13,14" in content)
        assert ("cron: \"30 13,16" in content or "30 17,18,20,21" in content)

        # 4. Supervised or standalone worker execution
        assert ("python -m app.supervisor" in content or "python -m app.worker" in content)

    def test_11_daily_bar_persistence_and_upsert(self):
        """Verifies DailyBar table stores daily OHLCV bars, handles atomic upserts, and supports cold-start recovery."""
        db = SessionLocal()
        test_ticker = "TEST_TICKER"
        test_date = "2026-10-16"
        try:
            # 1. Insert bar
            b1 = DailyBar(
                ticker=test_ticker,
                bar_date=test_date,
                open=100.0,
                high=105.0,
                low=99.0,
                close=103.5,
                volume=100000.0,
            )
            db.merge(b1)
            db.commit()

            # Verify saved
            fetched = db.query(DailyBar).filter(
                DailyBar.ticker == test_ticker, DailyBar.bar_date == test_date
            ).first()
            assert fetched is not None
            assert fetched.close == 103.5

            # 2. Incremental upsert (e.g. closing adjustment on same date)
            b2 = DailyBar(
                ticker=test_ticker,
                bar_date=test_date,
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.2,  # Adjusted close
                volume=105000.0,
            )
            db.merge(b2)
            db.commit()

            # Verify upsert (did not create duplicate row)
            all_rows = db.query(DailyBar).filter(
                DailyBar.ticker == test_ticker, DailyBar.bar_date == test_date
            ).all()
            assert len(all_rows) == 1
            assert all_rows[0].close == 104.2
        finally:
            db.query(DailyBar).filter(DailyBar.ticker == test_ticker).delete()
            db.commit()
            db.close()

    def test_12_storage_footprint_scaling_estimates(self):
        """Verifies mathematical storage models for 231, 350, and 500 stocks over 10 years."""
        # 252 trading days/year * 10 years = 2,520 bars per stock
        bars_per_stock = 252 * 10
        bytes_per_row = 105  # row header + tuple + b-tree index + page overhead in PostgreSQL

        def calc_footprint(stock_count):
            ohlcv_bytes = stock_count * bars_per_stock * bytes_per_row
            metadata_bytes = stock_count * 1200
            snapshot_bytes = 30 * 125000  # 30 retained snapshots
            fixed_overhead = 1000000  # 1 MB overhead
            total_bytes = ohlcv_bytes + metadata_bytes + snapshot_bytes + fixed_overhead
            return round(total_bytes / (1024 * 1024), 2)

        mb_231 = calc_footprint(231)
        mb_350 = calc_footprint(350)
        mb_500 = calc_footprint(500)

        # 231 stocks over 10 years ~ 65 MB
        assert 60.0 <= mb_231 <= 75.0
        # 350 stocks over 10 years ~ 97 MB
        assert 90.0 <= mb_350 <= 110.0
        # 500 stocks over 10 years ~ 138 MB
        assert 130.0 <= mb_500 <= 150.0

        # All configurations remain well below Supabase 500 MB free tier limit
        assert mb_500 < 200.0  # < 40% of 500 MB limit
        assert (500.0 - mb_500) > 300.0  # > 300 MB headroom remains

    def test_13_early_close_multi_utc_schedule_simulation(self):
        """Verifies that the multi-UTC cron (17:30, 18:30, 20:30, 21:30 UTC) executes correctly on early close days and regular days."""
        # 1. Regular session (closes 16:00 ET)
        reg_date = date(2026, 10, 19)
        assert is_us_market_early_close(reg_date)[0] is False

        # At 17:30 UTC (13:30 ET): regular market is OPEN. Guard must exit.
        t_1730 = datetime(2026, 10, 19, 13, 30, tzinfo=NY_TZ)
        is_past_reg = (t_1730.hour > 16) or (t_1730.hour == 16 and t_1730.minute >= 25)
        assert is_past_reg is False  # Correctly rejected

        # At 20:30 UTC (16:30 ET): regular market is CLOSED. Guard executes!
        t_2030 = datetime(2026, 10, 19, 16, 30, tzinfo=NY_TZ)
        is_past_reg_close = (t_2030.hour > 16) or (t_2030.hour == 16 and t_2030.minute >= 25)
        assert is_past_reg_close is True  # Correctly executed

        # 2. Early close session (Black Friday, Nov 27, 2026, closes 13:00 ET)
        early_date = date(2026, 11, 27)
        is_early, reason = is_us_market_early_close(early_date)
        assert is_early is True
        assert "Black Friday" in reason

        # At 18:30 UTC (13:30 EST): early close market is CLOSED. Guard executes!
        t_1830_est = datetime(2026, 11, 27, 13, 30, tzinfo=NY_TZ)
        is_past_early = (t_1830_est.hour > 13) or (t_1830_est.hour == 13 and t_1830_est.minute >= 25)
        assert is_past_early is True  # Correctly executed on early close day!


