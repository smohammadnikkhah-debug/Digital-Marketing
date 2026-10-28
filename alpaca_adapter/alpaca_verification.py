"""Alpaca Paper Trading Read-Only Verification Script (Stage D2.3B.6).

Performs comprehensive read-only empirical verification of:
1. Alpaca paper account authentication & status.
2. Account equity, cash, and leveraged vs cash-only buying power.
3. Paper open positions and paper open orders.
4. IEX market-data feed access for configured symbols (multi-sample).
5. Separate feed-connectivity vs execution-suitability contracts.
6. Max execution spread 0.5%, max quote age 30s, regular-session gate,
   positive uncrossed bid/ask, and material future-timestamp rejection.
7. Per-symbol reliability metrics and session labeling (D2.3B.6).
8. Freshness aggregates computed strictly from freshness outcomes (not spread).

Guarantees:
- Zero credentials or account IDs printed in logs or reports.
- Zero orders submitted, modified, or cancelled.
- Fails closed on any live endpoint or invalid configuration.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ensure Digital Marketing repo root and StockAnalysis backend are importable
ADAPTER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ADAPTER_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "stockanalysis" / "web_app" / "backend"
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


def _classify_failure_reasons(reasons: Sequence[str]) -> Dict[str, bool]:
    """Map failure reason strings to independent gate categories."""
    text = " | ".join(reasons).lower()
    return {
        "freshness_fail": any(
            k in text for k in ("stale quote", "future-dated", "unparseable quote timestamp")
        ),
        "spread_fail": "wide spread" in text,
        "session_fail": any(
            k in text for k in ("post_market", "pre_market", "market closed", "regular")
        )
        and ("execution blocked" in text or "markets are currently" in text),
        "structure_fail": any(
            k in text
            for k in (
                "crossed market",
                "invalid bid",
                "invalid ask",
                "malformed",
                "unlicensed",
                "unrecognized",
                "delayed quote",
                "synthetic",
            )
        ),
    }


def _freshness_pass_from_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[float]]:
    """Determine freshness PASS strictly from age/skew/timestamp validity.

    Fail-closed: missing/invalid age or material future skew => FAIL.
    Does NOT depend on spread, session, or overall execution suitability.
    """
    exec_block = payload.get("execution_suitability") or {}
    reasons = exec_block.get("failure_reasons") or []
    flags = _classify_failure_reasons(reasons)

    age = exec_block.get("quote_age_seconds")
    skew = exec_block.get("clock_skew_seconds")
    quote = payload.get("quote") or {}

    # Prefer quote-level meets_30s_freshness when present and no freshness-class failures
    if flags["freshness_fail"]:
        return False, age if isinstance(age, (int, float)) else None

    if age is None:
        # Fail closed on missing age
        raw_ts = quote.get("quote_timestamp")
        if not raw_ts:
            return False, None
        try:
            market_data_service.parse_quote_timestamp(str(raw_ts))
        except Exception:
            return False, None
        return False, None

    if skew is not None and float(skew) > DEFAULT_MAX_FUTURE_SKEW_SECONDS:
        return False, float(age)

    fresh = float(age) <= DEFAULT_MAX_QUOTE_AGE_SECONDS
    return fresh, float(age)


def _spread_pass_from_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[float]]:
    spread_pct = payload.get("spread_pct")
    if spread_pct is None:
        exec_block = payload.get("execution_suitability") or {}
        spread_pct = exec_block.get("spread_pct")
    if spread_pct is None:
        return False, None
    return float(spread_pct) <= DEFAULT_MAX_SPREAD_PCT, float(spread_pct)


def _evaluate_sample_quotes(
    quotes: Dict[str, Dict[str, Any]],
    sample_index: int,
    now_utc: datetime,
    expected_symbols: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Evaluate one multi-symbol quote sample for connectivity and execution suitability."""
    per_symbol: Dict[str, Any] = {}
    feed_pass = True
    exec_pass = True
    all_fresh = True
    missing_symbols: List[str] = []

    expected = list(expected_symbols) if expected_symbols else list(quotes.keys())
    for sym in expected:
        if sym not in quotes:
            missing_symbols.append(sym)
            feed_pass = False
            exec_pass = False
            all_fresh = False
            per_symbol[sym] = {
                "received": False,
                "quote": None,
                "spread_pct": None,
                "freshness_pass": False,
                "spread_pass": False,
                "feed_connectivity": {
                    "is_connected": False,
                    "verdict": "FAIL",
                    "failure_reasons": [f"Missing quote sample for symbol '{sym}'."],
                },
                "execution_suitability": {
                    "is_valid": False,
                    "verdict": "FAIL",
                    "failure_reasons": [f"Missing quote sample for symbol '{sym}'."],
                    "quote_age_seconds": None,
                    "clock_skew_seconds": None,
                    "market_session": None,
                    "midpoint": None,
                    "spread_pct": None,
                },
            }
            continue

        q = quotes[sym]
        feed = market_data_service.evaluate_feed_connectivity(q, now_utc=now_utc)
        exec_res = market_data_service.evaluate_execution_suitability(q, now_utc=now_utc)

        if not feed.is_connected:
            feed_pass = False
        if not exec_res.is_valid:
            exec_pass = False

        spread_pct = exec_res.spread_pct
        if spread_pct is None and q.get("midpoint") and q.get("spread") is not None and q["midpoint"]:
            spread_pct = round((q["spread"] / q["midpoint"]) * 100.0, 3)

        payload = {
            "received": True,
            "quote": q,
            "spread_pct": spread_pct,
            "feed_connectivity": feed.model_dump(),
            "execution_suitability": {
                "is_valid": exec_res.is_valid,
                "verdict": "PASS" if exec_res.is_valid else "FAIL",
                "failure_reasons": list(exec_res.failure_reasons),
                "quote_age_seconds": exec_res.quote_age_seconds,
                "clock_skew_seconds": exec_res.clock_skew_seconds,
                "market_session": exec_res.market_session,
                "midpoint": exec_res.midpoint,
                "spread_pct": exec_res.spread_pct,
            },
        }
        fresh_ok, _age = _freshness_pass_from_payload(payload)
        spread_ok, _sp = _spread_pass_from_payload(payload)
        payload["freshness_pass"] = fresh_ok
        payload["spread_pass"] = spread_ok
        if not fresh_ok:
            all_fresh = False

        logger.info(f"\n[Sample {sample_index}][{sym}]")
        logger.info(f"  Bid/Ask: ${q.get('bid')} / ${q.get('ask')}")
        logger.info(f"  Spread %: {spread_pct}")
        logger.info(f"  Quote ts: {q.get('quote_timestamp')}")
        logger.info(f"  Received: {q.get('received_at')}")
        logger.info(f"  Age: {exec_res.quote_age_seconds}s  Skew: {exec_res.clock_skew_seconds}s")
        logger.info(f"  Session: {exec_res.market_session}")
        logger.info(f"  Freshness: {'PASS' if fresh_ok else 'FAIL'}")
        logger.info(f"  Feed connectivity: {feed.verdict}")
        logger.info(f"  Execution suitability: {'PASS' if exec_res.is_valid else 'FAIL'}")
        if exec_res.failure_reasons:
            for reason in exec_res.failure_reasons:
                logger.info(f"    - {reason}")

        per_symbol[sym] = payload

    return {
        "sample_index": sample_index,
        "sampled_at_utc": now_utc.isoformat(),
        "symbols": per_symbol,
        "missing_symbols": missing_symbols,
        "feed_connectivity_verdict": "PASS" if feed_pass else "FAIL",
        "execution_suitability_verdict": "PASS" if exec_pass else "FAIL",
        "all_fresh_within_30s": all_fresh and len(missing_symbols) == 0 and len(per_symbol) > 0,
    }


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(float(statistics.median(values)), 6)


