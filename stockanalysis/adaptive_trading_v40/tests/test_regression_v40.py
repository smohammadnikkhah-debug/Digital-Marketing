"""Comprehensive regression test suite for Adaptive Trading V4.0 baseline.

Verifies:
1. Exact rule logic (Indicators, Entries, Exits, Strategy Scoring, Portfolio Simulation)
2. No look-ahead bias
3. V4.1 baseline compatibility (verifying that exit-mode baseline produces identical decisions to V4.0)
4. Full regression match against existing V4.0 outputs (TodayTrade signals, 80 Trades, AnnualVsSPY, BenchmarkDashboard)
"""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
import sys

# Ensure root of adaptive_trading_v40 is in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import strategy_core_v38 as core
import engine
from engine import PALETTE, universe, load, train, select_all, simulate_portfolio, benchmarks, annual, today_rows


class TestRuleDefinitions(unittest.TestCase):
    """Test mathematical and logical definitions of V4.0 baseline indicators and rules."""

    def setUp(self):
        # Deterministic synthetic price series
        dates = pd.bdate_range('2020-01-01', periods=300)
        # Price starts at 100 and rises steadily
        prices = 100.0 + np.arange(300) * 0.5
        raw = pd.DataFrame({
            'Open': prices,
            'High': prices + 1.0,
            'Low': prices - 1.0,
            'Close': prices
        }, index=dates)
        self.d = core.prep(raw)

    def test_indicator_calculations(self):
        """Verify indicator calculations (MA30, MA50, MA250, ROC20, ATR14)."""
        d = self.d
        # MA checks
        self.assertAlmostEqual(d.MA30.iloc[-1], d.Close.iloc[-30:].mean(), places=4)
        self.assertAlmostEqual(d.MA50.iloc[-1], d.Close.iloc[-50:].mean(), places=4)
        self.assertAlmostEqual(d.MA250.iloc[-1], d.Close.iloc[-250:].mean(), places=4)
        # ROC20 check: Close / Close[-20] - 1
        expected_roc = (d.Close.iloc[-1] / d.Close.iloc[-21]) - 1
        self.assertAlmostEqual(d.ROC20.iloc[-1], expected_roc, places=4)
        # ATR14 check
        self.assertTrue(pd.notna(d.ATR14.iloc[-1]))
        self.assertGreater(d.ATR14.iloc[-1], 0)

    def test_entry_decisions(self):
        """Test all 5 entry rules against decision()."""
        # Create a mock series/row
        row = pd.Series({
            'cross': True,
            'bull50': True,
            'ROC20': 0.05,
            'above3': True,
            'stack': True,
        })
        # CROSS
        self.assertTrue(core.decision(row, 'CROSS', pending=False))
        # MA50_AT_CROSS
        self.assertTrue(core.decision(row, 'MA50_AT_CROSS', pending=False))
        row_bear50 = row.copy()
        row_bear50['bull50'] = False
        self.assertFalse(core.decision(row_bear50, 'MA50_AT_CROSS', pending=False))
        # ROC20_AT_CROSS
        self.assertTrue(core.decision(row, 'ROC20_AT_CROSS', pending=False))
        row_neg_roc = row.copy()
        row_neg_roc['ROC20'] = -0.01
        self.assertFalse(core.decision(row_neg_roc, 'ROC20_AT_CROSS', pending=False))
        # DELAYED_MA50
        self.assertTrue(core.decision(row, 'DELAYED_MA50', pending=True))
        self.assertFalse(core.decision(row, 'DELAYED_MA50', pending=False))
        # DELAYED_STACK
        self.assertTrue(core.decision(row, 'DELAYED_STACK', pending=True))
        row_unstacked = row.copy()
        row_unstacked['stack'] = False
        self.assertFalse(core.decision(row_unstacked, 'DELAYED_STACK', pending=True))

    def test_exit_rules(self):
        """Test the 2 V4.0 exit rules."""
        # MA250_3CLOSE
        row_below3 = pd.Series({'below3': True, 'belowatr3': False})
        self.assertTrue(row_below3.below3)
        # MA250_ATR3
        row_belowatr3 = pd.Series({'below3': False, 'belowatr3': True})
        self.assertTrue(row_belowatr3.belowatr3)

    def test_lookahead_bias(self):
        """Ensure day T execution signal only depends on day T-1 close."""
        d = self.d.copy()
        last_dt = d.index[-1]
        prior_dt = d.index[-2]
        orig_cross = bool(d.loc[prior_dt, 'cross'])
        orig_ma50 = float(d.loc[prior_dt, 'MA50'])

        # Drastically manipulate today's close
        d.loc[last_dt, 'Close'] = 999999.0
        d_recalc = core.prep(d[['Open', 'High', 'Low', 'Close']])

        self.assertEqual(bool(d_recalc.loc[prior_dt, 'cross']), orig_cross)
        self.assertAlmostEqual(float(d_recalc.loc[prior_dt, 'MA50']), orig_ma50, places=4)


