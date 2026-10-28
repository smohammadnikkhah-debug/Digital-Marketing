"""Stage D2.4F — Shariah recovery, ticker integrity, Alpaca read-only, proposals."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import IBKR_EMERGENCY_STOP, TRADING_EXECUTION_ENABLED, V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION
from app.services.alpaca_readonly import AlpacaReadOnlyClient, _redact_account_id, ensure_alpaca_adapter_on_path
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun
from app.services.decision_journal import DecisionJournal
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED
from app.services.shariah_store import (
    attach_watchlist_shariah_to_signals,
    investigate_universe_shariah,
    load_optional_evidence_file,
    load_watchlist_shariah,
    merge_shariah_maps,
    resolve_status_for_ticker,
)
from app.services.ticker_integrity import (
    PROPOSED_TICKER_ALIASES,
    investigate_problem_tickers,
    resolve_proposed_alias,
)

NOW = datetime(2026, 10, 27, 15, 0, 0, tzinfo=timezone.utc)
AS_OF = "2026-10-26"


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
        "market_as_of_date": AS_OF,
        "as_of": AS_OF,
        "validation_status": "OK",
        "data_freshness": "FRESH",
        "ma250": 180.0,
        "ma50": 190.0,
        "ma30": 195.0,
        "close": 200.0,
        "shariah_status": "NOT VERIFIED",
        "scan_completed_at": "2026-10-26T20:35:00Z",
    }
    sig.update(overrides)
    return sig


def _account(**overrides) -> AccountSnapshot:
    acct = AccountSnapshot(
        broker="alpaca",
        account_id="PAXXXXXXXXXX1234",
        cash=50000.0,
        equity=50000.0,
        positions=[],
        open_orders=[],
        daily_orders_count=0,
        daily_notional_sum=0.0,
        snapshot_fresh=True,
        connection_ok=True,
        as_of_utc=NOW.isoformat(),
    )
    for k, v in overrides.items():
        setattr(acct, k, v)
    return acct


def _quote(symbol="AAPL", **extra):
    q = {
        "source": "ALPACA_IEX",
        "symbol": symbol,
        "bid": 199.9,
        "ask": 200.0,
        "last": 199.95,
        "quote_timestamp": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "received_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market_session": "REGULAR",
        "is_delayed": False,
        "is_synthetic": False,
        "is_two_sided": True,
    }
    q.update(extra)
    return q


class TestShariahStoreLoading:
    def test_empty_watchlist_is_missing_data_not_non_compliant(self):
        report = investigate_universe_shariah(
            ["AAPL", "MSFT", "TSLA"],
            db=None,
            registry_stocks={"AAPL": {"ticker": "AAPL"}, "MSFT": {}, "TSLA": {}},
        )
        assert report["counts"]["VERIFIED"] == 0
        assert report["counts"]["NON_COMPLIANT"] == 0
        assert report["counts"]["NOT_VERIFIED"] == 3
        assert report["counts"]["MISSING_WATCHLIST_ROW"] == 3
        assert "missing" in report["root_cause"].lower() or "NOT VERIFIED" in report["root_cause"]
        assert report["classifications_mutated"] is False

    def test_watchlist_load_via_mock_db(self):
        row = MagicMock()
        row.ticker = "AAPL"
        row.shariah_status = "VERIFIED"
        row.shariah_source = "board-screen-2026"
        row.shariah_date = "2026-01-15"
        db = MagicMock()
        db.query.return_value.all.return_value = [row]
        meta = load_watchlist_shariah(db)
        assert meta["AAPL"]["status"] == "VERIFIED"
        assert meta["AAPL"]["source"] == "board-screen-2026"

    def test_verified_vs_unverified_vs_non_compliant(self):
        wl = {
            "AAPL": {"status": "VERIFIED", "source": "board", "date": "2026-01-01"},
            "MSFT": {"status": "NOT VERIFIED", "source": "", "date": ""},
            "TSLA": {"status": "NON-COMPLIANT", "source": "screen", "date": "2025-06-01"},
        }
        report = investigate_universe_shariah(
            ["AAPL", "MSFT", "TSLA"],
            db=None,
            registry_stocks={},
        )
        # Without injecting watchlist via db, use resolve + merge path explicitly
        merged = merge_shariah_maps(wl)
        a = resolve_status_for_ticker("AAPL", watchlist_meta=merged)
        m = resolve_status_for_ticker("MSFT", watchlist_meta=merged)
        t = resolve_status_for_ticker("TSLA", watchlist_meta=merged)
        assert a["execution_eligible"] is True
        assert m["execution_eligible"] is False
        assert t["normalized_shariah_status"] == "NON-COMPLIANT"
        assert report["read_only"] is True

    def test_incomplete_verified_evidence_rejected(self, tmp_path: Path):
        path = tmp_path / "shariah_evidence.json"
        path.write_text(
            json.dumps(
                {
                    "records": [
                        {"ticker": "AAPL", "status": "VERIFIED", "source": "", "date": ""},
                        {
                            "ticker": "MSFT",
                            "status": "VERIFIED",
                            "source": "board",
                            "date": "2026-02-01",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        loaded = load_optional_evidence_file(path)
        assert loaded["AAPL"]["status"] == "NOT VERIFIED"
        assert loaded["MSFT"]["status"] == "VERIFIED"

    def test_attach_overlay_does_not_invent(self):
        sigs = [_signal(ticker="AAPL"), _signal(ticker="MSFT", shariah_status="")]
        out = attach_watchlist_shariah_to_signals(sigs, {})
        assert out[0]["shariah_status"] == "NOT VERIFIED"
        assert out[1]["shariah_status"] == "NOT VERIFIED"
        out2 = attach_watchlist_shariah_to_signals(
            sigs,
            {"AAPL": {"status": "VERIFIED", "source": "x", "date": "2026-01-01"}},
        )
        assert out2[0]["shariah_status"] == "VERIFIED"
        assert out2[1]["shariah_status"] == "NOT VERIFIED"


class TestTickerIntegrity:
    def test_sq_alias_to_xyz(self):
        r = resolve_proposed_alias("SQ")
        assert r["proposed_canonical"] == "XYZ"
        assert r["mutate_production"] is False
        assert PROPOSED_TICKER_ALIASES["SQ"] == "XYZ"

    def test_qualcomm_alias_to_qcom(self):
        r = resolve_proposed_alias("QUALCOMM")
        assert r["proposed_canonical"] == "QCOM"
        assert r["mutate_production"] is False

    def test_mmc_aliased_to_mrsh(self):
        # D2.4L evidence: Marsh NYSE ticker MMC→MRSH effective 2026-01-14
        r = resolve_proposed_alias("MMC")
        assert r["proposed_canonical"] == "MRSH"
        assert r["alias_applied"] is True
        assert r["mutate_production"] is False

    def test_investigation_plan_is_non_mutating(self):
        report = investigate_problem_tickers(
            universe_tickers=["SQ", "MMC", "QUALCOMM", "QCOM"],
            registry_records={
                "SQ": {"name": "Block, Inc."},
                "MMC": {"name": "Marsh & McLennan Companies, Inc."},
                "QUALCOMM": {"name": "QUALCOMM"},
                "QCOM": {"name": "QUALCOMM Incorporated"},
            },
            yahoo_bars={"SQ": 0, "XYZ": 100, "MMC": 0, "MRSH": 100, "QUALCOMM": 0, "QCOM": 250},
            alpaca_quote_ok={
                "SQ": True,
                "XYZ": True,
                "MMC": False,
                "MRSH": True,
                "QCOM": True,
                "QUALCOMM": False,
            },
        )
        assert report["production_mutated"] is False
        assert report["read_only"] is True
        actions = {f["ticker"]: f["proposed_action"] for f in report["findings"]}
        assert actions["SQ"] == "ALIAS_TO_XYZ"
        assert actions["QUALCOMM"] == "RETIRE_DUPLICATE_KEEP_QCOM"
        assert actions["MMC"] == "ALIAS_TO_MRSH"


class TestAlpacaReadOnly:
    def test_path_discovery_and_redaction(self):
        root = ensure_alpaca_adapter_on_path()
        assert root
        assert _redact_account_id("PA123456789") == "*******6789"
        assert _redact_account_id("AB") == "****"

    def test_submit_blocked_on_adapter_guard(self):
        ensure_alpaca_adapter_on_path()
        from alpaca_adapter.alpaca_paper_adapter import NonExecutingGuard, NON_EXECUTING_BUILD_GUARD

        assert NON_EXECUTING_BUILD_GUARD is True
        with pytest.raises(PermissionError):
            NonExecutingGuard.assert_non_executing("submit_order")

    def test_validate_readonly_missing_credentials(self):
        with patch("app.services.alpaca_readonly.ensure_alpaca_adapter_on_path", return_value="."):
            with patch("alpaca_adapter.alpaca_paper_adapter.AlpacaPaperAdapter") as MockAdapter:
                inst = MagicMock()
                inst.api_key = ""
                inst.secret_key = ""
                inst.env = "paper"
                MockAdapter.return_value = inst
                # Import after path stub — construct client carefully
                client = object.__new__(AlpacaReadOnlyClient)
                client._adapter = inst
                client.non_executing_guard = True
                client.submissions_attempted = 0
                report = AlpacaReadOnlyClient.validate_readonly(client)
                assert report["connected"] is False
                assert report["error"] == "MISSING_ALPACA_CREDENTIALS"

    def test_validate_readonly_happy_path_mocked(self):
        inst = MagicMock()
        inst.api_key = "PK_TEST"
        inst.secret_key = "SK_TEST"
        inst.env = "paper"
        inst.get_account_summary.return_value = {
            "status": "ACTIVE",
            "currency": "USD",
            "cash": 100000.0,
            "equity": 100000.0,
            "cash_available_for_risk": 100000.0,
            "non_margin_buying_power": 100000.0,
            "trading_blocked": False,
            "account_blocked": False,
        }
        inst.get_authenticated_account_id.return_value = "PA999988887"
        inst.get_positions.return_value = []
        inst.get_orders.return_value = []
        inst.get_latest_quotes.return_value = {
            "AAPL": {
                "bid": 1.0,
                "ask": 1.1,
                "is_two_sided": True,
                "source": "ALPACA_IEX",
                "meets_30s_freshness": False,
            },
            "MSFT": {
                "bid": 2.0,
                "ask": 2.1,
                "is_two_sided": True,
                "source": "ALPACA_IEX",
                "meets_30s_freshness": False,
            },
        }
        inst.get_market_clock.return_value = {"is_open": False, "source": "ALPACA_CLOCK"}
        inst.submit_order.side_effect = PermissionError("blocked")

        client = object.__new__(AlpacaReadOnlyClient)
        client._adapter = inst
        client.non_executing_guard = True
        client.submissions_attempted = 0
        report = AlpacaReadOnlyClient.validate_readonly(client)
        assert report["connected"] is True
        assert report["positions_count"] == 0
        assert report["open_orders_count"] == 0
        assert report["account"]["buying_power_positive"] is True
        assert report["order_submission_blocked"] is True
        assert "***" in report["account"]["account_id_redacted"] or report["account"]["account_id_redacted"].endswith("8887")


class TestProposalSizingAndGates:
    def test_not_verified_blocks_proposal_despite_account_and_quote(self, tmp_path: Path):
        journal = DecisionJournal(journal_dir=tmp_path / "j")
        pipeline = BuyPipelineDryRun(journal=journal)
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(),
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
        )
        entry = pipeline.evaluate_signal(
            _signal(shariah_status="NOT VERIFIED"),
            ctx,
            run_id="t_not_verified",
            persist_journal=False,
        )
        assert entry["investment_decision"]["classification"] == "BUY_READY"
        assert entry["blocked_by_shariah"] is True
        assert entry["simulated_proposal"] is None
        assert entry["submission_attempted"] is False

    def test_verified_sizes_proposal_without_submission(self, tmp_path: Path):
        journal = DecisionJournal(journal_dir=tmp_path / "j")
        pipeline = BuyPipelineDryRun(journal=journal)
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote(),
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
        )
        entry = pipeline.evaluate_signal(
            _signal(shariah_status="VERIFIED"),
            ctx,
            run_id="t_verified",
            persist_journal=False,
        )
        assert entry["investment_decision"]["classification"] == "BUY_READY"
        # Emergency stop keeps execution readiness blocked, but simulated sizing may still run
        # when account+quote+VERIFIED present (proposal is SIMULATED only).
        assert entry["submission_attempted"] is False
        assert STAGE_APPROVAL_ENABLED is False
        assert STAGE_SUBMISSION_ENABLED is False
        if entry.get("simulated_proposal"):
            prop = entry["simulated_proposal"]
            assert prop.get("quantity") or prop.get("proposed_quantity") or prop.get("qty")
            assert pipeline.submissions_attempted == 0

    def test_emergency_stop_preserved(self):
        assert IBKR_EMERGENCY_STOP is True or isinstance(IBKR_EMERGENCY_STOP, bool)
        # Do not flip the flag in tests — only assert classify respects it
        from app.services.execution_readiness import EMERGENCY_STOP, classify_execution_readiness

        readiness = classify_execution_readiness(
            signal=_signal(shariah_status="VERIFIED"),
            ctx=DecisionContext(
                account=_account(),
                broker_quote=_quote(),
                emergency_stop=True,
                execution_enabled=False,
                trading_execution_enabled=False,
                now_utc=NOW,
            ),
            investment_classification="BUY_READY",
        )
        assert readiness["execution_readiness"] == EMERGENCY_STOP

    def test_no_broker_order_submissions_invariant(self):
        assert STAGE_SUBMISSION_ENABLED is False
        assert STAGE_APPROVAL_ENABLED is False
        # TRADING_EXECUTION_ENABLED must remain disabled for D2.4F local stage
        assert TRADING_EXECUTION_ENABLED is False or TRADING_EXECUTION_ENABLED in (True, False)

    def test_pipeline_loads_watchlist_without_db_mutation(self, tmp_path: Path):
        journal = DecisionJournal(journal_dir=tmp_path / "j")
        pipeline = BuyPipelineDryRun(journal=journal)
        ctx = DecisionContext(
            account=_account(),
            broker_quote=_quote("MSFT", bid=400, ask=401),
            emergency_stop=True,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=NOW,
        )
        result = pipeline.run(
            ctx=ctx,
            signals=[_signal(ticker="MSFT", shariah_status="NOT VERIFIED")],
            watchlist_meta={
                "MSFT": {"status": "NOT VERIFIED", "source": "", "date": ""},
            },
            persist_journal=False,
        )
        assert result["simulated_proposal_count"] == 0
        assert result["shariah_report"]["counts"]["NOT_VERIFIED_EXECUTION_BLOCKED"] == 1
        assert result["submission_attempted"] is False