def compute_symbol_reliability(
    samples: List[Dict[str, Any]],
    symbols: Sequence[str],
) -> Dict[str, Any]:
    """Per-symbol reliability summary. Missing samples do not inflate pass rates."""
    report: Dict[str, Any] = {}
    attempted = len(samples)

    for sym in symbols:
        received = 0
        feed_pass = 0
        exec_pass = 0
        fresh_pass = 0
        spread_pass = 0
        spreads: List[float] = []
        ages: List[float] = []
        reason_counter: Counter[str] = Counter()
        invalid_or_missing = 0

        for s in samples:
            payload = (s.get("symbols") or {}).get(sym)
            if not payload or not payload.get("received", True) or payload.get("quote") is None:
                invalid_or_missing += 1
                continue
            received += 1
            if (payload.get("feed_connectivity") or {}).get("verdict") == "PASS":
                feed_pass += 1
            if (payload.get("execution_suitability") or {}).get("verdict") == "PASS":
                exec_pass += 1

            fresh_ok, age = _freshness_pass_from_payload(payload)
            if fresh_ok:
                fresh_pass += 1
            if age is not None:
                ages.append(float(age))

            sp_ok, sp = _spread_pass_from_payload(payload)
            if sp is not None:
                spreads.append(float(sp))
            if sp_ok:
                spread_pass += 1

            for r in (payload.get("execution_suitability") or {}).get("failure_reasons") or []:
                reason_counter[r] += 1

        def _pct(num: int, den: int) -> Optional[float]:
            if den <= 0:
                return None
            return round(100.0 * num / den, 2)

        report[sym] = {
            "samples_attempted": attempted,
            "samples_received": received,
            "samples_missing_or_invalid": invalid_or_missing,
            "feed_connectivity_pass_count": feed_pass,
            "feed_connectivity_pass_pct": _pct(feed_pass, received),
            "execution_suitability_pass_count": exec_pass,
            "execution_suitability_pass_pct": _pct(exec_pass, received),
            "freshness_pass_count": fresh_pass,
            "freshness_pass_pct": _pct(fresh_pass, received),
            "spread_pass_count": spread_pass,
            "spread_pass_pct": _pct(spread_pass, received),
            "spread_pct_min": round(min(spreads), 6) if spreads else None,
            "spread_pct_median": _median(spreads),
            "spread_pct_max": round(max(spreads), 6) if spreads else None,
            "quote_age_seconds_min": round(min(ages), 6) if ages else None,
            "quote_age_seconds_median": _median(ages),
            "quote_age_seconds_max": round(max(ages), 6) if ages else None,
            "failure_reason_frequencies": dict(reason_counter.most_common()),
        }
    return report


