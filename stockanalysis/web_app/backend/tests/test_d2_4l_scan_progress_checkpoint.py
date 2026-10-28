"""D2.4L scanner progress / checkpoint / optimize-cache (no V4.0 math changes)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.config import V40_STRATEGY_VERSION
from app.services.observation_runner import ObservationRunner
from app.services.scanner_service import scanner_service


def _fake_df(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
        },
        index=idx,
    )


class TestOptimizeCache:
    def test_optimize_cache_roundtrip(self, tmp_path, monkeypatch):
        import app.services.scanner_service as ss

        monkeypatch.setattr(ss, "OPTIMIZE_CACHE_DIR", tmp_path)
        calls = {"n": 0}

        def fake_train(*args, **kwargs):
            calls["n"] += 1
            return {"entry": "CROSS", "exit": "MA250_3CLOSE"}, None

        with patch.dict("sys.modules", {}):
            import engine as v41_engine

            with patch.object(v41_engine, "train", side_effect=fake_train):
                d = _fake_df()
                asof = d.index[-1]
                w1 = scanner_service.optimize_v40_rule(
                    d, asof, cache_key=("ZZZZ", "2026-10-26")
                )
                w2 = scanner_service.optimize_v40_rule(
                    d, asof, cache_key=("ZZZZ", "2026-10-26")
                )
        assert w1["entry"] == "CROSS"
        assert w2["entry"] == "CROSS"
        assert calls["n"] == 1  # second call served from cache


class TestCheckpointResume:
    def test_resume_restores_scan_rows(self, tmp_path):
        runner = ObservationRunner(
            evidence_dir=tmp_path / "ev",
            refresh_prices=False,
            checkpoint_scope="test_scope_2026-10-26",
            use_optimize_cache=False,
        )
        runner.checkpoint_path = tmp_path / "ckpt" / "checkpoint.json"
        runner.checkpoint_path.parent.mkdir(parents=True)

        fake_row = {
            "ticker": "AAA",
            "signal": "BUY CANDIDATE",
            "strategy_version": V40_STRATEGY_VERSION,
            "market_as_of_date": "2026-10-26",
        }
        runner._save_checkpoint(
            {
                "completed_tickers": ["AAA"],
                "scan_rows_by_ticker": {"AAA": fake_row},
                "universe_tickers": ["AAA", "BBB"],
                "strategy_version": V40_STRATEGY_VERSION,
                "timings": [{"ticker": "AAA", "total_s": 1.0, "prices_s": 0.2, "evaluate_s": 0.8}],
            }
        )

        calls = []

        def fake_eval(ticker, df=None, use_optimize_cache=False):
            calls.append(ticker)
            return {
                "ticker": ticker,
                "signal": "AVOID",
                "strategy_version": V40_STRATEGY_VERSION,
                "market_as_of_date": "2026-10-26",
            }

        with patch.object(scanner_service, "get_price_df", return_value=_fake_df()):
            with patch.object(scanner_service, "evaluate_stock_signal", side_effect=fake_eval):
                out = runner.scan_universe(["AAA", "BBB"], resume=True)

        assert "AAA" not in calls
        assert calls == ["BBB"]
        assert out["scan_rows"][0]["ticker"] == "AAA"
        assert out["scan_rows"][0]["signal"] == "BUY CANDIDATE"
        assert out["resumed_from_checkpoint"] is True
        assert len(out["tickers_scanned"]) == 2
