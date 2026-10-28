"""Stage D2.4K — Autonomous observation pilot validation (local, non-submitting).

Runs a bounded observation session + schedule plan + execution lifecycle audit.
Does not activate Windows tasks / DigitalOcean cron.
Does not submit broker orders.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import (  # noqa: E402
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.execution_lifecycle_audit import run_execution_lifecycle_audit  # noqa: E402
from app.services.observation_runner import ObservationRunner  # noqa: E402
from app.services.observation_schedule import (  # noqa: E402
    ensure_schedule_config,
    plan_upcoming_slots,
)
from app.services.order_proposal_engine import (  # noqa: E402
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
)

# Bounded pilot universe — enough for real evidence without full-universe soak
DEFAULT_TICKERS = [
    "AAPL",
    "MSFT",
    "AMD",
    "MU",
    "PYPL",
    "KMI",
    "ZS",
    "GILD",
    "CRM",
    "PLTR",
    "SOXX",
    "SPY",
    "XLP",
    "JPM",
    "MO",
    "LMT",
    "DAL",
    "ROST",
    "DG",
    "APD",
]


def _write_report(path: Path, payload: Dict[str, Any]) -> None:
    obs = payload.get("observation") or {}
    life = payload.get("execution_lifecycle_audit") or {}
    sched = payload.get("schedule") or {}
    lines: List[str] = [
        "# D2.4K — Autonomous Observation Pilot Report",
        "",
        f"- Run ID: `{payload.get('run_id')}`",
        f"- Broker orders: **{payload.get('broker_orders')}**",
        f"- Submissions attempted: **{payload.get('submissions_attempted')}**",
        f"- STAGE_SUBMISSION_ENABLED: `{STAGE_SUBMISSION_ENABLED}`",
        f"- IBKR_EMERGENCY_STOP: `{IBKR_EMERGENCY_STOP}`",
        f"- TRADING_EXECUTION_ENABLED: `{TRADING_EXECUTION_ENABLED}`",
        f"- Windows/DO cron activated: **False**",
        "",
        "## Observation runner architecture",
        "",
        "1. `ObservationRunner.scan_universe` → `scanner_service.evaluate_stock_signal`",
        "2. `classify_user_policy` (USER_POLICY)",
        "3. `BuyPipelineDryRun.evaluate_signal` → BUY_READY / WAIT / BLOCKED / NO_ACTION",
        "4. Alpaca read-only account + quotes",
        "5. Risk-constrained SIMULATED proposals (no submission)",
        "6. Decision journal + session summary + optional performance approx",
        "",
        "## Scheduling configuration",
        "",
        f"- Config path: `{sched.get('config_path')}`",
        f"- Activation flags: `{json.dumps((sched.get('config') or {}).get('activation'))}`",
        f"- Upcoming plan events: **{len((sched.get('upcoming') or {}).get('events') or [])}**",
        "",
        "## Session summary",
        "",
        f"- Universe size: **{obs.get('scanned_universe_size')}**",
        f"- Signal distribution: `{obs.get('signal_distribution')}`",
        f"- Policy breakdown: `{obs.get('policy_eligibility_breakdown')}`",
        f"- BUY candidates: **{len(obs.get('buy_candidates') or [])}**",
        f"- Simulated proposals: **{len(obs.get('simulated_proposals') or [])}**",
        f"- Rejected/deferred (sample count): **{obs.get('rejected_or_deferred_count')}**",
        f"- Scanner runtime (s): **{obs.get('scanner_runtime_seconds')}**",
        f"- Data-quality failures: **{len(obs.get('data_quality_failures') or [])}**",
        f"- Portfolio exposure: `{obs.get('portfolio_exposure')}`",
        "",
        "### BUY candidates",
        "",
    ]
    for c in obs.get("buy_candidates") or []:
        lines.append(
            f"- {c.get('ticker')}: rule=`{c.get('entry_rule')}` "
            f"px=`{c.get('signal_price')}` policy=`{c.get('policy')}` "
            f"inv=`{c.get('investment')}`"
        )
    lines += ["", "### Simulated proposals", ""]
    for p in obs.get("simulated_proposals") or []:
        lines.append(
            f"- rank {p.get('pilot_rank')}: {p.get('ticker')} "
            f"limit=`{p.get('proposed_limit')}` qty=`{p.get('proposed_qty')}` "
            f"notional=`{p.get('proposed_notional')}`"
        )
    lines += [
        "",
        "### Performance (approx — NOT broker fills)",
        "",
    ]
    perf = obs.get("performance") or []
    if not perf:
        lines.append("_Insufficient subsequent bars or no SIMULATED proposals for metrics._")
    for row in perf:
        pe = row.get("performance") or {}
        lines.append(
            f"- {row.get('ticker')}: approx=`{pe.get('approx_fill_label')}` "
            f"ret=`{pe.get('subsequent_return_pct')}` "
            f"MFE=`{pe.get('max_favorable_excursion_pct')}` "
            f"MAE=`{pe.get('max_adverse_excursion_pct')}` "
            f"excess_vs_SPY=`{pe.get('excess_return_pct')}` "
            f"(real_broker_fill={pe.get('is_real_broker_fill')})"
        )

    lines += [
        "",
        "## Execution lifecycle audit",
        "",
        f"- Summary verdict: **{life.get('summary_verdict')}**",
        f"- Guards: `{life.get('guards')}`",
        f"- Idempotency: `{life.get('idempotency', {}).get('verdict')}`",
        f"- Adapter mutation guards: `{life.get('adapter_mutation_guards', {}).get('verdict')}`",
        f"- Fill handlers (mocked): `{life.get('fill_handlers_mocked', {}).get('verdict')}`",
        f"- Restart/reconcile: `{life.get('restart_and_reconciliation', {}).get('verdict')}`",
        "",
        "### Blockers before paper trading",
        "",
    ]
    for b in life.get("blockers_before_paper_trading") or []:
        lines.append(f"- {b}")

    lines += [
        "",
        "## Stop for review",
        "",
        "Observation-only pilot validated locally. No unattended schedule activation. "
        "No broker submissions. Await explicit approval before paper-order enablement.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("d2_4k_%Y%m%dT%H%M%SZ")
    evidence_dir = DATA_CACHE_DIR / "evidence" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    schedule_cfg = ensure_schedule_config()
    upcoming = plan_upcoming_slots(from_utc=started, trading_days=5, config=schedule_cfg)

    runner = ObservationRunner(
        evidence_dir=evidence_dir,
        refresh_prices=False,  # local cache-first for safe validation
    )
    # Fresh checkpoint for this validation universe
    runner.checkpoint_path.write_text(
        json.dumps({"completed_tickers": [], "sessions": [], "last_run_id": None}, indent=2),
        encoding="utf-8",
    )
    observation = runner.run_observation_session(
        mode="post_close",
        tickers=DEFAULT_TICKERS,
        resume=False,
        force_run=True,
        now_utc=started,
    )

    lifecycle = run_execution_lifecycle_audit()

    payload = {
        "stage": "D2.4K",
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_db_writes": False,
        "broker_orders": False,
        "submissions_attempted": 0,
        "windows_task_activated": False,
        "digitalocean_cron_activated": False,
        "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
        "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "schedule": {
            "config_path": str(DATA_CACHE_DIR / "observation" / "schedule_config.json"),
            "config": schedule_cfg,
            "upcoming": upcoming,
        },
        "observation": observation,
        "execution_lifecycle_audit": lifecycle,
        "files_changed_note": (
            "See agent summary — observation_*, execution_lifecycle_audit, "
            "tests/test_d2_4k_*, scratch/run_d2_4k_validation.py"
        ),
        "stop_for_review": True,
    }

    results_path = evidence_dir / "d2_4k_results.json"
    # observation already wrote nested results; wrap at top level
    results_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    report_path = evidence_dir / "D2_4K_OBSERVATION_PILOT_REPORT.md"
    _write_report(report_path, payload)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "results": str(results_path),
                "report": str(report_path),
                "buy_candidates": len(observation.get("buy_candidates") or []),
                "simulated": len(observation.get("simulated_proposals") or []),
                "lifecycle": lifecycle.get("summary_verdict"),
                "broker_orders": False,
                "cron_activated": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
