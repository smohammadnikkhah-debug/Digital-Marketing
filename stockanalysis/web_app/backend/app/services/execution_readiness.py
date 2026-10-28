"""Execution readiness classifier (Stage D2.4D).

Separates investment opportunity (BUY_READY/…) from ability to submit orders.
Never bypasses emergency stops or enables submission.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import (
    ALPACA_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    IBKR_EXECUTION_ENABLED,
    TRADING_EXECUTION_ENABLED,
)
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext
from app.services.shariah_eligibility import ELIGIBLE, classify_execution_eligibility

READY = "READY"
DISABLED = "DISABLED"
EMERGENCY_STOP = "EMERGENCY_STOP"
ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
RISK_BLOCKED = "RISK_BLOCKED"


def classify_execution_readiness(
    *,
    signal: Dict[str, Any],
    ctx: DecisionContext,
    investment_classification: str,
) -> Dict[str, Any]:
    """Return execution readiness independent of investment decision visibility."""
    reasons: List[str] = []

    # Hard environment / stage guards — never bypass
    emergency = bool(ctx.emergency_stop) or bool(IBKR_EMERGENCY_STOP)
    if emergency:
        return {
            "execution_readiness": EMERGENCY_STOP,
            "execution_ready": False,
            "reason_codes": ["EMERGENCY_STOP_ACTIVE"],
            "submissions_permitted": False,
        }

    if not TRADING_EXECUTION_ENABLED and not ctx.trading_execution_enabled:
        reasons.append("TRADING_EXECUTION_DISABLED")
    if ctx.execution_enabled is False and not ALPACA_EXECUTION_ENABLED and not IBKR_EXECUTION_ENABLED:
        reasons.append("BROKER_EXECUTION_DISABLED")

    # Even if flags were true, D2.4D dry-run never permits submission
    submissions_permitted = False

    if reasons:
        # Execution path disabled — investment decision may still be BUY_READY
        return {
            "execution_readiness": DISABLED,
            "execution_ready": False,
            "reason_codes": reasons,
            "submissions_permitted": submissions_permitted,
        }

    shariah = classify_execution_eligibility(signal.get("shariah_status"))
    stored = str(signal.get("shariah_status") or "").strip().upper()
    from app.services.investment_eligibility import evaluate_investment_eligibility

    inv_elig = evaluate_investment_eligibility(
        str(signal.get("ticker") or ""),
        shariah_status=signal.get("shariah_status"),
        evidence_records=getattr(ctx, "shariah_evidence_records", None),
        watchlist_meta=getattr(ctx, "watchlist_shariah_meta", None),
        personal_config=getattr(ctx, "personal_restrictions_config", None),
        sector=signal.get("sector"),
        industry=signal.get("industry"),
        name=signal.get("name") or signal.get("company_name"),
        as_of=(ctx.now_utc.date() if getattr(ctx, "now_utc", None) else None),
        eligibility_mode=getattr(ctx, "eligibility_mode", None),
    )
    if not inv_elig.get("execution_eligible"):
        codes = list(inv_elig.get("reason_codes") or [])
        if not codes:
            codes = ["SHARIAH_BLOCKS_EXECUTION"]
        return {
            "execution_readiness": RISK_BLOCKED,
            "execution_ready": False,
            "reason_codes": codes,
            "submissions_permitted": False,
            "shariah": shariah,
            "investment_eligibility": inv_elig,
            "user_policy_status": inv_elig.get("user_policy_status"),
        }
    mode = str(getattr(ctx, "eligibility_mode", None) or "").strip().upper()
    if mode != "USER_POLICY":
        if stored != "VERIFIED" or not shariah.get("execution_eligible") or shariah.get("execution_eligibility") != ELIGIBLE:
            # Bare VERIFIED label without evidence still blocked by inv_elig above;
            # keep legacy guard when overlays absent and status is not VERIFIED.
            if stored != "VERIFIED":
                return {
                    "execution_readiness": RISK_BLOCKED,
                    "execution_ready": False,
                    "reason_codes": ["SHARIAH_BLOCKS_EXECUTION"],
                    "submissions_permitted": False,
                    "shariah": shariah,
                    "investment_eligibility": inv_elig,
                }

    acct: Optional[AccountSnapshot] = ctx.account
    if acct is None or not acct.account_id:
        return {
            "execution_readiness": ACCOUNT_UNAVAILABLE,
            "execution_ready": False,
            "reason_codes": ["ACCOUNT_DATA_UNAVAILABLE"],
            "submissions_permitted": False,
        }
    if not acct.snapshot_fresh or not acct.connection_ok:
        return {
            "execution_readiness": ACCOUNT_UNAVAILABLE,
            "execution_ready": False,
            "reason_codes": ["ACCOUNT_SNAPSHOT_STALE"],
            "submissions_permitted": False,
        }

    if not ctx.broker_quote:
        return {
            "execution_readiness": DATA_UNAVAILABLE,
            "execution_ready": False,
            "reason_codes": ["BROKER_QUOTE_UNAVAILABLE"],
            "submissions_permitted": False,
        }

    if investment_classification != "BUY_READY":
        return {
            "execution_readiness": RISK_BLOCKED,
            "execution_ready": False,
            "reason_codes": ["INVESTMENT_NOT_BUY_READY"],
            "submissions_permitted": False,
        }

    # Theoretically ready — still no submission in D2.4D
    return {
        "execution_readiness": READY,
        "execution_ready": True,
        "reason_codes": ["ACCOUNT_AND_QUOTE_OK", "SHARIAH_VERIFIED"],
        "submissions_permitted": False,
        "note": "D2.4D dry-run: submission remains disabled regardless of readiness",
    }