def _aggregate_verdicts(
    samples: List[Dict[str, Any]],
    symbols: Sequence[str],
) -> Dict[str, Any]:
    """Aggregate multi-sample feed, freshness, and execution verdicts."""
    if not samples:
        return {
            "feed_connectivity_verdict": "FAIL",
            "execution_suitability_verdict": "FAIL",
            "overall_execution_suitability": "FAIL",
            "all_fresh_within_30s": False,
            "all_positive_two_sided": False,
            "explanation": "No quote samples collected.",
            "symbol_reliability": {},
        }

    feed_ok = all(s.get("feed_connectivity_verdict") == "PASS" for s in samples)
    exec_ok = all(s.get("execution_suitability_verdict") == "PASS" for s in samples)

    # Freshness: every received symbol in every sample must pass freshness independently
    freshness_flags: List[bool] = []
    two_sided_flags: List[bool] = []
    for s in samples:
        for sym in symbols:
            payload = (s.get("symbols") or {}).get(sym)
            if not payload or not payload.get("received", True) or payload.get("quote") is None:
                freshness_flags.append(False)
                two_sided_flags.append(False)
                continue
            fresh_ok, _ = _freshness_pass_from_payload(payload)
            freshness_flags.append(fresh_ok)
            q = payload.get("quote") or {}
            bid = float(q.get("bid") or 0)
            ask = float(q.get("ask") or 0)
            two_sided_flags.append(bid > 0 and ask > 0 and ask >= bid)

    all_fresh = bool(freshness_flags) and all(freshness_flags)
    all_two_sided = bool(two_sided_flags) and all(two_sided_flags)

    failing_symbols: Dict[str, List[str]] = {}
    for s in samples:
        for sym, payload in (s.get("symbols") or {}).items():
            reasons = (payload.get("execution_suitability") or {}).get("failure_reasons") or []
            if reasons:
                failing_symbols.setdefault(sym, [])
                for r in reasons:
                    tag = f"sample_{s['sample_index']}: {r}"
                    if tag not in failing_symbols[sym]:
                        failing_symbols[sym].append(tag)

    symbol_reliability = compute_symbol_reliability(samples, symbols)

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
        "all_fresh_within_30s": all_fresh,
        "all_positive_two_sided": all_two_sided,
        "failing_symbols": failing_symbols,
        "symbol_reliability": symbol_reliability,
        "explanation": (
            "Overall execution-suitability PASS requires every sample for every symbol to satisfy "
            f"positive uncrossed bid/ask, age <= {DEFAULT_MAX_QUOTE_AGE_SECONDS:.0f}s, "
            f"spread <= {DEFAULT_MAX_SPREAD_PCT}%, regular US session, "
            f"and future skew <= {DEFAULT_MAX_FUTURE_SKEW_SECONDS:.0f}s."
            if exec_ok
            else "One or more samples failed the execution-suitability contract; see failing_symbols."
        ),
    }


