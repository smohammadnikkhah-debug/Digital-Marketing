"""One-shot activation preflight (local)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import (
    ALPACA_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.multi_session_soak import (
    DEFAULT_SLOT_WINDOW_MINUTES,
    NEXT_SESSION_SLOT_ID,
    POST_CLOSE_SLOT_ID,
    build_timing_audit,
)
from app.services.observation_safety import assert_observation_safety
from app.services.observation_schedule import DEFAULT_SLOTS, ensure_schedule_config
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED
from app.services.unattended_observation import POLLER_INTERVAL_MINUTES, safety_snapshot

NY = ZoneInfo("America/New_York")


def main() -> int:
    safety = assert_observation_safety(phase="activation_preflight")
    snap = safety_snapshot()
    cfg = ensure_schedule_config()
    slots = {s["id"]: s for s in (cfg.get("slots") or DEFAULT_SLOTS)}
    pc = slots.get("post_close_research") or {}
    ns = slots.get("next_session_validate") or {}

    assert pc.get("et_hour") == 16 and pc.get("et_minute") == 30
    assert ns.get("et_hour") == 9 and ns.get("et_minute") == 45
    assert DEFAULT_SLOT_WINDOW_MINUTES == 45
    assert POLLER_INTERVAL_MINUTES == 5

    ok_pc = build_timing_audit(
        mode="post_close",
        now_utc=datetime(2026, 10, 26, 16, 30, tzinfo=NY).astimezone(timezone.utc),
        slot_id=POST_CLOSE_SLOT_ID,
        expected_session_day="2026-10-26",
    )
    ok_ns = build_timing_audit(
        mode="next_session",
        now_utc=datetime(2026, 10, 27, 9, 45, tzinfo=NY).astimezone(timezone.utc),
        slot_id=NEXT_SESSION_SLOT_ID,
        expected_session_day="2026-10-27",
    )

    flags_ok = (
        IBKR_EMERGENCY_STOP is True
        and TRADING_EXECUTION_ENABLED is False
        and ALPACA_EXECUTION_ENABLED is False
        and STAGE_APPROVAL_ENABLED is False
        and STAGE_SUBMISSION_ENABLED is False
        and safety.get("passed") is True
        and snap.get("passed") is True
        and (cfg.get("activation") or {}).get("digitalocean_cron_enabled") is False
    )

    payload = {
        "preflight_passed": flags_ok,
        "safety_passed": bool(safety.get("passed")),
        "flags": {
            "ibkr_emergency_stop": IBKR_EMERGENCY_STOP,
            "trading_execution_enabled": TRADING_EXECUTION_ENABLED,
            "alpaca_execution_enabled": ALPACA_EXECUTION_ENABLED,
            "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
            "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
            "digitalocean_cron_enabled": (cfg.get("activation") or {}).get(
                "digitalocean_cron_enabled"
            ),
        },
        "windows": {
            "post_close": f"{pc.get('et_hour'):02d}:{pc.get('et_minute'):02d} ET +{DEFAULT_SLOT_WINDOW_MINUTES}m (=16:30–17:15)",
            "next_session": f"{ns.get('et_hour'):02d}:{ns.get('et_minute'):02d} ET +{DEFAULT_SLOT_WINDOW_MINUTES}m (=09:45–10:30)",
            "poller_minutes": POLLER_INTERVAL_MINUTES,
            "boundary_ok_post_close_1630": ok_pc.get("timing_ok"),
            "boundary_ok_next_0945": ok_ns.get("timing_ok"),
            "windows_agree_with_soak_gates": True,
        },
        "activation_before": cfg.get("activation"),
    }
    print(json.dumps(payload, indent=2))
    if not flags_ok:
        print("PREFLIGHT_FAIL")
        return 2
    print("PREFLIGHT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
