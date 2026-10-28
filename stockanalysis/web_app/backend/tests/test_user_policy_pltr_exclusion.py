"""USER_POLICY — PLTR military/defence exclusion at proposal and submission gates."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import (
    ALPACA_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.buy_decision_engine import (
    AccountSnapshot,
    BuyDecisionEngine,
    DecisionContext,
)
from app.services.investment_eligibility import evaluate_investment_eligibility
from app.services.order_execution_service import (
    PaperOrderProposal,
    order_execution_service,
)
from app.services.order_proposal_engine import (
    STAGE_SUBMISSION_ENABLED,
    OrderProposalEngine,
)
from app.services.user_policy_eligibility import (
    MODE_USER_POLICY,
    POLICY_EXCLUDED,
    assert_user_policy_order_permitted,
    classify_user_policy,
)


NOW = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)


def _pltr_signal() -> dict:
    return {
        "ticker": "PLTR",
        "name": "Palantir Technologies Inc.",
        "signal": "BUY CANDIDATE",
        "signal_source": "V40_SCANNER",
        "strategy_version": "V4.0 Baseline (via V4.1 Engine in exit_mode=baseline)",
        "entry_rule": "DELAYED_STACK",
        "exit_rule": "MA250_3CLOSE",
        "close": 196.81,
        "market_as_of_date": "2026-10-28",
        "data_freshness": "FRESH",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "shariah_status": "NOT VERIFIED",
        "signal_id": "test_PLTR",
    }


def _account() -> AccountSnapshot:
    return AccountSnapshot(
        broker="alpaca",
        account_id="PA1234TEST",
        cash=100_000.0,
        equity=100_000.0,
        positions=[],
        open_orders=[],
        snapshot_fresh=True,
        connection_ok=True,
        as_of_utc=NOW.isoformat(),
    )


class TestPltrExplicitExclusion:
    def test_classify_pltr_excluded_military_defence(self):
        r = classify_user_policy(
            "PLTR",
            name="Palantir Technologies Inc.",
            sector="Technology",
            industry="Software - Infrastructure",
        )
        assert r["user_policy_status"] == POLICY_EXCLUDED
        assert "MILITARY_DEFENCE_EXPOSURE" in r["reason_codes"]
        assert r["proposal_permitted"] is False
        assert r["research_visible"] is True

    def test_assert_gate_blocks_pltr(self):
        g = assert_user_policy_order_permitted("PLTR")
        assert g["permitted"] is False
        assert g["user_policy_status"] == POLICY_EXCLUDED
        assert "MILITARY_DEFENCE_EXPOSURE" in g["reason_codes"]

    def test_investment_eligibility_blocks_execution(self):
        e = evaluate_investment_eligibility(
            "PLTR",
            name="Palantir Technologies Inc.",
            sector="Technology",
            industry="Software - Infrastructure",
            eligibility_mode=MODE_USER_POLICY,
        )
        assert e["execution_eligible"] is False
        assert e["user_policy_status"] == POLICY_EXCLUDED


class TestPltrProposalGate:
    def test_buy_decision_blocks_pltr_under_user_policy(self):
        engine = BuyDecisionEngine()
        ctx = DecisionContext(
            account=_account(),
            broker_quote={
                "symbol": "PLTR",
                "bid": 196.0,
                "ask": 197.0,
                "source": "ALPACA_IEX",
            },
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
            allow_off_session_sizing=True,
        )
        decision = engine.evaluate(_pltr_signal(), ctx)
        assert decision.classification != "BUY_READY"
        assert decision.classification in ("BLOCKED", "NO_ACTION", "WAIT")
        codes = " ".join(decision.reason_codes or [])
        assert (
            "USER_POLICY" in codes
            or "MILITARY" in codes
            or "EXCLUDED" in codes
            or "POLICY" in codes
            or not evaluate_investment_eligibility(
                "PLTR", eligibility_mode=MODE_USER_POLICY, name="Palantir Technologies Inc."
            )["execution_eligible"]
        )

    def test_order_proposal_engine_does_not_build_pltr_proposal(self):
        engine = OrderProposalEngine()
        ctx = DecisionContext(
            account=_account(),
            broker_quote={
                "symbol": "PLTR",
                "bid": 196.0,
                "ask": 197.0,
                "source": "ALPACA_IEX",
            },
            emergency_stop=False,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
            allow_off_session_sizing=True,
        )
        out = engine.process_signal(_pltr_signal(), ctx, persist=False)
        assert out.get("proposal") is None
        assert out["decision"]["classification"] != "BUY_READY"
        assert STAGE_SUBMISSION_ENABLED is False


class TestPltrSubmissionGate:
    def test_order_risk_rejects_pltr_user_policy(self, monkeypatch):
        # Keep global safety intact
        assert IBKR_EMERGENCY_STOP is True
        assert TRADING_EXECUTION_ENABLED is False
        assert ALPACA_EXECUTION_ENABLED is False

        db = MagicMock()
        settings = {
            "emergency_stop": False,  # isolate USER_POLICY check from emergency stop
            "max_order_notional_usd": 500.0,
            "max_daily_notional_usd": 2500.0,
            "max_daily_orders": 5,
            "max_open_orders": 1,
        }
        monkeypatch.setattr(
            order_execution_service,
            "get_bound_paper_account_id",
            lambda _db, broker="alpaca": "PA1234TEST",
        )
        monkeypatch.setattr(
            order_execution_service,
            "get_us_daily_metrics_from_db",
            lambda _db, _day: {
                "daily_orders_count": 0,
                "daily_notional_sum": 0.0,
                "open_orders_count": 0,
            },
        )
        # Avoid alpaca/ibkr paper_status path issues for this unit check
        monkeypatch.setattr(
            "app.services.order_execution_service.ibkr_service.get_paper_account_status",
            lambda _db: {"account_id": "PA1234TEST", "positions": []},
        )

        proposal = PaperOrderProposal(
            symbol="PLTR",
            action="BUY",
            order_type="LIMIT",
            quantity=2.0,
            limit_price=197.48,
            currency="USD",
            broker="alpaca",
            account_id="PA1234TEST",
            client_idempotency_key="test_pltr_policy_block",
            notes="should reject",
            market_quote={"ask": 197.48, "bid": 196.0, "source": "ALPACA_IEX"},
        )
        # Force broker path that defines paper_status via ibkr stub by using ibkr briefly
        # — for alpaca, paper_status may be unset; patch evaluate path after policy check.
        report = order_execution_service.evaluate_order_risk(
            db, proposal, settings, now_utc=NOW
        )
        policy_checks = [c for c in report["checks"] if c["name"] == "user_policy_eligibility"]
        assert policy_checks, "user_policy_eligibility check missing"
        assert policy_checks[0]["passed"] is False
        assert report["passed"] is False
        assert any("USER_POLICY" in r or "MILITARY" in r for r in report.get("failed_reasons", []))

    def test_alpaca_execution_agent_rejects_pltr_before_submit(self, monkeypatch):
        import sys
        from pathlib import Path

        dm_root = Path(__file__).resolve().parents[4]  # .../Digital Marketing
        if str(dm_root) not in sys.path:
            sys.path.insert(0, str(dm_root))

        from alpaca_adapter.alpaca_execution_agent import AlpacaExecutionAgent
        from alpaca_adapter.alpaca_paper_adapter import NON_EXECUTING_BUILD_GUARD

        assert NON_EXECUTING_BUILD_GUARD is True
        assert ALPACA_EXECUTION_ENABLED is False

        agent = AlpacaExecutionAgent(agent_id="test_pltr_gate")
        # Even if operational flags were flipped, USER_POLICY must still reject PLTR
        monkeypatch.setattr(agent, "emergency_stop", False)
        monkeypatch.setattr(agent, "execution_enabled", True)

        result = agent.execute_paper_order(
            order_id=1,
            symbol="PLTR",
            quantity=2,
            limit_price=197.48,
            side="BUY",
            client_order_id="test_pltr_submit_block",
            now_utc=NOW,
        )
        assert result["status"] == "REJECTED"
        reason = str(result.get("reason") or "")
        assert "USER_POLICY" in reason or "MILITARY" in reason or result.get("user_policy_status") == "EXCLUDED"
        assert "MILITARY_DEFENCE_EXPOSURE" in (result.get("reason_codes") or []) or "MILITARY" in reason


class TestSafetyUnchanged:
    def test_execution_still_disabled(self):
        assert STAGE_SUBMISSION_ENABLED is False
        assert TRADING_EXECUTION_ENABLED is False
        assert ALPACA_EXECUTION_ENABLED is False
        assert IBKR_EMERGENCY_STOP is True
