"""Stage D2.4L — Multi-session observation soak PREPARATION + local validation.

Runs preflight, schedule pairing checks, safety assertions, and optionally a
bounded plumbing validation. Does NOT claim the three-session soak is complete.

Unattended schedules are NOT activated.
Broker orders are NOT submitted.

Optional: --attempt-post-close runs one real post-close full-universe session
when market data permits (still counts as at most one of three required sessions).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import (  # noqa: E402
    ALPACA_EXECUTION_ENABLED,
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.multi_session_soak import (  # noqa: E402
    MultiSessionSoak,
    SOAK_TARGET_SESSIONS,
    soak_status,
)
from app.services.observation_safety import assert_observation_safety  # noqa: E402
from app.services.observation_schedule import (  # noqa: E402
    ensure_schedule_config,
    pair_post_close_to_next_session,
    plan_soak_pairs,
)
from app.services.order_proposal_engine import (  # noqa: E402
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
)


def _write_report(path: Path, payload: Dict[str, Any]) -> None:
    status = payload.get("soak_status") or {}
    pre = payload.get("preflight") or {}
    lines: List[str] = [
        "# D2.4L — Multi-Session Observation Soak (Preparation)",
        "",
        f"- Run ID: `{payload.get('run_id')}`",
        f"- Soak complete: **{status.get('soak_complete')}** "
        f"({status.get('observed_distinct_sessions')}/{SOAK_TARGET_SESSIONS} distinct sessions)",
        f"- Go/No-Go: **{status.get('recommendation')}**",
        f"- Broker orders: **{payload.get('broker_orders')}**",
        f"- Unattended schedule activated: **{payload.get('unattended_activated')}**",
        f"- Emergency stop: `{IBKR_EMERGENCY_STOP}` | "
        f"TRADING_EXECUTION_ENABLED=`{TRADING_EXECUTION_ENABLED}` | "
        f"ALPACA_EXECUTION_ENABLED=`{ALPACA_EXECUTION_ENABLED}` | "
        f"STAGE_SUBMISSION_ENABLED=`{STAGE_SUBMISSION_ENABLED}`",
        "",
        "## Preflight",
        "",
        f"- Safety passed: **{(pre.get('safety') or {}).get('passed')}**",
        f"- Full universe count: **{pre.get('full_universe_count')}**",
        f"- Today ET: `{pre.get('today_et')}`",
        f"- Today pair: `{json.dumps(pre.get('today_pair'), default=str)[:300]}`",
        "",
        "## Planned soak pairs (not activated)",
        "",
    ]
    for i, p in enumerate((pre.get("planned_soak_pairs") or {}).get("pairs") or [], 1):
        lines.append(
            f"{i}. post-close `{p.get('post_close_day')}` @ `{p.get('post_close_et')}` "
            f"→ next-session `{p.get('next_session_day')}` @ `{p.get('next_session_et')}`"
        )

    lines += [
        "",
        "## Session attempts this run",
        "",
    ]
    for s in payload.get("session_attempts") or []:
        lines.append(
            f"- mode=`{s.get('mode')}` freshness=`{(s.get('freshness') or {}).get('status')}` "
            f"universe=`{s.get('universe_count')}` scanned=`{s.get('successfully_scanned')}` "
            f"sims=`{len(s.get('simulated_proposals') or [])}` "
            f"evidence=`{s.get('evidence_dir')}`"
        )
        lines.append(
            f"  note: {s.get('claim_note') or 'Real session evidence if executed; soak still incomplete until 3 distinct sessions.'}"
        )

    lines += [
        "",
        "## Explicit limitation",
        "",
        f"Do **not** claim the three-session soak is complete. "
        f"Observed distinct sessions: **{status.get('observed_distinct_sessions')}** / "
        f"**{SOAK_TARGET_SESSIONS}**.",
        "",
        "Simulated fill approximations are research estimates only — not broker fills.",
        "",
        "## Stop for review",
        "",
        "Local preparation validated. Await authorization before unattended schedule "
        "activation or paper-order enablement.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="D2.4L soak preparation")
    parser.add_argument(
        "--attempt-post-close",
        action="store_true",
        help="Attempt one real full-universe post-close session (Yahoo refresh)",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Optional cap for preparation plumbing (omit for full universe)",
    )
    parser.add_argument(
        "--plumbing-probe",
        action="store_true",
        help="Run a small refreshed post-close probe that does NOT count toward soak",
    )
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    run_id = started.strftime("d2_4l_prep_%Y%m%dT%H%M%SZ")
    evidence_dir = DATA_CACHE_DIR / "evidence" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    soak = MultiSessionSoak(evidence_root=DATA_CACHE_DIR / "evidence")
    preflight = soak.preflight(now_utc=started)
    safety_bookend = assert_observation_safety(phase="prep_bookend")

    session_attempts: List[Dict[str, Any]] = []
    if args.plumbing_probe or args.attempt_post_close:
        from app.services.observation_runner import ObservationRunner

        tickers = None
        count_toward = bool(args.attempt_post_close) and not args.plumbing_probe
        if args.plumbing_probe and not args.attempt_post_close:
            tickers = ObservationRunner(refresh_prices=False).resolve_universe(
                include_benchmarks=True, max_tickers=args.max_tickers or 25
            )
            count_toward = False
        elif args.max_tickers:
            tickers = ObservationRunner(refresh_prices=False).resolve_universe(
                include_benchmarks=True, max_tickers=args.max_tickers
            )
        attempt = soak.run_post_close_session(
            now_utc=started,
            tickers=tickers,
            refresh_prices=True,
            force_run=True,
            resume=False,
            count_toward_soak=count_toward,
        )
        attempt["claim_note"] = (
            "Plumbing probe — not counted toward three-session soak."
            if not count_toward
            else (
                "At most one of three required distinct sessions if freshness=FRESH; "
                "soak remains incomplete."
            )
        )
        attempt["counted_toward_soak"] = count_toward
        session_attempts.append(attempt)

    status = soak_status()
    # Force honest incomplete claim in preparation report even if somehow 3 already logged
    claim_note = status.get("note")

    payload = {
        "stage": "D2.4L",
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "preparation_only": True,
        "three_session_soak_claimed_complete": False,
        "broker_orders": False,
        "submissions_attempted": 0,
        "unattended_activated": False,
        "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
        "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "alpaca_execution_enabled": bool(ALPACA_EXECUTION_ENABLED),
        "schedule_config": ensure_schedule_config(),
        "sample_pairs": plan_soak_pairs(pairs=3),
        "thanksgiving_pair_skip_check": pair_post_close_to_next_session(
            __import__("datetime").date(2026, 11, 25)  # Wed before Thanksgiving
        ),
        "preflight": preflight,
        "safety_bookend": safety_bookend,
        "session_attempts": session_attempts,
        "soak_status": status,
        "claim_note": claim_note,
        "go_no_go": "NO_GO_AWAIT_THREE_REAL_SESSIONS"
        if not status.get("soak_complete")
        else status.get("recommendation"),
        "stop_for_review": True,
    }

    results_path = evidence_dir / "d2_4l_results.json"
    results_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    report_path = evidence_dir / "D2_4L_SOAK_PREPARATION_REPORT.md"
    _write_report(report_path, payload)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "results": str(results_path),
                "report": str(report_path),
                "soak_complete": status.get("soak_complete"),
                "observed_sessions": status.get("observed_distinct_sessions"),
                "go_no_go": payload["go_no_go"],
                "preflight_passed": preflight.get("passed"),
                "universe": preflight.get("full_universe_count"),
                "session_attempts": len(session_attempts),
                "broker_orders": False,
                "unattended_activated": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
