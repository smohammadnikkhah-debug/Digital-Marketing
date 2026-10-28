"""Stage D2.4D — Autonomous BUY pipeline dry run (local, non-submitting)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION, RISK_UI_SIGNAL_SOURCE
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun
from app.services.decision_journal import DecisionJournal
from app.services.execution_readiness import (
    DISABLED,
    EMERGENCY_STOP,
    READY,
    RISK_BLOCKED,
    classify_execution_readiness,
)
from app.services.shariah_monitor import build_shariah_universe_report

NOW_REGULAR = datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc)
AS_OF_FRESH = "2026-10-19"


def _signal(**overrides):
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


def _quote(**extra):
    q = {
        "source": "ALPACA_IEX",
        "symbol": "AAPL",
        "bid": 199.9,
        "ask": 200.0,
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


def _ctx(**kwargs) -> DecisionContext:
    defaults = dict(
        account=_account(),
        broker_quote=_quote(),
        emergency_stop=True,  # production-like; investment still visible
        execution_enabled=False,
        trading_execution_enabled=False,
        now_utc=NOW_REGULAR,
        investment_mode=False,
    )
    defaults.update(kwargs)
    return DecisionContext(**defaults)


@pytest.fixture
def journal(tmp_path: Path):
    return DecisionJournal(journal_dir=tmp_path / "journal")


@pytest.fixture
def pipeline(journal):
    return BuyPipelineDryRun(journal=journal)


class TestInvestmentVsExecutionSeparation:
    def test_buy_ready_visible_under_emergency_stop(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(),
            _ctx(emergency_stop=True),
            run_id="sep1",
            persist_journal=True,
        )
        assert out["investment_decision"]["classification"] == "BUY_READY"
        assert out["execution_readiness"]["execution_readiness"] == EMERGENCY_STOP
        assert out["execution_readiness"]["submissions_permitted"] is False
        assert out["submission_attempted"] is False

    def test_watch_is_no_action_investment(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(signal="WATCH"),
            _ctx(),
            run_id="sep2",
            persist_journal=False,
        )
        assert out["investment_decision"]["classification"] == "NO_ACTION"

    def test_frozen_baseline_blocked_investment(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(provenance_mode="FROZEN_BASELINE", data_freshness="FROZEN_BASELINE"),
            _ctx(),
            run_id="sep3",
            persist_journal=False,
        )
        assert out["investment_decision"]["classification"] == "BLOCKED"
        assert "FROZEN_BASELINE_SIGNAL" in out["investment_decision"]["reason_codes"]
        assert out["simulated_proposal"] is None

    def test_risk_ui_rejected(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(signal_source=RISK_UI_SIGNAL_SOURCE, not_a_v40_scanner_signal=True),
            _ctx(),
            run_id="sep4",
            persist_journal=False,
        )
        assert out["investment_decision"]["classification"] == "NO_ACTION"
        assert out["simulated_proposal"] is None


class TestSimulatedProposals:
    def test_verified_buy_gets_simulated_limit_proposal(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(),
            _ctx(emergency_stop=True),
            run_id="prop1",
            persist_journal=True,
        )
        prop = out["simulated_proposal"]
        assert prop is not None
        assert prop["order_type"] == "LIMIT"
        assert prop["action"] == "BUY"
        assert prop["proposed_quantity"] >= 1
        assert prop["proposed_limit_price"] == 200.0
        assert prop["proposed_notional"] <= 500.0 + 1e-9
        assert prop["available_cash"] == 10000.0
        assert "idempotency_key" in prop
        assert prop["submission_attempted"] is False

    def test_shariah_not_verified_blocks_proposal_keeps_buy_ready(self, pipeline):
        out = pipeline.evaluate_signal(
            _signal(shariah_status="NOT VERIFIED"),
            _ctx(),
            run_id="prop2",
            persist_journal=True,
        )
        assert out["investment_decision"]["classification"] == "BUY_READY"
        assert out["blocked_by_shariah"] is True
        assert out["simulated_proposal"] is None
        assert out["execution_readiness"]["execution_readiness"] in (EMERGENCY_STOP, RISK_BLOCKED, DISABLED)

    def test_duplicate_proposal_idempotent_in_journal(self, pipeline, journal):
        ctx = _ctx()
        pipeline.evaluate_signal(_signal(), ctx, run_id="dedupe", persist_journal=True)
        pipeline.evaluate_signal(_signal(), ctx, run_id="dedupe", persist_journal=True)
        rows = journal.read_run("dedupe")
        assert len(rows) == 2
        assert rows[0]["simulated_proposal"] is not None
        assert rows[1]["proposal_deduplicated"] is True
        assert rows[1]["simulated_proposal"] is None


class TestShariahMonitor:
    def test_groups_verified_not_verified_non_compliant(self):
        signals = [
            _signal(ticker="AAPL", shariah_status="VERIFIED"),
            _signal(ticker="MSFT", shariah_status="NOT VERIFIED", signal="WATCH"),
            _signal(ticker="TSLA", shariah_status="NON-COMPLIANT", signal="AVOID"),
        ]
        report = build_shariah_universe_report(
            signals,
            watchlist_meta={
                "AAPL": {"status": "VERIFIED", "source": "manual", "date": "2026-01-01"},
                "MSFT": {"status": "NOT VERIFIED", "source": "", "date": ""},
                "TSLA": {"status": "NON-COMPLIANT", "source": "screen", "date": "2025-06-01"},
            },
        )
        assert report["classifications_mutated"] is False
        assert report["counts"]["VERIFIED_EXECUTION_ELIGIBLE"] == 1
        assert report["counts"]["NOT_VERIFIED_EXECUTION_BLOCKED"] == 1
        assert report["counts"]["NON_COMPLIANT_EXECUTION_BLOCKED"] == 1
        aapl = next(r for r in report["rows"] if r["ticker"] == "AAPL")
        assert aapl["screening_source"] == "manual"
        assert aapl["verification_date"] == "2026-01-01"
        assert aapl["blocking_reason"] == ""


class TestExecutionReadiness:
    def test_emergency_stop_priority(self, monkeypatch):
        monkeypatch.setattr("app.services.execution_readiness.IBKR_EMERGENCY_STOP", True)
        monkeypatch.setattr("app.services.execution_readiness.TRADING_EXECUTION_ENABLED", False)
        r = classify_execution_readiness(
            signal=_signal(),
            ctx=_ctx(emergency_stop=True),
            investment_classification="BUY_READY",
        )
        assert r["execution_readiness"] == EMERGENCY_STOP
        assert r["submissions_permitted"] is False

    def test_disabled_when_trading_off(self, monkeypatch):
        monkeypatch.setattr("app.services.execution_readiness.IBKR_EMERGENCY_STOP", False)
        monkeypatch.setattr("app.services.execution_readiness.TRADING_EXECUTION_ENABLED", False)
        r = classify_execution_readiness(
            signal=_signal(),
            ctx=_ctx(emergency_stop=False),
            investment_classification="BUY_READY",
        )
        assert r["execution_readiness"] == DISABLED
        assert r["submissions_permitted"] is False

    def test_ready_still_forbids_submission(self, monkeypatch):
        monkeypatch.setattr("app.services.execution_readiness.IBKR_EMERGENCY_STOP", False)
        monkeypatch.setattr("app.services.execution_readiness.TRADING_EXECUTION_ENABLED", True)
        monkeypatch.setattr("app.services.execution_readiness.ALPACA_EXECUTION_ENABLED", True)
        r = classify_execution_readiness(
            signal=_signal(),
            ctx=_ctx(emergency_stop=False, trading_execution_enabled=True, execution_enabled=True),
            investment_classification="BUY_READY",
        )
        assert r["execution_readiness"] == READY
        assert r["submissions_permitted"] is False


class TestEndToEndDryRun:
    def test_snapshot_pipeline_end_to_end(self, pipeline, journal):
        snapshot = {
            "snapshot_id": "snap_d24d_test",
            "market_as_of_date": AS_OF_FRESH,
            "signals": [
                _signal(ticker="AAPL", shariah_status="VERIFIED"),
                _signal(ticker="MSFT", signal="WATCH", shariah_status="NOT VERIFIED"),
                _signal(
                    ticker="OLD",
                    provenance_mode="FROZEN_BASELINE",
                    data_freshness="FROZEN_BASELINE",
                    is_fresh_analysis=False,
                    shariah_status="NOT VERIFIED",
                ),
                _signal(ticker="TSLA", shariah_status="NON-COMPLIANT"),
            ],
        }
        result = pipeline.run(
            ctx=_ctx(),
            snapshot=snapshot,
            watchlist_meta={
                "AAPL": {"status": "VERIFIED", "source": "board", "date": "2026-02-01"},
                "MSFT": {"status": "NOT VERIFIED", "source": "", "date": ""},
                "OLD": {"status": "NOT VERIFIED", "source": "", "date": ""},
                "TSLA": {"status": "NON-COMPLIANT", "source": "screen", "date": "2025-01-01"},
            },
            run_id="e2e_d24d",
            persist_journal=True,
        )
        assert result["signals_evaluated"] == 4
        assert result["submission_attempted"] is False
        assert result["submissions_attempted"] == 0
        assert result["invariants"]["stage_submission_enabled"] is False
        assert result["investment_buy_ready_count"] >= 1
        assert result["simulated_proposal_count"] >= 1
        assert result["shariah_report"]["counts"]["VERIFIED_EXECUTION_ELIGIBLE"] == 1
        assert result["shariah_report"]["counts"]["NON_COMPLIANT_EXECUTION_BLOCKED"] == 1
        assert result["shariah_report"]["counts"]["NOT_VERIFIED_EXECUTION_BLOCKED"] == 2
        summary = journal.summary("e2e_d24d")
        assert summary["entries"] == 4
        assert Path(summary["path"]).exists()
        # Journal file is valid JSONL
        with open(summary["path"], encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        assert len(lines) == 4
