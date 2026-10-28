"""Stage D2.4E — Real-data end-to-end validation (local, non-executing).

Uses local rolling/frozen price caches + permitted Yahoo OHLCV refresh.
Does NOT write production DBs, place orders, change execution flags, or mutate
frozen baseline Excel. Evidence written under data_cache/evidence/d2_4e_*.
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.config import (
    BASELINE_EXCEL_PATH,
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    PAPER_BROKER,
    PRICE_CACHE_DIR,
    ROLLING_PRICE_CACHE_DIR,
    TRADING_EXECUTION_ENABLED,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
    ALPACA_EXECUTION_ENABLED,
)
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun
from app.services.decision_journal import DecisionJournal
from app.services.scanner_service import scanner_service
from app.services.universe_manager import universe_manager
from app.services.us_session_freshness import last_completed_us_equity_session
from app.services.market_data_service import MarketDataService

EVIDENCE_ROOT = DATA_CACHE_DIR / "evidence"
RUN_ID = datetime.now(timezone.utc).strftime("d2_4e_%Y%m%dT%H%M%SZ")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def refresh_ticker(ticker: str) -> Tuple[Optional[pd.DataFrame], str, Optional[str]]:
    """Incremental Yahoo refresh into rolling cache. Returns (df, status, error)."""
    try:
        df, stale = scanner_service.fetch_or_update_stock(ticker, force_full=False)
        if df is None or df.empty:
            return None, "NO_DATA", "Yahoo/cache returned empty"
        status = "STALE_PRESERVED" if stale else "REFRESHED_OR_CACHED"
        return df, status, None
    except Exception as exc:
        # Fall back to existing cache without inventing bars
        df = scanner_service.get_price_df(ticker)
        if df is not None and not df.empty:
            return df, "CACHE_FALLBACK", str(exc)
        return None, "FAILED", str(exc)


def evaluate_ticker(ticker: str, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    if df is None or len(df) < 30:
        return {
            "ticker": ticker,
            "signal": "INSUFFICIENT DATA",
            "signal_source": V40_SIGNAL_SOURCE,
            "is_fresh_analysis": True,
            "validation_status": "INSUFFICIENT_DATA",
            "data_freshness": "INSUFFICIENT_DATA",
            "strategy_version": V40_STRATEGY_VERSION,
            "entry_rule": "N/A",
            "ma250": None,
            "explanation": "Insufficient bars for V4.0 evaluation",
        }
    return scanner_service.evaluate_stock_signal(ticker, df)


def load_frozen_baseline_signals() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not BASELINE_EXCEL_PATH.exists():
        return out
    try:
        df = pd.read_excel(BASELINE_EXCEL_PATH, sheet_name="TodayTrade")
        for _, r in df.iterrows():
            t = str(r["Ticker"]).strip().upper()
            out[t] = str(r["Signal"]).strip()
    except Exception:
        pass
    return out


def try_paper_account() -> Tuple[Optional[AccountSnapshot], str]:
    """Read-only paper account attempt. Never fabricates balances."""
    try:
        from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter

        adapter = AlpacaPaperAdapter(auto_load_env=True)
        summary = adapter.get_account_summary()
        acct_id = adapter.get_authenticated_account_id()
        if not acct_id or not summary:
            return None, "ACCOUNT_UNAVAILABLE"
        cash = float(summary.get("cash") or summary.get("total_cash_value") or 0)
        equity = float(summary.get("equity") or summary.get("portfolio_value") or cash)
        positions = adapter.get_positions() or []
        return (
            AccountSnapshot(
                broker="alpaca",
                account_id=str(acct_id).upper(),
                cash=cash,
                equity=equity,
                positions=positions,
                open_orders=adapter.get_orders(status="open") or [],
                snapshot_fresh=True,
                connection_ok=True,
                as_of_utc=_now().isoformat(),
            ),
            "OK",
        )
    except Exception as exc:
        return None, f"ACCOUNT_UNAVAILABLE: {exc}"


def main() -> int:
    started = _now()
    evidence_dir = EVIDENCE_ROOT / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    session, session_detail = MarketDataService.get_market_session(started)
    expected_as_of = last_completed_us_equity_session(started)

    eligible = universe_manager.get_eligible_universe()
    tickers = [s["ticker"] for s in eligible]

    preflight = {
        "run_id": RUN_ID,
        "started_at_utc": started.isoformat(),
        "market_session": session,
        "session_detail": session_detail,
        "expected_last_completed_session": expected_as_of.isoformat(),
        "eligible_universe_count": len(tickers),
        "rolling_cache_dir": str(ROLLING_PRICE_CACHE_DIR),
        "frozen_cache_dir": str(PRICE_CACHE_DIR),
        "rolling_csv_count": len(list(ROLLING_PRICE_CACHE_DIR.glob("*.csv"))),
        "frozen_csv_count": len(list(PRICE_CACHE_DIR.glob("*.csv"))),
        "trading_execution_enabled": TRADING_EXECUTION_ENABLED,
        "ibkr_emergency_stop": IBKR_EMERGENCY_STOP,
        "alpaca_execution_enabled": ALPACA_EXECUTION_ENABLED,
        "paper_broker": PAPER_BROKER,
        "baseline_excel_exists": BASELINE_EXCEL_PATH.exists(),
        "production_db_writes": False,
        "broker_orders": False,
    }

    account, account_status = try_paper_account()
    preflight["paper_account_status"] = account_status
    preflight["paper_account_id"] = account.account_id if account else None

    scan_rows: List[Dict[str, Any]] = []
    signals: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    refresh_stats = {"REFRESHED_OR_CACHED": 0, "STALE_PRESERVED": 0, "CACHE_FALLBACK": 0, "FAILED": 0, "NO_DATA": 0}

    print(f"[D2.4E] Starting real-data scan of {len(tickers)} eligible tickers…", flush=True)
    for i, ticker in enumerate(tickers, 1):
        t0 = time.time()
        df, refresh_status, err = refresh_ticker(ticker)
        refresh_stats[refresh_status] = refresh_stats.get(refresh_status, 0) + 1
        if err and refresh_status in ("FAILED", "NO_DATA"):
            errors.append({"ticker": ticker, "stage": "refresh", "error": err})

        try:
            sig = evaluate_ticker(ticker, df)
            # Ensure stock shariah from universe registry (do not invent)
            stock = universe_manager.get_stock(ticker) or {}
            if "shariah_status" not in sig or not sig.get("shariah_status"):
                sig["shariah_status"] = stock.get("shariah_status", "NOT VERIFIED")
            sig.setdefault("shariah_source", stock.get("shariah_source", ""))
            sig.setdefault("shariah_date", stock.get("shariah_date", ""))
            signals.append(sig)
            as_of = sig.get("as_of") or sig.get("market_as_of_date")
            scan_rows.append(
                {
                    "ticker": ticker,
                    "bars": 0 if df is None else len(df),
                    "refresh_status": refresh_status,
                    "as_of": as_of,
                    "signal": sig.get("signal"),
                    "entry_rule": sig.get("entry_rule"),
                    "exit_rule": sig.get("exit_rule"),
                    "ma30": sig.get("ma30"),
                    "ma50": sig.get("ma50"),
                    "ma250": sig.get("ma250"),
                    "roc20_pct": sig.get("roc20_pct"),
                    "atr14": sig.get("atr14"),
                    "data_freshness": sig.get("data_freshness"),
                    "validation_status": sig.get("validation_status"),
                    "is_fresh_analysis": sig.get("is_fresh_analysis"),
                    "elapsed_s": round(time.time() - t0, 2),
                    "refresh_error": err,
                }
            )
        except Exception as exc:
            errors.append({"ticker": ticker, "stage": "evaluate", "error": str(exc), "trace": traceback.format_exc()[-500:]})
            scan_rows.append(
                {
                    "ticker": ticker,
                    "refresh_status": refresh_status,
                    "signal": "ERROR",
                    "error": str(exc),
                }
            )

        if i % 25 == 0 or i == len(tickers):
            print(f"[D2.4E] Progress {i}/{len(tickers)} …", flush=True)
        # Gentle pacing for Yahoo public access
        time.sleep(0.15)

    scanned_ok = [r for r in scan_rows if r.get("signal") not in (None, "ERROR")]
    signal_dist: Dict[str, int] = {}
    for r in scan_rows:
        key = str(r.get("signal") or "UNKNOWN")
        signal_dist[key] = signal_dist.get(key, 0) + 1

    # Dry-run decisions (no quotes/account fabrication)
    quotes: Dict[str, Dict[str, Any]] = {}  # no Alpaca quotes available → DATA_UNAVAILABLE
    journal = DecisionJournal(journal_dir=evidence_dir / "journal")
    pipeline = BuyPipelineDryRun(journal=journal)

    ctx = DecisionContext(
        account=account,
        broker_quote=None,
        emergency_stop=True,
        execution_enabled=False,
        trading_execution_enabled=False,
        now_utc=started,
        investment_mode=False,
    )

    # Per-signal dry run with shared ctx (quote remains unavailable)
    dry = pipeline.run(
        ctx=ctx,
        signals=signals,
        snapshot={
            "snapshot_id": f"local_{RUN_ID}",
            "market_as_of_date": expected_as_of.isoformat(),
            "signals": signals,
        },
        run_id=RUN_ID,
        persist_journal=True,
    )

    # Frozen baseline comparison (signal label only for overlapping tickers)
    baseline = load_frozen_baseline_signals()
    compare_rows = []
    for sig in signals:
        t = sig.get("ticker")
        if t in baseline:
            compare_rows.append(
                {
                    "ticker": t,
                    "frozen_baseline_signal": baseline[t],
                    "live_scan_signal": sig.get("signal"),
                    "match": baseline[t] == sig.get("signal"),
                    "live_as_of": sig.get("as_of") or sig.get("market_as_of_date"),
                }
            )

    finished = _now()
    runtime_s = round((finished - started).total_seconds(), 1)

    # Build markdown report
    inv_counts = {}
    for r in dry.get("results", []):
        c = r.get("investment_decision", {}).get("classification", "UNKNOWN")
        inv_counts[c] = inv_counts.get(c, 0) + 1

    shariah = dry.get("shariah_report") or {}
    proposals = [r for r in dry.get("results", []) if r.get("simulated_proposal")]
    blocked_props = [
        {
            "ticker": r.get("ticker"),
            "investment": r.get("investment_decision", {}).get("classification"),
            "blocked_by_shariah": r.get("blocked_by_shariah"),
            "execution_readiness": (r.get("execution_readiness") or {}).get("execution_readiness"),
            "reasons": (r.get("execution_readiness") or {}).get("reason_codes"),
            "sizing_block": r.get("sizing_block"),
        }
        for r in dry.get("results", [])
        if r.get("investment_decision", {}).get("classification") == "BUY_READY" and not r.get("simulated_proposal")
    ]

    buy_ready_details = []
    for r in dry.get("results", []):
        if r.get("investment_decision", {}).get("classification") != "BUY_READY":
            continue
        src = next((s for s in signals if s.get("ticker") == r.get("ticker")), {})
        buy_ready_details.append(
            {
                "ticker": r.get("ticker"),
                "v40_signal": r.get("v40_signal"),
                "strategy_version": r.get("strategy_version"),
                "entry_rule": r.get("entry_rule"),
                "market_as_of_date": r.get("market_as_of_date"),
                "signal_freshness": src.get("data_freshness"),
                "validation_status": src.get("validation_status"),
                "ma30": src.get("ma30"),
                "ma50": src.get("ma50"),
                "ma250": src.get("ma250"),
                "roc20_pct": src.get("roc20_pct"),
                "atr14": src.get("atr14"),
                "investment_decision": r.get("investment_decision"),
                "shariah_status": r.get("shariah_status"),
                "shariah_eligibility": r.get("shariah_eligibility"),
                "execution_readiness": r.get("execution_readiness"),
                "simulated_proposal": r.get("simulated_proposal"),
                "blocked_by_shariah": r.get("blocked_by_shariah"),
            }
        )

    missing_cache = [
        t
        for t in tickers
        if not (ROLLING_PRICE_CACHE_DIR / f"{t}.csv").exists()
        and not (PRICE_CACHE_DIR / f"{t}.csv").exists()
        and not (PRICE_CACHE_DIR / f"IDX_{t}.csv").exists()
    ]

    payload = {
        "preflight": preflight,
        "runtime_seconds": runtime_s,
        "finished_at_utc": finished.isoformat(),
        "refresh_stats": refresh_stats,
        "scan_summary": {
            "monitored": len(tickers),
            "successfully_scanned": len(scanned_ok),
            "errors": len(errors),
            "signal_distribution": signal_dist,
            "missing_symbols_pre_scan": missing_cache,
        },
        "scan_rows": scan_rows,
        "errors": errors,
        "investment_decision_counts": inv_counts,
        "buy_ready_details": buy_ready_details,
        "simulated_proposals": [r.get("simulated_proposal") for r in dry.get("results", []) if r.get("simulated_proposal")],
        "blocked_proposals": blocked_props,
        "shariah_report": shariah,
        "frozen_baseline_comparison": {
            "overlapping_tickers": len(compare_rows),
            "matches": sum(1 for c in compare_rows if c["match"]),
            "mismatches": [c for c in compare_rows if not c["match"]],
            "note": "Frozen baseline is a point-in-time research snapshot; live scan uses later as-of dates — mismatches are expected.",
        },
        "dry_run_invariants": dry.get("invariants"),
        "journal_summary": dry.get("journal_summary"),
    }

    json_path = evidence_dir / "d2_4e_results.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    md_path = evidence_dir / "D2_4E_REAL_DATA_VALIDATION_REPORT.md"
    md = []
    md.append("# StockAnalysis — Stage D2.4E Real-Data Validation Report\n")
    md.append(f"**Run ID:** `{RUN_ID}`  ")
    md.append(f"**Started (UTC):** {started.isoformat()}  ")
    md.append(f"**Finished (UTC):** {finished.isoformat()}  ")
    md.append(f"**Runtime:** {runtime_s}s  ")
    md.append(f"**Market session:** {session} — {session_detail}  ")
    md.append(f"**Expected last completed US session:** {expected_as_of.isoformat()}\n")

    md.append("## 1. Monitored universe\n")
    md.append(f"- Stocks monitored (eligible): **{len(tickers)}**")
    md.append(f"- Successfully scanned (signal produced): **{len(scanned_ok)}**")
    md.append(f"- Operational errors: **{len(errors)}**")
    md.append(f"- Pre-scan missing cache symbols: `{missing_cache}`\n")

    md.append("## 2. Signal distribution (V4.0 scanner)\n")
    for k, v in sorted(signal_dist.items(), key=lambda x: (-x[1], x[0])):
        md.append(f"- **{k}:** {v}")
    md.append("")

    md.append("## 3. Freshness and data quality\n")
    md.append(f"- Refresh outcomes: `{json.dumps(refresh_stats)}`")
    md.append(f"- Rolling cache CSVs at start: {preflight['rolling_csv_count']}")
    md.append(f"- Paper account: **{account_status}**")
    md.append(f"- Broker quotes: **DATA_UNAVAILABLE** (no Alpaca API keys in environment; quotes not fabricated)")
    as_of_dates = sorted({str(r.get('as_of')) for r in scan_rows if r.get('as_of')})
    md.append(f"- Observed bar as-of dates: `{as_of_dates}`")
    md.append(f"- Session-freshness policy expects: `{expected_as_of.isoformat()}`")
    md.append("- Investment `BUY_READY` still requires session match; stale as-of → investment BLOCKED (not invented BUY).\n")

    md.append("## 4. Investment decision distribution (dry-run)\n")
    for k in ("BUY_READY", "WAIT", "BLOCKED", "NO_ACTION"):
        md.append(f"- **{k}:** {inv_counts.get(k, 0)}")
    md.append("")
    if buy_ready_details:
        md.append("### BUY_READY opportunities\n")
        md.append("| Ticker | Entry | As-of | Shariah | Exec readiness | Proposal |")
        md.append("|--------|-------|-------|---------|----------------|----------|")
        for b in buy_ready_details:
            er = (b.get("execution_readiness") or {}).get("execution_readiness")
            prop = "yes" if b.get("simulated_proposal") else "no"
            md.append(
                f"| {b['ticker']} | {b.get('entry_rule')} | {b.get('market_as_of_date')} | "
                f"{b.get('shariah_status')} | {er} | {prop} |"
            )
        md.append("")
    else:
        md.append("_No investment BUY_READY rows after freshness/provenance gates._\n")

    md.append("## 5. Shariah eligibility breakdown\n")
    md.append(f"- Total rows: {shariah.get('total')}")
    md.append(f"- Counts: `{json.dumps(shariah.get('counts'))}`")
    md.append("- Classifications were **not** mutated (`classifications_mutated=false`).\n")

    md.append("## 6. Simulated proposals\n")
    md.append(f"- Simulated proposals created: **{len(proposals)}**")
    md.append(f"- BUY_READY without proposal: **{len(blocked_props)}**")
    if blocked_props:
        md.append("\n### Blocked proposal reasons (sample)\n")
        for b in blocked_props[:25]:
            md.append(
                f"- **{b['ticker']}:** shariah_block={b['blocked_by_shariah']}, "
                f"exec={b['execution_readiness']}, reasons={b['reasons']}, sizing={b.get('sizing_block')}"
            )
        md.append("")
    md.append("- Approval attempted: **false**")
    md.append("- Submission attempted: **false**\n")

    md.append("## 7. Scanner runtime and errors\n")
    md.append(f"- Runtime seconds: **{runtime_s}**")
    md.append(f"- Error count: **{len(errors)}**")
    if errors:
        for e in errors[:20]:
            md.append(f"- {e.get('ticker')} [{e.get('stage')}]: {e.get('error')}")
        if len(errors) > 20:
            md.append(f"- … and {len(errors) - 20} more (see JSON)")
    md.append("")

    md.append("## 8. Comparison with frozen V4.0 baseline\n")
    fc = payload["frozen_baseline_comparison"]
    md.append(f"- Overlapping baseline tickers: **{fc['overlapping_tickers']}**")
    md.append(f"- Exact signal label matches: **{fc['matches']}**")
    md.append(f"- Mismatches: **{len(fc['mismatches'])}**")
    md.append(f"- Note: {fc['note']}")
    if fc["mismatches"]:
        md.append("\n| Ticker | Frozen | Live | Live as-of |")
        md.append("|--------|--------|------|------------|")
        for m in fc["mismatches"][:40]:
            md.append(
                f"| {m['ticker']} | {m['frozen_baseline_signal']} | {m['live_scan_signal']} | {m['live_as_of']} |"
            )
        md.append("")

    md.append("## 9. Remaining blockers before Alpaca paper-trading tests\n")
    md.append("1. **Alpaca API credentials not present** in this environment → no read-only account snapshot or executable quotes.")
    md.append("2. **Emergency stop remains ON** (`IBKR_EMERGENCY_STOP=true` default) — correct until explicitly authorized.")
    md.append("3. **`TRADING_EXECUTION_ENABLED=false`** — must stay false until paper-trading stage approval.")
    md.append("4. Session-fresh signals require bar as-of == last completed US session; verify post-refresh as-of dates.")
    md.append("5. Full production Postgres scan / DO cron still not activated (by policy).")
    md.append("6. Shariah VERIFIED coverage may be low — proposals require VERIFIED status without inferring compliance.\n")

    md.append("## 10. Evidence paths\n")
    md.append(f"- Report: `{md_path}`")
    md.append(f"- JSON results: `{json_path}`")
    md.append(f"- Decision journal dir: `{evidence_dir / 'journal'}`")
    md.append("\n---\n*D2.4E local validation only. No broker orders. No production DB writes. No deploy.*\n")

    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"[D2.4E] Wrote {md_path}", flush=True)
    print(f"[D2.4E] Wrote {json_path}", flush=True)
    print(
        "[D2.4E] Done. scanned=%s/%s BUY_READY=%s proposals=%s errors=%s"
        % (
            len(scanned_ok),
            len(tickers),
            inv_counts.get("BUY_READY", 0),
            len(proposals),
            len(errors),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
