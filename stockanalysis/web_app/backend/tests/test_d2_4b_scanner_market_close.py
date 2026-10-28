"""Stage D2.4B — Market-close scanner contract, provenance, Shariah eligibility, signal separation.

Local / mocked only. Does not run a real 230-stock production scan or write production DBs.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.cli import enqueue_market_close_refresh
from app.config import V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION, RISK_UI_SIGNAL_SOURCE
from app.services.scanner_service import (
    FULL_UNIVERSE_JOB_TYPES,
    normalize_refresh_job_type,
    scanner_service,
)
from app.services.shariah_eligibility import (
    BLOCKED,
    ELIGIBLE,
    classify_execution_eligibility,
    attach_execution_eligibility,
)


def _synthetic_ohlcv(n: int = 280, seed: int = 42, start_price: float = 100.0) -> pd.DataFrame:
    """Deterministic OHLCV bars sufficient for MA250 (no network)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    # Gentle uptrend so MA250 is defined and finite
    noise = rng.normal(0, 0.4, size=n)
    close = start_price + np.cumsum(0.05 + noise)
    high = close + 0.5
    low = close - 0.5
    open_ = close - 0.1
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close},
        index=dates,
    )


class TestMarketCloseJobTypeContract:
    def test_normalize_market_close_alias(self):
        assert normalize_refresh_job_type("market_close") == "MARKET_CLOSE"
        assert "MARKET_CLOSE" in FULL_UNIVERSE_JOB_TYPES
        assert "FULL" in FULL_UNIVERSE_JOB_TYPES

    def test_market_close_maps_to_full_universe_without_tickers(self, monkeypatch):
        """cli MARKET_CLOSE must enqueue a full-universe refresh (not raise ValueError)."""
        fake_universe = [
            {"ticker": "AAA", "is_active": True, "name": "AAA Inc"},
            {"ticker": "BBB", "is_active": True, "name": "BBB Inc"},
            {"ticker": "CCC", "is_active": True, "name": "CCC Inc"},
        ]

        captured = {}

        class FakeQuery:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def first(self):
                return None

        class FakeDB:
            def execute(self, *a, **k):
                return MagicMock(scalar=lambda: True)

            def query(self, *a, **k):
                return FakeQuery()

            def add(self, job):
                captured["job"] = job

            def commit(self):
                pass

            def refresh(self, job):
                pass

            def close(self):
                pass

        monkeypatch.setattr(
            "app.services.scanner_service.universe_manager.get_eligible_universe",
            lambda: fake_universe,
        )
        monkeypatch.setattr("app.database.SessionLocal", FakeDB)
        monkeypatch.setattr("app.services.scanner_service.is_sqlite", True)
        monkeypatch.setattr("app.services.scanner_service.WORKER_MODE", "standalone")

        res = scanner_service.start_refresh_async(force_all=False, job_type="MARKET_CLOSE")

        assert res["status"] == "QUEUED"
        job = captured["job"]
        assert job.job_type == "MARKET_CLOSE"
        assert job.total_stocks == 3
        meta = json.loads(job.errors_json)
        assert meta["requested_tickers"] == ["AAA", "BBB", "CCC"]
        assert "Market-close" in job.message or "market-close" in job.message.lower()

    def test_enqueue_market_close_refresh_helper_uses_market_close(self, monkeypatch):
        called = {}

        def fake_start(**kwargs):
            called.update(kwargs)
            return {"status": "QUEUED", "job_id": "job_test"}

        monkeypatch.setattr(
            "app.cli.scanner_service.start_refresh_async",
            fake_start,
        )
        out = enqueue_market_close_refresh(force_all=False)
        assert out["job_id"] == "job_test"
        assert called["job_type"] == "MARKET_CLOSE"
        assert called["force_all"] is False

    def test_market_close_rejects_ticker_list(self, monkeypatch):
        class FakeQuery:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def first(self):
                return None

        class FakeDB:
            def execute(self, *a, **k):
                return MagicMock(scalar=lambda: True)

            def query(self, *a, **k):
                return FakeQuery()

            def close(self):
                pass

        monkeypatch.setattr("app.database.SessionLocal", FakeDB)
        monkeypatch.setattr("app.services.scanner_service.is_sqlite", True)

        with pytest.raises(ValueError, match="Contradictory"):
            scanner_service.start_refresh_async(
                force_all=False,
                job_type="MARKET_CLOSE",
                tickers=["AAPL"],
            )


