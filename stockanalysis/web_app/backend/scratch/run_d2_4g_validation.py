"""Stage D2.4G — Shariah screening + investment eligibility foundation (local).

Read-only against universe / D2.4E BUY list. No production writes, no orders.
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
from app.database import SessionLocal  # noqa: E402
from app.services.shariah_review_workflow import (  # noqa: E402
    ensure_local_templates,
    run_universe_workflow,
)
from app.services.universe_manager import universe_manager  # noqa: E402

D2_4E = DATA_CACHE_DIR / "evidence" / "d2_4e_20261026T211547Z" / "d2_4e_results.json"
RUN_ID = datetime.now(timezone.utc).strftime("d2_4g_%Y%m%dT%H%M%SZ")


def main() -> int:
    started = datetime.now(timezone.utc)
    evidence_dir = DATA_CACHE_DIR / "evidence" / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    templates = ensure_local_templates()
    d2e: Dict[str, Any] = {}
    if D2_4E.exists():
        d2e = json.loads(D2_4E.read_text(encoding="utf-8"))

    buy_tickers = [
        str(x.get("ticker")).upper()
        for x in (d2e.get("buy_ready_details") or [])
        if x.get("ticker")
    ]
    scan_by = {
        str(r.get("ticker", "")).upper(): r for r in (d2e.get("scan_rows") or []) if r.get("ticker")
    }

    eligible = universe_manager.get_eligible_universe() or []
    universe_rows: List[Dict[str, Any]] = []
    for s in eligible:
        t = str(s.get("ticker") or "").upper()
        scan = scan_by.get(t) or {}
        latest = (s.get("latest_signal") or {}) if isinstance(s.get("latest_signal"), dict) else {}
        universe_rows.append(
            {
                "ticker": t,
                "name": s.get("name"),
                "sector": s.get("sector"),
                "signal": scan.get("signal") or latest.get("signal") or "",
                "v40_signal": scan.get("signal") or latest.get("signal") or "",
                "shariah_status": latest.get("shariah_status") or "NOT VERIFIED",
            }
        )

    db = SessionLocal()
    try:
        report = run_universe_workflow(
            universe_rows=universe_rows,
            buy_priority_tickers=buy_tickers,
            db=db,
        )
    finally:
        db.close()

    buy_queue = report.get("buy_candidates_review_queue") or []
    # Prefer the 31 D2.4E buys even if signal text drifted
    prioritized = []
    seen = set()
    for t in buy_tickers:
        for row in report.get("rows") or []:
            if row.get("ticker") == t and t not in seen:
                prioritized.append(row)
                seen.add(t)
                break
    for row in buy_queue:
        if row.get("ticker") not in seen:
            prioritized.append(row)
            seen.add(row.get("ticker"))

    payload = {
        "stage": "D2.4G",
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "templates_created": templates,
        "production_db_writes": False,
        "broker_orders": False,
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "reused_capabilities": [
            "WatchlistStock (status/source/date) via shariah_store",
            "shariah_eligibility.normalize/classify",
            "shariah_monitor report patterns",
            "ticker_integrity aliases",
            "buy_decision_engine / buy_pipeline proposal gates",
            "watchlist API VERIFIED source+date rule",
        ],
        "methodology": {
            "shariah_statuses": ["VERIFIED", "NOT VERIFIED", "NON-COMPLIANT"],
            "personal_statuses": ["ALLOWED", "EXCLUDED", "REVIEW REQUIRED"],
            "execution_requires": [
                "VERIFIED with complete evidence (provider, source, dates, reviewer, activity/ratios)",
                "personal ALLOWED",
                "no unresolved mandatory checks",
            ],
            "fail_closed_on": ["missing", "incomplete", "expired", "conflicting", "shortlist-only"],
            "sector_only_classification": False,
        },
        "counts": report.get("counts"),
        "inputs": report.get("inputs"),
        "buy_candidates_review_queue": prioritized,
        "shariah_blocked_buy_opportunities": report.get("shariah_blocked_buy_opportunities"),
        "review_queue_size": len(report.get("review_queue") or []),
        "external_data_provider_requirements": [
            "Independent Shariah screening provider (or board-approved methodology) for business-activity + financial-ratio assessments",
            "Documented source references and review/expiry dates per ticker",
            "Optional: licensed screening API (e.g. established Islamic equity screener) — not wired in D2.4G",
        ],
        "recommended_next_stage": [
            "D2.4H: Manually screen prioritized BUY candidates; stage complete evidence_records.json locally",
            "Confirm personal restriction overrides for banking/weapons/pork with evidence_notes",
            "Re-run proposal dry-run with strict evidence — expect proposals only for VERIFIED+ALLOWED",
            "Keep emergency stop / execution flags unchanged until paper pilot checklist complete",
        ],
        "sample_rows": (report.get("rows") or [])[:10],
    }

    (evidence_dir / "d2_4g_results.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    (evidence_dir / "universe_monitoring.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )

    md = _markdown(payload)
    (evidence_dir / "D2_4G_SHARIAH_SCREENING_REPORT.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[D2.4G] Evidence: {evidence_dir}")
    return 0


def _markdown(p: Dict[str, Any]) -> str:
    c = p.get("counts") or {}
    lines = [
        "# D2.4G — Shariah Screening and Investment Eligibility Foundation",
        "",
        f"Run ID: `{p.get('run_id')}`",
        "",
        "## Counts",
        "",
        f"- Shariah VERIFIED: **{c.get('shariah_VERIFIED')}**",
        f"- Shariah NOT VERIFIED: **{c.get('shariah_NOT_VERIFIED')}**",
        f"- Shariah NON-COMPLIANT: **{c.get('shariah_NON_COMPLIANT')}**",
        f"- Personal ALLOWED: **{c.get('personal_ALLOWED')}**",
        f"- Personal EXCLUDED: **{c.get('personal_EXCLUDED')}**",
        f"- Personal REVIEW REQUIRED: **{c.get('personal_REVIEW_REQUIRED')}**",
        f"- Execution eligible: **{c.get('execution_ELIGIBLE')}**",
        f"- Execution blocked: **{c.get('execution_BLOCKED')}**",
        "",
        "## 31 BUY candidates — review queue (priority)",
        "",
    ]
    for row in p.get("buy_candidates_review_queue") or []:
        lines.append(
            f"- **{row.get('ticker')}**: signal=`{row.get('v40_signal')}` "
            f"shariah=`{row.get('shariah_screening_status')}` "
            f"personal=`{row.get('personal_restriction_status')}` "
            f"→ `{row.get('next_review_action')}`"
        )
    lines += [
        "",
        "## External provider requirements",
        "",
    ]
    for r in p.get("external_data_provider_requirements") or []:
        lines.append(f"- {r}")
    lines += [
        "",
        "## Recommended next stage",
        "",
    ]
    for r in p.get("recommended_next_stage") or []:
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
