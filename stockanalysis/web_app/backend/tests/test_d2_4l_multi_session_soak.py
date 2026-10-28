"""Stage D2.4L — multi-session soak preparation: pairing, freshness, safety, ledger."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from app.config import (
    ALPACA_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.multi_session_soak import (
    SOAK_TARGET_SESSIONS,
    MultiSessionSoak,
    load_soak_ledger,
    save_soak_ledger,
    soak_status,
)
from app.services.observation_freshness import assess_scan_freshness
from app.services.observation_safety import assert_observation_safety, require_observation_safety
from app.services.observation_schedule import (
    pair_post_close_to_next_session,
    plan_soak_pairs,
)
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED


class TestSafety:
    def test_guards_intact(self):
        r = assert_observation_safety(phase="test")
        assert r["passed"] is True
        assert IBKR_EMERGENCY_STOP is True
        assert TRADING_EXECUTION_ENABLED is False
        assert ALPACA_EXECUTION_ENABLED is False
        assert STAGE_APPROVAL_ENABLED is False
        assert STAGE_SUBMISSION_ENABLED is False

    def test_require_safety_raises_on_submission_count(self):
        try:
            require_observation_safety(phase="bad", submissions_attempted=1)
            assert False, "expected AssertionError"
        except AssertionError as exc:
            assert "submissions_attempted" in str(exc)


class TestSchedulePairing:
    def test_weekday_pair(self):
        # Monday 2026-10-26 → next session Tuesday 2026-10-27
        pair = pair_post_close_to_next_session(date(2026, 10, 26))
        assert pair["valid_pair"] is True
        assert pair["post_close_day"] == "2026-10-26"
        assert pair["next_session_day"] == "2026-10-27"
        assert "16:30" in pair["post_close_et"] or "T16:30" in pair["post_close_et"]
        assert "09:45" in pair["next_session_et"] or "T09:45" in pair["next_session_et"]
        assert pair["activation"]["windows_task_enabled"] is False

    def test_friday_pairs_to_monday(self):
        pair = pair_post_close_to_next_session(date(2026, 10, 23))
        assert pair["next_session_day"] == "2026-10-26"
        assert pair["gap_calendar_days"] == 3

    def test_thanksgiving_eve_skips_holiday(self):
        # Wed 2026-11-25 post-close → next session Fri 2026-11-27 (Thu Thanksgiving)
        pair = pair_post_close_to_next_session(date(2026, 11, 25))
        assert pair["valid_pair"] is True
        assert pair["next_session_day"] == "2026-11-27"

    def test_weekend_post_close_invalid(self):
        pair = pair_post_close_to_next_session(date(2026, 10, 24))
        assert pair["valid_pair"] is False

    def test_plan_three_pairs_chained(self):
        plan = plan_soak_pairs(from_day=date(2026, 10, 26), pairs=3)
        assert len(plan["pairs"]) == 3
        assert plan["activation"]["unattended_enabled"] is False
        # First pair next day becomes second pair post-close day
        assert plan["pairs"][0]["next_session_day"] == plan["pairs"][1]["post_close_day"]


class TestFreshness:
    def test_data_pending_when_as_of_behind(self):
        rows = [
            {
                "ticker": "AAPL",
                "market_as_of_date": "2026-10-20",
                "data_freshness": "STALE",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "strategy_version": "V4.0 Baseline (via V4.1 Engine in exit_mode=baseline)",
                "scan_completed_at": "2026-10-26T21:00:00Z",
                "signal": "BUY CANDIDATE",
            }
        ]
        report = assess_scan_freshness(
            rows,
            now_utc=datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc),
            expected_session=date(2026, 10, 26),
        )
        assert report["status"] == "DATA_PENDING"
        assert report["fabricated_freshness"] is False

    def test_fresh_when_as_of_matches(self):
        rows = [
            {
                "ticker": "AAPL",
                "market_as_of_date": "2026-10-26",
                "data_freshness": "FRESH",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "strategy_version": "V4.0 Baseline (via V4.1 Engine in exit_mode=baseline)",
                "scan_completed_at": "2026-10-26T21:00:00Z",
                "signal": "BUY CANDIDATE",
            }
        ]
        report = assess_scan_freshness(
            rows,
            expected_session=date(2026, 10, 26),
        )
        assert report["status"] == "FRESH"

    def test_frozen_baseline_fails_provenance(self):
        rows = [
            {
                "ticker": "AAPL",
                "market_as_of_date": "2026-10-26",
                "provenance_mode": "FROZEN_BASELINE",
                "signal_source": "V40_SCANNER",
                "signal": "BUY CANDIDATE",
            }
        ]
        report = assess_scan_freshness(rows, expected_session=date(2026, 10, 26))
        assert report["status"] == "PROVENANCE_FAIL"


class TestSoakLedger:
    def test_incomplete_until_three_pairs(self, tmp_path, monkeypatch):
        import app.services.multi_session_soak as mss

        monkeypatch.setattr(mss, "LEDGER_PATH", tmp_path / "soak_ledger.json")
        monkeypatch.setattr(mss, "OBSERVATION_ROOT", tmp_path)
        save_soak_ledger(
            {
                "version": "D2.4L",
                "target_completed_pairs": 3,
                "sessions": [],
                "soak_complete": False,
                "unattended_activated": False,
            }
        )
        st = soak_status()
        assert st["soak_complete"] is False
        assert st["recommendation"] == "NO_GO_SOAK_INCOMPLETE"
        assert st["observed_completed_pairs"] == 0
        assert SOAK_TARGET_SESSIONS == 3

        # Post-close alone does not complete a pair
        led = load_soak_ledger()
        led["sessions"] = [
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "run_id": "a",
            }
        ]
        save_soak_ledger(led)
        assert soak_status()["observed_completed_pairs"] == 0

        # Both eligible legs → 1 completed pair
        led["sessions"].append(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": True,
                "run_id": "b",
            }
        )
        save_soak_ledger(led)
        st2 = soak_status()
        assert st2["observed_completed_pairs"] == 1
        assert st2["soak_complete"] is False

    def test_repeat_same_pair_does_not_double_count(self, tmp_path, monkeypatch):
        import app.services.multi_session_soak as mss

        monkeypatch.setattr(mss, "LEDGER_PATH", tmp_path / "soak_ledger.json")
        soak = MultiSessionSoak()
        # Record twice with same pair_id+mode — second replaces first
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "session_key": "2026-10-26|post_close",
                "run_id": "a1",
            }
        )
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "session_key": "2026-10-26|post_close",
                "run_id": "a2",
            }
        )
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": True,
                "session_key": "2026-10-27|next_session",
                "run_id": "b1",
            }
        )
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": True,
                "session_key": "2026-10-27|next_session",
                "run_id": "b2",
            }
        )
        st = soak_status()
        assert st["observed_completed_pairs"] == 1
        assert len(load_soak_ledger()["sessions"]) == 2  # one leg each

    def test_preflight_does_not_activate(self):
        soak = MultiSessionSoak()
        pre = soak.preflight(now_utc=datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc))
        assert pre["passed"] is True
        assert pre["unattended_schedules_activated"] is False
        assert pre["full_universe_count"] >= 28
        assert (pre.get("schedule_activation") or {}).get("windows_task_enabled") is False
