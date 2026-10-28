"""Stage D2.4C — BUY decision + order proposal engine (local, non-submitting)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.config import V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION, RISK_UI_SIGNAL_SOURCE
from app.services.buy_decision_engine import (
    BUY_READY,
    WAIT,
    BLOCKED,
    NO_ACTION,
    AccountSnapshot,
    BuyDecisionEngine,
    DecisionContext,
    VALID_V40_ENTRY_RULES,
)
from app.services.order_proposal_engine import (
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
    OrderProposalEngine,
    build_idempotency_key,
)
from app.services.us_session_freshness import (
    evaluate_signal_session_freshness,
    last_completed_us_equity_session,
)


# Tuesday 20 Oct 2026 15:00 UTC = 11:00 AM America/New_York — REGULAR session
NOW_REGULAR = datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc)
# Prior completed session while REGULAR is Monday 19 Oct 2026
AS_OF_FRESH = "2026-10-19"


def _base_signal(**overrides):
    sig = {
        "ticker": "AAPL",
        "signal": "BUY CANDIDATE",
        "signal_source": V40_SIGNAL_SOURCE,
        "strategy_version": V40_STRATEGY_VERSION,
        "entry_rule": "CROSS",
        "exit_rule": "MA250_3CLOSE",
        "is_fresh_analysis": True,
        "provenance_mode": "LIVE_SCAN",
        "market_as_of_date": AS_OF_FRESH,
        "as_of": AS_OF_FRESH,
        "validation_status": "OK",
        "data_freshness": "FRESH",
        "ma250": 180.0,
        "ma50": 190.0,
        "ma30": 195.0,
        "close": 200.0,
        "shariah_status": "VERIFIED",
        "scan_completed_at": "2026-10-19T20:35:00Z",
    }
    sig.update(overrides)
    return sig


def _quote(symbol="AAPL", bid=199.9, ask=200.0, source="ALPACA_IEX", **extra):
    q = {
        "source": source,
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "last": 199.95,
        "quote_timestamp": NOW_REGULAR.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "received_at": NOW_REGULAR.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_session": "REGULAR",
        "is_delayed": False,
        "is_synthetic": False,
    }
    q.update(extra)
    return q


def _account(**overrides) -> AccountSnapshot:
    acct = AccountSnapshot(
        broker="alpaca",
        account_id="PA1234567890ABCDEF",
        cash=10000.0,
        equity=10000.0,
        positions=[],
        open_orders=[],
        daily_orders_count=0,
        daily_notional_sum=0.0,
        snapshot_fresh=True,
        connection_ok=True,
        as_of_utc=NOW_REGULAR.isoformat(),
    )
    for k, v in overrides.items():
        setattr(acct, k, v)
    return acct


_MISSING = object()


def _ctx(account=_MISSING, quote=_MISSING, **kwargs) -> DecisionContext:
    defaults = dict(
        account=_account() if account is _MISSING else account,
        broker_quote=_quote() if quote is _MISSING else quote,
        emergency_stop=False,
        execution_enabled=False,
        trading_execution_enabled=False,
        now_utc=NOW_REGULAR,
    )
    defaults.update(kwargs)
    return DecisionContext(**defaults)


@pytest.fixture
def engine():
    return BuyDecisionEngine()


@pytest.fixture
def proposal_engine():
    return OrderProposalEngine()


class TestSessionFreshness:
    def test_regular_session_expects_prior_open_day(self):
        expected = last_completed_us_equity_session(NOW_REGULAR)
        assert expected.isoformat() == AS_OF_FRESH
        ok, code, _, _ = evaluate_signal_session_freshness(AS_OF_FRESH, NOW_REGULAR)
        assert ok and code == "SESSION_FRESH"

    def test_stale_as_of_rejected(self):
        ok, code, _, _ = evaluate_signal_session_freshness("2026-10-15", NOW_REGULAR)
        assert not ok and code == "STALE_MARKET_AS_OF"

    def test_weekend_uses_prior_session(self):
        # Saturday 2026-10-24 16:00 UTC
        sat = datetime(2026, 10, 24, 16, 0, 0, tzinfo=timezone.utc)
        expected = last_completed_us_equity_session(sat)
        assert expected.weekday() < 5
        assert expected.isoformat() == "2026-10-23"  # Friday


class TestDecisionClassifications:
    def test_buy_ready_happy_path(self, engine):
        d = engine.evaluate(_base_signal(), _ctx())
        assert d.classification == BUY_READY
        assert "V40_BUY_CONFIRMED" in d.reason_codes
        assert d.details["proposed_quantity"] >= 1
        assert d.details["limit_price_policy"] == "BUY_AT_ASK"
        assert d.signal_id.startswith("sig_")

    def test_no_action_non_buy(self, engine):
        d = engine.evaluate(_base_signal(signal="WATCH"), _ctx())
        assert d.classification == NO_ACTION
        assert "NOT_BUY_CANDIDATE" in d.reason_codes

    def test_no_action_risk_ui(self, engine):
        d = engine.evaluate(
            _base_signal(signal_source=RISK_UI_SIGNAL_SOURCE, not_a_v40_scanner_signal=True),
            _ctx(),
        )
        assert d.classification == NO_ACTION
        assert "RISK_UI_SIGNAL_REJECTED" in d.reason_codes

    def test_blocked_frozen_baseline(self, engine):
        d = engine.evaluate(
            _base_signal(provenance_mode="FROZEN_BASELINE", data_freshness="FROZEN_BASELINE"),
            _ctx(),
        )
        assert d.classification == BLOCKED
        assert "FROZEN_BASELINE_SIGNAL" in d.reason_codes

    def test_blocked_not_fresh_analysis(self, engine):
        d = engine.evaluate(_base_signal(is_fresh_analysis=False), _ctx())
        assert d.classification == BLOCKED
        assert "NOT_FRESH_ANALYSIS" in d.reason_codes

    def test_blocked_stale_session(self, engine):
        d = engine.evaluate(_base_signal(market_as_of_date="2026-10-01", as_of="2026-10-01"), _ctx())
        assert d.classification == BLOCKED
        assert "STALE_MARKET_AS_OF" in d.reason_codes

    def test_blocked_shariah_not_verified(self, engine):
        d = engine.evaluate(_base_signal(shariah_status="NOT VERIFIED"), _ctx())
        assert d.classification == BLOCKED
        assert "SHARIAH_NOT_VERIFIED" in d.reason_codes

    def test_blocked_shariah_non_compliant(self, engine):
        d = engine.evaluate(_base_signal(shariah_status="NON-COMPLIANT"), _ctx())
        assert d.classification == BLOCKED

    def test_blocked_emergency_stop(self, engine):
        d = engine.evaluate(_base_signal(), _ctx(emergency_stop=True))
        assert d.classification == BLOCKED
        assert "EMERGENCY_STOP_ACTIVE" in d.reason_codes

    def test_blocked_missing_account(self, engine):
        d = engine.evaluate(_base_signal(), _ctx(account=None))
        assert d.classification == BLOCKED
        assert "ACCOUNT_DATA_UNAVAILABLE" in d.reason_codes

    def test_blocked_stale_account(self, engine):
        d = engine.evaluate(_base_signal(), _ctx(account=_account(snapshot_fresh=False)))
        assert d.classification == BLOCKED
        assert "ACCOUNT_SNAPSHOT_STALE" in d.reason_codes

    def test_blocked_existing_position(self, engine):
        acct = _account(positions=[{"symbol": "AAPL", "qty": 10}])
        d = engine.evaluate(_base_signal(), _ctx(account=acct))
        assert d.classification == BLOCKED
        assert "EXISTING_LONG_POSITION" in d.reason_codes

    def test_blocked_yahoo_quote(self, engine):
        d = engine.evaluate(_base_signal(), _ctx(quote=_quote(source="YAHOO_FINANCE")))
        assert d.classification == BLOCKED
        assert "DISALLOWED_QUOTE_PROVIDER" in d.reason_codes

    def test_wait_market_closed_weekend(self, engine):
        sat = datetime(2026, 10, 24, 15, 0, 0, tzinfo=timezone.utc)
        # Fresh as-of relative to Saturday → Friday 23rd
        d = engine.evaluate(
            _base_signal(market_as_of_date="2026-10-23", as_of="2026-10-23"),
            _ctx(now_utc=sat, quote=_quote(quote_timestamp=sat.strftime("%Y-%m-%dT%H:%M:%SZ"))),
        )
        assert d.classification == WAIT
        assert "MARKET_CLOSED" in d.reason_codes

    def test_wait_open_order_capacity(self, engine):
        acct = _account(open_orders=[{"symbol": "MSFT", "qty": 1}])
        d = engine.evaluate(_base_signal(), _ctx(account=acct, max_open_orders=1))
        assert d.classification == WAIT
        assert "MAX_OPEN_ORDERS_REACHED" in d.reason_codes

    def test_wait_missing_quote(self, engine):
        d = engine.evaluate(_base_signal(), _ctx(quote=None, broker_quote=None))
        # DecisionContext uses broker_quote=; our helper sets both
        ctx = _ctx()
        ctx.broker_quote = None
        d = engine.evaluate(_base_signal(), ctx)
        assert d.classification == WAIT
        assert "BROKER_QUOTE_UNAVAILABLE" in d.reason_codes

    def test_insufficient_cash(self, engine):
        acct = _account(cash=50.0, equity=50.0)
        d = engine.evaluate(_base_signal(), _ctx(account=acct, quote=_quote(bid=199.9, ask=200.0)))
        assert d.classification == BLOCKED
        assert "INSUFFICIENT_CASH_FOR_ONE_SHARE" in d.reason_codes

    def test_all_entry_rule_families_can_be_buy_ready(self, engine):
        for rule in sorted(VALID_V40_ENTRY_RULES):
            d = engine.evaluate(_base_signal(entry_rule=rule), _ctx())
            assert d.classification == BUY_READY, f"entry_rule={rule} → {d.classification} {d.reason_codes}"
            assert d.entry_rule == rule


class TestProposalEngine:
    def test_stage_guards_disabled(self):
        assert STAGE_APPROVAL_ENABLED is False
        assert STAGE_SUBMISSION_ENABLED is False

    def test_wait_does_not_create_proposal(self, proposal_engine):
        ctx = _ctx()
        ctx.broker_quote = None
        out = proposal_engine.process_signal(_base_signal(), ctx, persist=False)
        assert out["decision"]["classification"] == WAIT
        assert out["proposal"] is None
        assert out["submission_attempted"] is False

    def test_buy_ready_builds_limit_proposal(self, proposal_engine):
        out = proposal_engine.process_signal(_base_signal(), _ctx(), persist=False)
        assert out["decision"]["classification"] == BUY_READY
        prop = out["proposal"]
        assert prop is not None
        assert prop["action"] == "BUY"
        assert prop["order_type"] == "LIMIT"
        assert prop["broker"] == "alpaca"
        assert prop["quantity"] >= 1
        assert prop["limit_price"] == 200.0
        assert prop["client_idempotency_key"].startswith("v40buy_")
        assert out["submission_attempted"] is False
        assert proposal_engine.submissions_attempted == 0

    def test_idempotency_stable_across_retries(self):
        k1 = build_idempotency_key(
            ticker="AAPL",
            market_as_of=AS_OF_FRESH,
            entry_rule="CROSS",
            strategy_version=V40_STRATEGY_VERSION,
            account_id="PA123",
            broker="alpaca",
            signal_id="sig_abc",
        )
        k2 = build_idempotency_key(
            ticker="AAPL",
            market_as_of=AS_OF_FRESH,
            entry_rule="CROSS",
            strategy_version=V40_STRATEGY_VERSION,
            account_id="PA123",
            broker="alpaca",
            signal_id="sig_abc",
        )
        assert k1 == k2

    def test_broker_independence_ibkr_payload(self, proposal_engine):
        acct = _account(broker="ibkr", account_id="DU1234567")
        out = proposal_engine.process_signal(_base_signal(), _ctx(account=acct), persist=False)
        assert out["proposal"]["broker"] == "ibkr"
        assert out["proposal"]["account_id"] == "DU1234567"

    def test_persist_idempotent_via_execution_service(self, proposal_engine, monkeypatch):
        calls = []

        def fake_propose(db, proposal, actor="ADMIN"):
            calls.append(proposal.client_idempotency_key)
            return {
                "order_id": "ORD-TEST-1",
                "client_idempotency_key": proposal.client_idempotency_key,
                "status": "AWAITING_APPROVAL",
            }

        monkeypatch.setattr(proposal_engine.execution, "propose_order", fake_propose)
        ctx = _ctx()
        db = MagicMock()
        out1 = proposal_engine.process_signal(_base_signal(), ctx, db=db, persist=True)
        out2 = proposal_engine.process_signal(_base_signal(), ctx, db=db, persist=True)
        assert out1["persisted_order"]["status"] == "AWAITING_APPROVAL"
        assert out1["approval_attempted"] is False
        assert out1["submission_attempted"] is False
        assert calls[0] == calls[1]
        assert proposal_engine.submissions_attempted == 0

    def test_fail_closed_no_fallback_order_on_build_error(self, proposal_engine, monkeypatch):
        # Force BUY_READY then break quantity
        eng = proposal_engine.decision_engine

        class FakeDecision:
            classification = BUY_READY
            reason_codes = ["V40_BUY_CONFIRMED"]
            ticker = "AAPL"
            signal_id = "sig_x"
            decided_at = "t"
            strategy_version = V40_STRATEGY_VERSION
            entry_rule = "CROSS"
            signal = "BUY CANDIDATE"
            market_as_of_date = AS_OF_FRESH
            expected_session_date = AS_OF_FRESH
            broker = "alpaca"
            account_id = "PA1234567890ABCDEF"
            details = {"proposed_quantity": 0, "proposed_limit_price": 0}

            def to_dict(self):
                return {"classification": self.classification, "reason_codes": self.reason_codes}

        monkeypatch.setattr(eng, "evaluate", lambda s, c: FakeDecision())
        out = proposal_engine.process_signal(_base_signal(), _ctx(), persist=False)
        assert out["proposal"] is None
        assert "PROPOSAL_BUILD_FAILED" in out["decision"]["reason_codes"]
        assert out["submission_attempted"] is False


class TestSizingLimits:
    def test_respects_max_order_notional(self, engine):
        # $500 max → at $200/share → qty 2
        d = engine.evaluate(
            _base_signal(),
            _ctx(max_order_notional_usd=500.0, quote=_quote(bid=199.9, ask=200.0)),
        )
        assert d.classification == BUY_READY
        assert d.details["proposed_notional"] <= 500.0 + 1e-9
        assert d.details["proposed_quantity"] == 2

    def test_portfolio_exposure_wait(self, engine):
        # equity 10k, cash 100 → already ~99% invested
        acct = _account(cash=100.0, equity=10000.0)
        d = engine.evaluate(
            _base_signal(),
            _ctx(account=acct, max_portfolio_exposure_pct=50.0, quote=_quote(bid=9.9, ask=10.0)),
        )
        assert d.classification == WAIT
        assert "PORTFOLIO_EXPOSURE_LIMIT" in d.reason_codes
