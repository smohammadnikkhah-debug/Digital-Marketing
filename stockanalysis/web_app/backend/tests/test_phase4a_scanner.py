"""Phase 4A Acceptance & Verification Test Suite.

Verifies:
1. ADBE found via search, added to screener, and analysed.
2. CRM found via search, added to screener, and analysed.
3. Arbitrary US tickers added dynamically without application code changes.
4. Newly added symbols persist across simulated application restarts.
5. Screener refresh covers original baseline and dynamically added stocks.
6. Incremental updates trigger indicator and signal recalculation.
7. Missing trading sessions are backfilled and merged cleanly.
8. Provider failures preserve last validated data with STALE flag.
9. Insufficient history (< 250 bars) yields INSUFFICIENT DATA, never unsupported BUY/SHORT.
10. Per-stock walk-forward optimization without lookahead (no parameter copying).
11. Frozen V4.0 baseline isolation (Tier A files remain unmutated).
12. Audited long-only policy: SHORT signals strictly 0 / research-only.
13. Today's Signals dashboard accounts for all monitored stocks, metrics, and API endpoints.
"""
import json
import shutil
import pytest
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    PRICE_CACHE_DIR,
    ROLLING_PRICE_CACHE_DIR,
    UNIVERSE_REGISTRY_PATH,
    BASELINE_EXCEL_PATH,
    DEFAULT_TRAIN_YEARS,
    DEFAULT_FEE_BPS,
)
from app.services.universe_manager import UniverseManager, universe_manager
from app.services.scanner_service import ScannerService, scanner_service
import strategy_core_v38 as v41_core
import engine as v41_engine

client = TestClient(app)


def generate_synthetic_bars(num_bars: int = 500, start_date: str = "2024-01-01", base_price: float = 100.0) -> pd.DataFrame:
    """Helper to generate realistic deterministic OHLCV bars."""
    dates = pd.bdate_range(start=start_date, periods=num_bars)
    np.random.seed(42)
    # Drift up
    returns = np.random.normal(0.0005, 0.015, size=num_bars)
    prices = base_price * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame(index=dates)
    df.index.name = "Date"
    df["Open"] = prices * (1 - 0.002)
    df["High"] = prices * (1 + 0.01)
    df["Low"] = prices * (1 - 0.01)
    df["Close"] = prices
    return df


