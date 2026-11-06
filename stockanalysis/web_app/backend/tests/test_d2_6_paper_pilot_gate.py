"""Stage D2.6 / D2.6A — paper pilot gate + quote/session/signal safety tests.

Deterministic mocked market data and controlled clocks. No live broker access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.paper_pilot_gate import (
    PILOT_AUTO_RETRY,
    PILOT_AUTO_SUBMIT,
    PILOT_BATCH_EXECUTION,
    PILOT_MAX_ORDERS,
    PilotGateState,
    assess_soak_prerequisite,
    build_order_preview,
    run_d2_6_readiness,
    size_whole_share_limit,
    verify_pilot_gate_invariants,
)
from app.services.paper_pilot_safety import (
    evaluate_candidate_execution_safety,
    parse_aware_quote_timestamp,
    validate_quote_for_pilot,
    validate_signal_for_pilot,
    validate_us_regular_session,
)

NY = ZoneInfo("America/New_York")


def _utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _ny_as_utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=NY).astimezone(timezone.utc)


def _candidate(**overrides):
    base = {
        "ticker": "AAPL",
        "scan_rank": 1,
        "policy": "ALLOWED",
        "entry_rule": "CLOSE_GT_MA50",
        "exit_rule": "MA250_3CLOSE",
        "signal_close": 180.0,
        "atr14": 2.5,
        "ma50": 175.0,
        "ma250": 160.0,
        "roc20_pct": 5.0,
        "market_as_of_date": "2026-11-04",
        "data_freshness": "FRESH",
        "strategy_version": "V4.0",
        "signal_source": "observation_scanner",
    }
    base.update(overrides)
    return base


def _fresh_quote(*, now_utc, bid=149.50, ask=150.00, age_seconds=5.0):
    ts = (now_utc.astimezone(timezone.utc)).timestamp() - age_seconds
    q_ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return {
        "bid": bid,
        "ask": ask,
        "quote_timestamp": q_ts,
        "source": "alpaca_iex",
        "received_at": now_utc.isoformat(),
        "meets_30s_freshness": age_seconds <= 30,
        "is_two_sided": True,
    }


# ---------------------------------------------------------------------------
# Existing D2.6 invariants
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# D2.6A — Quote timestamp & freshness
# ---------------------------------------------------------------------------


def test_quote_missing_timestamp():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    out = validate_quote_for_pilot({"bid": 100.0, "ask": 100.5}, now_utc=now)
    assert out["ok"] is False
    assert "QUOTE_TIMESTAMP_MISSING" in out["reason_codes"]


def test_quote_malformed_and_naive_timestamp():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    malformed = validate_quote_for_pilot(
        {"bid": 100.0, "ask": 100.5, "quote_timestamp": "not-a-time"},
        now_utc=now,
    )
    assert "QUOTE_TIMESTAMP_INVALID" in malformed["reason_codes"]

    naive = validate_quote_for_pilot(
        {"bid": 100.0, "ask": 100.5, "quote_timestamp": "2026-11-05T15:30:00"},
        now_utc=now,
    )
    assert "QUOTE_TIMESTAMP_INVALID" in naive["reason_codes"]

    dt_naive, err = parse_aware_quote_timestamp(datetime(2026, 11, 5, 15, 30, 0))
    assert dt_naive is None
    assert err == "QUOTE_TIMESTAMP_INVALID"


def test_quote_stale_over_30_seconds():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    q = _fresh_quote(now_utc=now, age_seconds=45.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert out["ok"] is False
    assert "QUOTE_STALE" in out["reason_codes"]
    assert out["quote_age_seconds"] > 30


def test_quote_future_timestamp():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    future = (now.timestamp() + 30)
    q = {
        "bid": 100.0,
        "ask": 100.5,
        "quote_timestamp": datetime.fromtimestamp(future, tz=timezone.utc).isoformat(),
    }
    out = validate_quote_for_pilot(q, now_utc=now)
    assert out["ok"] is False
    assert "QUOTE_FUTURE_TIMESTAMP" in out["reason_codes"]


def test_quote_valid_fresh():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    q = _fresh_quote(now_utc=now, bid=149.50, ask=150.00, age_seconds=5.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert out["ok"] is True
    assert out["reason_codes"] == []
    assert out["spread_pct"] is not None
    assert out["spread_pct"] < 1.0


def test_received_at_never_substitutes_for_missing_broker_timestamp():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    out = validate_quote_for_pilot(
        {"bid": 100.0, "ask": 100.4, "received_at": now.isoformat()},
        now_utc=now,
    )
    assert "QUOTE_TIMESTAMP_MISSING" in out["reason_codes"]
    assert out["received_at_ignored_for_freshness"] == now.isoformat()


# ---------------------------------------------------------------------------
# D2.6A — Bid/ask & spread
# ---------------------------------------------------------------------------


def test_zero_or_negative_bid_ask():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    q = _fresh_quote(now_utc=now, bid=0.0, ask=100.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert "INVALID_BID_ASK" in out["reason_codes"]

    q2 = _fresh_quote(now_utc=now, bid=-1.0, ask=100.0)
    out2 = validate_quote_for_pilot(q2, now_utc=now)
    assert "INVALID_BID_ASK" in out2["reason_codes"]


def test_crossed_bid_ask():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    q = _fresh_quote(now_utc=now, bid=101.0, ask=100.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert "INVALID_BID_ASK" in out["reason_codes"]


def test_spread_above_one_percent():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    # QCOM-like wide spread ~9.9%
    q = _fresh_quote(now_utc=now, bid=149.19, ask=164.75, age_seconds=5.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert out["ok"] is False
    assert "QUOTE_SPREAD_TOO_WIDE" in out["reason_codes"]
    assert out["spread_pct"] > 1.0


def test_spread_within_one_percent():
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    q = _fresh_quote(now_utc=now, bid=149.50, ask=150.00, age_seconds=5.0)
    out = validate_quote_for_pilot(q, now_utc=now)
    assert out["ok"] is True
    assert out["spread_pct"] <= 1.0


def test_qcom_scenario_missing_ts_and_wide_spread():
    """Original D2.6 unsafe QCOM quote must never be preview-ready."""
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    quote = {"bid": 149.19, "ask": 164.75, "quote_timestamp": None, "source": "alpaca_iex"}
    cand = _candidate(ticker="QCOM", market_as_of_date="2026-11-04")
    safety = evaluate_candidate_execution_safety(quote=quote, candidate=cand, now_utc=now)
    assert safety["ok"] is False
    codes = safety["reason_codes"]
    assert "QUOTE_TIMESTAMP_MISSING" in codes
    assert "QUOTE_SPREAD_TOO_WIDE" in codes

    selection = {
        "selected": True,
        "reason_code": "RESEARCH_ONLY_SAFETY_BLOCKED",
        "trading_day": "2026-11-04",
        "candidate": cand,
        "sizing": {"qty": 3, "limit_price": 164.75, "notional": 494.25, "ok": True},
        "live_quote": quote,
        "execution_safety": safety,
    }
    preview = build_order_preview(selection, now_utc=now)
    assert preview["preview_ready"] is False
    assert "QUOTE_TIMESTAMP_MISSING" in preview["reason_codes"]
    assert "QUOTE_SPREAD_TOO_WIDE" in preview["reason_codes"]

    soak = {
        "soak_complete": True,
        "target_completed_pairs": 3,
        "completed_pair_ids": ["a", "b", "c"],
        "sessions": [],
    }
    result = run_d2_6_readiness(
        write_evidence=False,
        now_utc=now,
        selection=selection,
        soak_ledger=soak,
    )
    assert result["recommendation"] == "NO-GO"
    assert result["order_preview"]["preview_ready"] is False
    assert result["execution_attempted"] is False
    assert result["submissions_attempted"] == 0
    assert "QUOTE_TIMESTAMP_MISSING" in result["safety_reason_codes"]
    assert "QUOTE_SPREAD_TOO_WIDE" in result["safety_reason_codes"]


# ---------------------------------------------------------------------------
# D2.6A — US market session
# ---------------------------------------------------------------------------


def test_market_closed_outside_hours():
    # Wednesday 2026-11-04 20:00 ET → CLOSED overnight
    now = _ny_as_utc(2026, 11, 4, 20, 0)
    out = validate_us_regular_session(now_utc=now)
    assert out["ok"] is False
    assert "MARKET_CLOSED" in out["reason_codes"]


def test_market_weekend_and_holiday():
    saturday = _ny_as_utc(2026, 11, 7, 11, 0)
    sat = validate_us_regular_session(now_utc=saturday)
    assert "MARKET_CLOSED" in sat["reason_codes"]
    assert sat["holiday"] is True

    thanksgiving = _ny_as_utc(2026, 11, 26, 11, 0)
    hol = validate_us_regular_session(now_utc=thanksgiving)
    assert "MARKET_CLOSED" in hol["reason_codes"]
    assert hol["holiday_name"] == "Thanksgiving Day"


def test_us_early_close_blocks_after_1300_et():
    # Black Friday 2026-11-27 early close 13:00 ET
    during = _ny_as_utc(2026, 11, 27, 11, 0)
    after = _ny_as_utc(2026, 11, 27, 13, 30)
    ok = validate_us_regular_session(now_utc=during)
    closed = validate_us_regular_session(now_utc=after)
    assert ok["ok"] is True
    assert ok["early_close"] is True
    assert closed["ok"] is False
    assert "MARKET_CLOSED" in closed["reason_codes"]
    assert closed["session"] == "POST_MARKET"


def test_daylight_saving_transition_regular_hours():
    # Spring forward Sunday 2026-03-08; first weekday session uses EDT
    spring = _ny_as_utc(2026, 3, 9, 10, 30)
    spring_out = validate_us_regular_session(now_utc=spring)
    assert spring_out["ok"] is True
    assert spring_out["session"] == "REGULAR"
    assert spring.astimezone(NY).dst().total_seconds() != 0
    # 10:30 ET → 14:30 UTC under EDT (not fixed UTC offset)
    assert spring.hour == 14 and spring.minute == 30

    # Fall back Sunday 2026-11-01; weekday session uses EST
    fall = _ny_as_utc(2026, 11, 4, 10, 30)
    fall_out = validate_us_regular_session(now_utc=fall)
    assert fall_out["ok"] is True
    assert fall_out["session"] == "REGULAR"
    assert fall.astimezone(NY).dst().total_seconds() == 0
    # 10:30 ET → 15:30 UTC under EST
    assert fall.hour == 15 and fall.minute == 30


def test_market_session_unverified_on_calendar_error(monkeypatch):
    def boom(_dt=None):
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(
        "app.services.paper_pilot_safety.MarketDataService.get_market_session",
        staticmethod(boom),
    )
    out = validate_us_regular_session(now_utc=_ny_as_utc(2026, 11, 5, 10, 30))
    assert out["ok"] is False
    assert "MARKET_SESSION_UNVERIFIED" in out["reason_codes"]


# ---------------------------------------------------------------------------
# D2.6A — Signal validity
# ---------------------------------------------------------------------------


def test_stale_or_invalid_signal():
    # During REGULAR on 2026-11-05, last completed session is 2026-11-04
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    stale = validate_signal_for_pilot(
        _candidate(market_as_of_date="2026-11-03"),
        now_utc=now,
    )
    assert stale["ok"] is False
    assert "SIGNAL_STALE" in stale["reason_codes"]

    missing = validate_signal_for_pilot(
        _candidate(market_as_of_date=None),
        now_utc=now,
    )
    assert "SIGNAL_VALIDITY_UNVERIFIED" in missing["reason_codes"]

    not_fresh_flag = validate_signal_for_pilot(
        _candidate(market_as_of_date="2026-11-04", data_freshness="STALE"),
        now_utc=now,
    )
    assert "SIGNAL_STALE" in not_fresh_flag["reason_codes"]


def test_valid_strategy_authorized_prior_session_signal():
    """Post-close signal dated last completed session may carry into next REGULAR."""
    now = _ny_as_utc(2026, 11, 5, 10, 30)
    out = validate_signal_for_pilot(
        _candidate(market_as_of_date="2026-11-04", data_freshness="FRESH"),
        now_utc=now,
    )
    assert out["ok"] is True
    assert out["carry_forward_authorized"] is True
    assert out["signal_date"] == "2026-11-04"
    assert out["expected_completed_session"] == "2026-11-04"
    assert out["current_market_session"] == "REGULAR"


# ---------------------------------------------------------------------------
# D2.6A — End-to-end readiness recommendation
# ---------------------------------------------------------------------------


def _passing_selection(now_utc):
    quote = _fresh_quote(now_utc=now_utc, bid=149.50, ask=150.00, age_seconds=3.0)
    cand = _candidate(ticker="AAPL", market_as_of_date="2026-11-04")
    safety = evaluate_candidate_execution_safety(
        quote=quote, candidate=cand, now_utc=now_utc
    )
    sizing = size_whole_share_limit(ask=150.00, max_order_notional_usd=500.0, cash=100_000.0)
    return {
        "selected": True,
        "reason_code": "OK",
        "ranking_method": "D2E_BUY_READY_SEQUENCE_THEN_TICKER",
        "trading_day": "2026-11-04",
        "candidate": cand,
        "live_quote": quote,
        "sizing": sizing,
        "execution_safety": safety,
    }


def test_all_checks_passing_conditional_go(monkeypatch):
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

    now = _ny_as_utc(2026, 11, 5, 10, 30)
    selection = _passing_selection(now)
    assert selection["execution_safety"]["ok"] is True

    preview = build_order_preview(selection, now_utc=now)
    assert preview["preview_ready"] is True

    soak = {
        "soak_complete": True,
        "target_completed_pairs": 3,
        "completed_pair_ids": ["p1", "p2", "p3"],
        "sessions": [],
    }
    result = run_d2_6_readiness(
        write_evidence=False,
        now_utc=now,
        selection=selection,
        soak_ledger=soak,
    )
    assert result["recommendation"] == "CONDITIONAL GO"
    assert result["order_preview"]["preview_ready"] is True
    assert result["execution_attempted"] is False
    assert result["submissions_attempted"] == 0
    assert result["safety_reason_codes"] == []


def test_any_hard_check_failing_produces_no_go(monkeypatch):
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

    now = _ny_as_utc(2026, 11, 5, 20, 0)  # after hours
    selection = _passing_selection(_ny_as_utc(2026, 11, 5, 10, 30))
    # Re-evaluate safety at closed-market clock
    selection["execution_safety"] = evaluate_candidate_execution_safety(
        quote=selection["live_quote"],
        candidate=selection["candidate"],
        now_utc=now,
    )
    soak = {
        "soak_complete": True,
        "target_completed_pairs": 3,
        "completed_pair_ids": ["p1", "p2", "p3"],
        "sessions": [],
    }
    result = run_d2_6_readiness(
        write_evidence=False,
        now_utc=now,
        selection=selection,
        soak_ledger=soak,
    )
    assert result["recommendation"] == "NO-GO"
    assert result["order_preview"]["preview_ready"] is False
    assert "MARKET_CLOSED" in result["safety_reason_codes"]


def test_no_candidate_produces_no_go(monkeypatch):
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

    soak = {
        "soak_complete": True,
        "target_completed_pairs": 3,
        "completed_pair_ids": ["p1", "p2", "p3"],
        "sessions": [],
    }
    result = run_d2_6_readiness(
        write_evidence=False,
        now_utc=_ny_as_utc(2026, 11, 5, 10, 30),
        selection={"selected": False, "reason_code": "NO_ALLOWED_BUY_CANDIDATES"},
        soak_ledger=soak,
    )
    assert result["recommendation"] == "NO-GO"
    assert result["order_preview"]["preview_ready"] is False
    assert result["execution_attempted"] is False


def test_execution_guards_unchanged():
    import sys
    from pathlib import Path

    dm_root = Path(__file__).resolve().parents[4]  # .../Digital Marketing
    if str(dm_root) not in sys.path:
        sys.path.insert(0, str(dm_root))

    from alpaca_adapter.alpaca_paper_adapter import NON_EXECUTING_BUILD_GUARD
    from app.config import (
        ALPACA_EXECUTION_ENABLED,
        IBKR_EMERGENCY_STOP,
        LIVE_TRADING_ENABLED,
        TRADING_EXECUTION_ENABLED,
    )
    from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED

    assert NON_EXECUTING_BUILD_GUARD is True
    assert ALPACA_EXECUTION_ENABLED is False
    assert TRADING_EXECUTION_ENABLED is False
    assert LIVE_TRADING_ENABLED is False
    assert STAGE_APPROVAL_ENABLED is False
    assert STAGE_SUBMISSION_ENABLED is False
    assert IBKR_EMERGENCY_STOP is True
