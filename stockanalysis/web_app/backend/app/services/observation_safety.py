"""Execution-safety assertions for observation sessions (Stage D2.4L).

Must pass before and after every observation session. Never mutates flags.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import (
    ALPACA_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    IBKR_EXECUTION_ENABLED,
    LIVE_TRADING_ENABLED,
    TRADING_EXECUTION_ENABLED,
)
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED


def assert_observation_safety(
    *,
    phase: str = "pre",
    submissions_attempted: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return structured safety verdict. Raises AssertionError only if caller asks via raise_on_fail."""
    failures: List[str] = []
    checks = {
        "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
        "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
        "alpaca_execution_enabled": bool(ALPACA_EXECUTION_ENABLED),
        "ibkr_execution_enabled": bool(IBKR_EXECUTION_ENABLED),
        "live_trading_enabled": bool(LIVE_TRADING_ENABLED),
        "stage_approval_enabled": bool(STAGE_APPROVAL_ENABLED),
        "stage_submission_enabled": bool(STAGE_SUBMISSION_ENABLED),
        "submissions_attempted": int(submissions_attempted),
    }
    if not checks["ibkr_emergency_stop"]:
        failures.append("IBKR_EMERGENCY_STOP must be True during observation")
    if checks["trading_execution_enabled"]:
        failures.append("TRADING_EXECUTION_ENABLED must be False")
    if checks["alpaca_execution_enabled"]:
        failures.append("ALPACA_EXECUTION_ENABLED must be False")
    if checks["ibkr_execution_enabled"]:
        failures.append("IBKR_EXECUTION_ENABLED must be False")
    if checks["live_trading_enabled"]:
        failures.append("LIVE_TRADING_ENABLED must be False")
    if checks["stage_approval_enabled"]:
        failures.append("STAGE_APPROVAL_ENABLED must be False")
    if checks["stage_submission_enabled"]:
        failures.append("STAGE_SUBMISSION_ENABLED must be False")
    if checks["submissions_attempted"] != 0:
        failures.append("submissions_attempted must remain 0")

    return {
        "phase": phase,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failures": failures,
        "passed": len(failures) == 0,
        "extra": extra or {},
    }


def require_observation_safety(**kwargs) -> Dict[str, Any]:
    result = assert_observation_safety(**kwargs)
    if not result["passed"]:
        raise AssertionError(
            f"Observation safety failed ({result['phase']}): {result['failures']}"
        )
    return result
