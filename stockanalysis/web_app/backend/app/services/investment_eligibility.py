"""Combined investment execution eligibility (Stage D2.4G).

Single authority for proposal gates:
  Shariah VERIFIED (valid evidence) AND personal ALLOWED AND no unresolved checks.

Reuses shariah_eligibility / shariah_evidence / personal_restrictions.
Does not modify V4.0 BUY mathematics. Research signals remain visible when blocked.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from app.services.personal_restrictions import (
    RESTRICT_ALLOWED,
    assess_personal_restriction,
)
from app.services.shariah_eligibility import (
    BLOCKED,
    ELIGIBLE,
    STATUS_NON_COMPLIANT,
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    classify_execution_eligibility,
    normalize_shariah_status,
)
from app.services.shariah_evidence import (
    EVIDENCE_MISSING,
    ShariahEvidenceRecord,
    resolve_ticker_evidence,
    validate_evidence_record,
    watchlist_row_to_evidence,
)

EXEC_ELIGIBLE = "EXECUTION_ELIGIBLE"
EXEC_BLOCKED = "BLOCKED_FROM_EXECUTION"


def evaluate_investment_eligibility(
    ticker: str,
    *,
    shariah_status: Optional[str] = None,
    evidence_records: Optional[Sequence[ShariahEvidenceRecord]] = None,
    watchlist_meta: Optional[Dict[str, str]] = None,
    personal_config: Optional[Dict[str, Any]] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    name: Optional[str] = None,
    as_of: Optional[date] = None,
    unresolved_mandatory_checks: Optional[Sequence[str]] = None,
    require_complete_evidence: Optional[bool] = None,
    eligibility_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Fail-closed combined eligibility for order proposals.

    Modes:
    - USER_POLICY (D2.4H): proposal permitted when user-policy status is ALLOWED.
      Formal Shariah VERIFIED is optional and not required.
    - SHARIAH_STRICT (D2.4G): VERIFIED evidence + personal ALLOWED.
    - LEGACY / None: pre-D2.4H VERIFIED label gate for unit-test compatibility.

    When D2.4G overlays are absent (None evidence/watchlist/personal), falls back to
    the pre-D2.4G VERIFIED label gate for backward-compatible unit tests. Explicit
    overlays (including empty evidence lists) enable strict evidence validation.
    """
    from app.services.user_policy_eligibility import (
        MODE_SHARIAH_STRICT,
        MODE_USER_POLICY,
        POLICY_ALLOWED,
        classify_user_policy,
    )

    from app.services.ticker_integrity import resolve_canonical_ticker

    t = str(resolve_canonical_ticker(ticker).get("canonical") or ticker or "").strip().upper()
    unresolved = [str(c) for c in (unresolved_mandatory_checks or []) if str(c).strip()]
    mode = (eligibility_mode or "").strip().upper() or None

    # --- D2.4H USER_POLICY path (Shariah optional) ---
    if mode == MODE_USER_POLICY:
        policy = classify_user_policy(
            t, name=name, sector=sector, industry=industry
        )
        personal = assess_personal_restriction(t, config=personal_config, sector=sector)
        # Preserve explicit personal EXCLUDED overlays on top of USER_POLICY
        if personal.get("personal_restriction_status") == "EXCLUDED":
            policy_status = "EXCLUDED"
            reasons = ["PERSONAL_EXCLUDED"] + list(policy.get("reason_codes") or [])
            eligible = False
            blocking = personal.get("blocking_reason") or policy.get("evidence_note") or ""
        elif personal.get("personal_restriction_status") == "REVIEW REQUIRED":
            policy_status = "REVIEW REQUIRED"
            reasons = ["PERSONAL_REVIEW_REQUIRED"] + list(policy.get("reason_codes") or [])
            eligible = False
            blocking = personal.get("blocking_reason") or ""
        else:
            policy_status = policy.get("user_policy_status")
            reasons = list(policy.get("reason_codes") or [])
            eligible = policy_status == POLICY_ALLOWED and not unresolved
            if unresolved:
                reasons.append("UNRESOLVED_MANDATORY_SCREENING_CHECKS")
                eligible = False
            if policy_status != POLICY_ALLOWED:
                eligible = False
            blocking = "" if eligible else (policy.get("evidence_note") or policy_status)

        legacy_class = classify_execution_eligibility(shariah_status)
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "execution_eligibility": EXEC_ELIGIBLE if eligible else EXEC_BLOCKED,
            "execution_eligible": eligible,
            "shariah_status": str(shariah_status or STATUS_NOT_VERIFIED),
            "shariah_optional": True,
            "shariah_required": False,
            "user_policy_status": policy_status,
            "personal_restriction_status": personal.get("personal_restriction_status"),
            "personal_category_tags": list(policy.get("category_tags") or [])
            + list(personal.get("category_tags") or []),
            "blocking_reason": blocking if not eligible else "",
            "reason_codes": reasons if not eligible else ["POLICY_ALLOWED"],
            "unresolved_mandatory_checks": list(unresolved),
            "research_visible": True,
            "proposal_permitted": eligible,
            "legacy_shariah_classification": legacy_class,
            "evidence_resolution": {
                "evidence_source": policy.get("evidence_source"),
                "evidence_note": policy.get("evidence_note"),
                "business_type": policy.get("business_type"),
            },
            "personal_assessment": personal,
            "user_policy_assessment": policy,
            "strict_evidence_mode": False,
            "execution_eligibility_legacy": ELIGIBLE if eligible else BLOCKED,
            "normalized_shariah_status": normalize_shariah_status(shariah_status),
        }

    # Force strict evidence when SHARIAH_STRICT
    if mode == MODE_SHARIAH_STRICT and require_complete_evidence is None:
        require_complete_evidence = True


    overlays_present = (
        evidence_records is not None
        or watchlist_meta is not None
        or personal_config is not None
    )
    strict = (
        bool(require_complete_evidence)
        if require_complete_evidence is not None
        else overlays_present
    )

    # Build evidence list: file records + optional watchlist projection
    records: List[ShariahEvidenceRecord] = list(evidence_records or [])
    if watchlist_meta:
        wl_ev = watchlist_row_to_evidence(watchlist_meta, t)
        if wl_ev is not None:
            records.append(wl_ev)

    evidence_resolution = resolve_ticker_evidence(t, records, as_of=as_of)

    if evidence_resolution.get("evidence_quality") == EVIDENCE_MISSING and shariah_status:
        bare = ShariahEvidenceRecord(ticker=t, status=str(shariah_status))
        if strict:
            bare_v = validate_evidence_record(bare, as_of=as_of)
            evidence_resolution = {
                "ticker": t,
                "evidence_quality": bare_v.get("evidence_quality"),
                "effective_status": bare_v.get("effective_status"),
                "is_valid_for_execution": bool(bare_v.get("is_valid_for_execution")),
                "blocking_reason": bare_v.get("blocking_reason") or "",
                "duplicate_count": 0,
                "conflict": False,
                "validations": [bare_v],
                "selected": bare_v,
                "source_reference": "",
                "assessment_date": "",
                "expiry_or_review_date": "",
                "methodology_provider": "",
            }
        else:
            # Legacy label gate (D2.4C/D2.4D): VERIFIED string alone
            norm = normalize_shariah_status(shariah_status)
            label_ok = norm == STATUS_VERIFIED and str(shariah_status).strip().upper() == STATUS_VERIFIED
            evidence_resolution = {
                "ticker": t,
                "evidence_quality": "LEGACY_STATUS_LABEL",
                "effective_status": STATUS_VERIFIED if label_ok else (
                    STATUS_NON_COMPLIANT if norm == STATUS_NON_COMPLIANT else STATUS_NOT_VERIFIED
                ),
                "is_valid_for_execution": label_ok,
                "blocking_reason": (
                    ""
                    if label_ok
                    else (
                        "Shariah status is NON-COMPLIANT"
                        if norm == STATUS_NON_COMPLIANT
                        else "Shariah status is NOT VERIFIED (fail-closed for execution)"
                    )
                ),
                "duplicate_count": 0,
                "conflict": False,
                "validations": [],
                "selected": None,
                "source_reference": "",
                "assessment_date": "",
                "expiry_or_review_date": "",
                "methodology_provider": "",
                "legacy_label_mode": True,
            }

    effective_shariah = str(
        evidence_resolution.get("effective_status") or STATUS_NOT_VERIFIED
    )
    # Preserve legacy classify for research display metadata
    legacy_class = classify_execution_eligibility(
        shariah_status or evidence_resolution.get("effective_status")
    )

    personal = assess_personal_restriction(t, config=personal_config, sector=sector)

    reasons: List[str] = []
    shariah_ok = (
        effective_shariah == STATUS_VERIFIED
        and bool(evidence_resolution.get("is_valid_for_execution"))
    )
    if not shariah_ok:
        if effective_shariah == STATUS_NON_COMPLIANT:
            reasons.append("SHARIAH_NON_COMPLIANT")
        elif evidence_resolution.get("conflict"):
            reasons.append("SHARIAH_EVIDENCE_CONFLICT")
        elif evidence_resolution.get("evidence_quality") == "EXPIRED":
            reasons.append("SHARIAH_EVIDENCE_EXPIRED")
        elif evidence_resolution.get("evidence_quality") in (
            "INCOMPLETE",
            "LEGACY_LABEL_NOT_INDEPENDENT",
            "RESEARCH_SHORTLIST_NOT_VERIFICATION",
        ):
            reasons.append("SHARIAH_EVIDENCE_INCOMPLETE")
        else:
            reasons.append("SHARIAH_NOT_VERIFIED")

    personal_ok = personal.get("personal_restriction_status") == RESTRICT_ALLOWED
    if not personal_ok:
        if personal.get("personal_restriction_status") == "EXCLUDED":
            reasons.append("PERSONAL_EXCLUDED")
        else:
            reasons.append("PERSONAL_REVIEW_REQUIRED")

    if unresolved:
        reasons.append("UNRESOLVED_MANDATORY_SCREENING_CHECKS")

    eligible = bool(shariah_ok and personal_ok and not unresolved)

    blocking_reason = ""
    if not eligible:
        parts = []
        if not shariah_ok:
            parts.append(
                evidence_resolution.get("blocking_reason")
                or f"Shariah {effective_shariah}"
            )
        if not personal_ok:
            parts.append(personal.get("blocking_reason") or "Personal restriction")
        if unresolved:
            parts.append("Unresolved mandatory checks: " + ", ".join(unresolved))
        blocking_reason = " | ".join(parts)

    return {
        "ticker": t,
        "execution_eligibility": EXEC_ELIGIBLE if eligible else EXEC_BLOCKED,
        "execution_eligible": eligible,
        "shariah_status": effective_shariah,
        "shariah_evidence_quality": evidence_resolution.get("evidence_quality"),
        "shariah_source": evidence_resolution.get("source_reference") or "",
        "shariah_assessment_date": evidence_resolution.get("assessment_date") or "",
        "shariah_expiry_or_review_date": evidence_resolution.get("expiry_or_review_date") or "",
        "shariah_methodology_provider": evidence_resolution.get("methodology_provider") or "",
        "personal_restriction_status": personal.get("personal_restriction_status"),
        "personal_category_tags": personal.get("category_tags") or [],
        "blocking_reason": blocking_reason,
        "reason_codes": reasons,
        "unresolved_mandatory_checks": list(unresolved),
        "research_visible": True,
        "proposal_permitted": eligible,
        "legacy_shariah_classification": legacy_class,
        "evidence_resolution": evidence_resolution,
        "personal_assessment": personal,
        "strict_evidence_mode": strict,
        # Back-compat fields expected by older callers
        "execution_eligibility_legacy": ELIGIBLE if eligible else BLOCKED,
        "normalized_shariah_status": normalize_shariah_status(effective_shariah),
    }


