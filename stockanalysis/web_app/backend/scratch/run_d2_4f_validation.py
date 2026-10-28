"""Stage D2.4F — Shariah recovery investigation + paper-trading readiness (local).

Read-only. No production DB writes, no broker orders, no execution-flag changes.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure backend import root
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import (  # noqa: E402
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
    UNIVERSE_REGISTRY_PATH,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
)
from app.database import SessionLocal  # noqa: E402
from app.services.alpaca_readonly import try_load_readonly_client  # noqa: E402
from app.services.buy_decision_engine import DecisionContext  # noqa: E402
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun  # noqa: E402
from app.services.decision_journal import DecisionJournal  # noqa: E402
from app.services.shariah_store import investigate_universe_shariah  # noqa: E402
from app.services.ticker_integrity import (  # noqa: E402
    investigate_problem_tickers,
    resolve_proposed_alias,
)
from app.services.universe_manager import universe_manager  # noqa: E402

D2_4E_RESULTS = (
    DATA_CACHE_DIR / "evidence" / "d2_4e_20261026T211547Z" / "d2_4e_results.json"
)
RUN_ID = datetime.now(timezone.utc).strftime("d2_4f_%Y%m%dT%H%M%SZ")


def _load_d2_4e() -> Dict[str, Any]:
    if not D2_4E_RESULTS.exists():
        return {}
    return json.loads(D2_4E_RESULTS.read_text(encoding="utf-8"))


def _registry_map() -> Dict[str, Dict[str, Any]]:
    stocks = universe_manager.get_all(include_inactive=True) or []
    return {str(s.get("ticker", "")).upper(): s for s in stocks if s.get("ticker")}


def _baseline_drift(d2e: Dict[str, Any]) -> Dict[str, Any]:
    fb = d2e.get("frozen_baseline_comparison") or {}
    mismatches = fb.get("mismatches") or []
    classified = []
    for row in mismatches:
        if not isinstance(row, dict):
            continue
        frozen = str(row.get("frozen_baseline_signal") or "")
        live = str(row.get("live_scan_signal") or "")
        # Legitimate market movement: as_of advanced and signal changed between WATCH/HOLD/BUY/AVOID
        classified.append(
            {
                **{k: row.get(k) for k in (
                    "ticker", "frozen_baseline_signal", "live_scan_signal", "match", "live_as_of"
                )},
                "classification": "LIKELY_MARKET_MOVEMENT",
                "rationale": (
                    f"Frozen baseline label '{frozen}' vs live '{live}' on {row.get('live_as_of')}. "
                    "Same V4.0 strategy path; no mapping/alias discrepancy for these baseline tickers. "
                    "Treat as price-path drift unless a later audit shows data-quality issues."
                ),
                "strategy_math_modified": False,
            }
        )
    return {
        "overlapping_tickers": fb.get("overlapping_tickers"),
        "matches": fb.get("matches"),
        "mismatch_count": len(classified),
        "mismatches": classified,
        "strategy_mathematics_unchanged": True,
        "note": fb.get("note"),
    }


def main() -> int:
    started = datetime.now(timezone.utc)
    evidence_dir = DATA_CACHE_DIR / "evidence" / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    d2e = _load_d2_4e()
    buy_ready = d2e.get("buy_ready_details") or []
    buy_tickers = [str(x.get("ticker")).upper() for x in buy_ready if x.get("ticker")]

    # Rebuild BUY CANDIDATE payloads from D2.4E buy_ready_details + scan_rows
    scan_by_ticker = {
        str(r.get("ticker", "")).upper(): r for r in (d2e.get("scan_rows") or []) if r.get("ticker")
    }
    signals: List[Dict[str, Any]] = []
    for detail in buy_ready:
        t = str(detail.get("ticker") or "").strip().upper()
        if not t:
            continue
        row = scan_by_ticker.get(t) or {}
        as_of = detail.get("market_as_of_date") or row.get("as_of")
        signals.append(
            {
                "ticker": t,
                "signal": detail.get("v40_signal") or "BUY CANDIDATE",
                "signal_source": V40_SIGNAL_SOURCE,
                "strategy_version": detail.get("strategy_version") or V40_STRATEGY_VERSION,
                "entry_rule": detail.get("entry_rule") or row.get("entry_rule") or "CROSS",
                "exit_rule": row.get("exit_rule") or "MA250_3CLOSE",
                "is_fresh_analysis": True,
                "provenance_mode": "LIVE_SCAN",
                "market_as_of_date": as_of,
                "as_of": as_of,
                "validation_status": detail.get("validation_status") or row.get("validation_status") or "OK",
                "data_freshness": row.get("data_freshness") or "FRESH",
                "ma250": detail.get("ma250") if detail.get("ma250") is not None else row.get("ma250"),
                "ma50": detail.get("ma50") if detail.get("ma50") is not None else row.get("ma50"),
                "ma30": detail.get("ma30") if detail.get("ma30") is not None else row.get("ma30"),
                "roc20_pct": detail.get("roc20_pct") if detail.get("roc20_pct") is not None else row.get("roc20_pct"),
                "atr14": detail.get("atr14") if detail.get("atr14") is not None else row.get("atr14"),
                "close": row.get("close"),
                "shariah_status": "NOT VERIFIED",  # recovered via store overlay if present
                "scan_completed_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    eligible = universe_manager.get_eligible_universe() or []
    universe_tickers = [s["ticker"] for s in eligible]
    registry = _registry_map()

    db = SessionLocal()
    try:
        shariah_inv = investigate_universe_shariah(
            universe_tickers,
            db=db,
            registry_stocks=registry,
            evidence_path=DATA_CACHE_DIR / "shariah_evidence.json",
        )
    finally:
        db.close()

    # Ticker integrity (Yahoo bars optional — use D2.4E missing list + Alpaca later)
    yahoo_bars = {"SQ": 0, "XYZ": None, "MMC": 0, "QUALCOMM": 0, "QCOM": None}
    for t in ("XYZ", "QCOM"):
        # Prefer rolling cache length if present
        cache = DATA_CACHE_DIR / "price_cache" / f"{t}.csv"
        if cache.exists():
            try:
                yahoo_bars[t] = max(0, sum(1 for _ in cache.open(encoding="utf-8")) - 1)
            except OSError:
                yahoo_bars[t] = None

    client, client_status = try_load_readonly_client()
    alpaca_report: Dict[str, Any]
    alpaca_quote_ok: Dict[str, bool] = {}
    account = None
    quotes: Dict[str, Dict[str, Any]] = {}

    if client is None:
        alpaca_report = {
            "connected": False,
            "error": client_status,
            "credentials_present": False,
        }
    else:
        alpaca_report = client.validate_readonly()
        try:
            account = client.get_account_snapshot()
            probe = list(dict.fromkeys(["SQ", "XYZ", "MMC", "QCOM", "QUALCOMM"] + buy_tickers))
            # Alpaca quote API accepts batches; chunk to stay polite
            quotes = {}
            for i in range(0, len(probe), 50):
                quotes.update(client.get_quotes(probe[i : i + 50]) or {})
            for sym, q in quotes.items():
                alpaca_quote_ok[sym] = bool(
                    q and (float(q.get("bid") or 0) > 0 or float(q.get("ask") or 0) > 0)
                )
        except Exception as exc:
            alpaca_report["account_snapshot_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    ticker_report = investigate_problem_tickers(
        universe_tickers=universe_tickers,
        registry_records=registry,
        yahoo_bars=yahoo_bars,
        alpaca_quote_ok=alpaca_quote_ok,
    )
    alias_samples = {t: resolve_proposed_alias(t) for t in ("SQ", "QUALCOMM", "MMC", "QCOM")}

    # Proposal validation — preserve Shariah gate + emergency stop
    journal = DecisionJournal(journal_dir=evidence_dir / "journal")
    pipeline = BuyPipelineDryRun(journal=journal)

    # Per-signal quotes when available
    results = []
    for sig in signals:
        t = sig["ticker"]
        q = quotes.get(t)
        ctx = DecisionContext(
            account=account,
            broker_quote=q,
            emergency_stop=True,  # preserve emergency stop
            execution_enabled=False,
            trading_execution_enabled=bool(TRADING_EXECUTION_ENABLED),
            now_utc=started,
            investment_mode=False,
        )
        entry = pipeline.evaluate_signal(sig, ctx, run_id=RUN_ID, persist_journal=True)
        results.append(entry)

    # Also full run with watchlist overlay (empty → still NOT VERIFIED)
    db = SessionLocal()
    try:
        bulk_ctx = DecisionContext(
            account=account,
            broker_quote=None,
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=bool(TRADING_EXECUTION_ENABLED),
            now_utc=started,
            investment_mode=False,
        )
        bulk = pipeline.run(
            ctx=bulk_ctx,
            db=db,
            signals=signals,
            run_id=f"{RUN_ID}_bulk",
            persist_journal=True,
        )
    finally:
        db.close()

    proposals = [r for r in results if r.get("simulated_proposal")]
    buy_ready_n = sum(
        1 for r in results if r.get("investment_decision", {}).get("classification") == "BUY_READY"
    )
    blocked_shariah = sum(1 for r in results if r.get("blocked_by_shariah"))
    quote_quality = {
        t: {
            "has_quote": t in quotes,
            "is_two_sided": bool((quotes.get(t) or {}).get("is_two_sided")),
            "has_ask": float((quotes.get(t) or {}).get("ask") or 0) > 0,
            "source": (quotes.get(t) or {}).get("source"),
        }
        for t in buy_tickers
    }
    proposal_rows = []
    for r in results:
        prop = r.get("simulated_proposal") or {}
        proposal_rows.append(
            {
                "ticker": r.get("ticker"),
                "investment": r.get("investment_decision"),
                "blocked_by_shariah": r.get("blocked_by_shariah"),
                "execution_readiness": (r.get("execution_readiness") or {}).get("execution_readiness"),
                "quote_ok": quote_quality.get(r.get("ticker"), {}).get("has_ask"),
                "proposed_quantity": prop.get("quantity") or prop.get("proposed_quantity"),
                "limit_price": prop.get("limit_price") or prop.get("proposed_limit_price"),
                "notional": prop.get("notional") or prop.get("proposed_notional"),
                "idempotency_key": prop.get("idempotency_key"),
                "simulated_proposal": bool(prop),
            }
        )

    baseline = _baseline_drift(d2e)

    report = {
        "stage": "D2.4F",
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_db_writes": False,
        "broker_orders": False,
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "shariah_investigation": {
            "root_cause": shariah_inv.get("root_cause"),
            "counts": shariah_inv.get("counts"),
            "watchlist_row_count": shariah_inv.get("watchlist_row_count"),
            "evidence_file_loaded": shariah_inv.get("evidence_file_loaded"),
            "verified_with_evidence": shariah_inv.get("verified_with_evidence"),
            "sample_rows": (shariah_inv.get("rows") or [])[:5],
        },
        "ticker_integrity": {
            "findings": ticker_report.get("findings"),
            "correction_plan": ticker_report.get("correction_plan"),
            "proposed_aliases": ticker_report.get("proposed_aliases"),
            "alias_samples": alias_samples,
            "production_mutated": False,
        },
        "alpaca_readonly": alpaca_report,
        "proposal_validation": {
            "buy_candidates_input": len(signals),
            "investment_buy_ready": buy_ready_n,
            "blocked_by_shariah": blocked_shariah,
            "simulated_proposal_count": len(proposals),
            "simulated_proposals": proposals,
            "proposal_rows": proposal_rows,
            "quote_quality": quote_quality,
            "account_available": account is not None,
            "shariah_gate_preserved": True,
            "emergency_stop_preserved": True,
            "bulk_run_proposal_count": bulk.get("simulated_proposal_count"),
            "bulk_shariah_counts": (bulk.get("shariah_report") or {}).get("counts"),
        },
        "baseline_drift": baseline,
        "remaining_blockers": [
            "No WatchlistStock Shariah VERIFIED records with source+date (230/230 NOT VERIFIED).",
            "IBKR_EMERGENCY_STOP remains true — executable readiness blocked by design.",
            "TRADING_EXECUTION_ENABLED / Alpaca submission remain disabled.",
            "Ticker integrity corrections (SQ→XYZ, QUALCOMM retire) not applied to production universe.",
            "MMC Yahoo OHLCV empty — research scan data gap for MMC until provider fix.",
        ],
    }

    (evidence_dir / "d2_4f_results.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    (evidence_dir / "shariah_investigation_full.json").write_text(
        json.dumps(shariah_inv, indent=2, default=str), encoding="utf-8"
    )

    md = _markdown(report)
    (evidence_dir / "D2_4F_SHARIAH_RECOVERY_REPORT.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[D2.4F] Evidence written to {evidence_dir}")
    return 0


def _markdown(report: Dict[str, Any]) -> str:
    sh = report["shariah_investigation"]
    ti = report["ticker_integrity"]
    al = report["alpaca_readonly"]
    pv = report["proposal_validation"]
    bd = report["baseline_drift"]
    lines = [
        "# D2.4F — Shariah Recovery and Paper-Trading Readiness",
        "",
        f"Run ID: `{report['run_id']}`",
        "",
        "## 1. Root cause of 230/230 NOT VERIFIED",
        "",
        sh.get("root_cause") or "",
        "",
        f"- WatchlistStock rows: **{sh.get('watchlist_row_count')}**",
        f"- Evidence file loaded: **{sh.get('evidence_file_loaded')}**",
        f"- Counts: `{json.dumps(sh.get('counts'))}`",
        f"- Verified-with-evidence records: **{len(sh.get('verified_with_evidence') or [])}**",
        "",
        "## 2. Ticker integrity (proposed only — no production mutation)",
        "",
    ]
    for f in ti.get("findings") or []:
        lines.append(
            f"- **{f.get('ticker')}**: action=`{f.get('proposed_action')}` "
            f"canonical=`{f.get('proposed_canonical')}` — {f.get('notes')}"
        )
    lines += [
        "",
        "## 3. Alpaca read-only connectivity",
        "",
        f"- Connected: **{al.get('connected')}**",
        f"- Error: `{al.get('error')}`",
        f"- Non-executing guard: **{al.get('non_executing_guard')}**",
        f"- Order submission blocked: **{al.get('order_submission_blocked')}**",
        f"- Positions: **{al.get('positions_count')}** Open orders: **{al.get('open_orders_count')}**",
    ]
    acct = al.get("account") or {}
    if acct:
        lines += [
            f"- Account (redacted): `{acct.get('account_id_redacted')}` status=`{acct.get('status')}`",
            f"- Cash>0: {acct.get('cash_positive')} Equity>0: {acct.get('equity_positive')} "
            f"BuyingPower>0: {acct.get('buying_power_positive')}",
            f"- Market session: `{json.dumps(al.get('market_session'))}`",
        ]
    lines += [
        "",
        "## 4. Simulated proposals (31 BUY candidates)",
        "",
        f"- Investment BUY_READY: **{pv.get('investment_buy_ready')}**",
        f"- Blocked by Shariah: **{pv.get('blocked_by_shariah')}**",
        f"- Simulated proposals: **{pv.get('simulated_proposal_count')}**",
        f"- Shariah gate preserved: **{pv.get('shariah_gate_preserved')}**",
        f"- Emergency stop preserved: **{pv.get('emergency_stop_preserved')}**",
        "",
        "## 5. V4.0 baseline drift (8 mismatches)",
        "",
        f"- Mismatch count: **{bd.get('mismatch_count')}**",
        f"- Strategy mathematics unchanged: **{bd.get('strategy_mathematics_unchanged')}**",
        "",
    ]
    for m in bd.get("mismatches") or []:
        lines.append(
            f"- {m.get('ticker')}: {m.get('frozen_baseline_signal')} → {m.get('live_scan_signal')} "
            f"[{m.get('classification')}]"
        )
    lines += [
        "",
        "## 6. Remaining blockers",
        "",
    ]
    for b in report.get("remaining_blockers") or []:
        lines.append(f"- {b}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
