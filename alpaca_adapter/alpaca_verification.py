"""Alpaca Paper Trading Read-Only Verification Script (Stage D2.3A.2).

Performs comprehensive read-only empirical verification of:
1. Alpaca paper account authentication & status.
2. Account equity, cash, and leveraged vs cash-only buying power.
3. Paper open positions and paper open orders.
4. IEX market-data feed access for AAPL, MSFT, and SPY.
5. Bid, ask, spread, quote timestamp, and 30-second freshness contract evaluation.
6. Price-collar and liquidity safeguard suitability analysis for IEX non-consolidated quotes.

Guarantees:
- Zero credentials or account IDs printed in logs or reports.
- Zero orders submitted, modified, or cancelled.
- Fails closed on any live endpoint or invalid configuration.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from alpaca_adapter.alpaca_paper_adapter import (
    AlpacaPaperAdapter,
    NON_EXECUTING_BUILD_GUARD,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AlpacaVerifier")


def run_verification(
    symbols: List[str],
    output_json_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Runs read-only verification suite against Alpaca Paper API."""
    logger.info("Initializing Alpaca Paper Trading Verifier (Strict Read-Only Mode)...")

    adapter = AlpacaPaperAdapter(auto_load_env=True)

    # 1. Environment & Endpoint Verification
    logger.info("Verifying endpoints and configuration...")
    logger.info(f"  Target Environment: {adapter.env}")
    logger.info(f"  Trading Endpoint:   {adapter.trading_url}")
    logger.info(f"  Market Data URL:    {adapter.data_url}")
    logger.info(f"  Data Feed:          {adapter.data_feed}")
    logger.info(f"  Non-Executing Guard:{NON_EXECUTING_BUILD_GUARD}")

    if dry_run:
        logger.info("[DRY-RUN] Dry run mode active. Skipping live API calls.")
        return {"status": "DRY_RUN_COMPLETED"}

    # 2. Account Authentication & Status
    logger.info("Authenticating and retrieving paper account summary...")
    account_summary = adapter.get_account_summary()
    logger.info("  Authentication: SUCCESS")
    logger.info(f"  Account Status: {account_summary['status']}")
    logger.info(f"  Account ID:     {account_summary['account_id']} (Masked)")
    logger.info(f"  Currency:       {account_summary['currency']}")
    logger.info(f"  Account Equity: ${account_summary['equity']:,.2f}")
    logger.info(f"  Account Cash:   ${account_summary['cash']:,.2f}")
    logger.info(f"  Leveraged Buying Power: ${account_summary['buying_power_leveraged']:,.2f}")
    logger.info(f"  Cash-Available-For-Risk: ${account_summary['cash_available_for_risk']:,.2f} (Cash-Only Invariant)")

    # 3. Positions
    logger.info("Querying current paper positions...")
    positions = adapter.get_positions()
    logger.info(f"  Open Positions Count: {len(positions)}")
    for pos in positions:
        logger.info(f"    - {pos['symbol']}: {pos['quantity']} shares @ avg ${pos['avg_entry_price']:.2f}")

    # 4. Orders
    logger.info("Querying existing paper orders...")
    orders = adapter.get_orders()
    logger.info(f"  Orders Count: {len(orders)}")
    for o in orders:
        logger.info(f"    - {o['symbol']} {o['side']} {o['quantity']} ({o['status']})")

    # 5. Market Data (IEX)
    logger.info(f"Querying IEX Level 1 market data for {symbols}...")
    now_utc = datetime.now(timezone.utc)
    quotes = adapter.get_latest_quotes(symbols, now_utc=now_utc)

    # 6. Evaluate Safeguards & Price-Collar Suitability
    quote_evaluations = {}
    for sym, q in quotes.items():
        logger.info(f"\n[{sym}] Market Data Evaluation (Source: {q['source']}):")
        logger.info(f"  Bid: ${q['bid']:.2f} (Size: {q['bid_size']})")
        logger.info(f"  Ask: ${q['ask']:.2f} (Size: {q['ask_size']})")
        logger.info(f"  Midpoint: ${q['midpoint']:.2f}" if q['midpoint'] else "  Midpoint: None")
        logger.info(f"  Spread:   ${q['spread']:.2f}" if q['spread'] else "  Spread: None")
        logger.info(f"  Timestamp: {q['quote_timestamp']}")
        logger.info(f"  Age:       {q['quote_age_seconds']:.1f}s")
        logger.info(f"  Positive Two-Sided: {q['is_two_sided']}")
        logger.info(f"  Meets <=30s Freshness: {q['meets_30s_freshness']}")
        logger.info(f"  Consolidated NBBO:     {q['is_consolidated_nbbo']} (Non-Consolidated Single Venue)")

        # Evaluate spread percentage
        spread_pct = (q['spread'] / q['midpoint'] * 100.0) if (q['midpoint'] and q['spread']) else None
        wide_spread_warning = spread_pct is not None and spread_pct > 2.0

        quote_evaluations[sym] = {
            "quote": q,
            "spread_pct": round(spread_pct, 3) if spread_pct else None,
            "wide_spread_warning": wide_spread_warning,
            "suitability_notes": (
                "Wide spread observed on IEX single-venue book. "
                "Limit order collar must be evaluated against IEX midpoint cautiously."
                if wide_spread_warning else "Spread is within normal range."
            ),
        }

    # 7. Compile Evidence Package
    evidence = {
        "timestamp_utc": now_utc.isoformat(),
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
        "quotes": quotes,
        "quote_evaluations": quote_evaluations,
        "execution_freshness_contract": {
            "max_quote_age_seconds": 30.0,
            "all_positive_two_sided": all(q["is_two_sided"] for q in quotes.values()),
            "all_fresh_within_30s": all(q["meets_30s_freshness"] for q in quotes.values()),
            "is_consolidated_nbbo": False,
            "verdict": (
                "PASS" if all(q["is_two_sided"] and q["meets_30s_freshness"] for q in quotes.values())
                else "STALE_OR_OUTSIDE_HOURS"
            ),
            "explanation": (
                "Alpaca IEX data provides positive two-sided quotes with exchange timestamps. "
                "When requested outside regular trading hours, quote age reflects time since last exchange quote."
            ),
        },
        "orders_placed_during_verification": 0,
    }

    if output_json_path:
        out_p = Path(output_json_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        logger.info(f"\nVerification evidence successfully saved to: {out_p.resolve()}")

    return evidence


def main():
    parser = argparse.ArgumentParser(description="Alpaca Paper Trading Read-Only Verifier")
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY", help="Comma-separated symbols")
    parser.add_argument("--output-json", type=str, default="", help="Path to save evidence JSON")
    parser.add_argument("--dry-run", action="store_true", help="Run without network calls")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    output_path = args.output_json if args.output_json else None

    try:
        run_verification(symbols=symbols, output_json_path=output_path, dry_run=args.dry_run)
    except Exception as exc:
        logger.error(f"Verification failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
