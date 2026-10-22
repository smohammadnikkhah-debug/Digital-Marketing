"""Alpaca Paper Trading Read-Only Verification Script (Stage D2.3B.4).

Performs comprehensive read-only empirical verification of:
1. Alpaca paper account authentication & status.
2. Account equity, cash, and leveraged vs cash-only buying power.
3. Paper open positions and paper open orders.
4. IEX market-data feed access for configured symbols (multi-sample).
5. Separate feed-connectivity vs execution-suitability contracts.
6. Max execution spread 0.5%, max quote age 30s, regular-session gate,
   positive uncrossed bid/ask, and material future-timestamp rejection.

Guarantees:
- Zero credentials or account IDs printed in logs or reports.
- Zero orders submitted, modified, or cancelled.
- Fails closed on any live endpoint or invalid configuration.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure Digital Marketing repo root and StockAnalysis backend are importable
ADAPTER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADAPTER_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "stockanalysis" / "web_app" / "backend"
# Secondary layout fallback (StockAnalysis workspace)
if not BACKEND_DIR.exists():
    BACKEND_DIR = PROJECT_ROOT / "web_app" / "backend"

for path in (PROJECT_ROOT, BACKEND_DIR):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from alpaca_adapter.alpaca_paper_adapter import (  # noqa: E402
    AlpacaPaperAdapter,
    NON_EXECUTING_BUILD_GUARD,
)
from app.services.market_data_service import (  # noqa: E402
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
    DEFAULT_MAX_SPREAD_PCT,
    DEFAULT_MAX_FUTURE_SKEW_SECONDS,
    market_data_service,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AlpacaVerifier")

DEFAULT_SAMPLE_COUNT = 3
DEFAULT_SAMPLE_INTERVAL_SECONDS = 30.0


def _evaluate_sample_quotes(
    quotes: Dict[str, Dict[str, Any]],
    sample_index: int,
    now_utc: datetime,
) -> Dict[str, Any]:
    """Evaluate one multi-symbol quote sample for connectivity and execution suitability."""
    per_symbol: Dict[str, Any] = {}
    feed_pass = True
    exec_pass = True

    for sym, q in quotes.items():
        feed = market_data_service.evaluate_feed_connectivity(q, now_utc=now_utc)
        exec_res = market_data_service.evaluate_execution_suitability(q, now_utc=now_utc)

        if not feed.is_connected:
            feed_pass = False
        if not exec_res.is_valid:
            exec_pass = False

        spread_pct = exec_res.spread_pct
        if spread_pct is None and q.get("midpoint") and q.get("spread") is not None:
            spread_pct = round((q["spread"] / q["midpoint"]) * 100.0, 3)

        logger.info(f"\n[Sample {sample_index}][{sym}]")
        logger.info(f"  Bid/Ask: ${q.get('bid')} / ${q.get('ask')}")
        logger.info(f"  Spread %: {spread_pct}")
        logger.info(f"  Quote ts: {q.get('quote_timestamp')}")
        logger.info(f"  Received: {q.get('received_at')}")
        logger.info(f"  Age: {exec_res.quote_age_seconds}s  Skew: {exec_res.clock_skew_seconds}s")
        logger.info(f"  Session: {exec_res.market_session}")
        logger.info(f"  Feed connectivity: {feed.verdict}")
        logger.info(f"  Execution suitability: {'PASS' if exec_res.is_valid else 'FAIL'}")
        if exec_res.failure_reasons:
            for reason in exec_res.failure_reasons:
                logger.info(f"    - {reason}")

        per_symbol[sym] = {
            "quote": q,
            "spread_pct": spread_pct,
            "feed_connectivity": feed.model_dump(),
            "execution_suitability": {
                "is_valid": exec_res.is_valid,
                "verdict": "PASS" if exec_res.is_valid else "FAIL",
                "failure_reasons": exec_res.failure_reasons,
                "quote_age_seconds": exec_res.quote_age_seconds,
                "clock_skew_seconds": exec_res.clock_skew_seconds,
                "market_session": exec_res.market_session,
                "midpoint": exec_res.midpoint,
                "spread_pct": exec_res.spread_pct,
            },
        }

    return {
        "sample_index": sample_index,
        "sampled_at_utc": now_utc.isoformat(),
        "symbols": per_symbol,
        "feed_connectivity_verdict": "PASS" if feed_pass else "FAIL",
        "execution_suitability_verdict": "PASS" if exec_pass else "FAIL",
    }


def _aggregate_verdicts(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate multi-sample feed and execution verdicts (all samples must pass)."""
    if not samples:
        return {
            "feed_connectivity_verdict": "FAIL",
            "execution_suitability_verdict": "FAIL",
            "overall_execution_suitability": "FAIL",
            "explanation": "No quote samples collected.",
        }

    feed_ok = all(s["feed_connectivity_verdict"] == "PASS" for s in samples)
    exec_ok = all(s["execution_suitability_verdict"] == "PASS" for s in samples)

    failing_symbols: Dict[str, List[str]] = {}
    for s in samples:
        for sym, payload in s["symbols"].items():
            reasons = payload["execution_suitability"].get("failure_reasons") or []
            if reasons:
                failing_symbols.setdefault(sym, [])
                for r in reasons:
                    tag = f"sample_{s['sample_index']}: {r}"
                    if tag not in failing_symbols[sym]:
                        failing_symbols[sym].append(tag)

    return {
        "sample_count": len(samples),
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "max_spread_pct": DEFAULT_MAX_SPREAD_PCT,
        "max_future_skew_seconds": DEFAULT_MAX_FUTURE_SKEW_SECONDS,
        "require_regular_session": True,
        "is_consolidated_nbbo": False,
        "feed_connectivity_verdict": "PASS" if feed_ok else "FAIL",
        "execution_suitability_verdict": "PASS" if exec_ok else "FAIL",
        "overall_execution_suitability": "PASS" if exec_ok else "FAIL",
        "failing_symbols": failing_symbols,
        "explanation": (
            "Overall execution-suitability PASS requires every sample for every symbol to satisfy "
            f"positive uncrossed bid/ask, age <= {DEFAULT_MAX_QUOTE_AGE_SECONDS:.0f}s, "
            f"spread <= {DEFAULT_MAX_SPREAD_PCT}%, regular US session, "
            f"and future skew <= {DEFAULT_MAX_FUTURE_SKEW_SECONDS:.0f}s."
            if exec_ok
            else "One or more samples failed the execution-suitability contract; see failing_symbols."
        ),
    }


