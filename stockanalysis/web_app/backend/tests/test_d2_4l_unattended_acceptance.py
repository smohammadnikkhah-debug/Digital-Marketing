"""Final acceptance checks for unattended scheduler (no task activation)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.multi_session_soak import DEFAULT_SLOT_WINDOW_MINUTES, build_timing_audit
from app.services.observation_schedule import should_run_slot
from app.services.unattended_observation import (
    MAX_ATTEMPTS_PER_SLOT_SESSION,
    generate_task_scheduler_artifacts,
    morning_status,
    record_slot_attempt,
    should_skip_slot_attempt,
    windows_tasks_activated,
)

NY = ZoneInfo("America/New_York")


def _utc(et: datetime) -> datetime:
    if et.tzinfo is None:
        et = et.replace(tzinfo=NY)
    return et.astimezone(ZoneInfo("UTC"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.services.unattended_observation as uo
    import app.services.multi_session_soak as mss
    import app.services.observation_schedule as osc

    monkeypatch.setattr(uo, "UNATTENDED_ROOT", tmp_path / "unattended")
    monkeypatch.setattr(uo, "LOCK_PATH", tmp_path / "unattended" / "unattended.lock")
    monkeypatch.setattr(uo, "RUN_LOG_DIR", tmp_path / "unattended" / "logs")
    monkeypatch.setattr(uo, "STATE_PATH", tmp_path / "unattended" / "unattended_state.json")
    monkeypatch.setattr(uo, "TASK_ARTIFACTS_DIR", tmp_path / "unattended" / "tasks")
    monkeypatch.setattr(
        uo, "ACTIVATION_FLAG_PATH", tmp_path / "unattended" / "ACTIVATION_APPROVED.flag"
    )
    monkeypatch.setattr(mss, "LEDGER_PATH", tmp_path / "soak_ledger.json")
    monkeypatch.setattr(mss, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(osc, "SCHEDULE_PATH", tmp_path / "schedule_config.json")
    mss.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    uo.ensure_unattended_dirs()
    return tmp_path


class TestOncePerSessionAndRetry:
    def test_eligible_blocks_further_polls(self, env):
        import app.services.multi_session_soak as mss

        mss.save_soak_ledger(
            {
                "sessions": [
                    {
                        "pair_id": "2026-10-26->2026-10-27",
                        "mode": "post_close",
                        "eligible": True,
                        "trading_day": "2026-10-26",
                        "freshness_status": "FRESH",
                        "run_id": "pc1",
                    }
                ]
            }
        )
        d = should_skip_slot_attempt(
            slot_id="post_close_research",
            ny_date="2026-10-26",
            mode="post_close",
        )
        assert d["skip"] is True
        assert d["reason_code"] == "LEDGER_ELIGIBLE_EXISTS"

    def test_failed_allows_one_retry_then_exhausts(self, env):
        record_slot_attempt(
            slot_id="post_close_research",
            ny_date="2026-10-26",
            run_id="a1",
            eligible=False,
            timing_ok=True,
            outcome="STALE_MIXED",
        )
        d1 = should_skip_slot_attempt(
            slot_id="post_close_research",
            ny_date="2026-10-26",
            mode="post_close",
        )
        assert d1["skip"] is False
        assert d1["reason_code"] == "RETRY_ALLOWED"

        record_slot_attempt(
            slot_id="post_close_research",
            ny_date="2026-10-26",
            run_id="a2",
            eligible=False,
            timing_ok=True,
            outcome="STALE_MIXED",
        )
        d2 = should_skip_slot_attempt(
            slot_id="post_close_research",
            ny_date="2026-10-26",
            mode="post_close",
        )
        assert d2["skip"] is True
        assert d2["reason_code"] == "MAX_ATTEMPTS_EXHAUSTED"
        assert MAX_ATTEMPTS_PER_SLOT_SESSION == 2

    def test_state_survives_reload(self, env):
        record_slot_attempt(
            slot_id="next_session_validate",
            ny_date="2026-10-27",
            run_id="ns1",
            eligible=True,
            timing_ok=True,
            outcome="ELIGIBLE",
            pair_id="2026-10-26->2026-10-27",
        )
        # New process simulation: reload state from disk
        from app.services.unattended_observation import load_state

        st = load_state()
        key = "next_session_validate|2026-10-27"
        assert st["slot_attempts"][key]["eligible"] is True
        assert st["slot_attempts"][key]["terminal"] is True


class TestWindowsAndHolidays:
    def test_windows_match_soak_gates(self):
        assert DEFAULT_SLOT_WINDOW_MINUTES == 45
        # 16:30 + 45 = 17:15; 09:45 + 45 = 10:30
        pc = build_timing_audit(
            mode="post_close",
            now_utc=_utc(datetime(2026, 10, 26, 17, 15, tzinfo=NY)),
            slot_id="post_close_research",
            expected_session_day="2026-10-26",
        )
        assert pc["timing_ok"] is True
        pc_out = build_timing_audit(
            mode="post_close",
            now_utc=_utc(datetime(2026, 10, 26, 17, 16, tzinfo=NY)),
            slot_id="post_close_research",
            expected_session_day="2026-10-26",
        )
        assert pc_out["timing_ok"] is False

        ns = build_timing_audit(
            mode="next_session",
            now_utc=_utc(datetime(2026, 10, 27, 10, 30, tzinfo=NY)),
            slot_id="next_session_validate",
            expected_session_day="2026-10-27",
        )
        assert ns["timing_ok"] is True

    def test_weekend_and_thanksgiving_blocked(self):
        # Saturday
        sat = should_run_slot(
            "post_close_research",
            now_utc=_utc(datetime(2026, 10, 24, 16, 35, tzinfo=NY)),
        )
        assert sat["should_run"] is False
        assert sat["reason_code"] == "MARKET_CLOSED"
        # Thanksgiving 2026-11-26
        thx = should_run_slot(
            "post_close_research",
            now_utc=_utc(datetime(2026, 11, 26, 16, 35, tzinfo=NY)),
        )
        assert thx["should_run"] is False
        assert thx["reason_code"] == "MARKET_CLOSED"


class TestArtifactsEnvAndNoActivation:
    def test_wrapper_sets_pythonpath_and_tasks_disabled(self, env):
        out = generate_task_scheduler_artifacts(backend_dir=Path(".").resolve())
        assert out["windows_tasks_registered"] is False
        wrap = Path(out["poll_xml"]).with_name("run_poll.cmd")
        assert wrap.exists()
        text = wrap.read_text(encoding="utf-8")
        assert "PYTHONPATH=" in text
        assert "poll" in text
        xml = Path(out["poll_xml"]).read_text(encoding="utf-16")
        assert "StartWhenAvailable>false" in xml.replace(" ", "")
        assert "Enabled>false" in xml
        assert "run_poll.cmd" in xml
        assert windows_tasks_activated() is False


class TestMorningStatusCategories:
    def test_status_buckets(self, env):
        import app.services.multi_session_soak as mss
        import app.services.unattended_observation as uo

        mss.save_soak_ledger(
            {
                "sessions": [
                    {
                        "pair_id": "2026-10-26->2026-10-27",
                        "mode": "post_close",
                        "eligible": True,
                        "trading_day": "2026-10-26",
                        "freshness_status": "FRESH",
                        "run_id": "ok1",
                        "bundle_path": str(env / "pc.json"),
                    }
                ]
            }
        )
        uo._write_run_log(
            {
                "mode": "next_session",
                "status": "SKIPPED_OUTSIDE_WINDOW",
                "eligibility_reason_code": "OUTSIDE_WINDOW",
            }
        )
        uo._write_run_log(
            {
                "mode": "post_close",
                "status": "ABORTED_SAFETY",
                "eligibility_reason_code": "SAFETY_FAIL",
            }
        )
        st = morning_status(now_utc=_utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY)))
        cats = st["session_categories"]
        assert cats["counts"]["completed"] >= 1
        assert cats["counts"]["skipped"] >= 1
        assert cats["counts"]["failed"] >= 1
        assert cats["counts"]["pending"] >= 1
        assert st["execution_flags_mutable_by_scheduler"] is False
        assert st["intentional_windows_et"]["aligned_with_soak_gates"] is True
        assert st["safety"]["trading_execution_enabled"] is False
        assert st["safety"]["ibkr_emergency_stop"] is True
