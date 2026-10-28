"""Read-only Shariah status store (Stage D2.4F).

Authoritative local store: WatchlistStock (status / source / date).
Universe registry and scanner signals do not certify compliance.

Never invents VERIFIED or NON-COMPLIANT classifications.
Never writes to production databases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.services.shariah_eligibility import (
    STATUS_NON_COMPLIANT,
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    STATUS_COMPLIANT_LEGACY,
    classify_execution_eligibility,
    normalize_shariah_status,
)


def _empty_meta() -> Dict[str, str]:
    return {"status": STATUS_NOT_VERIFIED, "source": "", "date": ""}


def load_watchlist_shariah(db: Optional[Session]) -> Dict[str, Dict[str, str]]:
    """Load ticker → {status, source, date} from WatchlistStock. Read-only."""
    if db is None:
        return {}
    from app.models import WatchlistStock

    out: Dict[str, Dict[str, str]] = {}
    for row in db.query(WatchlistStock).all():
        ticker = str(row.ticker or "").strip().upper()
        if not ticker:
            continue
        out[ticker] = {
            "status": str(row.shariah_status or STATUS_NOT_VERIFIED).strip() or STATUS_NOT_VERIFIED,
            "source": str(row.shariah_source or "").strip(),
            "date": str(row.shariah_date or "").strip(),
        }
    return out


def load_optional_evidence_file(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    """Load optional local evidence JSON without inventing statuses.

    Expected shape: {"records": [{"ticker": "AAPL", "status": "VERIFIED",
    "source": "...", "date": "YYYY-MM-DD"}, ...]}
    or a bare list of such records.
    """
    if path is None or not path.exists() or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    records: List[Any]
    if isinstance(raw, dict):
        records = list(raw.get("records") or raw.get("stocks") or [])
    elif isinstance(raw, list):
        records = raw
    else:
        return {}

    out: Dict[str, Dict[str, str]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ticker = str(rec.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        status = str(rec.get("status") or rec.get("shariah_status") or "").strip()
        if not status:
            continue
        source = str(rec.get("source") or rec.get("shariah_source") or "").strip()
        date = str(rec.get("date") or rec.get("shariah_date") or "").strip()
        # VERIFIED evidence requires documented source + date (same rule as watchlist API)
        if status.upper() == STATUS_VERIFIED and (not source or not date):
            status = STATUS_NOT_VERIFIED
            source = source or "REJECTED_INCOMPLETE_EVIDENCE"
        out[ticker] = {"status": status, "source": source, "date": date}
    return out


def merge_shariah_maps(*maps: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Merge overlays left-to-right; later maps win only when they provide a status."""
    merged: Dict[str, Dict[str, str]] = {}
    for m in maps:
        for ticker, meta in (m or {}).items():
            t = str(ticker).strip().upper()
            if not t or not isinstance(meta, dict):
                continue
            status = str(meta.get("status") or "").strip()
            if not status:
                continue
            merged[t] = {
                "status": status,
                "source": str(meta.get("source") or "").strip(),
                "date": str(meta.get("date") or "").strip(),
            }
    return merged


