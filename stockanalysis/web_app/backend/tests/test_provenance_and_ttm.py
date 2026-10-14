"""Automated Tests for Financial Data Provenance, TTM Derivations, and Look-Ahead Bias Prevention.

Verifies:
1. TTM revenue, EPS, and cash flow are calculated from 4 distinct non-overlapping quarters.
2. TTM margins and ratios are recalculated from underlying financial figures (not averaged).
3. Insufficient historical coverage (< 4 quarters) is explicitly identified and never fabricated.
4. Every financial metric stores fiscal period end, filing date, source, currency, units, and status.
5. Historical P/E multiples eliminate look-ahead bias by using observation filing dates.
6. SEC EDGAR primary-source verification adapter resolves CIK and extracts official accession numbers.
7. V4.0 trading strategy and all regression metrics remain strictly preserved.
"""
import unittest
import pandas as pd
from datetime import datetime

from app.services.financial_data import financial_data_service
from app.services.sec_edgar import sec_edgar_adapter
from app.engine_bridge import bridge


class TestFinancialProvenanceAndTTM(unittest.TestCase):
    """Test suite verifying institutional data provenance and strict TTM calculation."""

    def test_01_ttm_revenue_exact_sum_of_four_distinct_quarters(self):
        """1. Verify TTM revenue is the exact sum of 4 distinct non-overlapping fiscal quarters."""
        q_dates = [
            pd.Timestamp("2024-09-30"),
            pd.Timestamp("2024-12-31"),
            pd.Timestamp("2025-03-31"),
            pd.Timestamp("2025-06-30"),
        ]
        inc_df = pd.DataFrame(
            {
                q_dates[0]: {"Total Revenue": 1000.0, "Operating Income": 200.0, "Net Income": 150.0, "Diluted EPS": 1.5, "Diluted Average Shares": 100.0},
                q_dates[1]: {"Total Revenue": 1200.0, "Operating Income": 240.0, "Net Income": 180.0, "Diluted EPS": 1.8, "Diluted Average Shares": 100.0},
                q_dates[2]: {"Total Revenue": 1100.0, "Operating Income": 220.0, "Net Income": 165.0, "Diluted EPS": 1.65, "Diluted Average Shares": 100.0},
                q_dates[3]: {"Total Revenue": 1300.0, "Operating Income": 260.0, "Net Income": 195.0, "Diluted EPS": 1.95, "Diluted Average Shares": 100.0},
            }
        )
        cf_df = pd.DataFrame(
            {
                q_dates[0]: {"Free Cash Flow": 250.0, "Stock Based Compensation": 30.0},
                q_dates[1]: {"Free Cash Flow": 300.0, "Stock Based Compensation": 35.0},
                q_dates[2]: {"Free Cash Flow": 280.0, "Stock Based Compensation": 32.0},
                q_dates[3]: {"Free Cash Flow": 320.0, "Stock Based Compensation": 40.0},
            }
        )
        bs_df = pd.DataFrame(
            {
                q_dates[3]: {"Ordinary Shares Number": 100.0, "Total Debt": 500.0, "Cash And Cash Equivalents": 800.0}
            }
        )

        res = financial_data_service._calculate_ttm_fundamentals(inc_df, cf_df, bs_df)

        self.assertEqual(res["coverage_status"], "FULL")
        self.assertEqual(res["quarters_counted"], 4)
        # Sum of revenues: 1000 + 1200 + 1100 + 1300 = 4600.0
        self.assertAlmostEqual(res["ttm_revenue"], 4600.0, places=2)
        # Sum of FCF: 250 + 300 + 280 + 320 = 1150.0
        self.assertAlmostEqual(res["ttm_fcf"], 1150.0, places=2)
        # Sum of Diluted EPS: 1.5 + 1.8 + 1.65 + 1.95 = 6.9
        self.assertAlmostEqual(res["ttm_diluted_eps"], 6.9, places=2)

    def test_02_ttm_margins_recalculated_from_underlying_financials(self):
        """2. Verify TTM operating and net margins are recalculated from totals, never averaged."""
        q_dates = [
            pd.Timestamp("2024-09-30"),
            pd.Timestamp("2024-12-31"),
            pd.Timestamp("2025-03-31"),
            pd.Timestamp("2025-06-30"),
        ]
        # Quarter margins: 10%, 30%, 15%, 25%
        # Simple arithmetic average: (10 + 30 + 15 + 25) / 4 = 20.0%
        # Underlying recalculation: OpInc sum = 100+600+150+500 = 1350. Rev sum = 1000+2000+1000+2000 = 6000.
        # True volume-weighted margin: 1350 / 6000 = 22.5%
        inc_df = pd.DataFrame(
            {
                q_dates[0]: {"Total Revenue": 1000.0, "Operating Income": 100.0, "Net Income": 80.0, "Diluted EPS": 0.8},
                q_dates[1]: {"Total Revenue": 2000.0, "Operating Income": 600.0, "Net Income": 450.0, "Diluted EPS": 4.5},
                q_dates[2]: {"Total Revenue": 1000.0, "Operating Income": 150.0, "Net Income": 110.0, "Diluted EPS": 1.1},
                q_dates[3]: {"Total Revenue": 2000.0, "Operating Income": 500.0, "Net Income": 380.0, "Diluted EPS": 3.8},
            }
        )

        res = financial_data_service._calculate_ttm_fundamentals(inc_df, pd.DataFrame(), pd.DataFrame())

        expected_margin = (1350.0 / 6000.0) * 100.0  # 22.5%
        flawed_average = (10.0 + 30.0 + 15.0 + 25.0) / 4.0  # 20.0%

        self.assertAlmostEqual(res["ttm_operating_margin"], expected_margin, places=4)
        self.assertNotAlmostEqual(res["ttm_operating_margin"], flawed_average, places=2)

    def test_03_insufficient_historical_coverage_never_fabricates(self):
        """3. Verify stocks with < 4 quarters are flagged INSUFFICIENT_COVERAGE without synthetic numbers."""
        # Only 2 quarters reported
        q_dates = [pd.Timestamp("2025-03-31"), pd.Timestamp("2025-06-30")]
        short_inc = pd.DataFrame(
            {
                q_dates[0]: {"Total Revenue": 500.0, "Operating Income": 50.0},
                q_dates[1]: {"Total Revenue": 600.0, "Operating Income": 60.0},
            }
        )

        res = financial_data_service._calculate_ttm_fundamentals(short_inc, pd.DataFrame(), pd.DataFrame())

        self.assertEqual(res["coverage_status"], "INSUFFICIENT_COVERAGE")
        self.assertEqual(res["quarters_counted"], 2)
        self.assertIn("4 required", res.get("reason", ""))
        self.assertNotIn("ttm_revenue", res)

    def test_04_every_financial_metric_has_complete_provenance(self):
        """4. Verify every metric contains fiscal_period_end, filing_date, source, currency, units, and status."""
        overview = financial_data_service.get_company_overview("GOOGL")

        for panel_name in ["valuation", "cash_flow", "margins_and_growth", "balance_sheet", "dividends", "profitability"]:
            panel = overview[panel_name]
            for metric_key, metric in panel.items():
                self.assertIn("period", metric, f"{panel_name}.{metric_key} missing 'period'")
                self.assertIn("currency", metric, f"{panel_name}.{metric_key} missing 'currency'")
                self.assertIn("units", metric, f"{panel_name}.{metric_key} missing 'units'")
                self.assertIn("source", metric, f"{panel_name}.{metric_key} missing 'source'")
                self.assertIn("as_of", metric, f"{panel_name}.{metric_key} missing 'as_of'")
                self.assertIn("status", metric, f"{panel_name}.{metric_key} missing 'status'")
                self.assertIn(metric["status"], ["REPORTED", "ESTIMATED", "UNAVAILABLE"])
                self.assertIn("coverage_status", metric)

    def test_05_historical_pe_eliminates_look_ahead_bias(self):
        """5. Verify historical P/E uses filing/publication observation dates to prevent look-ahead bias."""
        history = financial_data_service.get_financial_chart_series("GOOGL", frequency="quarterly_ttm", time_range="5y")
        pe_series = history["series"]["historical_pe"]["data"]

        self.assertGreater(len(pe_series), 0)
        for pt in pe_series:
            filing_date = pt.get("filing_date")
            period_end = pt.get("fiscal_period_end")
            if filing_date and period_end:
                # Publication/filing date must be strictly after or equal to period end date
                dt_filing = datetime.strptime(filing_date, "%Y-%m-%d")
                dt_end = datetime.strptime(period_end, "%Y-%m-%d")
                self.assertGreaterEqual(
                    dt_filing,
                    dt_end,
                    f"Filing date {filing_date} cannot precede period end {period_end} (look-ahead bias detected)",
                )

    def test_06_sec_edgar_primary_source_verification_adapter(self):
        """6. Verify SEC EDGAR adapter resolves CIK and extracts primary-source 10-K/10-Q filing citations."""
        cik = sec_edgar_adapter.get_cik("GOOGL")
        self.assertEqual(cik, "0001652044")

        verif = sec_edgar_adapter.get_latest_filing_verification("GOOGL")
        self.assertTrue(verif["is_sec_verified"])
        self.assertEqual(verif["cik"], "0001652044")
        self.assertIn("10-Q", verif.get("sec_form", "") or verif.get("source_citation", ""))
        self.assertIsNotNone(verif.get("filing_date"))
        self.assertIsNotNone(verif.get("accession_number"))

    def test_07_v40_trading_strategy_and_regressions_untouched(self):
        """7. Verify V4.0 quantitative baseline remains 100% frozen ($1,396,996.56 ending equity, 27.763% CAGR)."""
        dash = bridge.get_baseline_dashboard()
        self.assertAlmostEqual(dash["portfolio_ending_value"], 1396996.56, places=2)
        self.assertAlmostEqual(dash["portfolio_cagr_pct"], 27.763, places=2)
        self.assertAlmostEqual(dash["portfolio_max_drawdown_pct"], -42.544, places=2)
        self.assertEqual(dash["completed_trades"], 80)


if __name__ == "__main__":
    unittest.main()
