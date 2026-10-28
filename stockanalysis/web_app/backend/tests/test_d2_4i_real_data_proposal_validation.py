"""Stage D2.4I — real-data proposal validation gates (deterministic)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.buy_decision_engine import AccountSnapshot, DecisionContext, buy_decision_engine
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun
from app.services.d2_4i_review_resolution import apply_local_review_resolutions
from app.services.decision_journal import DecisionJournal
from app.services.order_execution_service import (
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.order_proposal_engine import STAGE_SUBMISSION_ENABLED, build_idempotency_key
from app.services.user_policy_eligibility import MODE_USER_POLICY, classify_user_policy
from app.services.us_session_freshness import evaluate_signal_session_freshness
from app.config import IBKR_EMERGENCY_STOP, TRADING_EXECUTION_ENABLED, V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION

NOW = datetime(2026, 10, 26, 22, 0, 0, tzinfo=timezone.utc)  # post-close Monday


def _signal(**overrides):
    sig = {
        "ticker": "PYPL",
        "name": "PayPal Holdings, Inc.",
        "sector": "Financial Services",
        "industry": "Credit Services",
        "signal": "BUY CANDIDATE",
        "signal_source": V40_SIGNAL_SOURCE,
        "strategy_version": V40_STRATEGY_VERSION,
        "entry_rule": "CROSS",
        "is_fresh_analysis": True,
        "provenance_mode": "LIVE_SCAN",
        "market_as_of_date": "2026-10-26",
        "as_of": "2026-10-26",
        "validation_status": "OK",
        "data_freshness": "FRESH",
        "ma250": 50.0,
        "shariah_status": "NOT VERIFIED",
    }
    sig.update(overrides)
    return sig


def _quote(ask=57.48, bid=57.40, **extra):
    """Tight two-sided quote so collar/spread gates can pass in unit tests."""
    q = {
        "source": "ALPACA_IEX",
        "symbol": "PYPL",
        "bid": bid,
        "ask": ask,
        "quote_timestamp": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "received_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_delayed": False,
        "is_synthetic": False,
        "is_two_sided": ask > 0 and bid > 0,
    }
    q.update(extra)
    return q


def _account(**kwargs) -> AccountSnapshot:
    return AccountSnapshot(
        broker="alpaca",
        account_id="PATEST1234",
        cash=kwargs.get("cash", 100000.0),
        equity=kwargs.get("equity", 100000.0),
        positions=kwargs.get("positions", []),
        open_orders=kwargs.get("open_orders", []),
        daily_orders_count=kwargs.get("daily_orders_count", 0),
        daily_notional_sum=kwargs.get("daily_notional_sum", 0.0),
        snapshot_fresh=True,
        connection_ok=True,
        as_of_utc=NOW.isoformat(),
    )


class TestFreshnessAndSafety:
    def test_fresh_signal_matches_completed_session(self):
        ok, code, *_ = evaluate_signal_session_freshness("2026-10-26", now_utc=NOW)
        assert ok is True
        assert code == "SESSION_FRESH"

    def test_stale_signal_detected(self):
        ok, code, *_ = evaluate_signal_session_freshness("2026-10-20", now_utc=NOW)
        assert ok is False
        assert code == "STALE_MARKET_AS_OF"

    def test_risk_limit_defaults(self):
        assert DEFAULT_MAX_ORDER_NOTIONAL_USD == 500.0
        assert DEFAULT_MAX_DAILY_ORDERS == 5
        assert DEFAULT_MAX_DAILY_NOTIONAL_USD == 2500.0
        assert DEFAULT_MAX_OPEN_ORDERS == 1

    def test_no_submissions_and_stops_preserved(self):
        assert STAGE_SUBMISSION_ENABLED is False
        assert IBKR_EMERGENCY_STOP is True
        assert TRADING_EXECUTION_ENABLED is False


class TestReviewResolutions:
    def test_crm_pltr_spy_xlp_soxx_resolution(self):
        apply_local_review_resolutions()
        assert classify_user_policy("CRM", name="Salesforce, Inc.", sector="Technology", industry="Equity")[
            "user_policy_status"
        ] == "ALLOWED"
        pltr = classify_user_policy("PLTR", name="Palantir Technologies Inc.", industry="Equity")
        assert pltr["user_policy_status"] == "EXCLUDED"
        assert "MILITARY_DEFENCE_EXPOSURE" in pltr["reason_codes"]
        assert pltr["proposal_permitted"] is False
        assert pltr["research_visible"] is True
        assert classify_user_policy("SPY", sector="ETFs", industry="Large Blend ETF")["user_policy_status"] == "EXCLUDED"
        assert classify_user_policy("XLP", sector="ETFs", industry="Sector Staples ETF")["user_policy_status"] == "EXCLUDED"
        assert classify_user_policy("SOXX", sector="ETFs", industry="Semiconductor ETF")["user_policy_status"] == "ALLOWED"


class TestProposalSizingSeparation:
    def test_investment_buy_ready_with_emergency_stop_and_simulated_sizing(self, tmp_path):
        pipeline = BuyPipelineDryRun(journal=DecisionJournal(journal_dir=tmp_path / "j"))
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(),
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
        )
        entry = pipeline.evaluate_signal(_signal(), ctx, run_id="d24i", persist_journal=False)
        assert entry["investment_decision"]["classification"] == "BUY_READY"
        assert entry["execution_readiness"]["execution_readiness"] == "EMERGENCY_STOP"
        assert entry["submission_attempted"] is False
        prop = entry.get("simulated_proposal")
        assert prop is not None
        assert prop["status"] == "SIMULATED"
        assert prop["proposed_notional"] <= 500.0 + 1e-9
        assert prop["proposed_quantity"] >= 1

    def test_invalid_quote_blocks_sizing(self, tmp_path):
        pipeline = BuyPipelineDryRun(journal=DecisionJournal(journal_dir=tmp_path / "j"))
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(ask=0.0, bid=50.0),
            emergency_stop=True,
            execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
        )
        entry = pipeline.evaluate_signal(_signal(), ctx, run_id="d24i", persist_journal=False)
        assert entry["submission_attempted"] is False
        assert entry.get("simulated_proposal") is None

    def test_ask_above_max_order_blocks_share(self):
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(ask=550.0, bid=549.0),
            emergency_stop=False,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
            allow_off_session_sizing=True,
        )
        d = buy_decision_engine.evaluate(_signal(ticker="AMD", name="AMD", sector="Technology", industry="Semiconductors"), ctx)
        assert d.classification == "BLOCKED"
        assert "INSUFFICIENT_CASH_FOR_ONE_SHARE" in d.reason_codes

    def test_extreme_spread_still_blocks_off_session_sizing(self, tmp_path):
        """Spreads beyond dry-run tolerance (25%) still fail — data gate preserved."""
        pipeline = BuyPipelineDryRun(journal=DecisionJournal(journal_dir=tmp_path / "j"))
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(ask=80.0, bid=50.0),  # ~46% spread
            emergency_stop=True,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
        )
        entry = pipeline.evaluate_signal(_signal(), ctx, run_id="d24i", persist_journal=False)
        assert entry.get("simulated_proposal") is None
        assert entry.get("sizing_block") is not None
        assert "QUOTE_VALIDATION_FAILED" in (entry.get("sizing_block") or {}).get("reason_codes", [])

    def test_open_order_limit_wait(self):
        ctx = DecisionContext(
            account=_account(open_orders=[{"symbol": "MSFT", "quantity": 1}]),
            broker_quote=_quote(),
            emergency_stop=False,
            execution_enabled=False,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
            allow_off_session_sizing=True,
        )
        d = buy_decision_engine.evaluate(_signal(), ctx)
        assert d.classification == "WAIT"
        assert "MAX_OPEN_ORDERS_REACHED" in d.reason_codes

    def test_idempotency_stable(self):
        k1 = build_idempotency_key(
            ticker="PYPL",
            market_as_of="2026-10-26",
            entry_rule="CROSS",
            strategy_version=V40_STRATEGY_VERSION,
            account_id="PA1",
            broker="alpaca",
            signal_id="sig1",
        )
        k2 = build_idempotency_key(
            ticker="PYPL",
            market_as_of="2026-10-26",
            entry_rule="CROSS",
            strategy_version=V40_STRATEGY_VERSION,
            account_id="PA1",
            broker="alpaca",
            signal_id="sig1",
        )
        assert k1 == k2

    def test_mo_excluded_no_proposal(self, tmp_path):
        pipeline = BuyPipelineDryRun(journal=DecisionJournal(journal_dir=tmp_path / "j"))
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(ask=70.0, bid=69.0),
            emergency_stop=True,
            now_utc=NOW,
            eligibility_mode=MODE_USER_POLICY,
        )
        entry = pipeline.evaluate_signal(
            _signal(
                ticker="MO",
                name="Altria",
                sector="Consumer Defensive",
                industry="Tobacco",
            ),
            ctx,
            run_id="d24i",
            persist_journal=False,
        )
        assert entry["investment_decision"]["classification"] == "BUY_READY"
        assert entry.get("simulated_proposal") is None
        assert entry.get("blocked_by_user_policy") is True
