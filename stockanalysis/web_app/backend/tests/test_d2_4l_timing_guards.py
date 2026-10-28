"""D2.4L fail-closed observation timing guards (injected clock)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.multi_session_soak import (
    MultiSessionSoak,
    NEXT_SESSION_SLOT_ID,
    POST_CLOSE_SLOT_ID,
    build_timing_audit,
    load_soak_ledger,
    soak_status,
)

NY = ZoneInfo("America/New_York")


def _utc(et: datetime) -> datetime:
    """ET wall clock → aware UTC."""
    if et.tzinfo is None:
        et = et.replace(tzinfo=NY)
    return et.astimezone(ZoneInfo("UTC"))


def _prior_bundle(path: Path, *, next_day: str = "2026-10-27") -> Path:
    payload = {
        "trading_day": "2026-10-26",
        "pair": {
            "valid_pair": True,
            "post_close_day": "2026-10-26",
            "next_session_day": next_day,
            "next_session_et": f"{next_day}T09:45:00-04:00",
            "post_close_et": "2026-10-26T16:30:00-04:00",
        },
        "freshness": {"status": "FRESH", "reason_code": "SESSION_AS_OF_MATCH"},
        "signals": [
            {
                "ticker": "AAPL",
                "signal": "BUY CANDIDATE",
                "market_as_of_date": "2026-10-26",
                "as_of": "2026-10-26",
                "close": 100.0,
                "signal_source": "V40_SCANNER",
                "provenance_mode": "LIVE_SCAN",
            }
        ],
        "buy_candidates": [{"ticker": "AAPL", "policy": "ALLOWED"}],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def soak_env(tmp_path, monkeypatch):
    import app.services.multi_session_soak as mss

    monkeypatch.setattr(mss, "LEDGER_PATH", tmp_path / "soak_ledger.json")
    monkeypatch.setattr(mss, "SESSIONS_DIR", tmp_path / "sessions")
    mss.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    soak = MultiSessionSoak(evidence_root=evidence)
    return soak, tmp_path


class TestBuildTimingAudit:
    def test_wrong_session_day(self):
        # 2026-10-26 20:08 ET — evening after post-close, not next session day
        now = _utc(datetime(2026, 10, 26, 20, 8, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["timing_ok"] is False
        assert audit["eligibility_reason_code"] == "WRONG_SESSION_DAY"
        assert audit["actual_ny_date"] == "2026-10-26"
        assert audit["day_match"] is False

    def test_correct_day_0800_outside_window(self):
        now = _utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["day_match"] is True
        assert audit["timing_ok"] is False
        assert audit["eligibility_reason_code"] == "OUTSIDE_WINDOW"

    def test_correct_day_0950_inside_window(self):
        now = _utc(datetime(2026, 10, 27, 9, 50, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["timing_ok"] is True
        assert audit["eligibility_reason_code"] == "OK"
        assert audit["slot_check_passed"] is True

    def test_boundary_start_0945_inclusive(self):
        now = _utc(datetime(2026, 10, 27, 9, 45, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["timing_ok"] is True

    def test_boundary_end_1030_inclusive(self):
        # 09:45 + 45m = 10:30
        now = _utc(datetime(2026, 10, 27, 10, 30, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["timing_ok"] is True

    def test_boundary_just_after_window(self):
        now = _utc(datetime(2026, 10, 27, 10, 31, tzinfo=NY))
        audit = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day="2026-10-27",
        )
        assert audit["timing_ok"] is False
        assert audit["eligibility_reason_code"] == "OUTSIDE_WINDOW"

    def test_post_close_1630_in_window(self):
        now = _utc(datetime(2026, 10, 26, 16, 35, tzinfo=NY))
        audit = build_timing_audit(
            mode="post_close",
            now_utc=now,
            slot_id=POST_CLOSE_SLOT_ID,
            expected_session_day="2026-10-26",
        )
        assert audit["timing_ok"] is True

    def test_post_close_2000_outside(self):
        now = _utc(datetime(2026, 10, 26, 20, 0, tzinfo=NY))
        audit = build_timing_audit(
            mode="post_close",
            now_utc=now,
            slot_id=POST_CLOSE_SLOT_ID,
            expected_session_day="2026-10-26",
        )
        assert audit["timing_ok"] is False
        assert audit["eligibility_reason_code"] == "OUTSIDE_WINDOW"


class TestNextSessionGate:
    def test_early_attempt_zero_proposals_zero_credit(self, soak_env):
        soak, tmp = soak_env
        prior = _prior_bundle(tmp / "prior.json")
        # Seed eligible post-close pending
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "session_key": "2026-10-26|post_close",
                "run_id": "pc1",
            }
        )
        now = _utc(datetime(2026, 10, 26, 20, 8, tzinfo=NY))
        result = soak.run_next_session_validation(
            prior_bundle_path=prior, now_utc=now, force_run=False
        )
        assert result["eligibility_reason_code"] == "WRONG_SESSION_DAY"
        assert result["gated_before_proposals"] is True
        assert result["simulated_proposals"] == []
        assert result["eligible"] is False
        assert result["counts_toward_pair"] is False
        st = soak_status()
        assert st["observed_completed_pairs"] == 0
        assert "2026-10-26->2026-10-27" in st["pending_post_close_pair_ids"]

    def test_0800_outside_window_gates(self, soak_env):
        soak, tmp = soak_env
        prior = _prior_bundle(tmp / "prior.json")
        now = _utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY))
        result = soak.run_next_session_validation(prior_bundle_path=prior, now_utc=now)
        assert result["eligibility_reason_code"] == "OUTSIDE_WINDOW"
        assert result["simulated_proposals"] == []
        assert result["gated_before_proposals"] is True

    def test_force_diagnostic_still_gates_next_session(self, soak_env):
        soak, tmp = soak_env
        prior = _prior_bundle(tmp / "prior.json")
        now = _utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY))
        result = soak.run_next_session_validation(
            prior_bundle_path=prior, now_utc=now, force_run=True
        )
        assert result["eligibility_reason_code"] == "OUTSIDE_WINDOW"
        assert result["simulated_proposals"] == []
        assert result["eligible"] is False


class TestLedgerProtection:
    def test_ineligible_cannot_replace_eligible(self, soak_env):
        soak, _ = soak_env
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": True,
                "session_key": "2026-10-27|next_session",
                "run_id": "good",
                "counts_toward_pair": True,
            }
        )
        status = soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": False,
                "session_key": "2026-10-27|next_session",
                "run_id": "bad",
                "eligibility_reason_code": "OUTSIDE_WINDOW",
            }
        )
        assert status["ledger_write"] == "PRESERVED_ELIGIBLE_LEG"
        led = load_soak_ledger()
        ns = [s for s in led["sessions"] if s["mode"] == "next_session"]
        assert len(ns) == 1
        assert ns[0]["run_id"] == "good"
        assert ns[0]["eligible"] is True

    def test_later_eligible_replaces_ineligible(self, soak_env):
        soak, tmp = soak_env
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "session_key": "2026-10-26|post_close",
                "run_id": "pc1",
            }
        )
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": False,
                "session_key": "2026-10-26|next_session",
                "run_id": "early_bad",
                "eligibility_reason_code": "WRONG_SESSION_DAY",
            }
        )
        assert soak_status()["observed_completed_pairs"] == 0
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "next_session",
                "eligible": True,
                "session_key": "2026-10-27|next_session",
                "run_id": "later_good",
                "counts_toward_pair": True,
            }
        )
        st = soak_status()
        assert st["observed_completed_pairs"] == 1
        assert "2026-10-26->2026-10-27" in st["completed_pair_ids"]
        led = load_soak_ledger()
        ns = [s for s in led["sessions"] if s["mode"] == "next_session"]
        assert len(ns) == 1
        assert ns[0]["run_id"] == "later_good"


class TestPostCloseGate:
    def test_post_close_outside_window_gated(self, soak_env):
        soak, _ = soak_env
        now = _utc(datetime(2026, 10, 26, 20, 0, tzinfo=NY))
        result = soak.run_post_close_session(
            now_utc=now, force_run=False, refresh_prices=False, count_toward_soak=True
        )
        assert result["eligibility_reason_code"] == "OUTSIDE_WINDOW"
        assert result["gated_before_proposals"] is True
        assert result["simulated_proposals"] == []
        assert result["eligible"] is False
        assert result["counts_toward_pair"] is False

    def test_force_run_diagnostic_never_earns_soak(self, soak_env, monkeypatch):
        soak, _ = soak_env

        class FakeRunner:
            def __init__(self, *a, **k):
                self.submissions_attempted = 0
                self.run_id = None
                self.evidence_dir = None
                self.journal = type("J", (), {"journal_dir": None})()

            def resolve_universe(self, *a, **k):
                return ["AAPL"]

            def scan_universe(self, *a, **k):
                return {
                    "tickers_requested": ["AAPL"],
                    "tickers_scanned": ["AAPL"],
                    "scan_rows": [
                        {
                            "ticker": "AAPL",
                            "signal": "WATCH",
                            "market_as_of_date": "2026-10-26",
                            "as_of": "2026-10-26",
                            "data_freshness": "FRESH",
                            "provenance_mode": "LIVE_SCAN",
                            "signal_source": "V40_SCANNER",
                        }
                    ],
                    "signal_distribution": {"WATCH": 1},
                    "data_quality_failures": [],
                    "scanner_runtime_seconds": 0.01,
                    "partial_universe": False,
                }

            def evaluate_decisions(self, *a, **k):
                return {
                    "policy_eligibility_breakdown": {},
                    "results": [],
                    "buy_candidates": [],
                    "simulated_proposals": [{"ticker": "AAPL"}],
                    "rejected_or_deferred": [],
                    "performance": [],
                    "portfolio_exposure": None,
                }

            def _signal_from_scan(self, row):
                return row

        monkeypatch.setattr(
            "app.services.multi_session_soak.ObservationRunner", FakeRunner
        )
        monkeypatch.setattr(
            "app.services.multi_session_soak.try_load_readonly_client",
            lambda: (None, {"ok": False}),
        )
        monkeypatch.setattr(
            "app.services.multi_session_soak.assess_scan_freshness",
            lambda *a, **k: {"status": "FRESH", "reason_code": "SESSION_AS_OF_MATCH"},
        )
        now = _utc(datetime(2026, 10, 26, 20, 0, tzinfo=NY))
        result = soak.run_post_close_session(
            now_utc=now,
            force_run=True,
            refresh_prices=False,
            count_toward_soak=True,
            tickers=None,
        )
        assert result["diagnostic_force_run"] is True
        assert result["eligible"] is False
        assert result["eligibility_reason_code"] == "DIAGNOSTIC_FORCE_RUN_INELIGIBLE"
        assert result["counts_toward_pair"] is False
        # Diagnostic may produce proposals but must not complete soak credit
        st = soak_status()
        assert st["observed_completed_pairs"] == 0
        pc = [s for s in load_soak_ledger()["sessions"] if s["mode"] == "post_close"]
        assert pc and pc[0]["eligible"] is False


class TestEligibleNextSessionPath:
    def test_in_window_runs_and_can_complete_pair(self, soak_env, monkeypatch):
        soak, tmp = soak_env
        prior = _prior_bundle(tmp / "prior.json")
        soak._record_ledger_entry(
            {
                "pair_id": "2026-10-26->2026-10-27",
                "mode": "post_close",
                "eligible": True,
                "freshness_status": "FRESH",
                "session_key": "2026-10-26|post_close",
                "run_id": "pc1",
            }
        )

        class FakeRunner:
            def __init__(self, *a, **k):
                self.submissions_attempted = 0
                self.run_id = None
                self.evidence_dir = None
                self.journal = type("J", (), {"journal_dir": None})()

            def evaluate_decisions(self, *a, **k):
                return {
                    "policy_eligibility_breakdown": {"ALLOWED": 1},
                    "results": [],
                    "buy_candidates": [{"ticker": "AAPL", "policy": "ALLOWED"}],
                    "simulated_proposals": [{"ticker": "AAPL", "simulated_proposal": {}}],
                    "rejected_or_deferred": [],
                    "performance": [],
                    "portfolio_exposure": None,
                }

            def _signal_from_scan(self, row):
                return row

        monkeypatch.setattr(
            "app.services.multi_session_soak.ObservationRunner", FakeRunner
        )
        monkeypatch.setattr(
            "app.services.multi_session_soak.try_load_readonly_client",
            lambda: (None, {"ok": False}),
        )
        monkeypatch.setattr(
            "app.services.multi_session_soak.attach_performance_to_proposals",
            lambda rows: [],
        )
        now = _utc(datetime(2026, 10, 27, 9, 50, tzinfo=NY))
        result = soak.run_next_session_validation(prior_bundle_path=prior, now_utc=now)
        assert result["eligibility_reason_code"] == "OK"
        assert result["eligible"] is True
        assert result["counts_toward_pair"] is True
        assert result.get("gated_before_proposals") in (None, False)
        assert len(result["simulated_proposals"]) == 1
        st = soak_status()
        assert st["observed_completed_pairs"] == 1
        assert st["pending_post_close_pair_ids"] == []