def build_evidence_from_samples(
    samples: List[Dict[str, Any]],
    symbols: Sequence[str],
    *,
    adapter_config: Optional[Dict[str, Any]] = None,
    account_summary: Optional[Dict[str, Any]] = None,
    positions: Optional[List[Any]] = None,
    orders: Optional[List[Any]] = None,
    session_meta: Optional[Dict[str, Any]] = None,
    sample_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble evidence package (usable for live runs and historical reprocessing)."""
    aggregate = _aggregate_verdicts(samples, symbols)
    last_sample = samples[-1] if samples else {}
    last_quotes = {
        sym: payload["quote"]
        for sym, payload in (last_sample.get("symbols") or {}).items()
        if payload.get("quote") is not None
    }
    quote_evaluations = {
        sym: {
            "quote": payload.get("quote"),
            "spread_pct": payload.get("spread_pct"),
            "wide_spread_warning": (
                payload.get("spread_pct") is not None
                and payload["spread_pct"] > DEFAULT_MAX_SPREAD_PCT
            ),
            "suitability_notes": (
                "; ".join((payload.get("execution_suitability") or {}).get("failure_reasons") or [])
                or "Quote satisfies execution-suitability contract."
            ),
            "feed_connectivity_verdict": (payload.get("feed_connectivity") or {}).get("verdict"),
            "execution_suitability_verdict": (payload.get("execution_suitability") or {}).get("verdict"),
            "freshness_pass": payload.get("freshness_pass"),
            "spread_pass": payload.get("spread_pass"),
        }
        for sym, payload in (last_sample.get("symbols") or {}).items()
    }

    evidence = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "D2.3B.6",
        "session": session_meta or {},
        "adapter_config": adapter_config or {},
        "account_verification": account_summary,
        "positions_count": len(positions or []),
        "positions": positions or [],
        "orders_count": len(orders or []),
        "orders": orders or [],
        "quotes": last_quotes,
        "quote_evaluations": quote_evaluations,
        "quote_samples": samples,
        "sample_policy": sample_policy
        or {
            "sample_count": len(samples),
            "sample_interval_seconds": DEFAULT_SAMPLE_INTERVAL_SECONDS,
            "symbols": list(symbols),
        },
        "feed_connectivity_contract": {
            "verdict": aggregate["feed_connectivity_verdict"],
            "explanation": (
                "Feed connectivity PASS requires positive two-sided uncrossed quotes from an allowed "
                "real-time provider without material future timestamp skew on every sample."
            ),
        },
        "execution_suitability_contract": {
            k: v
            for k, v in aggregate.items()
            if k != "symbol_reliability"
        },
        "symbol_reliability": aggregate.get("symbol_reliability") or {},
        # Legacy key: freshness fields are now independent of overall suitability.
        "execution_freshness_contract": {
            "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
            "max_spread_pct": DEFAULT_MAX_SPREAD_PCT,
            "all_positive_two_sided": aggregate["all_positive_two_sided"],
            "all_fresh_within_30s": aggregate["all_fresh_within_30s"],
            "is_consolidated_nbbo": False,
            "verdict": "PASS" if aggregate["all_fresh_within_30s"] else "FAIL",
            "explanation": (
                "all_fresh_within_30s is computed strictly from per-sample freshness "
                f"(age <= {DEFAULT_MAX_QUOTE_AGE_SECONDS:.0f}s and future skew "
                f"<= {DEFAULT_MAX_FUTURE_SKEW_SECONDS:.0f}s). It does not depend on spread "
                "or overall execution-suitability."
            ),
        },
        "orders_placed_during_verification": 0,
    }
    return evidence


def reprocess_evidence_file(path: Path) -> Dict[str, Any]:
    """Rebuild aggregates/reliability from an existing evidence JSON (no network)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    samples = raw.get("quote_samples") or []
    symbols = (
        (raw.get("sample_policy") or {}).get("symbols")
        or sorted({sym for s in samples for sym in (s.get("symbols") or {}).keys()})
    )
    # Ensure freshness_pass flags exist on historical payloads
    for s in samples:
        for sym, payload in (s.get("symbols") or {}).items():
            if "freshness_pass" not in payload:
                payload["freshness_pass"] = _freshness_pass_from_payload(payload)[0]
            if "spread_pass" not in payload:
                payload["spread_pass"] = _spread_pass_from_payload(payload)[0]
            if "received" not in payload:
                payload["received"] = payload.get("quote") is not None

    rebuilt = build_evidence_from_samples(
        samples,
        symbols,
        adapter_config=raw.get("adapter_config"),
        account_summary=raw.get("account_verification"),
        positions=raw.get("positions") or [],
        orders=raw.get("orders") or [],
        session_meta={
            **(raw.get("session") or {}),
            "source_evidence": str(path.name),
            "reprocessed": True,
            "label": "HISTORICAL_REPROCESS",
        },
        sample_policy=raw.get("sample_policy"),
    )
    rebuilt["orders_placed_during_verification"] = raw.get("orders_placed_during_verification", 0)
    return rebuilt


def run_verification(
    symbols: List[str],
    output_json_path: Optional[str] = None,
    dry_run: bool = False,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    session_id: str = "",
    session_label: str = "",
    minutes_after_open: Optional[int] = None,
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
    if session_id or session_label:
        logger.info(f"  Session:            {session_id or '-'} / {session_label or '-'}")

    if dry_run:
        logger.info("[DRY-RUN] Dry run mode active. Skipping live API calls.")
        return {"status": "DRY_RUN_COMPLETED"}

    logger.info("Authenticating and retrieving paper account summary...")
    account_summary = adapter.get_account_summary()
    logger.info("  Authentication: SUCCESS")
    logger.info(f"  Account Status: {account_summary['status']}")
    logger.info(f"  Account ID:     {account_summary['account_id']} (Masked)")

    logger.info("Querying current paper positions...")
    positions = adapter.get_positions()
    logger.info(f"  Open Positions Count: {len(positions)}")

    logger.info("Querying existing paper orders...")
    orders = adapter.get_orders()
    logger.info(f"  Orders Count: {len(orders)}")

    samples: List[Dict[str, Any]] = []
    api_errors: List[str] = []

    for i in range(1, max(1, sample_count) + 1):
        logger.info(f"\n=== Quote Sample {i}/{sample_count} for {symbols} ===")
        try:
            quotes = adapter.get_latest_quotes(symbols)
        except Exception as exc:
            api_errors.append(f"sample_{i}: {exc}")
            logger.error(f"Quote fetch failed for sample {i}: {exc}")
            samples.append(
                _evaluate_sample_quotes({}, sample_index=i, now_utc=datetime.now(timezone.utc), expected_symbols=symbols)
            )
        else:
            sample_now = datetime.now(timezone.utc)
            samples.append(
                _evaluate_sample_quotes(
                    quotes, sample_index=i, now_utc=sample_now, expected_symbols=symbols
                )
            )
        if i < sample_count and sample_interval_seconds > 0:
            logger.info(f"Waiting {sample_interval_seconds:.0f}s before next sample...")
            time.sleep(sample_interval_seconds)

    session_now = datetime.now(timezone.utc)
    session_name, session_detail = market_data_service.get_market_session(session_now)
    session_meta = {
        "session_id": session_id or None,
        "session_label": session_label or None,
        "minutes_after_open": minutes_after_open,
        "market_session_at_run": session_name,
        "market_session_detail": session_detail,
        "evaluated_at_utc": session_now.isoformat(),
        "api_errors": api_errors,
    }

    evidence = build_evidence_from_samples(
        samples,
        symbols,
        adapter_config={
            "broker": "alpaca",
            "environment": adapter.env,
            "trading_url": adapter.trading_url,
            "data_url": adapter.data_url,
            "data_feed": adapter.data_feed,
            "non_executing_build_guard": NON_EXECUTING_BUILD_GUARD,
        },
        account_summary=account_summary,
        positions=positions,
        orders=orders,
        session_meta=session_meta,
        sample_policy={
            "sample_count": sample_count,
            "sample_interval_seconds": sample_interval_seconds,
            "symbols": list(symbols),
        },
    )

    if output_json_path:
        out_p = Path(output_json_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        logger.info(f"\nVerification evidence successfully saved to: {out_p.resolve()}")

    logger.info(
        f"\nAggregate feed connectivity: "
        f"{evidence['feed_connectivity_contract']['verdict']} | "
        f"freshness: {evidence['execution_freshness_contract']['verdict']} | "
        f"execution suitability: "
        f"{evidence['execution_suitability_contract']['overall_execution_suitability']}"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca Paper Trading Read-Only Verifier (D2.3B.6)")
    parser.add_argument("--symbols", type=str, default="AAPL,MSFT,SPY", help="Comma-separated symbols")
    parser.add_argument("--output-json", type=str, default="", help="Path to save evidence JSON")
    parser.add_argument("--dry-run", action="store_true", help="Run without network calls")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--sample-interval-seconds", type=float, default=DEFAULT_SAMPLE_INTERVAL_SECONDS)
    parser.add_argument("--session-id", type=str, default="", help="Session id e.g. open_plus_15")
    parser.add_argument("--session-label", type=str, default="", help="Human-readable session label")
    parser.add_argument(
        "--minutes-after-open",
        type=int,
        default=-1,
        help="Minutes after US regular open (for reporting metadata)",
    )
    parser.add_argument(
        "--reprocess-evidence",
        type=str,
        default="",
        help="Rebuild aggregates from existing evidence JSON (no network)",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    output_path = args.output_json if args.output_json else None

    try:
        if args.reprocess_evidence:
            rebuilt = reprocess_evidence_file(Path(args.reprocess_evidence))
            if output_path:
                Path(output_path).write_text(json.dumps(rebuilt, indent=2), encoding="utf-8")
            print(json.dumps({
                "status": "REPROCESSED",
                "all_fresh_within_30s": rebuilt["execution_freshness_contract"]["all_fresh_within_30s"],
                "overall_execution_suitability": rebuilt["execution_suitability_contract"][
                    "overall_execution_suitability"
                ],
                "symbol_reliability_keys": list(rebuilt.get("symbol_reliability", {}).keys()),
            }, indent=2))
            sys.exit(0)

        evidence = run_verification(
            symbols=symbols,
            output_json_path=output_path,
            dry_run=args.dry_run,
            sample_count=args.samples,
            sample_interval_seconds=args.sample_interval_seconds,
            session_id=args.session_id,
            session_label=args.session_label,
            minutes_after_open=(args.minutes_after_open if args.minutes_after_open >= 0 else None),
        )
        if args.dry_run:
            sys.exit(0)
        overall = evidence.get("execution_suitability_contract", {}).get("overall_execution_suitability")
        if overall != "PASS":
            logger.error("Verification completed with execution-suitability FAIL.")
            sys.exit(2)
    except Exception as exc:
        logger.error(f"Verification failed: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
