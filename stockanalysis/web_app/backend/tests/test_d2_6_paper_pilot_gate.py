"""Stage D2.6 — paper pilot gate unit tests (no broker calls required for core invariants)."""
from __future__ import annotations

from app.services.paper_pilot_gate import (
    PILOT_AUTO_RETRY,
    PILOT_AUTO_SUBMIT,
    PILOT_BATCH_EXECUTION,
    PILOT_MAX_ORDERS,
    PilotGateState,
    assess_soak_prerequisite,
    build_order_preview,
    size_whole_share_limit,
    verify_pilot_gate_invariants,
)


def test_pilot_gate_defaults_are_strict():
    assert PILOT_MAX_ORDERS == 1
    assert PILOT_AUTO_SUBMIT is False
    assert PILOT_AUTO_RETRY is False
    assert PILOT_BATCH_EXECUTION is False


def test_verify_pilot_gate_invariants_pass_with_safe_flags(monkeypatch):
    monkeypatch.setattr("app.services.paper_pilot_gate.IBKR_EMERGENCY_STOP", True)
    monkeypatch.setattr("app.services.paper_pilot_gate.TRADING_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.paper_pilot_gate.ALPACA_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.paper_pilot_gate.IBKR_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.paper_pilot_gate.LIVE_TRADING_ENABLED", False)
    monkeypatch.setattr("app.services.paper_pilot_gate.STAGE_APPROVAL_ENABLED", False)
    monkeypatch.setattr("app.services.paper_pilot_gate.STAGE_SUBMISSION_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.IBKR_EMERGENCY_STOP", True)
    monkeypatch.setattr("app.services.observation_safety.TRADING_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.ALPACA_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.IBKR_EXECUTION_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.LIVE_TRADING_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.STAGE_APPROVAL_ENABLED", False)
    monkeypatch.setattr("app.services.observation_safety.STAGE_SUBMISSION_ENABLED", False)

    result = verify_pilot_gate_invariants(PilotGateState())
    assert result["passed"] is True
    assert result["automatic_submission_permitted"] is False
    assert result["manual_approval_required"] is True


def test_sizing_rejects_ask_above_cap():
    out = size_whole_share_limit(ask=550.0, max_order_notional_usd=500.0, cash=100_000.0)
    assert out["ok"] is False
    assert "INSUFFICIENT_CASH_FOR_ONE_SHARE" in out["reason_codes"]


def test_sizing_whole_shares_under_cap():
    out = size_whole_share_limit(ask=150.13, max_order_notional_usd=500.0, cash=100_000.0)
    assert out["ok"] is True
    assert out["qty"] == 3
    assert out["notional"] == round(3 * 150.13, 2)


def test_soak_incomplete_blocks_prerequisite():
    ledger = {
        "soak_complete": False,
        "target_completed_pairs": 3,
        "completed_pair_ids": ["2026-10-26->2026-10-27", "2026-10-27->2026-10-28"],
        "sessions": [],
    }
    out = assess_soak_prerequisite(ledger)
    assert out["prerequisite_met"] is False
    assert out["reason_code"] == "SOAK_INCOMPLETE"
    assert out["remaining"]


def test_preview_not_ready_without_selection():
    preview = build_order_preview({"selected": False, "reason_code": "NOPE"})
    assert preview["preview_ready"] is False
    assert preview["reason_code"] == "NOPE"