def attach_investment_eligibility(
    signal: Dict[str, Any],
    *,
    evidence_records: Optional[Sequence[ShariahEvidenceRecord]] = None,
    watchlist_meta: Optional[Dict[str, Dict[str, str]]] = None,
    personal_config: Optional[Dict[str, Any]] = None,
    as_of: Optional[date] = None,
    eligibility_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Shallow-copy signal with D2.4G/D2.4H eligibility fields attached."""
    out = dict(signal)
    ticker = str(out.get("ticker") or "").strip().upper()
    wl = (watchlist_meta or {}).get(ticker)
    meta = evaluate_investment_eligibility(
        ticker,
        shariah_status=out.get("shariah_status"),
        evidence_records=evidence_records,
        watchlist_meta=wl,
        personal_config=personal_config,
        sector=out.get("sector"),
        industry=out.get("industry"),
        name=out.get("name") or out.get("company_name"),
        as_of=as_of,
        eligibility_mode=eligibility_mode,
    )
    out["shariah_status"] = meta.get("shariah_status") or out.get("shariah_status")
    out["personal_restriction_status"] = meta.get("personal_restriction_status")
    out["user_policy_status"] = meta.get("user_policy_status")
    out["investment_eligibility"] = meta
    out["execution_eligible"] = meta["execution_eligible"]
    out["execution_eligibility"] = meta["execution_eligibility"]
    out["eligibility_reason"] = meta["blocking_reason"] or "Eligible for execution consideration"
    out["proposal_permitted"] = meta["proposal_permitted"]
    out["eligibility_mode"] = meta.get("eligibility_mode") or eligibility_mode
    return out
