"""Local Shariah research / verification workflow (Stage D2.4G).

Read-only-first against the monitored universe. Manual confirmations may be
staged only under data_cache/shariah/ (never production DB).
Does not fabricate screening results or treat LLM opinion as verification.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.config import DATA_CACHE_DIR
from app.services.investment_eligibility import evaluate_investment_eligibility
from app.services.personal_restrictions import (
    default_personal_restrictions_config,
    load_personal_restrictions_config,
)
from app.services.shariah_evidence import (
    ShariahEvidenceRecord,
    load_evidence_records,
)
from app.services.shariah_store import load_watchlist_shariah
from app.services.ticker_integrity import resolve_proposed_alias

SHARIAH_DIR = DATA_CACHE_DIR / "shariah"
EVIDENCE_PATH = SHARIAH_DIR / "evidence_records.json"
PERSONAL_RESTRICTIONS_PATH = SHARIAH_DIR / "personal_restrictions.json"
LOCAL_REVIEWS_PATH = SHARIAH_DIR / "local_manual_reviews.jsonl"


def ensure_local_shariah_dirs() -> Path:
    """Create local isolated shariah data directory (not production)."""
    SHARIAH_DIR.mkdir(parents=True, exist_ok=True)
    return SHARIAH_DIR


def ensure_local_templates() -> Dict[str, str]:
    """Write empty template files if missing — never invents VERIFIED rows."""
    ensure_local_shariah_dirs()
    created = {}
    if not EVIDENCE_PATH.exists():
        payload = {
            "version": "D2.4G",
            "description": (
                "Local Shariah evidence store. Records require methodology_provider, "
                "source_reference, assessment_date, expiry_or_review_date, "
                "reviewer_or_authority, and business_activity or financial_ratio assessment "
                "before VERIFIED is accepted for execution."
            ),
            "records": [],
        }
        EVIDENCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        created["evidence"] = str(EVIDENCE_PATH)
    if not PERSONAL_RESTRICTIONS_PATH.exists():
        cfg = default_personal_restrictions_config()
        PERSONAL_RESTRICTIONS_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        created["personal_restrictions"] = str(PERSONAL_RESTRICTIONS_PATH)
    return created


def load_local_screening_inputs(db=None) -> Dict[str, Any]:
    """Load evidence + personal config + optional watchlist (read-only)."""
    ensure_local_templates()
    evidence = load_evidence_records(EVIDENCE_PATH)
    personal = load_personal_restrictions_config(PERSONAL_RESTRICTIONS_PATH)
    watchlist = load_watchlist_shariah(db) if db is not None else {}
    return {
        "evidence_records": evidence,
        "evidence_path": str(EVIDENCE_PATH),
        "personal_config": personal,
        "personal_path": str(PERSONAL_RESTRICTIONS_PATH),
        "watchlist_meta": watchlist,
        "production_writes": False,
    }


def stage_local_manual_review(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append an explicit manual review note to the isolated local review log.

    Does NOT write production DB and does NOT auto-approve VERIFIED status.
    Confirmation of VERIFIED still requires a complete evidence record in
    evidence_records.json reviewed by a human.
    """
    ensure_local_shariah_dirs()
    ticker = str(entry.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker required")
    canonical = resolve_proposed_alias(ticker).get("proposed_canonical") or ticker
    row = {
        "staged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": canonical,
        "action": str(entry.get("action") or "REVIEW_NOTE").strip().upper(),
        "notes": str(entry.get("notes") or "").strip(),
        "proposed_status": entry.get("proposed_status"),
        "reviewer": str(entry.get("reviewer") or "").strip(),
        "auto_approved": False,
        "production_written": False,
        "is_independent_verification": False,
    }
    with LOCAL_REVIEWS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def build_universe_monitoring_report(
    *,
    universe_rows: Sequence[Dict[str, Any]],
    evidence_records: Sequence[ShariahEvidenceRecord],
    personal_config: Dict[str, Any],
    watchlist_meta: Optional[Dict[str, Dict[str, str]]] = None,
    buy_priority_tickers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Full-universe monitoring report with eligibility and review actions."""
    watchlist_meta = watchlist_meta or {}
    priority = {str(t).strip().upper() for t in (buy_priority_tickers or []) if t}
    rows: List[Dict[str, Any]] = []
    counts = {
        "shariah_VERIFIED": 0,
        "shariah_NOT_VERIFIED": 0,
        "shariah_NON_COMPLIANT": 0,
        "personal_ALLOWED": 0,
        "personal_EXCLUDED": 0,
        "personal_REVIEW_REQUIRED": 0,
        "execution_ELIGIBLE": 0,
        "execution_BLOCKED": 0,
    }
    review_queue: List[Dict[str, Any]] = []
    shariah_blocked_buys: List[Dict[str, Any]] = []

    for item in universe_rows:
        if not item:
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        signal = item.get("v40_signal") or item.get("signal") or ""
        sector = item.get("sector")
        wl = watchlist_meta.get(ticker)
        elig = evaluate_investment_eligibility(
            ticker,
            shariah_status=item.get("shariah_status"),
            evidence_records=list(evidence_records),
            watchlist_meta=wl if wl else None,
            personal_config=personal_config,
            sector=sector,
            require_complete_evidence=True,
        )
        sh = elig["shariah_status"]
        pr = elig["personal_restriction_status"]
        if sh == "VERIFIED":
            counts["shariah_VERIFIED"] += 1
        elif sh == "NON-COMPLIANT":
            counts["shariah_NON_COMPLIANT"] += 1
        else:
            counts["shariah_NOT_VERIFIED"] += 1
        if pr == "ALLOWED":
            counts["personal_ALLOWED"] += 1
        elif pr == "EXCLUDED":
            counts["personal_EXCLUDED"] += 1
        else:
            counts["personal_REVIEW_REQUIRED"] += 1
        if elig["execution_eligible"]:
            counts["execution_ELIGIBLE"] += 1
        else:
            counts["execution_BLOCKED"] += 1

        next_action = _next_review_action(elig, signal=str(signal), is_priority=ticker in priority)
        row = {
            "ticker": ticker,
            "name": item.get("name") or item.get("company_name") or "",
            "v40_signal": signal,
            "shariah_screening_status": sh,
            "personal_restriction_status": pr,
            "evidence_source": elig.get("shariah_source") or "",
            "evidence_date": elig.get("shariah_assessment_date") or "",
            "evidence_quality": elig.get("shariah_evidence_quality"),
            "eligibility_outcome": elig["execution_eligibility"],
            "execution_eligible": elig["execution_eligible"],
            "blocking_reason": elig.get("blocking_reason") or "",
            "next_review_action": next_action,
            "is_buy_priority": ticker in priority,
            "reason_codes": elig.get("reason_codes") or [],
        }
        rows.append(row)

        if not elig["execution_eligible"] and (
            sh != "VERIFIED"
            or elig.get("shariah_evidence_quality") not in ("VALID",)
            or pr != "ALLOWED"
        ):
            review_queue.append(row)

        sig_u = str(signal).strip().upper()
        if sig_u in ("BUY CANDIDATE", "BUY") and not elig["execution_eligible"]:
            if "SHARIAH" in ",".join(elig.get("reason_codes") or []) or sh != "VERIFIED":
                shariah_blocked_buys.append(row)

    # Prioritize review queue: BUY candidates first, then others
    def _queue_key(r: Dict[str, Any]):
        return (0 if r.get("is_buy_priority") else 1, 0 if str(r.get("v40_signal")).upper().startswith("BUY") else 1, r.get("ticker") or "")

    review_queue_sorted = sorted(review_queue, key=_queue_key)
    buy_queue = [r for r in review_queue_sorted if r.get("is_buy_priority") or str(r.get("v40_signal")).upper() in ("BUY CANDIDATE", "BUY")]

    return {
        "stage": "D2.4G",
        "read_only": True,
        "production_writes": False,
        "total": len(rows),
        "counts": {
            "shariah_VERIFIED": counts["shariah_VERIFIED"],
            "shariah_NOT_VERIFIED": counts["shariah_NOT_VERIFIED"],
            "shariah_NON_COMPLIANT": counts["shariah_NON_COMPLIANT"],
            "personal_ALLOWED": counts["personal_ALLOWED"],
            "personal_EXCLUDED": counts["personal_EXCLUDED"],
            "personal_REVIEW_REQUIRED": counts["personal_REVIEW_REQUIRED"],
            "execution_ELIGIBLE": counts["execution_ELIGIBLE"],
            "execution_BLOCKED": counts["execution_BLOCKED"],
        },
        "rows": rows,
        "review_queue": review_queue_sorted,
        "buy_candidates_review_queue": buy_queue,
        "shariah_blocked_buy_opportunities": shariah_blocked_buys,
        "broker_submissions": 0,
    }


def _next_review_action(elig: Dict[str, Any], *, signal: str, is_priority: bool) -> str:
    codes = set(elig.get("reason_codes") or [])
    prefix = "PRIORITY: " if is_priority or str(signal).upper() in ("BUY CANDIDATE", "BUY") else ""
    if "SHARIAH_EVIDENCE_CONFLICT" in codes:
        return prefix + "Resolve conflicting assessments with documented provider evidence"
    if "SHARIAH_EVIDENCE_EXPIRED" in codes:
        return prefix + "Re-screen — evidence expired"
    if "SHARIAH_NON_COMPLIANT" in codes:
        return prefix + "Confirm NON-COMPLIANT documentation; keep blocked from proposals"
    if "PERSONAL_EXCLUDED" in codes:
        return prefix + "Personal exclusion in force — no proposal"
    if "PERSONAL_REVIEW_REQUIRED" in codes:
        return prefix + "Complete personal restriction review with evidence_note"
    if "SHARIAH_EVIDENCE_INCOMPLETE" in codes or "SHARIAH_NOT_VERIFIED" in codes:
        return prefix + "Obtain independent screening evidence (business + ratios + source + dates)"
    if elig.get("execution_eligible"):
        return "No action — execution eligible (still subject to emergency stop / flags)"
    return prefix + "Manual screening review required"


def run_universe_workflow(
    *,
    universe_rows: Sequence[Dict[str, Any]],
    buy_priority_tickers: Optional[Sequence[str]] = None,
    db=None,
) -> Dict[str, Any]:
    """End-to-end local workflow: load inputs → monitor → review queues."""
    inputs = load_local_screening_inputs(db=db)
    report = build_universe_monitoring_report(
        universe_rows=universe_rows,
        evidence_records=inputs["evidence_records"],
        personal_config=inputs["personal_config"],
        watchlist_meta=inputs["watchlist_meta"],
        buy_priority_tickers=buy_priority_tickers,
    )
    report["inputs"] = {
        "evidence_path": inputs["evidence_path"],
        "evidence_record_count": len(inputs["evidence_records"]),
        "personal_path": inputs["personal_path"],
        "watchlist_row_count": len(inputs["watchlist_meta"]),
        "production_writes": False,
    }
    return report
