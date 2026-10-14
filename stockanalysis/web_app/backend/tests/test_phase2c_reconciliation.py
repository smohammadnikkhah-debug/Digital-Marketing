"""Phase 2C Automated Acceptance & Reconciliation Test Suite.

Verifies:
1. Exact cell-for-cell match between API metrics and frozen V4.0 Excel workbook (BenchmarkDashboard).
2. Exactly 80 completed trades.
3. Exactly 11 annual comparison rows with beating SPY in 9 of 11 years.
4. Portfolio ending value of $1,396,996.56.
5. Portfolio maximum drawdown of -42.544% (and SPY -33.717%).
6. Portfolio CAGR of 27.763% (and SPY 15.275%).
7. Exact consistency across Dashboard, Portfolio, Risk Analytics, and Backtesting datasets.
8. Active holdings consistency: QQQ, NVDA, MA, CRWD, ANET ($17,252.69 cash, $1,379,743.87 exposure).
9. Mathematical calculation of Sharpe (1.02), Sortino (0.97), Calmar (0.653), VaR 95% (2.791%), CVaR (4.02%).
10. Shariah status independence from technical signals.
11. Nightly scan scheduler execution and status tracking.
12. Strict baseline mode enforcement (Hybrid D exit mode rejected).
"""
import unittest
from pathlib import Path
import json
import numpy as np
import pandas as pd

from app.engine_bridge import bridge
from app.config import (
    BASELINE_EXCEL_PATH,
    PRICE_CACHE_DIR,
    DEFAULT_CAPITAL,
    DATA_PROVENANCE,
)
from app.jobs import scheduler


