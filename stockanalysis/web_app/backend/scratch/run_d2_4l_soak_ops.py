"""D2.4L operational soak commands (manual; no cron activation; no broker orders).

Usage (from stockanalysis/web_app/backend with PYTHONPATH=.):

  python scratch/run_d2_4l_soak_ops.py schedule
  python scratch/run_d2_4l_soak_ops.py status
  python -u scratch/run_d2_4l_soak_ops.py post-close          # live progress; resumes same day
  python -u scratch/run_d2_4l_soak_ops.py post-close --fresh  # clear checkpoint, full restart
  python scratch/run_d2_4l_soak_ops.py next-session --prior <session_bundle.json>
  python scratch/run_d2_4l_soak_ops.py report

Full-universe post-close is dominated by per-ticker V4.0 walk-forward train()
(~1–2s/ticker → ~5–10+ minutes for ~230 names). Progress lines flush each ticker.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.multi_session_soak import (  # noqa: E402
    LEDGER_PATH,
    MultiSessionSoak,
    SOAK_TARGET_PAIRS,
    load_soak_ledger,
    soak_status,
)
from app.services.observation_schedule import plan_soak_pairs  # noqa: E402

NY = ZoneInfo("America/New_York")
MEL = ZoneInfo("Australia/Melbourne")


def cmd_schedule(_: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    plan = plan_soak_pairs(from_day=now.astimezone(NY).date(), pairs=3)
    rows = []
    for i, p in enumerate(plan.get("pairs") or [], 1):
        pc = datetime.fromisoformat(p["post_close_et"])
        ns = datetime.fromisoformat(p["next_session_et"])
        rows.append(
            {
                "pair": i,
                "post_close_et": pc.strftime("%Y-%m-%d %H:%M %Z"),
                "post_close_melbourne": pc.astimezone(MEL).strftime("%Y-%m-%d %H:%M %Z"),
                "next_session_et": ns.strftime("%Y-%m-%d %H:%M %Z"),
                "next_session_melbourne": ns.astimezone(MEL).strftime("%Y-%m-%d %H:%M %Z"),
                "pair_id": f"{p['post_close_day']}->{p['next_session_day']}",
            }
        )
    print(
        json.dumps(
            {
                "now_utc": now.isoformat(),
                "now_et": now.astimezone(NY).isoformat(),
                "now_melbourne": now.astimezone(MEL).isoformat(),
                "activation": plan.get("activation"),
                "pairs": rows,
                "note": "Manual runbook only — do not activate Task Scheduler / DO cron",
            },
            indent=2,
        )
    )
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    st = soak_status()
    led = load_soak_ledger()
    print(
        json.dumps(
            {
                "ledger_path": str(LEDGER_PATH),
                "soak_status": st,
                "session_records": led.get("sessions") or [],
                "target_pairs": SOAK_TARGET_PAIRS,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def cmd_post_close(args: argparse.Namespace) -> int:
    soak = MultiSessionSoak()
    # Default: resume same trading-day checkpoint after interrupt.
    # --fresh clears checkpoint and restarts the full universe.
    resume = not bool(getattr(args, "fresh", False))
    if getattr(args, "resume", False):
        resume = True
    force_diag = bool(getattr(args, "force_diagnostic", False))
    print(
        f"[OPS] post-close starting resume={resume} force_diagnostic={force_diag} "
        f"(use python -u for live progress)",
        flush=True,
    )
    result = soak.run_post_close_session(
        refresh_prices=True,
        force_run=force_diag,
        resume=resume,
        count_toward_soak=True,
        tickers=None,
    )
    print(
        json.dumps(
            {
                "mode": "post_close",
                "run_id": result.get("run_id"),
                "trading_day_et": result.get("trading_day_et"),
                "eligibility_reason_code": result.get("eligibility_reason_code"),
                "eligible": result.get("eligible"),
                "counts_toward_pair": result.get("counts_toward_pair"),
                "timing": result.get("timing"),
                "gated_before_proposals": result.get("gated_before_proposals"),
                "diagnostic_force_run": result.get("diagnostic_force_run"),
                "freshness": (result.get("freshness") or {}).get("status"),
                "universe_count": result.get("universe_count"),
                "successfully_scanned": result.get("successfully_scanned"),
                "simulated_proposals": len(result.get("simulated_proposals") or []),
                "bundle_path": result.get("bundle_path"),
                "evidence_dir": result.get("evidence_dir"),
                "pair": result.get("pair"),
                "soak_status": result.get("soak_status"),
                "broker_orders": False,
                "note": result.get("note")
                or (
                    "Post-close leg recorded. Pair does NOT count until paired "
                    "next-session succeeds. Pass bundle_path to next-session."
                ),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.get("eligibility_reason_code") in (None, "OK") else 3


def cmd_next_session(args: argparse.Namespace) -> int:
    prior = Path(args.prior)
    if not prior.exists():
        print(json.dumps({"error": "PRIOR_BUNDLE_NOT_FOUND", "path": str(prior)}, indent=2))
        return 2
    soak = MultiSessionSoak()
    result = soak.run_next_session_validation(
        prior_bundle_path=prior,
        force_run=bool(getattr(args, "force_diagnostic", False)),
    )
    print(
        json.dumps(
            {
                "mode": "next_session",
                "run_id": result.get("run_id"),
                "trading_day_et": result.get("trading_day_et"),
                "prior_bundle_path": result.get("prior_bundle_path"),
                "expected_next_session_day": result.get("expected_next_session_day"),
                "eligibility_reason_code": result.get("eligibility_reason_code"),
                "eligible": result.get("eligible"),
                "counts_toward_pair": result.get("counts_toward_pair"),
                "timing": result.get("timing"),
                "gated_before_proposals": result.get("gated_before_proposals"),
                "simulated_proposals": len(result.get("simulated_proposals") or []),
                "bundle_path": result.get("bundle_path"),
                "evidence_dir": result.get("evidence_dir"),
                "soak_status": result.get("soak_status"),
                "broker_orders": False,
                "note": result.get("note"),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.get("eligible") else 3


def cmd_report(_: argparse.Namespace) -> int:
    soak = MultiSessionSoak()
    payload = soak.write_final_soak_report()
    print(json.dumps(payload, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="D2.4L soak operational commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("schedule", help="Show upcoming ET/Melbourne pairs (no activation)")
    sub.add_parser("status", help="Read soak ledger / pair progress")
    p_post = sub.add_parser("post-close", help="Full-universe refreshed post-close observation")
    p_post.add_argument(
        "--resume",
        action="store_true",
        help="Resume incomplete same-day checkpoint (default behavior)",
    )
    p_post.add_argument(
        "--fresh",
        action="store_true",
        help="Clear same-day checkpoint and restart the full universe scan",
    )
    p_post.add_argument(
        "--force-diagnostic",
        action="store_true",
        help=(
            "Allow scan outside post_close_research window for diagnostics only; "
            "results are INELIGIBLE and never count toward soak"
        ),
    )
    p_next = sub.add_parser("next-session", help="Paired next-session quote/proposal evaluation")
    p_next.add_argument(
        "--prior",
        required=True,
        help="Path to prior post-close session_bundle.json",
    )
    p_next.add_argument(
        "--force-diagnostic",
        action="store_true",
        help=(
            "Recorded for audit only; next-session still fail-closes before proposals "
            "when outside the 09:45 ET ±45m window or wrong NY date"
        ),
    )
    sub.add_parser("report", help="Generate three-session soak report from ledger")

    args = parser.parse_args()
    if args.cmd == "schedule":
        return cmd_schedule(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "post-close":
        return cmd_post_close(args)
    if args.cmd == "next-session":
        return cmd_next_session(args)
    if args.cmd == "report":
        return cmd_report(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
