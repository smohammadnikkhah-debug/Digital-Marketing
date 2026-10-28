"""Pilot candidate ranking for paper-trading selection (Stage D2.4J).

V4.0 does not persist a live BUY-priority / investment-rank field on scanner
signals or the TodayTrade sheet. TrainingScores.Score selects entry/exit rules
during walk-forward training — it is not a cross-sectional buy ranking.

This module therefore:
  - Does NOT use share price / ask as investment priority
  - Does NOT invent a new investment score
  - Preserves deterministic order from authoritative scan evidence when available
  - Falls back to ticker sort only as a stable tie-break

Does not alter V4.0 strategy mathematics.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# Documented gap — not a runtime error
V40_LIVE_RANK_MISSING = (
    "Scanner BUY CANDIDATE payloads and TodayTrade do not include a comparable "
    "V4.0 cross-sectional investment rank/score. TrainingScores.Score is "
    "rule-selection metadata (per ticker/year/entry/exit), not buy priority."
)

RANKING_METHOD_ID = "D2E_BUY_READY_SEQUENCE_THEN_TICKER"


def describe_ranking_methodology() -> Dict[str, Any]:
    return {
        "method_id": RANKING_METHOD_ID,
        "uses_share_price": False,
        "invents_investment_score": False,
        "v40_strategy_math_modified": False,
        "v40_live_rank_available": False,
        "missing_data": V40_LIVE_RANK_MISSING,
        "ordering": [
            "1. Prefer candidates that already have a SIMULATED dry-run proposal "
            "(operational readiness for sizing — not an investment score)",
            "2. Preserve D2.4E buy_ready_details sequence index when provided",
            "3. Stable ticker alphabetical tie-break",
        ],
        "explicitly_removed": [
            "Lower ask / lower share-price preference (D2.4I pilot anti-pattern)",
        ],
    }


def build_scan_sequence_index(
    buy_ready_details: Sequence[Dict[str, Any]],
) -> Dict[str, int]:
    """Map ticker → 0-based order of appearance in authoritative D2.4E buy list."""
    index: Dict[str, int] = {}
    for i, row in enumerate(buy_ready_details or []):
        t = str((row or {}).get("ticker") or "").strip().upper()
        if t and t not in index:
            index[t] = i
    return index


def rank_key(
    row: Dict[str, Any],
    *,
    scan_sequence: Optional[Dict[str, int]] = None,
) -> Tuple:
    """Deterministic sort key — no share-price component."""
    scan_sequence = scan_sequence or {}
    prop = row.get("simulated_proposal") or {}
    has_sim = 0 if prop.get("status") == "SIMULATED" else 1
    ticker = str(row.get("ticker") or "").strip().upper()
    seq = scan_sequence.get(ticker, 10_000)
    return (has_sim, seq, ticker)


def rank_candidates(
    rows: Sequence[Dict[str, Any]],
    *,
    buy_ready_details: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return a new list sorted by rank_key; annotates each row with pilot_rank."""
    seq = build_scan_sequence_index(buy_ready_details or [])
    ordered = sorted(list(rows), key=lambda r: rank_key(r, scan_sequence=seq))
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(ordered, start=1):
        annotated = dict(row)
        annotated["pilot_rank"] = i
        annotated["pilot_rank_sequence_index"] = seq.get(
            str(row.get("ticker") or "").upper()
        )
        annotated["pilot_ranking_method"] = RANKING_METHOD_ID
        out.append(annotated)
    return out