def run_verification(
    symbols: List[str],
    output_json_path: Optional[str] = None,
    dry_run: bool = False,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> Dict[str, Any]:
    """Runs read-only verification suite against Alpaca Paper API."""
    logger.info("Initializing Alpaca Paper Trading Verifier (Strict Read-Only Mode)...")

    adapter = AlpacaPaperAdapter(auto_load_env=True)

    logger.info("Verifying endpoints and configuration...")
    logger.info(f"  Target Environment: {adapter.env}")
    logger.info(f"  Trading Endpoint:   {adapter.trading_url}")
    logger.info(f"  Market Data URL:    {adapter.data_url}")
    logger.info(f"  Data Feed:          {adapter.data_feed}")
    logger.info(f"  Non-Executing Guard:{NON_EXECUTING_BUILD_GUARD}")
    logger.info(f"  Samples:            {sample_count} x ~{sample_interval_seconds:.0f}s")

    if dry_run:
        logger.info("[DRY-RUN] Dry run mode active. Skipping live API calls.")
        return {"status": "DRY_RUN_COMPLETED"}

    logger.info("Authenticating and retrieving paper account summary...")
    account_summary = adapter.get_account_summary()
    logger.info("  Authentication: SUCCESS")
    logger.info(f"  Account Status: {account_summary['status']}")
    logger.info(f"  Account ID:     {account_summary['account_id']} (Masked)")
    logger.info(f"  Currency:       {account_summary['currency']}")
    logger.info(f"  Account Equity: ${account_summary['equity']:,.2f}")
    logger.info(f"  Account Cash:   ${account_summary['cash']:,.2f}")
    logger.info(f"  Leveraged Buying Power: ${account_summary['buying_power_leveraged']:,.2f}")
    logger.info(
        f"  Cash-Available-For-Risk: ${account_summary['cash_available_for_risk']:,.2f} (Cash-Only Invariant)"
    )

    logger.info("Querying current paper positions...")
    positions = adapter.get_positions()
    logger.info(f"  Open Positions Count: {len(positions)}")

    logger.info("Querying existing paper orders...")
    orders = adapter.get_orders()
    logger.info(f"  Orders Count: {len(orders)}")

    samples: List[Dict[str, Any]] = []
    last_quotes: Dict[str, Dict[str, Any]] = {}

    for i in range(1, max(1, sample_count) + 1):
        logger.info(f"\n=== Quote Sample {i}/{sample_count} for {symbols} ===")
        quotes = adapter.get_latest_quotes(symbols)
        last_quotes = quotes
        sample_now = datetime.now(timezone.utc)
        samples.append(_evaluate_sample_quotes(quotes, sample_index=i, now_utc=sample_now))
        if i < sample_count and sample_interval_seconds > 0:
            logger.info(f"Waiting {sample_interval_seconds:.0f}s before next sample...")
            time.sleep(sample_interval_seconds)

    aggregate = _aggregate_verdicts(samples)
    # Backward-compatible single-map view = last sample quotes
    last_sample = samples[-1] if samples else {}
    quote_evaluations = {
        sym: {
            "quote": payload["quote"],
            "spread_pct": payload["spread_pct"],
            "wide_spread_warning": (
                payload["spread_pct"] is not None and payload["spread_pct"] > DEFAULT_MAX_SPREAD_PCT
            ),
            "suitability_notes": (
                "; ".join(payload["execution_suitability"]["failure_reasons"])
                if payload["execution_suitability"]["failure_reasons"]
                else "Quote satisfies execution-suitability contract."
            ),
            "feed_connectivity_verdict": payload["feed_connectivity"]["verdict"],
            "execution_suitability_verdict": payload["execution_suitability"]["verdict"],
        }
        for sym, payload in last_sample.get("symbols", {}).items()
    }

    evidence = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "adapter_config": {
            "broker": "alpaca",
            "environment": adapter.env,
            "trading_url": adapter.trading_url,
            "data_url": adapter.data_url,
            "data_feed": adapter.data_feed,
            "non_executing_build_guard": NON_EXECUTING_BUILD_GUARD,
        },
        "account_verification": account_summary,
        "positions_count": len(positions),
        "positions": positions,
        "orders_count": len(orders),
        "orders": orders,
        "quotes": last_quotes,
        "quote_evaluations": quote_evaluations,
        "quote_samples": samples,
        "sample_policy": {
            "sample_count": sample_count,
            "sample_interval_seconds": sample_interval_seconds,
        },
        "feed_connectivity_contract": {
            "verdict": aggregate["feed_connectivity_verdict"],
            "explanation": (
                "Feed connectivity PASS requires positive two-sided uncrossed quotes from an allowed "
                "real-time provider without material future timestamp skew on every sample."
            ),
        },
        "execution_suitability_contract": aggregate,
        # Legacy key retained for older consumers; maps to execution suitability.
        "execution_freshness_contract": {
            "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
            "max_spread_pct": DEFAULT_MAX_SPREAD_PCT,
            "all_positive_two_sided": aggregate["feed_connectivity_verdict"] == "PASS",
            "all_fresh_within_30s": aggregate["execution_suitability_verdict"] == "PASS",
            "is_consolidated_nbbo": False,
            "verdict": aggregate["overall_execution_suitability"],
            "explanation": aggregate["explanation"],
        },
        "orders_placed_during_verification": 0,
    }

    if output_json_path:
        out_p = Path(output_json_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        logger.info(f"\nVerification evidence successfully saved to: {out_p.resolve()}")

    logger.info(
        f"\nAggregate feed connectivity: {aggregate['feed_connectivity_verdict']} | "
        f"execution suitability: {aggregate['overall_execution_suitability']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca Paper Trading Read-Only Verifier")
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY", help="Comma-separated symbols")
    parser.add_argument("--output-json", type=str, default="", help="Path to save evidence JSON")
    parser.add_argument("--dry-run", action="store_true", help="Run without network calls")
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"Number of quote samples (default {DEFAULT_SAMPLE_COUNT})",
    )
    parser.add_argument(
        "--sample-interval-seconds",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help=f"Seconds between samples (default {DEFAULT_SAMPLE_INTERVAL_SECONDS})",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    output_path = args.output_json if args.output_json else None

    try:
        evidence = run_verification(
            symbols=symbols,
            output_json_path=output_path,
            dry_run=args.dry_run,
            sample_count=args.samples,
            sample_interval_seconds=args.sample_interval_seconds,
        )
        if args.dry_run:
            sys.exit(0)
        # Non-zero exit when execution suitability fails (overnight alerting).
        overall = (
            evidence.get("execution_suitability_contract", {}).get("overall_execution_suitability")
            or evidence.get("execution_freshness_contract", {}).get("verdict")
        )
        if overall != "PASS":
            logger.error("Verification completed with execution-suitability FAIL.")
            sys.exit(2)
    except Exception as exc:
        logger.error(f"Verification failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
