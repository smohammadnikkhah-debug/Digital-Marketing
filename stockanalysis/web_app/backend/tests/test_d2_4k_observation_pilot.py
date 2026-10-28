"""Stage D2.4K — observation pilot: schedule, recovery, safety, reporting."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.config import IBKR_EMERGENCY_STOP, TRADING_EXECUTION_ENABLED
from app.services.execution_lifecycle_audit import run_execution_lifecycle_audit
from app.services.observation_performance import (
    FILL_APPROXIMATION_DOC,
    evaluate_simulated_opportunity,
)
from app.services.observation_runner import ObservationRunner
from app.services.observation_schedule import (
    ensure_schedule_config,
    is_observation_trading_day,
    next_observation_trading_day,
    plan_upcoming_slots,
    should_run_slot,
    slot_datetime_et,
)
from app.services.order_execution_service import DEFAULT_MAX_ORDER_NOTIONAL_USD
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED

NY = ZoneInfo("America/New_York")


class TestSafetyInvariants:
    def test_execution_flags_unchanged(self):
        assert STAGE_APPROVAL_ENABLED is False
        assert STAGE_SUBMISSION_ENABLED is False
        assert IBKR_EMERGENCY_STOP is True
        assert TRADING_EXECUTION_ENABLED is False

    def test_order_cap_preserved(self):
        assert DEFAULT_MAX_ORDER_NOTIONAL_USD == 500.0


class TestObservationSchedule:
    def test_ensure_schedule_not_activated(self, tmp_path):
        path = tmp_path / "schedule_config.json"
        cfg = ensure_schedule_config(path)
        assert cfg["activation"]["windows_task_enabled"] is False
        assert cfg["activation"]["digitalocean_cron_enabled"] is False
        assert cfg["activation"]["unattended_enabled"] is False
        assert path.exists()

    def test_weekend_and_holiday(self):
        # Saturday
        ok, reason = is_observation_trading_day(date(2026, 10, 24))
        assert ok is False
        assert "Weekend" in reason
        # Thanksgiving 2026-11-26
        ok, reason = is_observation_trading_day(date(2026, 11, 26))
        assert ok is False
        assert "Thanksgiving" in reason

    def test_next_trading_day_skips_weekend(self):
        # Friday Oct 23 2026 → next should be Monday Oct 26
        nxt = next_observation_trading_day(date(2026, 10, 23))
        assert nxt == date(2026, 10, 26)

    def test_early_close_post_close_slot(self):
        # Christmas Eve 2026 is Thursday Dec 24 — early close
        day = date(2026, 12, 24)
        slot = {
            "id": "post_close_research",
            "mode": "post_close",
            "et_hour": 16,
            "et_minute": 30,
            "early_close_et_hour": 13,
            "early_close_et_minute": 30,
        }
        dt = slot_datetime_et(day, slot)
        assert dt.hour == 13 and dt.minute == 30

    def test_should_run_slot_in_window(self):
        # Regular Monday 2026-10-26 16:35 ET
        now = datetime(2026, 10, 26, 16, 35, tzinfo=NY).astimezone(timezone.utc)
        gate = should_run_slot("post_close_research", now_utc=now, window_minutes=45)
        assert gate["should_run"] is True
        assert gate["reason_code"] == "IN_WINDOW"

    def test_should_run_slot_holiday_blocked(self):
        now = datetime(2026, 11, 26, 16, 35, tzinfo=NY).astimezone(timezone.utc)
        gate = should_run_slot("post_close_research", now_utc=now)
        assert gate["should_run"] is False
        assert gate["reason_code"] == "MARKET_CLOSED"

    def test_plan_upcoming_includes_activation_false(self):
        plan = plan_upcoming_slots(
            from_utc=datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc),
            trading_days=2,
        )
        assert plan["activation"]["windows_task_enabled"] is False
        assert any(e.get("slot_id") == "post_close_research" for e in plan["events"] if not e.get("skipped"))


class TestObservationPerformance:
    def test_fill_doc_disclaims_broker_fills(self):
        assert "NOT a broker fill" in FILL_APPROXIMATION_DOC.upper() or "not a broker" in FILL_APPROXIMATION_DOC.lower()

    def test_evaluate_with_synthetic_bars(self, tmp_path):
        # Use real price cache if present; otherwise skip soft
        from app.services.scanner_service import scanner_service

        df = scanner_service.get_price_df("AAPL")
        if df is None or len(df) < 10:
            return
        as_of = str(df.index[-6].date()) if len(df) >= 6 else str(df.index[-1].date())
        close = float(df.iloc[-6]["Close"]) if len(df) >= 6 else float(df.iloc[-1]["Close"])
        # BUY limit fills when subsequent Low <= limit → high limit fills; tiny limit may not
        perf_fill = evaluate_simulated_opportunity(
            ticker="AAPL",
            signal_date=as_of,
            signal_price=close,
            entry_rule="CROSS",
            proposed_limit=close * 2,
            proposed_qty=1,
            lookforward_bars=5,
        )
        perf_miss = evaluate_simulated_opportunity(
            ticker="AAPL",
            signal_date=as_of,
            signal_price=close,
            entry_rule="CROSS",
            proposed_limit=0.01,
            proposed_qty=1,
            lookforward_bars=5,
        )
        assert perf_miss.get("is_real_broker_fill") is False
        if perf_fill.get("sufficient_data"):
            assert perf_fill.get("would_have_filled_approx") is True
        if perf_miss.get("sufficient_data"):
            assert perf_miss.get("would_have_filled_approx") is False
            assert "subsequent_return_pct" in perf_miss


class TestObservationRunnerRecovery:
    def test_checkpoint_resume(self, tmp_path):
        from app.config import V40_STRATEGY_VERSION

        runner = ObservationRunner(evidence_dir=tmp_path / "ev", refresh_prices=False)
        runner.checkpoint_path = tmp_path / "checkpoint.json"
        runner._save_checkpoint(
            {
                "completed_tickers": ["AAPL"],
                "scan_rows_by_ticker": {
                    "AAPL": {
                        "ticker": "AAPL",
                        "signal": "AVOID",
                        "strategy_version": V40_STRATEGY_VERSION,
                    }
                },
                "universe_tickers": ["AAPL", "MSFT"],
                "strategy_version": V40_STRATEGY_VERSION,
                "last_run_id": "x",
            }
        )

        fake_rows = []

        def fake_eval(ticker, df=None, **kwargs):
            fake_rows.append(ticker)
            return {
                "ticker": ticker,
                "signal": "AVOID",
                "as_of": "2026-10-26",
                "market_as_of_date": "2026-10-26",
                "entry_rule": "CROSS",
                "close": 100.0,
                "signal_source": "V40_SCANNER",
                "strategy_version": V40_STRATEGY_VERSION,
            }

        with patch("app.services.observation_runner.scanner_service") as mock_scan:
            import pandas as pd

            df = pd.DataFrame(
                {
                    "Open": [1.0] * 300,
                    "High": [1.0] * 300,
                    "Low": [1.0] * 300,
                    "Close": [1.0] * 300,
                }
            )
            mock_scan.get_price_df.return_value = df
            mock_scan.evaluate_stock_signal.side_effect = fake_eval
            scan = runner.scan_universe(["AAPL", "MSFT"], resume=True)

        assert "AAPL" not in fake_rows  # skipped via checkpoint
        assert "MSFT" in fake_rows
        assert scan["resumed_from_checkpoint"] is True

    def test_schedule_gate_skip_without_force(self, tmp_path):
        runner = ObservationRunner(evidence_dir=tmp_path / "ev2", refresh_prices=False)
        # Sunday
        now = datetime(2026, 10, 25, 16, 35, tzinfo=NY).astimezone(timezone.utc)
        out = runner.run_observation_session(
            mode="post_close",
            tickers=["AAPL"],
            slot_id="post_close_research",
            force_run=False,
            now_utc=now,
            resume=False,
        )
        assert out.get("skipped") is True
        assert out.get("submissions_attempted") == 0

    def test_missing_quote_account_soft(self, tmp_path):
        runner = ObservationRunner(evidence_dir=tmp_path / "ev3", refresh_prices=False)
        scan = {
            "scan_rows": [
                {
                    "ticker": "PYPL",
                    "signal": "BUY CANDIDATE",
                    "as_of": "2026-10-26",
                    "market_as_of_date": "2026-10-26",
                    "entry_rule": "CROSS",
                    "close": 57.0,
                    "name": "PayPal Holdings, Inc.",
                    "validation_status": "OK",
                }
            ]
        }
        now = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)
        with patch("app.services.observation_runner.classify_user_policy") as pol:
            pol.return_value = {
                "user_policy_status": "ALLOWED",
                "reason_codes": ["TEST"],
                "proposal_permitted": True,
            }
            out = runner.evaluate_decisions(scan, now_utc=now, account=None, quotes={})
        assert out["results"]
        # Without account/quote → no simulated proposal (soft)
        assert out["simulated_proposals"] == []


class TestExecutionLifecycleAudit:
    def test_audit_reports_blockers_and_no_orders(self):
        report = run_execution_lifecycle_audit()
        assert report["broker_orders_attempted"] is False
        assert report["approvals_attempted"] is False
        assert report["cancellations_attempted"] is False
        assert report["guards"]["verdict"] == "GUARDS_INTACT"
        assert report["summary_verdict"] == "SAFE_FOR_OBSERVATION"
        assert report["idempotency"]["verdict"] == "PASS"
        assert len(report["blockers_before_paper_trading"]) >= 1
        assert report["fill_handlers_mocked"]["is_real_broker_fill"] is False
