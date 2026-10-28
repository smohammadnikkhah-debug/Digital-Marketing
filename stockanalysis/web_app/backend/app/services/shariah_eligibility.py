"""Shariah execution-eligibility classification (Stage D2.4B).

Preserves stored Shariah status metadata unchanged. Provides a separate,
testable eligibility layer for a future order-proposal engine.

Research signals may still be displayed regardless of eligibility.
"""
from typing import Any, Dict, Optional

# Statuses that may appear in watchlist / universe metadata.
STATUS_VERIFIED = "VERIFIED"
STATUS_NOT_VERIFIED = "NOT VERIFIED"
STATUS_NON_COMPLIANT = "NON-COMPLIANT"
# Legacy seed label used in some baseline seed paths; not a new certification.
STATUS_COMPLIANT_LEGACY = "COMPLIANT"

ELIGIBLE = "ELIGIBLE"
BLOCKED = "BLOCKED_FROM_EXECUTION"


def normalize_shariah_status(raw: Optional[str]) -> str:
    """Normalize free-text status for classification without mutating storage."""
    if raw is None:
        return STATUS_NOT_VERIFIED
    text = str(raw).strip().upper().replace("_", " ")
    if not text:
        return STATUS_NOT_VERIFIED
    if text in ("VERIFIED", "COMPLIANT", "SHARIAH COMPLIANT"):
        # COMPLIANT is treated as historically verified labeling only.
        return STATUS_VERIFIED if text == "VERIFIED" else STATUS_COMPLIANT_LEGACY
    if text in ("NON-COMPLIANT", "NON COMPLIANT", "NONCOMPLIANT"):
        return STATUS_NON_COMPLIANT
    if text in ("NOT VERIFIED", "UNVERIFIED", "UNKNOWN"):
        return STATUS_NOT_VERIFIED
    return STATUS_NOT_VERIFIED


def classify_execution_eligibility(shariah_status: Optional[str]) -> Dict[str, Any]:
    """Map Shariah metadata to future execution eligibility.

    Rules (fail-closed):
    - VERIFIED → ELIGIBLE for future execution consideration
    - COMPLIANT (legacy label) → ELIGIBLE (does not re-certify; classification only)
    - NOT VERIFIED → BLOCKED_FROM_EXECUTION
    - NON-COMPLIANT → BLOCKED_FROM_EXECUTION
    - Anything else → BLOCKED_FROM_EXECUTION

    Does not modify or overwrite the caller's stored shariah_status.
    """
    normalized = normalize_shariah_status(shariah_status)
    stored = str(shariah_status).strip() if shariah_status is not None else STATUS_NOT_VERIFIED

    if normalized in (STATUS_VERIFIED, STATUS_COMPLIANT_LEGACY):
        return {
            "execution_eligibility": ELIGIBLE,
            "execution_eligible": True,
            "eligibility_reason": (
                "Shariah status is VERIFIED"
                if normalized == STATUS_VERIFIED
                else "Legacy COMPLIANT label treated as eligible for classification only"
            ),
            "shariah_status_preserved": stored or STATUS_NOT_VERIFIED,
            "normalized_shariah_status": normalized,
        }

    if normalized == STATUS_NON_COMPLIANT:
        reason = "Shariah status is NON-COMPLIANT"
    else:
        reason = "Shariah status is NOT VERIFIED (fail-closed for execution)"

    return {
        "execution_eligibility": BLOCKED,
        "execution_eligible": False,
        "eligibility_reason": reason,
        "shariah_status_preserved": stored or STATUS_NOT_VERIFIED,
        "normalized_shariah_status": normalized,
    }


def attach_execution_eligibility(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of signal with eligibility fields attached."""
    out = dict(signal)
    meta = classify_execution_eligibility(out.get("shariah_status"))
    out.update(meta)
    return out
