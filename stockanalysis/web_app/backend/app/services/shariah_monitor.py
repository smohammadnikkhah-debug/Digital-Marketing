"""Read-only Shariah monitoring report for the monitored universe (Stage D2.4D).

Never infers compliance or mutates stored screening classifications.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.shariah_eligibility import (
    STATUS_NON_COMPLIANT,
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    STATUS_COMPLIANT_LEGACY,
    classify_execution_eligibility,
    normalize_shariah_status,
)


def _blocking_reason(status: str, eligibility: Dict[str, Any]) -> str:
    if status == "VERIFIED" and eligibility.get("execution_eligible"):
        return ""
    if normalize_shariah_status(status) == STATUS_NON_COMPLIANT:
        return "NON-COMPLIANT — blocked from execution"
    if normalize_shariah_status(status) == STATUS_COMPLIANT_LEGACY:
        return "Legacy COMPLIANT label — not VERIFIED for D2.4D proposals"
    return "NOT VERIFIED — blocked from execution"


def build_shariah_universe_report(
    signals: List[Dict[str, Any]],
    *,
    watchlist_meta: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Build grouped Shariah monitoring report from scanner/universe signals.

    watchlist_meta: optional ticker → {status, source, date} overlay (read-only).
    """
    watchlist_meta = watchlist_meta or {}
    rows: List[Dict[str, Any]] = []
    groups = {
        "VERIFIED_EXECUTION_ELIGIBLE": [],
        "NOT_VERIFIED_EXECUTION_BLOCKED": [],
        "NON_COMPLIANT_EXECUTION_BLOCKED": [],
    }

    for sig in signals:
        if not sig:
            continue
        ticker = str(sig.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        wl = watchlist_meta.get(ticker) or {}
        # Prefer watchlist stored status when present; else signal field — never invent
        stored = wl.get("status") or sig.get("shariah_status") or "NOT VERIFIED"
        eligibility = classify_execution_eligibility(stored)
        normalized = normalize_shariah_status(stored)
        row = {
            "ticker": ticker,
            "v40_signal": sig.get("signal"),
            "shariah_status": stored,
            "execution_eligibility": eligibility.get("execution_eligibility"),
            "execution_eligible": bool(eligibility.get("execution_eligible")) and str(stored).strip().upper() == "VERIFIED",
            "blocking_reason": _blocking_reason(str(stored).strip().upper(), eligibility),
            "screening_source": wl.get("source") or sig.get("shariah_source") or "",
            "verification_date": wl.get("date") or sig.get("shariah_date") or "",
            "market_as_of_date": sig.get("market_as_of_date") or sig.get("as_of"),
            "normalized_shariah_status": normalized,
        }
        rows.append(row)

        if str(stored).strip().upper() == "VERIFIED" and eligibility.get("execution_eligible"):
            groups["VERIFIED_EXECUTION_ELIGIBLE"].append(row)
        elif normalized == STATUS_NON_COMPLIANT:
            groups["NON_COMPLIANT_EXECUTION_BLOCKED"].append(row)
        else:
            groups["NOT_VERIFIED_EXECUTION_BLOCKED"].append(row)

    return {
        "total": len(rows),
        "counts": {k: len(v) for k, v in groups.items()},
        "groups": groups,
        "rows": rows,
        "read_only": True,
        "classifications_mutated": False,
    }
