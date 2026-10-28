"""Stage D2.4I — Real-data LIMIT proposal validation (local, non-submitting).

Loads D2.4E signals + D2.4H policy. Uses read-only Alpaca. No production writes.
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
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
)
from app.services.alpaca_readonly import try_load_readonly_client  # noqa: E402
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext  # noqa: E402
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun  # noqa: E402
from app.services.candidate_ranking import (  # noqa: E402
    describe_ranking_methodology,
    rank_candidates,
)
from app.services.d2_4i_review_resolution import (  # noqa: E402
    apply_local_review_resolutions,
    review_resolution_summary,
)
from app.services.decision_journal import DecisionJournal  # noqa: E402
from app.services.market_data_service import MarketDataService  # noqa: E402
from app.services.order_execution_service import (  # noqa: E402
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.order_proposal_engine import (  # noqa: E402
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
    build_idempotency_key,
)
from app.services.user_policy_eligibility import (  # noqa: E402
    MODE_USER_POLICY,
    classify_user_policy,
)
from app.services.us_session_freshness import (  # noqa: E402
    evaluate_signal_session_freshness,
    last_completed_us_equity_session,
)
from app.services.universe_manager import universe_manager  # noqa: E402

D2_4E = DATA_CACHE_DIR / "evidence" / "d2_4e_20261026T211547Z" / "d2_4e_results.json"
D2_4H = DATA_CACHE_DIR / "evidence" / "d2_4h_20261026T215340Z" / "d2_4h_results.json"
RUN_ID = datetime.now(timezone.utc).strftime("d2_4i_%Y%m%dT%H%M%SZ")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _rebuild_signal(detail: Dict[str, Any], scan_row: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild signal from D2.4E evidence — do not invent new BUY labels."""
    t = str(detail.get("ticker") or "").upper()
    stock = universe_manager.get_stock(t) or {}
    as_of = detail.get("market_as_of_date") or scan_row.get("as_of")
    return {
        "ticker": t,
        "name": stock.get("name") or t,
        "company_name": stock.get("name") or t,
        "sector": stock.get("sector") or "",
        "industry": stock.get("industry") or "",
        "signal": detail.get("v40_signal") or "BUY CANDIDATE",
        "signal_source": V40_SIGNAL_SOURCE,
        "strategy_version": detail.get("strategy_version") or V40_STRATEGY_VERSION,
        "entry_rule": detail.get("entry_rule") or scan_row.get("entry_rule") or "CROSS",
        "exit_rule": scan_row.get("exit_rule") or "MA250_3CLOSE",
        "is_fresh_analysis": True,
        "provenance_mode": "LIVE_SCAN",
        "market_as_of_date": as_of,
        "as_of": as_of,
        "validation_status": detail.get("validation_status") or "OK",
        "data_freshness": scan_row.get("data_freshness") or "FRESH",
        "ma250": detail.get("ma250") if detail.get("ma250") is not None else scan_row.get("ma250"),
        "ma50": detail.get("ma50") if detail.get("ma50") is not None else scan_row.get("ma50"),
        "ma30": detail.get("ma30") if detail.get("ma30") is not None else scan_row.get("ma30"),
        "roc20_pct": detail.get("roc20_pct"),
        "atr14": detail.get("atr14"),
        "shariah_status": "NOT VERIFIED",
        "signal_id": f"d2e_{t}_{as_of}",
        "scan_completed_at": "2026-10-26T21:15:47Z",
    }


