"""Shariah screening evidence model (Stage D2.4G).

Captures independently supported assessments. Does not invent VERIFIED results.
Missing or expired evidence fails closed. A research shortlist is not verification.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.shariah_eligibility import (
    STATUS_COMPLIANT_LEGACY,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    normalize_shariah_status,
)
from app.services.ticker_integrity import resolve_proposed_alias

# Evidence quality labels (not Shariah statuses)
EVIDENCE_VALID = "VALID"
EVIDENCE_MISSING = "MISSING"
EVIDENCE_INCOMPLETE = "INCOMPLETE"
EVIDENCE_EXPIRED = "EXPIRED"
EVIDENCE_CONFLICTING = "CONFLICTING"
EVIDENCE_LEGACY_LABEL = "LEGACY_LABEL_NOT_INDEPENDENT"
EVIDENCE_SHORTLIST_ONLY = "RESEARCH_SHORTLIST_NOT_VERIFICATION"


@dataclass
class ShariahEvidenceRecord:
    """One screening assessment for a ticker."""

    ticker: str
    status: str = STATUS_NOT_VERIFIED
    company_identifier: str = ""
    methodology_provider: str = ""
    business_activity_assessment: str = ""
    financial_ratio_assessment: str = ""
    source_reference: str = ""
    assessment_date: str = ""
    expiry_or_review_date: str = ""
    reviewer_or_authority: str = ""
    rationale: str = ""
    is_research_shortlist: bool = False
    record_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _canonical_ticker(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    alias = resolve_proposed_alias(raw)
    return str(alias.get("proposed_canonical") or raw).upper()


def evidence_from_dict(raw: Dict[str, Any]) -> ShariahEvidenceRecord:
    return ShariahEvidenceRecord(
        ticker=_canonical_ticker(raw.get("ticker") or ""),
        status=str(raw.get("status") or raw.get("shariah_status") or STATUS_NOT_VERIFIED).strip(),
        company_identifier=str(
            raw.get("company_identifier") or raw.get("name") or raw.get("company_name") or ""
        ).strip(),
        methodology_provider=str(
            raw.get("methodology_provider") or raw.get("methodology") or raw.get("provider") or ""
        ).strip(),
        business_activity_assessment=str(
            raw.get("business_activity_assessment") or raw.get("business_activity") or ""
        ).strip(),
        financial_ratio_assessment=str(
            raw.get("financial_ratio_assessment") or raw.get("financial_ratios") or ""
        ).strip(),
        source_reference=str(
            raw.get("source_reference") or raw.get("source") or raw.get("shariah_source") or ""
        ).strip(),
        assessment_date=str(
            raw.get("assessment_date") or raw.get("date") or raw.get("shariah_date") or ""
        ).strip(),
        expiry_or_review_date=str(
            raw.get("expiry_or_review_date") or raw.get("expiry_date") or raw.get("review_date") or ""
        ).strip(),
        reviewer_or_authority=str(
            raw.get("reviewer_or_authority") or raw.get("reviewer") or raw.get("authority") or ""
        ).strip(),
        rationale=str(raw.get("rationale") or raw.get("notes") or "").strip(),
        is_research_shortlist=bool(raw.get("is_research_shortlist") or raw.get("research_shortlist")),
        record_id=str(raw.get("record_id") or raw.get("id") or "").strip(),
    )


def validate_evidence_record(
    record: ShariahEvidenceRecord,
    *,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """Validate evidence completeness / expiry. Never upgrades status."""
    today = as_of or datetime.now(timezone.utc).date()
    normalized = normalize_shariah_status(record.status)
    missing_fields: List[str] = []

    if not record.ticker:
        missing_fields.append("ticker")

    # Research shortlist alone is never independent verification
    if record.is_research_shortlist and normalized == STATUS_VERIFIED:
        return {
            "evidence_quality": EVIDENCE_SHORTLIST_ONLY,
            "effective_status": STATUS_NOT_VERIFIED,
            "normalized_status": STATUS_NOT_VERIFIED,
            "is_valid_for_execution": False,
            "blocking_reason": "Research shortlist is not independent Shariah verification",
            "missing_fields": [],
            "expired": False,
            "record": record.to_dict(),
        }

    if normalized == STATUS_COMPLIANT_LEGACY:
        return {
            "evidence_quality": EVIDENCE_LEGACY_LABEL,
            "effective_status": STATUS_NOT_VERIFIED,
            "normalized_status": STATUS_COMPLIANT_LEGACY,
            "is_valid_for_execution": False,
            "blocking_reason": "Legacy COMPLIANT label is not independently verified evidence",
            "missing_fields": [],
            "expired": False,
            "record": record.to_dict(),
        }

    if normalized == STATUS_VERIFIED:
        for field_name, value in (
            ("methodology_provider", record.methodology_provider),
            ("source_reference", record.source_reference),
            ("assessment_date", record.assessment_date),
            ("reviewer_or_authority", record.reviewer_or_authority),
        ):
            if not value:
                missing_fields.append(field_name)
        # At least one of business-activity or financial-ratio assessments required
        if not record.business_activity_assessment and not record.financial_ratio_assessment:
            missing_fields.append("business_activity_assessment|financial_ratio_assessment")
        if missing_fields:
            return {
                "evidence_quality": EVIDENCE_INCOMPLETE,
                "effective_status": STATUS_NOT_VERIFIED,
                "normalized_status": STATUS_VERIFIED,
                "is_valid_for_execution": False,
                "blocking_reason": "VERIFIED claim missing required evidence fields",
                "missing_fields": missing_fields,
                "expired": False,
                "record": record.to_dict(),
            }

    assessment_d = _parse_date(record.assessment_date)
    expiry_d = _parse_date(record.expiry_or_review_date)
    expired = False
    if expiry_d is not None and expiry_d < today:
        expired = True
    # If VERIFIED without expiry, treat as needing review (fail closed for execution)
    if normalized == STATUS_VERIFIED and expiry_d is None:
        return {
            "evidence_quality": EVIDENCE_INCOMPLETE,
            "effective_status": STATUS_NOT_VERIFIED,
            "normalized_status": STATUS_VERIFIED,
            "is_valid_for_execution": False,
            "blocking_reason": "VERIFIED evidence missing expiry/review date (fail-closed)",
            "missing_fields": ["expiry_or_review_date"],
            "expired": False,
            "record": record.to_dict(),
        }

    if expired:
        return {
            "evidence_quality": EVIDENCE_EXPIRED,
            "effective_status": STATUS_NOT_VERIFIED,
            "normalized_status": normalized,
            "is_valid_for_execution": False,
            "blocking_reason": "Screening evidence expired — re-review required",
            "missing_fields": [],
            "expired": True,
            "record": record.to_dict(),
        }

    if normalized == STATUS_NON_COMPLIANT:
        return {
            "evidence_quality": EVIDENCE_VALID,
            "effective_status": STATUS_NON_COMPLIANT,
            "normalized_status": STATUS_NON_COMPLIANT,
            "is_valid_for_execution": False,
            "blocking_reason": "Shariah status is NON-COMPLIANT",
            "missing_fields": [],
            "expired": False,
            "record": record.to_dict(),
        }

    if normalized == STATUS_VERIFIED:
        return {
            "evidence_quality": EVIDENCE_VALID,
            "effective_status": STATUS_VERIFIED,
            "normalized_status": STATUS_VERIFIED,
            "is_valid_for_execution": True,
            "blocking_reason": "",
            "missing_fields": [],
            "expired": False,
            "assessment_date": assessment_d.isoformat() if assessment_d else record.assessment_date,
            "expiry_or_review_date": expiry_d.isoformat() if expiry_d else "",
            "record": record.to_dict(),
        }

    return {
        "evidence_quality": EVIDENCE_MISSING if not record.source_reference else EVIDENCE_INCOMPLETE,
        "effective_status": STATUS_NOT_VERIFIED,
        "normalized_status": normalized,
        "is_valid_for_execution": False,
        "blocking_reason": "Shariah status is NOT VERIFIED (fail-closed)",
        "missing_fields": missing_fields,
        "expired": False,
        "record": record.to_dict(),
    }


def load_evidence_records(path: Optional[Path]) -> List[ShariahEvidenceRecord]:
    """Load local evidence JSON. Empty/missing file → no records (not an error)."""
    if path is None or not path.exists() or not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records_raw: List[Any]
    if isinstance(raw, dict):
        records_raw = list(raw.get("records") or [])
    elif isinstance(raw, list):
        records_raw = raw
    else:
        return []
    out: List[ShariahEvidenceRecord] = []
    for item in records_raw:
        if isinstance(item, dict) and (item.get("ticker") or item.get("symbol")):
            if "ticker" not in item and item.get("symbol"):
                item = {**item, "ticker": item["symbol"]}
            out.append(evidence_from_dict(item))
    return out


def resolve_ticker_evidence(
    ticker: str,
    records: Sequence[ShariahEvidenceRecord],
    *,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """Pick effective evidence for a ticker; detect duplicates/conflicts; fail closed."""
    canonical = _canonical_ticker(ticker)
    matches = [r for r in records if _canonical_ticker(r.ticker) == canonical]
    if not matches:
        # Also match raw alias input (e.g. SQ vs XYZ) already handled by canonical
        return {
            "ticker": canonical,
            "evidence_quality": EVIDENCE_MISSING,
            "effective_status": STATUS_NOT_VERIFIED,
            "is_valid_for_execution": False,
            "blocking_reason": "No Shariah screening evidence on file",
            "duplicate_count": 0,
            "conflict": False,
            "validations": [],
            "selected": None,
        }

    validations = [validate_evidence_record(r, as_of=as_of) for r in matches]
    effective_statuses = {v["effective_status"] for v in validations}
    conflict = STATUS_VERIFIED in effective_statuses and STATUS_NON_COMPLIANT in effective_statuses

    if conflict:
        return {
            "ticker": canonical,
            "evidence_quality": EVIDENCE_CONFLICTING,
            "effective_status": STATUS_NOT_VERIFIED,
            "is_valid_for_execution": False,
            "blocking_reason": "Conflicting VERIFIED vs NON-COMPLIANT assessments — fail-closed",
            "duplicate_count": len(matches),
            "conflict": True,
            "validations": validations,
            "selected": None,
        }

    # Prefer valid VERIFIED, else NON-COMPLIANT (documented), else first incomplete/missing
    selected = None
    for v in validations:
        if v.get("is_valid_for_execution"):
            selected = v
            break
    if selected is None:
        for v in validations:
            if v.get("effective_status") == STATUS_NON_COMPLIANT:
                selected = v
                break
    if selected is None:
        selected = validations[0]

    return {
        "ticker": canonical,
        "evidence_quality": selected.get("evidence_quality"),
        "effective_status": selected.get("effective_status"),
        "is_valid_for_execution": bool(selected.get("is_valid_for_execution")),
        "blocking_reason": selected.get("blocking_reason") or "",
        "duplicate_count": len(matches),
        "conflict": False,
        "validations": validations,
        "selected": selected,
        "source_reference": (selected.get("record") or {}).get("source_reference", ""),
        "assessment_date": (selected.get("record") or {}).get("assessment_date", ""),
        "expiry_or_review_date": (selected.get("record") or {}).get("expiry_or_review_date", ""),
        "methodology_provider": (selected.get("record") or {}).get("methodology_provider", ""),
    }


def watchlist_row_to_evidence(meta: Dict[str, str], ticker: str) -> Optional[ShariahEvidenceRecord]:
    """Map legacy WatchlistStock fields into an evidence record (may be incomplete)."""
    if not meta:
        return None
    status = str(meta.get("status") or "").strip()
    if not status:
        return None
    return ShariahEvidenceRecord(
        ticker=_canonical_ticker(ticker),
        status=status,
        source_reference=str(meta.get("source") or "").strip(),
        assessment_date=str(meta.get("date") or "").strip(),
        methodology_provider=str(meta.get("methodology_provider") or "").strip(),
        reviewer_or_authority=str(meta.get("reviewer_or_authority") or "").strip(),
        expiry_or_review_date=str(meta.get("expiry_or_review_date") or "").strip(),
        business_activity_assessment=str(meta.get("business_activity_assessment") or "").strip(),
        financial_ratio_assessment=str(meta.get("financial_ratio_assessment") or "").strip(),
        rationale=str(meta.get("notes") or "").strip(),
    )