class TestV40SignalPipelineProvenance:
    def test_evaluate_attaches_provenance_and_never_buys_on_short_history(self):
        short = _synthetic_ohlcv(n=40, seed=1)
        sig = scanner_service.evaluate_stock_signal("TESTPIPE", short)
        assert sig["signal"] == "INSUFFICIENT DATA"
        assert sig["signal_source"] == V40_SIGNAL_SOURCE
        assert sig["strategy_version"] == V40_STRATEGY_VERSION
        assert sig["is_fresh_analysis"] is True
        assert sig["provenance_mode"] == "LIVE_SCAN"
        assert sig["validation_status"] == "INSUFFICIENT_DATA"
        assert sig["market_as_of_date"] == sig["as_of"]
        assert sig["scan_completed_at"]
        assert "entry_rule" in sig

    def test_evaluate_full_history_emits_v40_classification_with_indicators(self):
        df = _synthetic_ohlcv(n=280, seed=7)
        # Force a below-MA250 regime on last bar by crashing the last close
        df = df.copy()
        df.iloc[-1, df.columns.get_loc("Close")] = float(df["Close"].iloc[-50:].mean()) * 0.5
        df.iloc[-1, df.columns.get_loc("Open")] = df.iloc[-1]["Close"]
        df.iloc[-1, df.columns.get_loc("High")] = df.iloc[-1]["Close"]
        df.iloc[-1, df.columns.get_loc("Low")] = df.iloc[-1]["Close"] * 0.99

        with patch.object(scanner_service, "optimize_v40_rule", return_value={"entry": "CROSS", "exit": "MA250_3CLOSE"}):
            sig = scanner_service.evaluate_stock_signal("TESTPIPE", df)

        assert sig["signal"] in ("BUY CANDIDATE", "WATCH", "HOLD", "EXIT", "AVOID")
        assert sig["signal"] != "INSUFFICIENT DATA"
        assert sig["ma250"] is not None
        assert sig["ma30"] is not None
        assert sig["ma50"] is not None
        assert sig["entry_rule"] == "CROSS"
        assert sig["exit_rule"] == "MA250_3CLOSE"
        assert sig["signal_source"] == V40_SIGNAL_SOURCE
        assert sig["is_fresh_analysis"] is True
        assert sig["provenance_mode"] == "LIVE_SCAN"
        assert "execution_eligibility" in sig

    def test_publish_partial_pipeline_persists_snapshot_locally(self, monkeypatch):
        """Tiny mocked FULL-equivalent path: evaluate → publish snapshot (SQLite/local)."""
        from app.services.snapshot_service import snapshot_service
        from app.database import SessionLocal

        df = _synthetic_ohlcv(n=280, seed=9)
        with patch.object(scanner_service, "optimize_v40_rule", return_value={"entry": "CROSS", "exit": "MA250_3CLOSE"}):
            sig = scanner_service.evaluate_stock_signal("MOCK1", df)

        assert sig["signal_source"] == V40_SIGNAL_SOURCE
        db = SessionLocal()
        try:
            snap = snapshot_service.publish_new_snapshot(
                staged_signals=[sig],
                market_as_of_date=sig["as_of"],
                refresh_job_id="job_d24b_test",
                db=db,
                is_partial=True,
            )
            assert snap["snapshot_id"]
            active = snapshot_service.get_active_snapshot(db)
            assert active is not None
            signals = active.get("signals") or []
            match = next((s for s in signals if s.get("ticker") == "MOCK1"), None)
            assert match is not None
            assert match.get("signal_source") == V40_SIGNAL_SOURCE
            assert match.get("as_of") == sig["as_of"]
            assert match.get("entry_rule") == "CROSS"
        finally:
            db.close()


class TestShariahExecutionEligibility:
    def test_verified_eligible(self):
        meta = classify_execution_eligibility("VERIFIED")
        assert meta["execution_eligibility"] == ELIGIBLE
        assert meta["execution_eligible"] is True

    def test_not_verified_blocked(self):
        meta = classify_execution_eligibility("NOT VERIFIED")
        assert meta["execution_eligibility"] == BLOCKED
        assert meta["execution_eligible"] is False

    def test_non_compliant_blocked(self):
        meta = classify_execution_eligibility("NON-COMPLIANT")
        assert meta["execution_eligibility"] == BLOCKED
        assert meta["execution_eligible"] is False

    def test_does_not_mutate_stored_status(self):
        original = {"ticker": "XYZ", "signal": "WATCH", "shariah_status": "NOT VERIFIED"}
        enriched = attach_execution_eligibility(original)
        assert original["shariah_status"] == "NOT VERIFIED"
        assert enriched["shariah_status_preserved"] == "NOT VERIFIED"
        assert enriched["execution_eligible"] is False


class TestRiskUiSignalSeparation:
    def test_risk_ui_labels_are_not_v40_scanner_vocabulary(self):
        from app.services.financial_data import financial_data_service

        # Use synthetic price path via monkeypatch of internal helpers
        n = 280
        dates = pd.bdate_range("2024-01-02", periods=n)
        close = pd.Series(np.linspace(80, 120, n), index=dates)
        price_df = pd.DataFrame(
            {
                "close": close,
                "high": close + 1,
                "low": close - 1,
                "open": close,
            }
        )

        with patch.object(financial_data_service, "_get_historical_prices_df", side_effect=lambda t: price_df if t != "SPY" else price_df):
            with patch.object(financial_data_service, "_read_disk_cache", return_value=None):
                with patch.object(financial_data_service, "_write_disk_cache", return_value=None):
                    with patch("yfinance.Ticker") as mock_ticker:
                        mock_ticker.return_value.info = {"currentPrice": float(close.iloc[-1])}
                        risk = financial_data_service.get_stock_risk_assessment("SEPTEST", refresh=True)

        trend = risk["trend_risk"]
        assert trend["signal_family"] == RISK_UI_SIGNAL_SOURCE or trend["signal_family"] == "FINANCIAL_RISK_UI"
        assert trend["not_a_v40_scanner_signal"] is True
        assert trend["technical_signal"] not in {
            "BUY CANDIDATE",
            "WATCH",
            "HOLD",
            "EXIT",
            "AVOID",
        }
        assert trend["risk_ui_recommendation"] == trend["technical_signal"]
        assert trend["technical_signal"].startswith("TREND_")