def _spus_readiness(client) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ticker": "SPUS",
        "production_added": False,
        "yahoo_ohlcv_bars": None,
        "yahoo_last_date": None,
        "alpaca_asset": None,
        "alpaca_quote": None,
        "user_policy": None,
        "errors": [],
    }
    try:
        import yfinance as yf

        h = yf.Ticker("SPUS").history(period="1y")
        out["yahoo_ohlcv_bars"] = 0 if h is None else len(h)
        if h is not None and not h.empty:
            out["yahoo_last_date"] = str(h.index[-1].date())
    except Exception as exc:
        out["errors"].append(f"yahoo: {exc}")

    if client is not None:
        try:
            asset = client.adapter._get_trading_client().get_asset("SPUS")
            out["alpaca_asset"] = {
                "symbol": str(getattr(asset, "symbol", "")),
                "tradable": bool(getattr(asset, "tradable", False)),
                "status": str(getattr(asset, "status", "")),
                "exchange": str(getattr(asset, "exchange", "")),
                "asset_class": str(
                    getattr(asset, "asset_class", None) or getattr(asset, "class_", "")
                ),
            }
        except Exception as exc:
            out["errors"].append(f"alpaca_asset: {exc}")
        try:
            q = client.get_quotes(["SPUS"]).get("SPUS") or {}
            out["alpaca_quote"] = {
                "has_bid": float(q.get("bid") or 0) > 0,
                "has_ask": float(q.get("ask") or 0) > 0,
                "is_two_sided": bool(q.get("is_two_sided")),
                "source": q.get("source"),
            }
        except Exception as exc:
            out["errors"].append(f"alpaca_quote: {exc}")

    out["user_policy"] = classify_user_policy(
        "SPUS",
        name="SP Funds S&P 500 Sharia Industry Exclusions ETF",
        sector="ETFs",
        industry="Large Blend ETF",
    )
    out["ready_for_proposed_universe"] = bool(
        (out.get("yahoo_ohlcv_bars") or 0) >= 250
        and (out.get("alpaca_asset") or {}).get("tradable")
        and out["user_policy"].get("user_policy_status") == "ALLOWED"
    )
    return out


def _select_portfolio(
    ranked: List[Dict[str, Any]],
    *,
    max_orders: int,
    max_daily_notional: float,
    max_open_orders: int,
) -> Dict[str, Any]:
    selected = []
    rejected_capacity = []
    used_notional = 0.0
    for row in ranked:
        prop = row.get("simulated_proposal") or {}
        if prop.get("status") != "SIMULATED":
            continue
        notional = float(prop.get("proposed_notional") or 0)
        if len(selected) >= max_orders:
            rejected_capacity.append({"ticker": row["ticker"], "reason": "DAILY_ORDER_CAPACITY"})
            continue
        if used_notional + notional > max_daily_notional + 1e-9:
            rejected_capacity.append({"ticker": row["ticker"], "reason": "DAILY_NOTIONAL_CAPACITY"})
            continue
        if len(selected) >= max_open_orders:
            rejected_capacity.append(
                {
                    "ticker": row["ticker"],
                    "reason": "MAX_OPEN_ORDERS_CAPACITY",
                    "note": "Queued behind open-order limit; not simultaneously executable",
                }
            )
            continue
        selected.append(
            {
                "rank": len(selected) + 1,
                "ticker": row["ticker"],
                "quantity": prop.get("proposed_quantity"),
                "limit_price": prop.get("proposed_limit_price"),
                "notional": prop.get("proposed_notional"),
                "idempotency_key": prop.get("idempotency_key"),
                "entry_rule": row.get("entry_rule"),
                "actionable_now": False,  # emergency stop + flags still block submission
            }
        )
        used_notional += notional

    return {
        "selected_proposals": selected,
        "capacity_deferred": rejected_capacity,
        "selected_count": len(selected),
        "selected_notional": round(used_notional, 2),
        "limits": {
            "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
            "max_daily_orders": max_orders,
            "max_daily_notional_usd": max_daily_notional,
            "max_open_orders": max_open_orders,
        },
    }