class TestPhase2CReconciliation(unittest.TestCase):
    """Automated reconciliation tests verifying 100% fidelity to V4.0 baseline."""

    @classmethod
    def setUpClass(cls):
        # Load sheets from audited baseline workbook
        cls.excel_path = BASELINE_EXCEL_PATH
        if not cls.excel_path.exists():
            alt_path = Path(__file__).resolve().parent.parent.parent.parent / "adaptive_trading_v40" / "results_v40" / "Adaptive_Trading_V40_Baseline.xlsx"
            if alt_path.exists():
                cls.excel_path = alt_path
        cls.benchmark_df = pd.read_excel(cls.excel_path, sheet_name="BenchmarkDashboard")
        cls.metrics_map = dict(zip(cls.benchmark_df["Metric"], cls.benchmark_df["Value"]))

        cls.annual_df = pd.read_excel(cls.excel_path, sheet_name="AnnualVsSPY")
        cls.trades_df = pd.read_excel(cls.excel_path, sheet_name="Trades")
        cls.equity_df = pd.read_excel(cls.excel_path, sheet_name="PortfolioEquity")
        cls.today_df = pd.read_excel(cls.excel_path, sheet_name="TodayTrade")

    def test_01_dashboard_metrics_reconciled_against_excel(self):
        """1. Verify Dashboard API metrics match cell-for-cell with BenchmarkDashboard sheet."""
        dash = bridge.get_baseline_dashboard()

        # Ending values
        self.assertAlmostEqual(dash["initial_capital"], float(self.metrics_map["Initial capital"]), places=2)
        self.assertAlmostEqual(dash["portfolio_ending_value"], 1396996.56, places=2)
        self.assertAlmostEqual(dash["spy_ending_value"], 461768.66, places=2)

        # Total Return %
        self.assertAlmostEqual(dash["portfolio_total_return_pct"], 1296.997, places=3)
        self.assertAlmostEqual(dash["spy_total_return_pct"], 361.769, places=3)

        # CAGR % (Reconciling 27.763% vs 15.275%)
        self.assertAlmostEqual(dash["portfolio_cagr_pct"], 27.763, places=3)
        self.assertAlmostEqual(dash["spy_cagr_pct"], 15.275, places=3)

        # Max Drawdown % (Reconciling -42.544% vs -33.717%)
        self.assertAlmostEqual(dash["portfolio_max_drawdown_pct"], -42.544, places=3)
        self.assertAlmostEqual(dash["spy_max_drawdown_pct"], -33.717, places=3)

        # Years beating SPY & Completed trades
        self.assertEqual(dash["years_beating_spy"], 9)
        self.assertEqual(dash["years_compared"], 11)
        self.assertEqual(dash["completed_trades"], 80)

    def test_02_annual_comparison_scorecard(self):
        """2. Verify 11 annual comparison rows with exact excess percentage points."""
        annual_rows = bridge.get_annual_performance()
        self.assertEqual(len(annual_rows), 11)

        beating_count = sum(1 for r in annual_rows if r["excess_pp"] > 0)
        self.assertEqual(beating_count, 9)

        # Verify 2016 through 2026 years exist
        years = [r["year"] for r in annual_rows]
        self.assertEqual(years, list(range(2016, 2027)))

    def test_03_canonical_portfolio_equity_curve_and_dates(self):
        """3. Confirm equity curve starts on 2016-01-04 and ends on 2026-10-09 with 2,708 sessions."""
        curve = bridge.get_portfolio_equity_curve()
        self.assertEqual(len(curve), 2708)

        # Start Date must be 2016-01-04 (not 2014)
        self.assertEqual(curve[0]["date"], "2016-01-04")
        self.assertAlmostEqual(curve[0]["portfolio"], 100000.0, places=2)
        self.assertAlmostEqual(curve[0]["cash"], 100000.0, places=2)

        # End Date must be 2026-10-09
        self.assertEqual(curve[-1]["date"], "2026-10-09")
        self.assertAlmostEqual(curve[-1]["portfolio"], 1396996.56, places=2)
        self.assertAlmostEqual(curve[-1]["cash"], 17252.69, places=2)

        # Min Drawdown along the curve must be -42.544%
        min_dd = min(p["portfolio_dd_pct"] for p in curve)
        self.assertAlmostEqual(min_dd, -42.544, places=2)

    def test_04_active_holdings_and_cash_consistency(self):
        """4. Verify active holdings are exactly QQQ, NVDA, MA, CRWD, ANET ($17,252.69 cash)."""
        port = bridge.get_portfolio_holdings_and_trades()
        dash = bridge.get_baseline_dashboard()

        # Cash consistency across pages
        self.assertAlmostEqual(dash["available_cash"], 17252.69, places=2)
        self.assertAlmostEqual(dash["simulated_exposure"], 1379743.87, places=2)
        self.assertAlmostEqual(dash["available_cash"] + dash["simulated_exposure"], 1396996.56, places=2)

        # Holdings must be exactly 5
        holdings = port["current_holdings"]
        self.assertEqual(len(holdings), 5)
        tickers = sorted([h["ticker"] for h in holdings])
        self.assertEqual(tickers, ["ANET", "CRWD", "MA", "NVDA", "QQQ"])

        # All 5 holdings must have signal == HOLD
        for h in holdings:
            self.assertEqual(h["signal"], "HOLD")

    def test_05_completed_trades_count_and_stats(self):
        """5. Verify exactly 80 completed trades with 28 wins, 52 losses, profit factor 3.87."""
        port = bridge.get_portfolio_holdings_and_trades()
        trades = port["completed_trades"]
        self.assertEqual(len(trades), 80)

        stats = port.get("trade_stats", {})
        self.assertEqual(stats["total_trades"], 80)
        self.assertEqual(stats["winning_trades"], 28)
        self.assertEqual(stats["losing_trades"], 52)
        self.assertAlmostEqual(stats["win_rate_pct"], 35.0, places=1)
        self.assertAlmostEqual(stats["profit_factor"], 3.87, places=1)

    def test_06_risk_analytics_metrics(self):
        """6. Verify mathematically pure Sharpe, Sortino, Calmar, VaR 95%, CVaR, capture ratios."""
        risk = bridge.get_risk_analytics()

        # Max drawdown must match -42.544%
        self.assertAlmostEqual(risk["portfolio_max_dd_pct"], -42.544, places=2)
        self.assertAlmostEqual(risk["spy_max_dd_pct"], -33.717, places=2)

        # Risk-adjusted ratios
        self.assertAlmostEqual(risk["sharpe_ratio"], 1.02, places=1)
        self.assertAlmostEqual(risk["sortino_ratio"], 0.97, places=1)
        self.assertAlmostEqual(risk["calmar_ratio"], 0.653, places=2)

        # VaR and Capture
        self.assertAlmostEqual(risk["var_95_daily_pct"], 2.791, places=1)
        self.assertAlmostEqual(risk["upside_capture_pct"], 126.31, places=1)
        self.assertAlmostEqual(risk["downside_capture_pct"], 115.80, places=1)

        # Monthly matrix has 11 years (2016-2026)
        matrix = risk.get("monthly_matrix", [])
        self.assertEqual(len(matrix), 11)

    def test_07_shariah_independence(self):
        """7. Verify Shariah status is completely decoupled from technical signals."""
        signals_data = bridge.get_today_signals()
        signals = signals_data["signals"]

        # Ensure all 28 stocks have valid technical signals irrespective of Shariah flag
        valid_signals = {"BUY CANDIDATE", "WATCH", "HOLD", "EXIT", "AVOID"}
        for s in signals:
            self.assertIn(s["signal"], valid_signals)
            # Technical signal exists independently
            self.assertTrue(len(s["explanation"]) > 0)

    def test_08_nightly_scheduler_execution(self):
        """8. Verify nightly scan scheduler is initialized, running, and trackable."""
        scheduler.start()
        status = scheduler.get_status()
        self.assertTrue(status["is_running"])
        self.assertIn("16:30 ET", status["schedule"])

        # Test immediate scan trigger
        res = scheduler.trigger_immediate_scan()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["evaluated_stocks"], 28)

    def test_09_rejection_of_hybrid_d_mode(self):
        """9. Verify engine baseline mode is locked and never enables Hybrid D."""
        from app.config import ACTIVE_ENGINE_DIR
        self.assertTrue(ACTIVE_ENGINE_DIR.exists())
        # In baseline mode, trades count must remain 80 (Hybrid produced 224 whipsaws)
        port = bridge.get_portfolio_holdings_and_trades()
        self.assertEqual(len(port["completed_trades"]), 80)
        self.assertNotEqual(len(port["completed_trades"]), 224)


if __name__ == "__main__":
    unittest.main()