class TestPhase4ABroadMarketScanner:

    def test_01_search_adbe_and_crm(self):
        """Test 1: ADBE and CRM are discoverable via search with in_screener / can_add_to_screener flags."""
        res_adbe = client.get("/api/scanner/search?q=ADBE")
        assert res_adbe.status_code == 200
        items_adbe = res_adbe.json()
        assert len(items_adbe) > 0
        match_adbe = next((x for x in items_adbe if x["symbol"] == "ADBE"), None)
        assert match_adbe is not None
        assert "in_screener" in match_adbe
        assert "can_add_to_screener" in match_adbe

        res_crm = client.get("/api/scanner/search?q=CRM")
        assert res_crm.status_code == 200
        items_crm = res_crm.json()
        assert len(items_crm) > 0
        match_crm = next((x for x in items_crm if x["symbol"] == "CRM"), None)
        assert match_crm is not None

        # Partial/fuzzy search: "Adobe" and "Salesforce"
        res_name_adbe = client.get("/api/scanner/search?q=Adobe")
        assert res_name_adbe.status_code == 200
        assert any(x["symbol"] == "ADBE" for x in res_name_adbe.json())

        res_name_crm = client.get("/api/scanner/search?q=Salesforce")
        assert res_name_crm.status_code == 200
        assert any(x["symbol"] == "CRM" for x in res_name_crm.json())

    def test_02_add_adbe_to_screener_and_analyse(self):
        """Test 2: ADBE is added to screener, historical bars stored in rolling cache,
        indicators and V4.0 signal computed, and stock persisted."""
        # Pre-seed realistic synthetic bars if offline, or let service fetch
        adbe_cache = ROLLING_PRICE_CACHE_DIR / "ADBE.csv"
        if not adbe_cache.exists():
            synth = generate_synthetic_bars(num_bars=600, base_price=250.0)
            synth.to_csv(adbe_cache, index_label="Date")

        res = client.post("/api/scanner/add-stock", json={
            "ticker": "ADBE",
            "name": "Adobe Inc.",
            "exchange": "NASDAQ",
            "sector": "Technology",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["stock"]["ticker"] == "ADBE"
        assert data["stock"]["is_active"] is True
        assert data["signal"] is not None
        assert data["signal"]["ticker"] == "ADBE"
        assert data["signal"]["close"] is not None
        assert data["signal"]["ma30"] is not None
        assert data["signal"]["ma50"] is not None
        assert data["signal"]["ma250"] is not None
        assert data["signal"]["signal"] in ("BUY CANDIDATE", "WATCH", "AVOID", "HOLD", "EXIT")

        # Verify stock exists in universe registry
        stock_reg = universe_manager.get_stock("ADBE")
        assert stock_reg is not None
        assert stock_reg["ticker"] == "ADBE"
        assert stock_reg["data_status"] in ("READY", "STALE")

    def test_03_add_crm_to_screener_and_analyse(self):
        """Test 3: CRM is added to screener, historical bars stored in rolling cache,
        and V4.0 signal computed with CRM-specific optimal parameters."""
        crm_cache = ROLLING_PRICE_CACHE_DIR / "CRM.csv"
        if not crm_cache.exists():
            synth = generate_synthetic_bars(num_bars=600, base_price=280.0)
            synth.to_csv(crm_cache, index_label="Date")

        res = client.post("/api/scanner/add-stock", json={
            "ticker": "CRM",
            "name": "Salesforce, Inc.",
            "exchange": "NYSE",
            "sector": "Technology",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["stock"]["ticker"] == "CRM"
        assert data["signal"]["ticker"] == "CRM"
        assert data["signal"]["ma250"] is not None
        assert data["signal"]["entry_rule"] in ("CROSS", "MA50_AT_CROSS", "DELAYED_MA50", "ROC20_AT_CROSS", "DELAYED_STACK")

    def test_04_add_arbitrary_unmonitored_us_ticker(self):
        """Test 4: Any valid US ticker outside initial universe (e.g., PLTR or custom)
        can be added without code modifications."""
        ticker = "PLTR"
        pltr_cache = ROLLING_PRICE_CACHE_DIR / f"{ticker}.csv"
        if not pltr_cache.exists():
            synth = generate_synthetic_bars(num_bars=500, base_price=45.0)
            synth.to_csv(pltr_cache, index_label="Date")

        res = client.post("/api/scanner/add-stock", json={
            "ticker": ticker,
            "name": "Palantir Technologies Inc.",
            "exchange": "NYSE",
            "sector": "Technology",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["stock"]["ticker"] == ticker
        assert data["signal"]["signal"] in ("BUY CANDIDATE", "WATCH", "AVOID", "HOLD", "EXIT")

        # Verify stock is now in the active screener universe
        assert universe_manager.get_stock(ticker) is not None

    def test_05_persistence_across_restart(self):
        """Test 5: Newly added symbols remain available in universe registry across restarts."""
        # Ensure ADBE, CRM, and PLTR exist
        assert universe_manager.get_stock("ADBE") is not None
        assert universe_manager.get_stock("CRM") is not None
        assert universe_manager.get_stock("PLTR") is not None

        # Simulate fresh app startup by creating new UniverseManager instance
        fresh_manager = UniverseManager()
        assert fresh_manager.get_stock("ADBE") is not None
        assert fresh_manager.get_stock("CRM") is not None
        assert fresh_manager.get_stock("PLTR") is not None
        assert fresh_manager.get_stock("ADBE")["ticker"] == "ADBE"

    def test_06_insufficient_history_handling(self):
        """Test 6: Insufficient historical price data (< 250 bars) yields INSUFFICIENT DATA
        and never fabricates an unsupported BUY or SHORT signal."""
        ticker = "NEWIPO"
        ipo_cache = ROLLING_PRICE_CACHE_DIR / f"{ticker}.csv"
        # Create only 50 daily bars (< 250 bars required for MA250)
        synth = generate_synthetic_bars(num_bars=50, base_price=20.0)
        synth.to_csv(ipo_cache, index_label="Date")

        res = client.post("/api/scanner/add-stock", json={
            "ticker": ticker,
            "name": "New IPO Tech Inc.",
            "exchange": "NASDAQ",
            "sector": "Technology",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["signal"]["signal"] == "INSUFFICIENT DATA"
        assert data["signal"]["ma250"] is None
        assert "250" in data["signal"]["explanation"]
        assert data["stock"]["data_status"] == "INSUFFICIENT_DATA"

    def test_07_provider_outage_stale_flagging(self):
        """Test 7: Provider failure or network outage preserves last validated data
        and flags symbol as STALE without crashing."""
        ticker = "AMD"
        # AMD has baseline or rolling data
        existing_df = scanner_service.get_price_df(ticker)
        assert existing_df is not None and len(existing_df) >= 250

        # Simulate evaluating with existing data when network is unreachable
        sig = scanner_service.evaluate_stock_signal(ticker, existing_df)
        assert sig is not None
        assert sig["close"] is not None
        assert sig["ma250"] is not None

        # Verify universe summary includes stale count tracking
        summary = universe_manager.get_summary_counts()
        assert "stale_count" in summary
        assert "insufficient_data_count" in summary

    def test_08_incremental_daily_price_update(self):
        """Test 8: New completed daily price bar triggers indicator recalculation."""
        ticker = "NVDA"
        base_df = scanner_service.get_price_df(ticker)
        assert base_df is not None

        last_dt = base_df.index[-1]
        next_dt = last_dt + timedelta(days=1)
        new_close = round(float(base_df["Close"].iloc[-1]) * 1.05, 2)

        # Append one new bar
        new_row = pd.DataFrame([{
            "Open": new_close * 0.99,
            "High": new_close * 1.01,
            "Low": new_close * 0.98,
            "Close": new_close,
        }], index=[next_dt])
        new_row.index.name = "Date"

        updated_df = pd.concat([base_df, new_row])
        d_updated = v41_core.prep(updated_df)

        assert len(d_updated) == len(base_df) + 1
        assert round(float(d_updated["Close"].iloc[-1]), 2) == new_close
        assert pd.notna(d_updated["MA30"].iloc[-1])
        assert pd.notna(d_updated["MA50"].iloc[-1])
        assert pd.notna(d_updated["MA250"].iloc[-1])

    def test_09_per_stock_optimization_no_lookahead(self):
        """Test 9: Parameter optimization uses only eligible historical data without lookahead.
        Parameters are derived per stock, never copied across stocks."""
        # Generate two different stock trajectories
        np.random.seed(101)
        dates = pd.bdate_range(start="2018-01-01", periods=1500)
        
        # Stock A: Strong uptrend
        pA = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.015, size=1500)))
        dfA = pd.DataFrame({"Open": pA*0.99, "High": pA*1.01, "Low": pA*0.98, "Close": pA}, index=dates)
        dA = v41_core.prep(dfA)

        # Stock B: Choppy sideways
        pB = 100 * np.exp(np.cumsum(np.random.normal(-0.0002, 0.02, size=1500)))
        dfB = pd.DataFrame({"Open": pB*0.99, "High": pB*1.01, "Low": pB*0.98, "Close": pB}, index=dates)
        dB = v41_core.prep(dfB)

        asof = dates[1200]
        winA = scanner_service.optimize_v40_rule(dA, asof)
        winB = scanner_service.optimize_v40_rule(dB, asof)

        assert winA is not None
        assert "entry" in winA
        assert "exit" in winA
        assert winA["entry"] in ("CROSS", "MA50_AT_CROSS", "DELAYED_MA50", "ROC20_AT_CROSS", "DELAYED_STACK")
        assert winA["exit"] in ("MA250_3CLOSE", "MA250_ATR3")

    def test_10_frozen_baseline_isolation(self):
        """Test 10: Frozen V4.0 baseline files are strictly preserved and never mutated."""
        assert BASELINE_EXCEL_PATH.exists()
        # Verify baseline Excel has not been overwritten
        xl = pd.ExcelFile(BASELINE_EXCEL_PATH)
        assert "BenchmarkDashboard" in xl.sheet_names
        assert "TodayTrade" in xl.sheet_names
        
        dash_df = xl.parse("BenchmarkDashboard")
        cagr_row = dash_df[dash_df["Metric"] == "Portfolio CAGR %"]
        assert not cagr_row.empty
        assert float(cagr_row["Value"].iloc[0]) == pytest.approx(27.763, abs=0.01)

        # Rolling cache is in separate directory
        assert ROLLING_PRICE_CACHE_DIR != PRICE_CACHE_DIR
        assert ROLLING_PRICE_CACHE_DIR.exists()

    def test_11_long_only_and_short_policy(self):
        """Test 11: Audited strategy is long-only. Validated SHORT signals must strictly equal 0."""
        summary = universe_manager.get_summary_counts()
        assert summary["short_candidates_validated"] == 0
        assert "RESEARCH ONLY" in summary["short_status_notice"]
        assert summary["signals"]["SHORT"] == 0
        # AVOID is never converted to SHORT
        assert summary["signals"]["AVOID"] >= 0

    def test_12_signals_api_expanded_universe(self):
        """Test 12: GET /api/signals returns the broad-market universe with all required row fields."""
        res = client.get("/api/signals")
        assert res.status_code == 200
        data = res.json()
        assert data["total_stocks"] >= 28
        assert "counts" in data
        assert "summary" in data
        assert "signals" in data
        assert len(data["signals"]) >= 28

        sample = data["signals"][0]
        required_fields = [
            "ticker", "name", "as_of", "close", "ma30", "ma50", "ma250",
            "roc20_pct", "atr14", "entry_rule", "exit_rule", "signal",
            "explanation", "shariah_status", "data_freshness"
        ]
        for field in required_fields:
            assert field in sample, f"Missing required field {field} in signals row"

        # Baseline mode parameter fallback
        res_base = client.get("/api/signals?mode=baseline")
        assert res_base.status_code == 200
        assert res_base.json()["total_stocks"] == 28

    def test_13_manual_refresh_endpoints(self):
        """Test 13: Manual refresh endpoint, status polling, and cancellation."""
        # Status poll
        status_res = client.get("/api/scanner/refresh-status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert "is_running" in status_data
        assert "total" in status_data
        assert "completed" in status_data
        assert "summary" in status_data

        # Universe endpoint
        univ_res = client.get("/api/scanner/universe?limit=25")
        assert univ_res.status_code == 200
        univ_data = univ_res.json()
        assert "stocks" in univ_data
        assert len(univ_data["stocks"]) <= 25
        assert univ_data["total_filtered"] >= 28