def main() -> int:
    started = datetime.now(timezone.utc)
    evidence_dir = DATA_CACHE_DIR / "evidence" / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    review_write = apply_local_review_resolutions()

    d2e = _load_json(D2_4E)
    d2h = _load_json(D2_4H)
    buy_details = {str(x["ticker"]).upper(): x for x in (d2e.get("buy_ready_details") or [])}
    scan_by = {
        str(r.get("ticker", "")).upper(): r for r in (d2e.get("scan_rows") or []) if r.get("ticker")
    }
    policy_rows = {
        str(r["ticker"]).upper(): r for r in (d2h.get("buy_candidates_eligibility") or [])
    }
    allowed_tickers = [
        t for t, r in policy_rows.items() if r.get("user_policy_status") == "ALLOWED"
    ]

    expected_session = last_completed_us_equity_session(started)
    session, session_detail = MarketDataService.get_market_session(started)

    # Freshness of D2.4E signals (do not refresh BUY list)
    freshness_common = None
    if buy_details:
        sample_as_of = next(iter(buy_details.values())).get("market_as_of_date")
        freshness_common = evaluate_signal_session_freshness(sample_as_of, now_utc=started)

    signals_stale = not (freshness_common and freshness_common[0])
    freshness_report = {
        "evaluated_at_utc": started.isoformat(),
        "market_session": session,
        "session_detail": session_detail,
        "expected_last_completed_session": expected_session.isoformat(),
        "d2e_market_as_of": freshness_common[2].isoformat() if freshness_common and freshness_common[2] else None,
        "is_fresh": bool(freshness_common and freshness_common[0]),
        "reason_code": freshness_common[1] if freshness_common else "MISSING",
        "actionable_proposals_permitted": bool(freshness_common and freshness_common[0]),
    }

    client, client_status = try_load_readonly_client()
    account: Optional[AccountSnapshot] = None
    alpaca_meta: Dict[str, Any] = {"connected": False, "status": client_status}
    quotes: Dict[str, Dict[str, Any]] = {}

    if client is not None:
        try:
            alpaca_meta = client.validate_readonly()
            account = client.get_account_snapshot()
            quotes = client.get_quotes(allowed_tickers + ["SPUS", "CRM", "PLTR", "SPY", "XLP", "SOXX"])
        except Exception as exc:
            alpaca_meta["error"] = f"{type(exc).__name__}: {exc}"

    spus = _spus_readiness(client)

    # Re-classify review tickers after local evidence write
    review_after = {}
    for t in ("CRM", "PLTR", "SPY", "XLP", "SOXX"):
        stock = universe_manager.get_stock(t) or {
            "name": t,
            "sector": "ETFs" if t in ("SPY", "XLP", "SOXX") else "Technology",
            "industry": "",
        }
        if t == "SPUS":
            continue
        review_after[t] = classify_user_policy(
            t,
            name=stock.get("name"),
            sector=stock.get("sector"),
            industry=stock.get("industry")
            or ("Large Blend ETF" if t == "SPY" else "Sector Staples ETF" if t == "XLP" else "Semiconductor ETF" if t == "SOXX" else "Equity"),
        )

    journal = DecisionJournal(journal_dir=evidence_dir / "journal")
    pipeline = BuyPipelineDryRun(journal=journal)

    candidate_results: List[Dict[str, Any]] = []
    for t in allowed_tickers:
        detail = buy_details.get(t) or {}
        scan = scan_by.get(t) or {}
        if not detail:
            candidate_results.append(
                {
                    "ticker": t,
                    "error": "MISSING_D2E_BUY_DETAIL",
                    "simulated_proposal": None,
                }
            )
            continue

        sig = _rebuild_signal(detail, scan)
        fresh_ok, fresh_code, as_of_d, expected_d = evaluate_signal_session_freshness(
            sig.get("market_as_of_date"), now_utc=started
        )
        policy = classify_user_policy(
            t,
            name=sig.get("name"),
            sector=sig.get("sector"),
            industry=sig.get("industry"),
        )
        quote = quotes.get(t)
        quote_ok = bool(
            quote
            and float(quote.get("bid") or 0) > 0
            and float(quote.get("ask") or 0) > 0
            and float(quote.get("ask") or 0) >= float(quote.get("bid") or 0)
            and not quote.get("is_synthetic")
            and not quote.get("is_delayed")
        )

        ctx = DecisionContext(
            account=account,
            broker_quote=quote if quote_ok else None,
            emergency_stop=True,  # preserve emergency stop for readiness
            execution_enabled=False,
            trading_execution_enabled=False,
            max_order_notional_usd=DEFAULT_MAX_ORDER_NOTIONAL_USD,
            max_daily_orders=DEFAULT_MAX_DAILY_ORDERS,
            max_daily_notional_usd=DEFAULT_MAX_DAILY_NOTIONAL_USD,
            max_open_orders=DEFAULT_MAX_OPEN_ORDERS,
            now_utc=started,
            eligibility_mode=MODE_USER_POLICY,
        )

        # If signals stale: evaluate investment visibility but do not treat proposals as actionable
        entry = pipeline.evaluate_signal(sig, ctx, run_id=RUN_ID, persist_journal=True)
        prop = entry.get("simulated_proposal")
        actionable = bool(
            fresh_ok
            and prop
            and prop.get("status") == "SIMULATED"
            and policy.get("proposal_permitted")
        )
        # Operational readiness still blocked by emergency stop
        if not fresh_ok:
            prop = None  # do not create actionable proposals when stale
            entry["simulated_proposal"] = None
            entry["stale_signal_blocks_actionable_proposal"] = True

        candidate_results.append(
            {
                "ticker": t,
                "v40_signal": sig.get("signal"),
                "entry_rule": sig.get("entry_rule"),
                "strategy_version": sig.get("strategy_version"),
                "market_as_of_date": sig.get("market_as_of_date"),
                "signal_id": sig.get("signal_id"),
                "freshness": {
                    "is_fresh": fresh_ok,
                    "reason_code": fresh_code,
                    "expected_session": expected_d.isoformat() if expected_d else None,
                },
                "user_policy_status": policy.get("user_policy_status"),
                "policy_reason_codes": policy.get("reason_codes"),
                "quote": {
                    "available": quote is not None,
                    "valid_two_sided": quote_ok,
                    "bid": (quote or {}).get("bid"),
                    "ask": (quote or {}).get("ask"),
                    "source": (quote or {}).get("source"),
                    "is_two_sided": (quote or {}).get("is_two_sided"),
                },
                "investment_decision": entry.get("investment_decision"),
                "execution_readiness": entry.get("execution_readiness"),
                "blocked_by_user_policy": entry.get("blocked_by_user_policy"),
                "simulated_proposal": (
                    None
                    if not fresh_ok
                    else (prop if (prop and prop.get("status") == "SIMULATED") else None)
                ),
                "sizing_block": None if not fresh_ok else entry.get("sizing_block"),
                "actionable_proposal": False,  # emergency stop + flags always block actionable
                "dry_run_proposal_generated": bool(
                    fresh_ok and prop and prop.get("status") == "SIMULATED"
                ),
                "submission_attempted": False,
            }
        )

    # For portfolio selection use dry-run simulated props even if emergency stop blocks actionable
    # but require session-fresh + valid sizing
    selectable = []
    for row in candidate_results:
        if not row.get("freshness", {}).get("is_fresh"):
            continue
        # Re-run sizing-only path to capture SIMULATED even when we nulled for stale
        # (already handled). Use existing simulated_proposal if present.
        if row.get("dry_run_proposal_generated") or (
            row.get("simulated_proposal") or {}
        ).get("status") == "SIMULATED":
            selectable.append(row)
        else:
            # Attempt isolated sizing for reporting if quote valid and policy allowed
            if (
                row.get("user_policy_status") == "ALLOWED"
                and row.get("quote", {}).get("valid_two_sided")
                and account is not None
            ):
                detail = buy_details.get(row["ticker"]) or {}
                scan = scan_by.get(row["ticker"]) or {}
                sig = _rebuild_signal(detail, scan)
                ctx = DecisionContext(
                    account=account,
                    broker_quote=quotes.get(row["ticker"]),
                    emergency_stop=True,
                    execution_enabled=False,
                    trading_execution_enabled=False,
                    now_utc=started,
                    eligibility_mode=MODE_USER_POLICY,
                )
                entry = pipeline.evaluate_signal(
                    sig, ctx, run_id=f"{RUN_ID}_resize", persist_journal=False
                )
                if (entry.get("simulated_proposal") or {}).get("status") == "SIMULATED":
                    row["simulated_proposal"] = entry["simulated_proposal"]
                    row["dry_run_proposal_generated"] = True
                    row["investment_decision"] = entry.get("investment_decision")
                    row["execution_readiness"] = entry.get("execution_readiness")
                    selectable.append(row)

    simulated_rows = [
        r
        for r in candidate_results
        if (r.get("simulated_proposal") or {}).get("status") == "SIMULATED"
    ]
    ranked = rank_candidates(
        simulated_rows,
        buy_ready_details=d2e.get("buy_ready_details") or [],
    )
    portfolio = _select_portfolio(
        ranked,
        max_orders=DEFAULT_MAX_DAILY_ORDERS,
        max_daily_notional=DEFAULT_MAX_DAILY_NOTIONAL_USD,
        max_open_orders=DEFAULT_MAX_OPEN_ORDERS,
    )

    rejected = [
        {
            "ticker": r["ticker"],
            "investment": (r.get("investment_decision") or {}).get("classification"),
            "execution_readiness": (r.get("execution_readiness") or {}).get("execution_readiness"),
            "reasons": (
                (r.get("investment_decision") or {}).get("reason_codes")
                or (r.get("execution_readiness") or {}).get("reason_codes")
                or []
            ),
            "quote_valid": r.get("quote", {}).get("valid_two_sided"),
            "policy": r.get("user_policy_status"),
            "no_simulated_proposal": not r.get("dry_run_proposal_generated"),
        }
        for r in candidate_results
        if (r.get("simulated_proposal") or {}).get("status") != "SIMULATED"
    ]

    payload = {
        "stage": "D2.4I",
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_db_writes": False,
        "broker_orders": False,
        "submissions_attempted": 0,
        "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
        "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "freshness": freshness_report,
        "signals_stale": signals_stale,
        "alpaca_readonly": {
            "connected": alpaca_meta.get("connected"),
            "account": alpaca_meta.get("account"),
            "positions_count": alpaca_meta.get("positions_count"),
            "open_orders_count": alpaca_meta.get("open_orders_count"),
            "order_submission_blocked": alpaca_meta.get("order_submission_blocked"),
            "market_session": alpaca_meta.get("market_session"),
            "error": alpaca_meta.get("error"),
        },
        "risk_limits": {
            "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
            "max_daily_orders": DEFAULT_MAX_DAILY_ORDERS,
            "max_daily_notional_usd": DEFAULT_MAX_DAILY_NOTIONAL_USD,
            "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
            "cash_only": True,
            "long_only": True,
            "no_margin": True,
        },
        "allowed_candidates_evaluated": len(candidate_results),
        "candidate_results": candidate_results,
        "simulated_proposal_count": sum(
            1
            for r in candidate_results
            if (r.get("simulated_proposal") or {}).get("status") == "SIMULATED"
        ),
        "rejected_candidates": rejected,
        "portfolio_selection": portfolio,
        "ranking_method": describe_ranking_methodology(),
        "review_resolution": {
            "local_evidence_write": review_write,
            "summary": review_resolution_summary(),
            "reclassified": review_after,
        },
        "spus_readiness": spus,
        "remaining_blockers": [
            "IBKR_EMERGENCY_STOP remains true — submissions blocked",
            "TRADING_EXECUTION_ENABLED / ALPACA_EXECUTION_ENABLED remain false",
            "max_open_orders=1 limits simultaneous executable proposals to 1",
            "Off-hours IEX quotes may lack ask → INVALID_QUOTE / no sizing for some names",
            "SPUS not added to production universe (proposal only)",
            "Session-fresh actionable submission still requires regular-session quotes + flags",
        ],
    }

    (evidence_dir / "d2_4i_results.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    md = _markdown(payload)
    (evidence_dir / "D2_4I_REAL_DATA_PROPOSAL_VALIDATION_REPORT.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[D2.4I] Evidence: {evidence_dir}")
    return 0


def _markdown(p: Dict[str, Any]) -> str:
    fr = p.get("freshness") or {}
    al = p.get("alpaca_readonly") or {}
    port = p.get("portfolio_selection") or {}
    lines = [
        "# D2.4I — Real-Data Proposal Validation",
        "",
        f"Run ID: `{p.get('run_id')}`",
        "",
        "## Signal freshness",
        "",
        f"- Fresh: **{fr.get('is_fresh')}** (`{fr.get('reason_code')}`)",
        f"- D2.4E as_of: `{fr.get('d2e_market_as_of')}` expected: `{fr.get('expected_last_completed_session')}`",
        f"- Session: `{fr.get('market_session')}`",
        f"- Actionable proposals permitted by freshness: **{fr.get('actionable_proposals_permitted')}**",
        "",
        "## Alpaca read-only",
        "",
        f"- Connected: **{al.get('connected')}** positions={al.get('positions_count')} "
        f"open_orders={al.get('open_orders_count')}",
        f"- Submission blocked: **{al.get('order_submission_blocked')}**",
        f"- Account: `{json.dumps(al.get('account'))}`",
        "",
        f"## Candidates evaluated: {p.get('allowed_candidates_evaluated')}",
        f"## Simulated proposals: {p.get('simulated_proposal_count')}",
        "",
        "### Simulated LIMIT proposals (dry-run, non-submitting)",
        "",
    ]
    for r in p.get("candidate_results") or []:
        prop = r.get("simulated_proposal") or {}
        if prop.get("status") != "SIMULATED":
            continue
        lines.append(
            f"- **{r.get('ticker')}**: qty={prop.get('proposed_quantity')} "
            f"limit={prop.get('proposed_limit_price')} notional={prop.get('proposed_notional')} "
            f"entry={r.get('entry_rule')} idem={prop.get('idempotency_key')}"
        )
    lines += [
        "",
        "### Portfolio selection (risk-constrained)",
        "",
        f"- Selected for simultaneous capacity: **{port.get('selected_count')}** "
        f"notional=${port.get('selected_notional')}",
        f"- Limits: `{json.dumps(port.get('limits'))}`",
        f"- Ranking: {p.get('ranking_method')}",
        "",
    ]
    for s in port.get("selected_proposals") or []:
        lines.append(
            f"- #{s.get('rank')} **{s.get('ticker')}** qty={s.get('quantity')} "
            f"limit={s.get('limit_price')} notional={s.get('notional')} "
            f"idem={s.get('idempotency_key')} actionable_now={s.get('actionable_now')}"
        )
    if port.get("capacity_deferred"):
        lines.append("")
        lines.append("Deferred by capacity (would size, but open-order/daily caps):")
        for d in port.get("capacity_deferred") or []:
            lines.append(f"- **{d.get('ticker')}**: {d.get('reason')}")
    lines += ["", "### Rejected / no proposal", ""]
    for r in p.get("rejected_candidates") or []:
        lines.append(
            f"- **{r.get('ticker')}**: policy={r.get('policy')} quote_valid={r.get('quote_valid')} "
            f"readiness={r.get('execution_readiness')} reasons={r.get('reasons')}"
        )
    lines += ["", "## Review resolutions", ""]
    for r in (p.get("review_resolution") or {}).get("summary") or []:
        lines.append(
            f"- **{r.get('ticker')}** → `{r.get('resolved_status')}` {r.get('reason_codes')}"
        )
    spus = p.get("spus_readiness") or {}
    lines += [
        "",
        "## SPUS readiness",
        "",
        f"- Yahoo bars: **{spus.get('yahoo_ohlcv_bars')}** last={spus.get('yahoo_last_date')}",
        f"- Alpaca asset: `{json.dumps(spus.get('alpaca_asset'))}`",
        f"- Policy: `{(spus.get('user_policy') or {}).get('user_policy_status')}`",
        f"- Ready for proposed universe (not production): **{spus.get('ready_for_proposed_universe')}**",
        f"- Production added: **{spus.get('production_added')}**",
        "",
        "## Remaining blockers",
        "",
    ]
    for b in p.get("remaining_blockers") or []:
        lines.append(f"- {b}")
    lines += [
        "",
        f"Emergency stop={p.get('ibkr_emergency_stop')} "
        f"execution_enabled={p.get('trading_execution_enabled')} "
        f"submissions={p.get('submissions_attempted')}",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
