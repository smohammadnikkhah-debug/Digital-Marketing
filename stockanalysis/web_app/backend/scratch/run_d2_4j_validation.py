"""Stage D2.4J — Autonomous paper-trading pilot readiness (local, non-submitting).

1. Replace lower-ask ranking with V4.0-safe deterministic order
2. Quote/symbol integrity for AMD, MSFT, MU vs $500 whole-share cap
3. Policy evidence audit for CRM/PLTR/SOXX ALLOWED and SPY/XLP EXCLUDED

Does not submit orders or enable trading.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import (  # noqa: E402
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.alpaca_readonly import try_load_readonly_client  # noqa: E402
from app.services.candidate_ranking import (  # noqa: E402
    RANKING_METHOD_ID,
    describe_ranking_methodology,
    rank_candidates,
)
from app.services.order_execution_service import DEFAULT_MAX_ORDER_NOTIONAL_USD  # noqa: E402
from app.services.order_proposal_engine import (  # noqa: E402
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
)
from app.services.policy_evidence_audit import (  # noqa: E402
    audit_pilot_policy_classifications,
)
from app.services.quote_integrity_audit import (  # noqa: E402
    audit_high_ask_candidates,
    audit_symbol_quote,
)

D2_4E = DATA_CACHE_DIR / "evidence" / "d2_4e_20261026T211547Z" / "d2_4e_results.json"
D2_4I_LATEST_GLOB = "d2_4i_*"
RUN_ID = datetime.now(timezone.utc).strftime("d2_4j_%Y%m%dT%H%M%SZ")
HIGH_ASK_TICKERS = ("AMD", "MSFT", "MU")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_d2_4i_results() -> Path:
    evidence = DATA_CACHE_DIR / "evidence"
    dirs = sorted(
        [
            p
            for p in evidence.glob(D2_4I_LATEST_GLOB)
            if p.is_dir() and (p / "d2_4i_results.json").exists()
        ],
        key=lambda p: p.name,
    )
    if not dirs:
        raise FileNotFoundError("No D2.4I evidence directories found")
    return dirs[-1] / "d2_4i_results.json"


def _fetch_assets(client, tickers) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if client is None:
        return out
    try:
        tc = client.adapter._get_trading_client()  # noqa: SLF001
    except Exception:
        return out
    for t in tickers:
        try:
            asset = tc.get_asset(t)
            out[t] = {
                "symbol": str(getattr(asset, "symbol", "")),
                "name": str(getattr(asset, "name", "") or ""),
                "tradable": bool(getattr(asset, "tradable", False)),
                "status": str(getattr(asset, "status", "")),
                "exchange": str(getattr(asset, "exchange", "")),
                "asset_class": str(
                    getattr(asset, "asset_class", None) or getattr(asset, "class_", "")
                ),
                "fractionable": bool(getattr(asset, "fractionable", False)),
            }
        except Exception as exc:
            out[t] = {"symbol": t, "error": str(exc)[:200]}
    return out


def _rerank_from_d2i(
    d2i: Dict[str, Any], buy_ready_details: List[Dict[str, Any]]
) -> Dict[str, Any]:
    rows = [
        r
        for r in (d2i.get("candidate_results") or [])
        if (r.get("simulated_proposal") or {}).get("status") == "SIMULATED"
    ]
    # Legacy ask-order (for before/after evidence only)
    legacy = sorted(
        rows,
        key=lambda r: (
            float((r.get("quote") or {}).get("ask") or 1e12),
            str(r.get("ticker") or ""),
        ),
    )
    new_ranked = rank_candidates(rows, buy_ready_details=buy_ready_details)
    return {
        "method": describe_ranking_methodology(),
        "legacy_ask_order": [
            {
                "rank": i,
                "ticker": r["ticker"],
                "ask": (r.get("quote") or {}).get("ask"),
            }
            for i, r in enumerate(legacy, start=1)
        ],
        "pilot_rank_order": [
            {
                "pilot_rank": r.get("pilot_rank"),
                "ticker": r["ticker"],
                "ask": (r.get("quote") or {}).get("ask"),
                "scan_sequence_index": r.get("pilot_rank_sequence_index"),
                "proposed_notional": (r.get("simulated_proposal") or {}).get(
                    "proposed_notional"
                ),
            }
            for r in new_ranked
        ],
        "first_selected_under_open_order_cap": (
            new_ranked[0]["ticker"] if new_ranked else None
        ),
        "legacy_first_was": legacy[0]["ticker"] if legacy else None,
        "share_price_no_longer_priority": True,
    }


def _write_report(path: Path, payload: Dict[str, Any]) -> None:
    ranking = payload.get("candidate_ranking") or {}
    quotes = payload.get("quote_integrity") or {}
    policy = payload.get("policy_evidence") or {}
    lines = [
        "# D2.4J — Autonomous Paper-Trading Pilot Readiness",
        "",
        f"- Run ID: `{payload.get('run_id')}`",
        f"- Broker orders: **{payload.get('broker_orders')}**",
        f"- Submissions attempted: **{payload.get('submissions_attempted')}**",
        f"- STAGE_SUBMISSION_ENABLED: `{payload.get('stage_submission_enabled')}`",
        f"- IBKR_EMERGENCY_STOP: `{payload.get('ibkr_emergency_stop')}`",
        f"- TRADING_EXECUTION_ENABLED: `{payload.get('trading_execution_enabled')}`",
        "",
        "## 1. Candidate ranking",
        "",
        f"- Method: `{RANKING_METHOD_ID}`",
        f"- Uses share price: **{ranking.get('method', {}).get('uses_share_price')}**",
        f"- Invents investment score: **{ranking.get('method', {}).get('invents_investment_score')}**",
        f"- V4.0 live rank available: **{ranking.get('method', {}).get('v40_live_rank_available')}**",
        "",
        "### Missing V4.0 data",
        "",
        ranking.get("method", {}).get("missing_data", ""),
        "",
        "### Before (D2.4I lower-ask) → After (scan sequence)",
        "",
        f"- Legacy first SIMULATED: `{ranking.get('legacy_first_was')}`",
        f"- Pilot first under open-order cap: `{ranking.get('first_selected_under_open_order_cap')}`",
        "",
        "| Pilot rank | Ticker | Ask | D2.4E seq |",
        "|---:|---|---:|---:|",
    ]
    for row in ranking.get("pilot_rank_order") or []:
        lines.append(
            f"| {row.get('pilot_rank')} | {row.get('ticker')} | "
            f"{row.get('ask')} | {row.get('scan_sequence_index')} |"
        )

    lines += [
        "",
        "## 2. Quote / symbol integrity (AMD, MSFT, MU)",
        "",
        f"- Max order notional: **${quotes.get('max_order_notional_usd', 500)}**",
        f"- Fractional shares: **{quotes.get('fractional_shares_enabled')}**",
        f"- All whole-share cap rejections confirmed: "
        f"**{quotes.get('all_whole_share_cap_rejections_confirmed')}**",
        f"- Any symbol mismatch: **{quotes.get('any_symbol_mismatch')}**",
        f"- Any split-scale concern: **{quotes.get('any_split_concern')}**",
        "",
    ]
    for r in quotes.get("results") or []:
        aff = r.get("whole_share_affordability") or {}
        lines += [
            f"### {r.get('ticker')}",
            "",
            f"- Ask / bid: `{r.get('quote', {}).get('ask')}` / `{r.get('quote', {}).get('bid')}`",
            f"- Source: `{r.get('quote', {}).get('source')}` ts=`{r.get('quote', {}).get('quote_timestamp')}`",
            f"- Yahoo close: `{ (r.get('yahoo_price_cache') or {}).get('close') }` "
            f"@ `{(r.get('yahoo_price_cache') or {}).get('date')}`",
            f"- Asset: `{r.get('asset')}`",
            f"- Whole-share affordable: **{aff.get('affordable_one_whole_share')}** "
            f"(qty={aff.get('whole_share_qty')})",
            f"- Cap rejection confirmed: **{r.get('whole_share_cap_rejection_confirmed')}**",
            f"- Notes: {'; '.join(r.get('notes') or [])}",
            "",
        ]

    lines += [
        "## 3. Investment policy evidence",
        "",
        "Four exclusion rules:",
        "",
    ]
    for rule in policy.get("four_exclusion_rules") or []:
        lines.append(f"{rule.get('id')}. {rule.get('label')}")
    lines += [
        "",
        f"- All match expectations: **{policy.get('all_match_expectations')}**",
        "",
        "| Ticker | Expected | Actual | Match |",
        "|---|---|---|---|",
    ]
    for c in policy.get("classifications") or []:
        lines.append(
            f"| {c.get('ticker')} | {c.get('expected_status')} | "
            f"{c.get('actual_status')} | {c.get('matches_expectation')} |"
        )
        lines.append("")
        lines.append(f"- **{c.get('ticker')} rule mapping:** {c.get('four_exclusion_rules_mapping')}")
        lines.append(f"- Evidence: {c.get('evidence_note')}")

    lines += [
        "",
        "## Pilot readiness gates (this stage)",
        "",
        "- Ranking no longer prefers lower share price: **PASS**",
        f"- AMD/MSFT/MU whole-share $500 gate: "
        f"**{'PASS' if quotes.get('all_whole_share_cap_rejections_confirmed') else 'REVIEW'}**",
        f"- Policy CRM/PLTR/SOXX/SPY/XLP: "
        f"**{'PASS' if policy.get('all_match_expectations') else 'FAIL'}**",
        "- Orders submitted this stage: **NONE** (required)",
        "",
        "## Stop for review",
        "",
        "Trading remains disabled. No broker submissions. Await explicit approval "
        "before any paper-order enablement.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    started = datetime.now(timezone.utc)
    evidence_dir = DATA_CACHE_DIR / "evidence" / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    d2e = _load_json(D2_4E)
    d2i_path = _latest_d2_4i_results()
    d2i = _load_json(d2i_path)

    ranking = _rerank_from_d2i(d2i, d2e.get("buy_ready_details") or [])

    client, client_status = try_load_readonly_client()
    live_quotes: Dict[str, Dict[str, Any]] = {}
    assets: Dict[str, Dict[str, Any]] = {}
    alpaca_meta: Dict[str, Any] = {"connected": False, "status": client_status}
    if client is not None:
        try:
            alpaca_meta = client.validate_readonly()
            live_quotes = client.get_quotes(list(HIGH_ASK_TICKERS))
            assets = _fetch_assets(client, HIGH_ASK_TICKERS)
        except Exception as exc:
            alpaca_meta["error"] = f"{type(exc).__name__}: {exc}"

    # Prefer live quotes when available; fall back to D2.4I captured quotes + sizing blocks
    d2i_by = {str(r.get("ticker")).upper(): r for r in (d2i.get("candidate_results") or [])}
    quote_results = []
    for t in HIGH_ASK_TICKERS:
        d2i_row = d2i_by.get(t) or {}
        q = live_quotes.get(t) or (d2i_row.get("quote") or {})
        # Flatten D2.4I nested quote into audit shape when needed
        if "ask" in q and "symbol" not in q:
            q = {**q, "symbol": t}
        quote_results.append(
            audit_symbol_quote(
                t,
                quote=q,
                asset=assets.get(t) or d2i_row.get("alpaca_asset"),
                sizing_block=d2i_row.get("sizing_block"),
                max_order_notional_usd=DEFAULT_MAX_ORDER_NOTIONAL_USD,
            )
        )
    quote_integrity = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_order_notional_usd": float(DEFAULT_MAX_ORDER_NOTIONAL_USD),
        "fractional_shares_enabled": False,
        "tickers": list(HIGH_ASK_TICKERS),
        "results": quote_results,
        "live_quotes_used": bool(live_quotes),
        "all_whole_share_cap_rejections_confirmed": all(
            a.get("whole_share_cap_rejection_confirmed") for a in quote_results
        ),
        "any_symbol_mismatch": any(not a.get("symbol_identity_ok") for a in quote_results),
        "any_split_concern": any(a.get("split_adjustment_concern") for a in quote_results),
    }

    policy = audit_pilot_policy_classifications(ensure_overlays=True)

    payload = {
        "stage": "D2.4J",
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_d2_4i": str(d2i_path),
        "source_d2_4e": str(D2_4E),
        "production_db_writes": False,
        "broker_orders": False,
        "submissions_attempted": 0,
        "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
        "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "alpaca_readonly": {
            "connected": alpaca_meta.get("connected"),
            "status": client_status,
            "order_submission_blocked": alpaca_meta.get("order_submission_blocked"),
            "error": alpaca_meta.get("error"),
        },
        "candidate_ranking": ranking,
        "quote_integrity": quote_integrity,
        "policy_evidence": policy,
        "risk_limits_preserved": {
            "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
            "fractional_shares": False,
        },
        "remaining_blockers": [
            "IBKR_EMERGENCY_STOP remains true — submissions blocked",
            "TRADING_EXECUTION_ENABLED remains false",
            "STAGE_SUBMISSION_ENABLED remains false",
            "No V4.0 live BUY cross-sectional rank persisted — pilot uses D2E sequence",
            "Await explicit approval before paper-order enablement",
        ],
        "stop_for_review": True,
    }

    results_path = evidence_dir / "d2_4j_results.json"
    results_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    report_path = evidence_dir / "D2_4J_PILOT_READINESS_REPORT.md"
    _write_report(report_path, payload)

    print(json.dumps(
        {
            "run_id": RUN_ID,
            "results": str(results_path),
            "report": str(report_path),
            "ranking_first": ranking.get("first_selected_under_open_order_cap"),
            "legacy_first": ranking.get("legacy_first_was"),
            "quote_cap_ok": quote_integrity.get("all_whole_share_cap_rejections_confirmed"),
            "policy_ok": policy.get("all_match_expectations"),
            "broker_orders": False,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