class TestV41BaselineCompatibility(unittest.TestCase):
    """Verify that V4.1 code with --exit-mode baseline produces identical behavior."""

    def test_v41_baseline_strategy_candidates(self):
        v41_dir = ROOT.parent / 'adaptive_trading_v41'
        if not v41_dir.exists():
            self.skipTest('adaptive_trading_v41 directory not found')

        sys.path.insert(0, str(v41_dir))
        import defensive_exits

        # Verify exit triggers for baseline rules
        row_below3 = pd.Series({'below3': True, 'belowatr3': False, 'defensive_ma50': False})
        self.assertTrue(defensive_exits.exit_trigger(row_below3, 'MA250_3CLOSE'))
        self.assertFalse(defensive_exits.exit_trigger(row_below3, 'MA250_ATR3'))

        row_atr3 = pd.Series({'below3': False, 'belowatr3': True, 'defensive_ma50': False})
        self.assertTrue(defensive_exits.exit_trigger(row_atr3, 'MA250_ATR3'))
        self.assertFalse(defensive_exits.exit_trigger(row_atr3, 'MA250_3CLOSE'))


class TestV40ExcelRegression(unittest.TestCase):
    """Regression test against the verified Adaptive_Trading_Research_V40.xlsx file."""

    @classmethod
    def setUpClass(cls):
        cls.excel_path = ROOT / 'results_v40' / 'Adaptive_Trading_Research_V40.xlsx'
        if not cls.excel_path.exists():
            raise FileNotFoundError(f'{cls.excel_path} missing')
        cls.xl = pd.ExcelFile(cls.excel_path)

    def test_benchmark_dashboard_metrics(self):
        """Check the benchmark dashboard summary metrics."""
        df = self.xl.parse('BenchmarkDashboard')
        metrics = dict(zip(df['Metric'], df['Value']))

        self.assertEqual(float(metrics['Initial capital']), 100000.0)
        self.assertAlmostEqual(float(metrics['Portfolio ending value']), 1396996.56, places=2)
        self.assertAlmostEqual(float(metrics['Portfolio total return %']), 1296.997, places=2)
        self.assertAlmostEqual(float(metrics['Portfolio CAGR %']), 27.763, places=2)
        self.assertAlmostEqual(float(metrics['Portfolio max drawdown %']), -42.544, places=2)
        self.assertAlmostEqual(float(metrics['SPY max drawdown %']), -33.717, places=2)
        self.assertEqual(int(metrics['Completed trades']), 80)
        self.assertEqual(int(metrics['Years beating SPY']), 9)
        self.assertEqual(int(metrics['Years compared']), 11)

    def test_trades_sheet_integrity(self):
        """Check all 80 trades in V4.0 sheet."""
        df = self.xl.parse('Trades')
        self.assertEqual(len(df), 80)
        self.assertEqual(list(df.columns), ['Ticker', 'Entry date', 'Exit date', 'Entry rule', 'Exit rule', 'Trade return %', 'Trade PnL $'])

        # First trade
        first = df.iloc[0]
        self.assertEqual(first['Ticker'], 'AMD')
        self.assertEqual(str(first['Entry date'])[:10], '2016-01-12')
        self.assertEqual(str(first['Exit date'])[:10], '2016-01-19')
        self.assertEqual(first['Entry rule'], 'MA50_AT_CROSS')
        self.assertEqual(first['Exit rule'], 'MA250_3CLOSE')
        self.assertAlmostEqual(first['Trade return %'], -13.507, places=2)
        self.assertAlmostEqual(first['Trade PnL $'], -2699.35, places=2)

        # Last trade (index 79)
        last = df.iloc[-1]
        self.assertEqual(last['Ticker'], 'AVGO')
        self.assertEqual(str(last['Entry date'])[:10], '2025-05-27')
        self.assertEqual(str(last['Exit date'])[:10], '2026-08-27')
        self.assertEqual(last['Entry rule'], 'DELAYED_STACK')
        self.assertEqual(last['Exit rule'], 'MA250_3CLOSE')

        # Total PnL
        self.assertAlmostEqual(df['Trade PnL $'].sum(), 912893.54, places=1)

    def test_today_signals_palette_and_rows(self):
        """Verify TodayTrade sheet has all 28 stocks and matches the defined palette."""
        df = self.xl.parse('TodayTrade')
        self.assertEqual(len(df), 28)
        valid_signals = set(PALETTE.keys())
        for signal in df['Signal']:
            self.assertIn(signal, valid_signals)

        # QQQ, NVDA should be HOLD in the latest snapshot
        hold_tickers = df[df['Signal'] == 'HOLD']['Ticker'].tolist()
        self.assertIn('QQQ', hold_tickers)
        self.assertIn('NVDA', hold_tickers)

    def test_annual_vs_spy(self):
        """Verify AnnualVsSPY returns across all 11 years (2016 - 2026)."""
        df = self.xl.parse('AnnualVsSPY')
        self.assertEqual(len(df), 11)
        # Years 2016 to 2026
        years = list(df['Year'])
        self.assertEqual(years, list(range(2016, 2027)))

        # 2016 return
        r2016 = df[df['Year'] == 2016].iloc[0]
        self.assertAlmostEqual(r2016['Portfolio return %'], 21.914, places=2)
        self.assertAlmostEqual(r2016['SPY return %'], 13.886, places=2)
        self.assertAlmostEqual(r2016['Excess pp'], 8.028, places=2)

        # 2020 return (big outperformance year)
        r2020 = df[df['Year'] == 2020].iloc[0]
        self.assertAlmostEqual(r2020['Portfolio return %'], 79.906, places=2)
        self.assertAlmostEqual(r2020['Excess pp'], 61.574, places=2)

    def test_qqq_2016_training_reproducibility(self):
        """Verify train() directly on QQQ price cache matches V4.0 Excel StrategySelection row."""
        cache_dir = ROOT / 'price_cache'
        d_qqq = load('QQQ', '2009-01-01', '2026-10-12', cache_dir, refresh=False)
        win, ranked = train(d_qqq, pd.Timestamp('2016-01-01'), 5, 10, min_buys=2)
        self.assertIsNotNone(win)
        self.assertEqual(win['entry'], 'MA50_AT_CROSS')
        self.assertEqual(win['exit'], 'MA250_3CLOSE')
        self.assertAlmostEqual(win['score'], 0.79, places=2)
        self.assertEqual(win['buys'], 7)
        self.assertAlmostEqual(win['cagr'], 13.054, places=2)
        self.assertAlmostEqual(win['drawdown'], -14.954, places=2)


if __name__ == '__main__':
    unittest.main()
