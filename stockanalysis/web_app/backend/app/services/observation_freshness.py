"""Scan freshness / provenance gates for multi-session soak (Stage D2.4L).

If current-session daily bars are unavailable, return DATA_PENDING — never fabricate
FRESH labels.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from app.config import V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION
from app.services.us_session_freshness import (
    last_completed_us_equity_session,
    parse_market_as_of,
)


def assess_scan_freshness(
    scan_rows: Sequence[Dict[str, Any]],
    *,
    now_utc: Optional[datetime] = None,
    expected_session: Optional[date] = None,
    require_live_scan: bool = True,
    exclude_tickers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Aggregate provenance + as-of checks across a scan.

    status:
      - FRESH: majority of evaluable rows match expected session as-of
      - DATA_PENDING: bars not yet available for expected session (or empty scan)
      - STALE_MIXED: rows present but as-of behind expected / mixed dates
      - PROVENANCE_FAIL: frozen baseline or wrong strategy source detected

    exclude_tickers: optional set of symbols omitted from evaluation (e.g. proposed
    universe retirements). Excluded rows are reported but do not affect status —
    so legitimate exclusions are distinguishable from stale active-market data.
    Strict as-of rules still apply to every remaining evaluable security.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    expected = expected_session or last_completed_us_equity_session(now)
    excluded = {str(t).strip().upper() for t in (exclude_tickers or []) if str(t).strip()}

    as_of_counts: Counter = Counter()
    freshness_counts: Counter = Counter()
    provenance_counts: Counter = Counter()
    strategy_versions: Counter = Counter()
    sources: Counter = Counter()
    scan_ts: List[str] = []
    evaluable = 0
    matching = 0
    pending_like = 0
    provenance_issues: List[str] = []
    excluded_rows: List[str] = []

    for row in scan_rows or []:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and ticker in excluded:
            excluded_rows.append(ticker)
            continue
        as_of = parse_market_as_of(row.get("market_as_of_date") or row.get("as_of"))
        if as_of:
            as_of_counts[as_of.isoformat()] += 1
            evaluable += 1
            if as_of == expected:
                matching += 1
            elif as_of < expected:
                pending_like += 1
        else:
            pending_like += 1

        dfresh = str(row.get("data_freshness") or "UNKNOWN")
        freshness_counts[dfresh] += 1
        prov = str(row.get("provenance_mode") or "UNKNOWN")
        provenance_counts[prov] += 1
        strategy_versions[str(row.get("strategy_version") or "UNKNOWN")] += 1
        sources[str(row.get("signal_source") or "UNKNOWN")] += 1
        if row.get("scan_completed_at"):
            scan_ts.append(str(row.get("scan_completed_at")))

        if require_live_scan and prov == "FROZEN_BASELINE":
            provenance_issues.append(
                f"{row.get('ticker')}: provenance_mode=FROZEN_BASELINE (silent snapshot reuse)"
            )
        src = str(row.get("signal_source") or "")
        if src and src != V40_SIGNAL_SOURCE and src != "UNKNOWN":
            # Allow missing on insufficient-data stubs
            if str(row.get("signal") or "") not in ("INSUFFICIENT DATA", "SCAN_ERROR"):
                provenance_issues.append(
                    f"{row.get('ticker')}: unexpected signal_source={src}"
                )

    coverage_pct = round(100.0 * matching / evaluable, 2) if evaluable else 0.0

    if provenance_issues:
        status = "PROVENANCE_FAIL"
        reason = "FROZEN_OR_WRONG_SOURCE"
    elif evaluable == 0:
        status = "DATA_PENDING"
        reason = "NO_EVALUABLE_BARS"
    elif matching == 0 and pending_like > 0:
        status = "DATA_PENDING"
        reason = "EXPECTED_SESSION_BARS_UNAVAILABLE"
    elif matching < evaluable:
        status = "STALE_MIXED"
        reason = "PARTIAL_AS_OF_MISMATCH"
    else:
        status = "FRESH"
        reason = "SESSION_AS_OF_MATCH"

    return {
        "status": status,
        "reason_code": reason,
        "expected_session": expected.isoformat(),
        "as_of_distribution": dict(as_of_counts),
        "matching_expected_count": matching,
        "evaluable_count": evaluable,
        "coverage_pct_matching_expected": coverage_pct,
        "excluded_ticker_count": len(excluded_rows),
        "excluded_tickers": sorted(set(excluded_rows)),
        "data_freshness_counts": dict(freshness_counts),
        "provenance_mode_counts": dict(provenance_counts),
        "strategy_version_counts": dict(strategy_versions),
        "signal_source_counts": dict(sources),
        "scan_completed_at_samples": scan_ts[:5],
        "scan_completed_at_max": max(scan_ts) if scan_ts else None,
        "expected_strategy_version": V40_STRATEGY_VERSION,
        "expected_signal_source": V40_SIGNAL_SOURCE,
        "provenance_issues": provenance_issues[:20],
        "fabricated_freshness": False,
        "note": (
            "DATA_PENDING means daily bars for the expected session were not available; "
            "freshness was not fabricated."
            if status == "DATA_PENDING"
            else None
        ),
    }
