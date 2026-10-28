"""D2.4L unattended observation CLI (does NOT register Windows tasks).

Usage (from stockanalysis/web_app/backend, PYTHONPATH=.):

  python -u scratch/run_d2_4l_unattended.py prepare-artifacts
  python -u scratch/run_d2_4l_unattended.py poll
  python -u scratch/run_d2_4l_unattended.py post-close
  python -u scratch/run_d2_4l_unattended.py next-session
  python -u scratch/run_d2_4l_unattended.py status

Windows Task Scheduler registration requires separate explicit approval
(see prepare-artifacts output). Broker execution remains disabled.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.unattended_observation import (  # noqa: E402
    generate_task_scheduler_artifacts,
    morning_status,
    resolve_prior_post_close_bundle,
    run_unattended_next_session,
    run_unattended_poll,
    run_unattended_post_close,
    safety_snapshot,
    windows_tasks_activated,
)


def _print(payload: dict) -> int:
    print(json.dumps(payload, indent=2, default=str), flush=True)
    status = str(payload.get("status") or "")
    if status == "ABORTED_SAFETY":
        return 2
    if status == "COMPLETED" and payload.get("eligible") is False:
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D2.4L unattended observation (inactive by default)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare-artifacts", help="Write inactive Task Scheduler XML + README")
    sub.add_parser(
        "poll",
        help="DST-safe slot check; run post-close or next-session if in window",
    )
    sub.add_parser("post-close", help="Attempt post-close (respects timing gate)")
    sub.add_parser("next-session", help="Attempt next-session with auto prior bundle")
    sub.add_parser("status", help="Morning review: soak, logs, prior bundle, safety")
    sub.add_parser("resolve-prior", help="Show auto-resolved prior post-close bundle")
    sub.add_parser("safety", help="Show execution-disabled / emergency-stop snapshot")
    args = parser.parse_args()

    if args.cmd == "prepare-artifacts":
        return _print(generate_task_scheduler_artifacts(backend_dir=BACKEND))
    if args.cmd == "poll":
        return _print(run_unattended_poll())
    if args.cmd == "post-close":
        return _print(run_unattended_post_close(force_diagnostic=False))
    if args.cmd == "next-session":
        return _print(run_unattended_next_session())
    if args.cmd == "status":
        return _print(morning_status())
    if args.cmd == "resolve-prior":
        return _print(resolve_prior_post_close_bundle())
    if args.cmd == "safety":
        return _print(
            {
                "safety": safety_snapshot(),
                "windows_tasks_activated": windows_tasks_activated(),
                "broker_orders": False,
            }
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
