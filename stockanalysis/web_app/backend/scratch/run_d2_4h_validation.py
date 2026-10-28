"""Stage D2.4H — USER_POLICY eligibility validation (local, non-executing)."""
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
    INVESTMENT_ELIGIBILITY_MODE,
    TRADING_EXECUTION_ENABLED,
)
from app.services.user_policy_eligibility import (  # noqa: E402
    MODE_USER_POLICY,
    classify_universe_user_policy,
    ensure_user_policy_templates,
    propose_spus_addition,
)
from app.services.universe_manager import universe_manager  # noqa: E402

D2_4E = DATA_CACHE_DIR / "evidence" / "d2_4e_20261026T211547Z" / "d2_4e_results.json"
RUN_ID = datetime.now(timezone.utc).strftime("d2_4h_%Y%m%dT%H%M%SZ")


def main() -> int:
    started = datetime.now(timezone.utc)
    evidence_dir = DATA_CACHE_DIR / "evidence" / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    templates = ensure_user_policy_templates()
    d2e: Dict[str, Any] = {}
    if D2_4E.exists():
        d2e = json.loads(D2_4E.read_text(encoding="utf-8"))
    buy_tickers = [
        str(x.get("ticker")).upper()
        for x in (d2e.get("buy_ready_details") or [])
        if x.get("ticker")
    ]
    scan_by = {
        str(r.get("ticker", "")).upper(): r
        for r in (d2e.get("scan_rows") or [])
        if r.get("ticker")
    }

    stocks = universe_manager.get_eligible_universe() or []
    universe_rows: List[Dict[str, Any]] = []
    for s in stocks:
        t = str(s.get("ticker") or "").upper()
        scan = scan_by.get(t) or {}
        latest = s.get("latest_signal") if isinstance(s.get("latest_signal"), dict) else {}
        universe_rows.append(
            {
                "ticker": t,
                "name": s.get("name"),
                "sector": s.get("sector"),
                "industry": s.get("industry"),
                "signal": scan.get("signal") or (latest or {}).get("signal") or "",
                "v40_signal": scan.get("signal") or (latest or {}).get("signal") or "",
            }
        )

    classified = classify_universe_user_policy(universe_rows)
    by_ticker = {r["ticker"]: r for r in classified["rows"]}

    buy_report = []
    for t in buy_tickers:
        row = by_ticker.get(t)
        if not row:
            continue
        buy_report.append(
            {
                "ticker": t,
                "v40_signal": row.get("v40_signal"),
                "user_policy_status": row.get("user_policy_status"),
                "reason_codes": row.get("reason_codes"),
                "evidence_source": row.get("evidence_source"),
                "evidence_note": row.get("evidence_note"),
                "proposal_permitted": row.get("proposal_permitted"),
                "business_type": row.get("business_type"),
            }
        )

    tickers_now = [s["ticker"] for s in stocks]
    spus = propose_spus_addition(current_tickers=tickers_now)

    # Highlight key policy cases
    highlights = {
        t: by_ticker.get(t)
        for t in ("V", "MO", "SPY", "XLP", "JPM", "LMT", "PYPL", "COF", "CB", "SOXX")
        if t in by_ticker
    }

    payload = {
        "stage": "D2.4H",
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "eligibility_mode": MODE_USER_POLICY,
        "config_mode": INVESTMENT_ELIGIBILITY_MODE,
        "shariah_certification": False,
        "shariah_optional": True,
        "templates_created": templates,
        "production_db_writes": False,
        "broker_orders": False,
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "universe_counts": classified["counts"],
        "universe_total": classified["total"],
        "buy_candidates_eligibility": buy_report,
        "buy_summary": {
            "ALLOWED": sum(1 for r in buy_report if r["user_policy_status"] == "ALLOWED"),
            "EXCLUDED": sum(1 for r in buy_report if r["user_policy_status"] == "EXCLUDED"),
            "REVIEW REQUIRED": sum(1 for r in buy_report if r["user_policy_status"] == "REVIEW REQUIRED"),
        },
        "spus_proposal": spus,
        "highlights": highlights,
        "policy": {
            "exclusions": [
                "conventional_banking_lending",
                "airlines",
                "weapons_defence",
                "tobacco",
            ],
            "visa_payment_network_allowed": True,
            "broad_etf_auto_approve": False,
        },
    }

    (evidence_dir / "d2_4h_results.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    (evidence_dir / "universe_user_policy.json").write_text(
        json.dumps(classified, indent=2, default=str), encoding="utf-8"
    )

    md = _markdown(payload)
    (evidence_dir / "D2_4H_USER_POLICY_ELIGIBILITY_REPORT.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[D2.4H] Evidence: {evidence_dir}")
    return 0


def _markdown(p: Dict[str, Any]) -> str:
    c = p.get("universe_counts") or {}
    bs = p.get("buy_summary") or {}
    lines = [
        "# D2.4H — User-Defined Investment Eligibility (USER_POLICY)",
        "",
        f"Run ID: `{p.get('run_id')}`",
        "",
        "Mode: **USER_POLICY** (formal Shariah verification optional / not required).",
        "",
        "## Universe counts",
        "",
        f"- ALLOWED: **{c.get('ALLOWED')}**",
        f"- EXCLUDED: **{c.get('EXCLUDED')}**",
        f"- REVIEW REQUIRED: **{c.get('REVIEW REQUIRED')}**",
        f"- Total: **{p.get('universe_total')}**",
        "",
        "## 31 BUY candidates",
        "",
        f"- ALLOWED: **{bs.get('ALLOWED')}** | EXCLUDED: **{bs.get('EXCLUDED')}** | REVIEW: **{bs.get('REVIEW REQUIRED')}**",
        "",
    ]
    for row in p.get("buy_candidates_eligibility") or []:
        lines.append(
            f"- **{row.get('ticker')}**: `{row.get('user_policy_status')}` "
            f"codes={row.get('reason_codes')} — {row.get('evidence_note')}"
        )
    spus = p.get("spus_proposal") or {}
    lines += [
        "",
        "## SPUS proposal",
        "",
        f"- Action: `{spus.get('action')}` duplicate={spus.get('duplicate')} "
        f"production_mutated={spus.get('production_mutated')}",
        f"- {spus.get('notes')}",
        "",
        "## Safeguards",
        "",
        f"- Trading execution enabled: `{p.get('trading_execution_enabled')}`",
        f"- Emergency stop: `{p.get('ibkr_emergency_stop')}`",
        f"- Broker orders: `{p.get('broker_orders')}`",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
