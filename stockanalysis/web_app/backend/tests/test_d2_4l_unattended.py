"""D2.4L unattended observation helpers — no Windows task registration."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.services.multi_session_soak import soak_status
from app.services.unattended_observation import (
    ACTIVATION_FLAG_PATH,
    OverlapLock,
    already_completed_in_window,
    generate_task_scheduler_artifacts,
    load_state,
    morning_status,
    resolve_prior_post_close_bundle,
    run_unattended_next_session,
    run_unattended_poll,
    run_unattended_post_close,
    save_state,
    windows_tasks_activated,
)

NY = ZoneInfo("America/New_York")


def _utc(et: datetime) -> datetime:
    if et.tzinfo is None:
        et = et.replace(tzinfo=NY)
    return et.astimezone(ZoneInfo("UTC"))


@pytest.fixture
def unattended_env(tmp_path, monkeypatch):
    import app.services.unattended_observation as uo
    import app.services.multi_session_soak as mss

    monkeypatch.setattr(uo, "UNATTENDED_ROOT", tmp_path / "unattended")
    monkeypatch.setattr(uo, "LOCK_PATH", tmp_path / "unattended" / "unattended.lock")
    monkeypatch.setattr(uo, "RUN_LOG_DIR", tmp_path / "unattended" / "logs")
    monkeypatch.setattr(uo, "STATE_PATH", tmp_path / "unattended" / "unattended_state.json")
    monkeypatch.setattr(uo, "TASK_ARTIFACTS_DIR", tmp_path / "unattended" / "tasks")
    monkeypatch.setattr(uo, "ACTIVATION_FLAG_PATH", tmp_path / "unattended" / "ACTIVATION_APPROVED.flag")
    monkeypatch.setattr(mss, "LEDGER_PATH", tmp_path / "soak_ledger.json")
    monkeypatch.setattr(mss, "SESSIONS_DIR", tmp_path / "sessions")
    mss.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    uo.ensure_unattended_dirs()
    return tmp_path


class TestPriorBundleResolution:
    def test_resolves_pending_eligible_post_close(self, unattended_env, monkeypatch):
        import app.services.multi_session_soak as mss

        bundle = unattended_env / "sessions" / "pc.json"
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(
            json.dumps(
                {
                    "trading_day": "2026-10-26",
                    "pair": {
                        "post_close_day": "2026-10-26",
                        "next_session_day": "2026-10-27",
                    },
                    "freshness": {"status": "FRESH"},
                    "signals": [{"ticker": "AAPL"}],
                }
            ),
            encoding="utf-8",
        )
        mss.save_soak_ledger(
            {
                "sessions": [
                    {
                        "pair_id": "2026-10-26->2026-10-27",
                        "mode": "post_close",
                        "eligible": True,
                        "freshness_status": "FRESH",
                        "bundle_path": str(bundle),
                        "run_id": "pc1",
                        "trading_day": "2026-10-26",
                        "recorded_at_utc": "2026-10-27T00:07:00+00:00",
                    }
                ],
                "unattended_activated": False,
            }
        )
        out = resolve_prior_post_close_bundle()
        assert out["found"] is True
        assert out["pair_id"] == "2026-10-26->2026-10-27"
        assert Path(out["bundle_path"]).exists()

    def test_no_pending(self, unattended_env):
        import app.services.multi_session_soak as mss

        mss.save_soak_ledger({"sessions": [], "unattended_activated": False})
        out = resolve_prior_post_close_bundle()
        assert out["found"] is False
        assert out["reason_code"] == "NO_PENDING_POST_CLOSE"


class TestOverlapAndSkip:
    def test_overlap_lock(self, unattended_env):
        a = OverlapLock()
        b = OverlapLock()
        assert a.acquire(mode="post_close")["acquired"] is True
        assert b.acquire(mode="next_session")["acquired"] is False
        a.release()
        assert b.acquire(mode="next_session")["acquired"] is True
        b.release()

    def test_poll_outside_window_idle(self, unattended_env):
        now = _utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY))
        out = run_unattended_poll(now_utc=now)
        assert out["status"] == "IDLE"
        assert out["eligibility_reason_code"] == "NO_SLOT_IN_WINDOW"
        assert out["broker_orders"] is False

    def test_post_close_outside_skips_no_credit(self, unattended_env):
        now = _utc(datetime(2026, 10, 26, 20, 0, tzinfo=NY))
        out = run_unattended_post_close(now_utc=now)
        assert out["status"] == "SKIPPED_OUTSIDE_WINDOW"
        assert soak_status()["observed_completed_pairs"] == 0

    def test_next_session_wrong_day_skips(self, unattended_env):
        import app.services.multi_session_soak as mss

        bundle = unattended_env / "pc.json"
        bundle.write_text(
            json.dumps(
                {
                    "trading_day": "2026-10-26",
                    "pair": {
                        "post_close_day": "2026-10-26",
                        "next_session_day": "2026-10-27",
                    },
                    "freshness": {"status": "FRESH"},
                    "signals": [{"ticker": "AAPL", "signal": "WATCH"}],
                }
            ),
            encoding="utf-8",
        )
        mss.save_soak_ledger(
            {
                "sessions": [
                    {
                        "pair_id": "2026-10-26->2026-10-27",
                        "mode": "post_close",
                        "eligible": True,
                        "freshness_status": "FRESH",
                        "bundle_path": str(bundle),
                        "run_id": "pc1",
                        "trading_day": "2026-10-26",
                        "recorded_at_utc": "2026-10-27T00:07:00+00:00",
                    }
                ]
            }
        )
        now = _utc(datetime(2026, 10, 26, 20, 10, tzinfo=NY))
        out = run_unattended_next_session(now_utc=now)
        assert out["status"] == "SKIPPED_WRONG_SESSION_DAY"
        assert out["eligibility_reason_code"] == "WRONG_SESSION_DAY"
        assert soak_status()["observed_completed_pairs"] == 0


class TestArtifactsAndActivation:
    def test_prepare_artifacts_does_not_activate(self, unattended_env, monkeypatch):
        import app.services.observation_schedule as osc

        monkeypatch.setattr(osc, "SCHEDULE_PATH", unattended_env / "schedule_config.json")
        out = generate_task_scheduler_artifacts(backend_dir=Path(".").resolve())
        assert out["windows_tasks_registered"] is False
        assert out["windows_tasks_enabled"] is False
        assert Path(out["poll_xml"]).exists()
        assert Path(out["readme"]).exists()
        assert windows_tasks_activated() is False
        cfg = json.loads((unattended_env / "schedule_config.json").read_text(encoding="utf-8"))
        assert cfg["activation"]["windows_task_enabled"] is False
        assert cfg["activation"]["unattended_enabled"] is False

    def test_morning_status_includes_safety(self, unattended_env):
        st = morning_status(now_utc=_utc(datetime(2026, 10, 27, 8, 0, tzinfo=NY)))
        assert st["broker_orders"] is False
        assert st["safety"]["ibkr_emergency_stop"] is True
        assert st["safety"]["trading_execution_enabled"] is False
        assert st["windows_tasks_activated"] is False


class TestDuplicateGuard:
    def test_already_completed_in_window(self, unattended_env):
        state = load_state()
        state["slot_attempts"] = {
            "post_close_research|2026-10-26": {
                "run_id": "x",
                "timing_ok": True,
                "eligible": True,
            }
        }
        save_state(state)
        prev = already_completed_in_window(
            slot_id="post_close_research", ny_date="2026-10-26"
        )
        assert prev is not None
        assert prev["run_id"] == "x"