def resolve_status_for_ticker(
    ticker: str,
    *,
    watchlist_meta: Optional[Dict[str, Dict[str, str]]] = None,
    signal_status: Optional[str] = None,
    registry_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve stored status with provenance. Prefer watchlist → signal → registry → NOT VERIFIED."""
    t = str(ticker or "").strip().upper()
    wl = (watchlist_meta or {}).get(t) or {}
    chosen_status = None
    provenance = "default_not_verified"
    source = ""
    date = ""

    if wl.get("status"):
        chosen_status = wl["status"]
        provenance = "watchlist_stocks"
        source = wl.get("source") or ""
        date = wl.get("date") or ""
    elif signal_status:
        chosen_status = signal_status
        provenance = "signal_payload"
    elif registry_status:
        chosen_status = registry_status
        provenance = "universe_registry"
    else:
        chosen_status = STATUS_NOT_VERIFIED

    eligibility = classify_execution_eligibility(chosen_status)
    normalized = normalize_shariah_status(chosen_status)
    return {
        "ticker": t,
        "shariah_status": chosen_status,
        "normalized_shariah_status": normalized,
        "screening_source": source,
        "verification_date": date,
        "provenance": provenance,
        "execution_eligible": bool(
            eligibility.get("execution_eligible")
            and str(chosen_status).strip().upper() == STATUS_VERIFIED
        ),
        "eligibility": eligibility,
    }


def investigate_universe_shariah(
    tickers: Iterable[str],
    *,
    db: Optional[Session] = None,
    registry_stocks: Optional[Dict[str, Dict[str, Any]]] = None,
    evidence_path: Optional[Path] = None,
    signal_statuses: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build evidence report explaining NOT VERIFIED / VERIFIED / NON-COMPLIANT counts.

    Does not mutate storage. Does not treat missing data as NON-COMPLIANT.
    """
    watchlist = load_watchlist_shariah(db)
    evidence = load_optional_evidence_file(evidence_path)
    merged = merge_shariah_maps(evidence, watchlist)  # watchlist wins over file

    registry_stocks = registry_stocks or {}
    signal_statuses = signal_statuses or {}

    rows: List[Dict[str, Any]] = []
    counts = {
        "VERIFIED": 0,
        "NOT_VERIFIED": 0,
        "NON_COMPLIANT": 0,
        "LEGACY_COMPLIANT": 0,
        "MISSING_WATCHLIST_ROW": 0,
        "REGISTRY_HAS_SHARIAH_FIELD": 0,
        "EVIDENCE_FILE_HIT": 0,
    }

    verified_with_evidence: List[Dict[str, Any]] = []

    for raw in tickers:
        ticker = str(raw or "").strip().upper()
        if not ticker:
            continue
        reg = registry_stocks.get(ticker) or {}
        reg_status = reg.get("shariah_status") if isinstance(reg, dict) else None
        if reg_status:
            counts["REGISTRY_HAS_SHARIAH_FIELD"] += 1
        if ticker in evidence:
            counts["EVIDENCE_FILE_HIT"] += 1
        if ticker not in watchlist:
            counts["MISSING_WATCHLIST_ROW"] += 1

        resolved = resolve_status_for_ticker(
            ticker,
            watchlist_meta=merged,
            signal_status=signal_statuses.get(ticker),
            registry_status=reg_status,
        )
        normalized = resolved["normalized_shariah_status"]
        if normalized == STATUS_VERIFIED:
            counts["VERIFIED"] += 1
            verified_with_evidence.append(resolved)
        elif normalized == STATUS_NON_COMPLIANT:
            counts["NON_COMPLIANT"] += 1
        elif normalized == STATUS_COMPLIANT_LEGACY:
            # Legacy COMPLIANT is not counted as VERIFIED for D2.4F execution.
            counts["LEGACY_COMPLIANT"] += 1
        else:
            counts["NOT_VERIFIED"] += 1

        rows.append(
            {
                **resolved,
                "watchlist_present": ticker in watchlist,
                "evidence_file_present": ticker in evidence,
                "registry_shariah_status": reg_status,
                "load_failure_reason": (
                    None
                    if resolved["provenance"] != "default_not_verified"
                    else (
                        "No WatchlistStock row, no evidence-file record, and universe "
                        "registry has no shariah_status field — fail-closed to NOT VERIFIED"
                    )
                ),
            }
        )

    return {
        "read_only": True,
        "classifications_mutated": False,
        "watchlist_row_count": len(watchlist),
        "evidence_file_path": str(evidence_path) if evidence_path else None,
        "evidence_file_loaded": bool(evidence),
        "evidence_file_record_count": len(evidence),
        "counts": counts,
        "verified_with_evidence": verified_with_evidence,
        "rows": rows,
        "root_cause": (
            "Shariah statuses were never loaded: WatchlistStock is empty, universe "
            "registry omits shariah_status, and no optional evidence file supplied "
            "verified records. Scanner therefore defaults every ticker to NOT VERIFIED. "
            "This is missing/inaccessible screening data — not automatic NON-COMPLIANT."
            if counts["VERIFIED"] == 0 and counts["NON_COMPLIANT"] == 0
            else "Mixed statuses found in local stores; see rows for provenance."
        ),
    }


def attach_watchlist_shariah_to_signals(
    signals: List[Dict[str, Any]],
    watchlist_meta: Dict[str, Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Return shallow copies with watchlist Shariah overlay when present. No invention."""
    out: List[Dict[str, Any]] = []
    for sig in signals:
        if not sig:
            continue
        copy = dict(sig)
        ticker = str(copy.get("ticker") or "").strip().upper()
        meta = watchlist_meta.get(ticker)
        if meta and meta.get("status"):
            copy["shariah_status"] = meta["status"]
            copy["shariah_source"] = meta.get("source") or copy.get("shariah_source") or ""
            copy["shariah_date"] = meta.get("date") or copy.get("shariah_date") or ""
        elif not copy.get("shariah_status"):
            copy["shariah_status"] = STATUS_NOT_VERIFIED
        out.append(copy)
    return out
