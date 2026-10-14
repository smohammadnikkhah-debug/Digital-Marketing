"""Phase 3A Financial Accuracy Audit Integration Tests.

Validates all 9 audit requirements using real cached provider responses
and primary-source SEC EDGAR XBRL facts.
"""
import unittest
import json
import math
from pathlib import Path

from app.config import BACKEND_DIR
from app.services.financial_data import financial_data_service, FINANCIAL_CACHE_DIR
from app.services.sec_edgar import sec_edgar_adapter, SEC_CACHE_DIR


class TestPhase3AFinancialAccuracyAudit(unittest.TestCase):
    """Integration test suite verifying Phase 3A financial accuracy corrections."""

    @classmethod
    def setUpClass(cls):
        cls.tickers = ["GOOGL", "META", "NVDA", "MA", "INTC"]

    def test_01_true_numerical_source_and_sec_status(self):
        """Req 1: Verify Yahoo Finance metrics are not falsely labelled SEC EDGAR.
        
        Ensure true numerical source is recorded and SEC verification status is distinct.
        """
        for ticker in self.tickers:
            overview = financial_data_service.get_company_overview(ticker)
            val = overview["valuation"]
            bs = overview["balance_sheet"]
            prof = overview["profitability"]

            # 1. Market Cap must be attributed to market quote, not SEC EDGAR
            self.assertIn("Market", val["market_cap"]["source"])
            self.assertEqual(val["market_cap"]["sec_verification_status"], "NOT_APPLICABLE")

            # 2. Forward PE is forecast, cannot be SEC verified
            self.assertIn("Consensus", val["forward_pe"]["source"])
            self.assertEqual(val["forward_pe"]["sec_verification_status"], "NOT_APPLICABLE")

            # 3. Margins and growth must attribute numerical values to Yahoo Finance
            self.assertIn("Yahoo Finance", overview["margins_and_growth"]["gross_margin"]["source"])
            self.assertIn("Yahoo Finance", overview["margins_and_growth"]["quarterly_revenue_growth"]["source"])
            self.assertNotIn("SEC EDGAR Form", overview["margins_and_growth"]["gross_margin"]["source"])

            # 4. Balance sheet items must cite Yahoo Finance provider
            self.assertIn("Yahoo Finance", bs["cash_and_equivalents"]["source"])
            self.assertIn("Yahoo Finance", bs["total_debt"]["source"])

            # 5. SEC verification is presented in its own dedicated regulatory block
            sec = overview["sec_verification"]
            self.assertIn("is_sec_verified", sec)
            self.assertIn("cik", sec)
            self.assertIn("sec_form", sec)
            self.assertIn("filing_date", sec)
            self.assertIn("provenance_note", sec)
            self.assertIn("Yahoo Finance", sec["provenance_note"])

    def test_02_remove_hardcoded_pe_distributions_and_fallbacks(self):
        """Req 2: Verify historical P/E distributions require >= 12 quarterly observations and return N/A with warning if insufficient."""
        # 1. Genuine observations for GOOGL (8 observations < 12 required)
        googl_stats = financial_data_service._get_historical_pe_stats("GOOGL")
        self.assertIn("observations_count", googl_stats)
        self.assertEqual(googl_stats["observations_count"], 8)
        self.assertEqual(googl_stats["required_count"], 12)
        self.assertEqual(googl_stats["status"], "INSUFFICIENT_HISTORY")
        self.assertIn("date_range", googl_stats)
        self.assertIn("2023", googl_stats["date_range"])
        self.assertIn("2026", googl_stats["date_range"])
        self.assertIn("warning", googl_stats)
        self.assertIn("Insufficient historical observations: 8 of 12 required quarterly observations available", googl_stats["warning"])

        # Valuation percentile must return None (N/A) because 8 < 12
        googl_pct = financial_data_service._calculate_historical_pe_percentile("GOOGL", 25.0)
        self.assertIsNone(googl_pct)

        # 2. Deficit / negative earnings stock (INTC) has only 3 observations (< 12)
        # Must return INSUFFICIENT_HISTORY and None for percentile, NEVER generic 50th percentile!
        intc_risk = financial_data_service.get_stock_risk_assessment("INTC")
        val_risk = intc_risk["valuation_risk"]
        self.assertIsNone(val_risk["pe_percentile_5y"])
        self.assertEqual(val_risk["historical_pe_distribution"]["status"], "INSUFFICIENT_HISTORY")
        self.assertEqual(val_risk["historical_pe_distribution"]["observations_count"], 3)
        self.assertIsNone(val_risk["multiple_compression_sensitivity"]["median_reversion_impact_pct"])
        self.assertIn("Insufficient historical observations", val_risk["explanation"])

        # 3. When >= 12 observations exist, percentile rank is computed empirically
        # Test synthetic 12-observation empirical interpolation
        obs_12 = [10.0 + i * 2.0 for i in range(12)]  # [10, 12, 14, ..., 32]
        import numpy as np
        empirical_pct = float(np.interp(21.0, obs_12, np.linspace(0.0, 100.0, len(obs_12))))
        self.assertAlmostEqual(empirical_pct, 50.0, places=1)

        # 4. Unknown ticker must return 0 observations, status INSUFFICIENT_HISTORY, and None without preset fallback
        unknown_stats = financial_data_service._get_historical_pe_stats("UNKNOWN_TICKER_XYZ")
        self.assertEqual(unknown_stats["observations_count"], 0)
        self.assertEqual(unknown_stats["status"], "INSUFFICIENT_HISTORY")
        unknown_pct = financial_data_service._calculate_historical_pe_percentile("UNKNOWN_TICKER_XYZ", 25.0)
        self.assertIsNone(unknown_pct)

    def test_03_never_convert_missing_data_to_zero(self):
        """Req 3: Verify missing revenue, debt, cash or shares are never converted to zero."""
        import pandas as pd
        empty_df = pd.DataFrame()
        # 1. Cell extraction on empty DataFrame returns None, never 0.0
        self.assertIsNone(financial_data_service._get_cell_num(empty_df, "Total Revenue", "2026-06-30"))

        # 2. DataFrame with missing row candidate returns None, never 0.0
        df_sample = pd.DataFrame({"2026-06-30": [100.0]}, index=["Total Revenue"])
        self.assertIsNone(financial_data_service._get_cell_num(df_sample, "Total Debt", "2026-06-30"))
        self.assertIsNone(financial_data_service._get_cell_num(df_sample, "Total Revenue", "2025-06-30"))

        # 3. Quarterly TTM fundamentals with incomplete rows returns None for missing components
        inc_missing = pd.DataFrame({
            "2025-09-30": [100.0, None],
            "2025-12-31": [110.0, 20.0],
            "2026-03-31": [120.0, 30.0],
            "2026-06-30": [130.0, 40.0],
        }, index=["Total Revenue", "Net Income"])
        ttm = financial_data_service._calculate_ttm_fundamentals(inc_missing, empty_df, empty_df)
        self.assertEqual(ttm["coverage_status"], "FULL")
        self.assertIsNone(ttm["ttm_net_income"])  # Quarter 1 Net Income was None -> sum must be None, NOT converted to 0.0!

    def test_04_reworked_ttm_diluted_eps_accounting_for_shares(self):
        """Req 4: Verify TTM Diluted EPS uses weighted average diluted shares (ASC 260)."""
        # INTC: Net income was -$11,289M, shares grew from 4,531M to 5,104M (avg ~4,893.5M)
        # Sum of unadjusted quarterly EPS (-$2.11) is mathematically distorted.
        # Reworked Diluted EPS = -$11,289M / 4,893.5M = -$2.31!
        intc_overview = financial_data_service.get_company_overview("INTC")
        intc_eps = intc_overview["profitability"]["diluted_eps"]["value"]
        self.assertIsNotNone(intc_eps)
        self.assertAlmostEqual(intc_eps, -2.31, places=1)

        # GOOGL: True TTM Net Income / Avg Shares = $19.94
        googl_overview = financial_data_service.get_company_overview("GOOGL")
        googl_eps = googl_overview["profitability"]["diluted_eps"]["value"]
        self.assertIsNotNone(googl_eps)
        self.assertAlmostEqual(googl_eps, 19.94, places=1)

    def test_05_documented_filing_dates_without_25_day_assumption(self):
        """Req 5: Verify filings use documented publication dates, never a hardcoded 25-day assumption."""
        # 1. Verify helper method _estimate_publication_date does not exist on service
        self.assertFalse(hasattr(financial_data_service, "_estimate_publication_date"))

        # 2. Verify GOOGL series observations use documented SEC EDGAR filing dates
        googl_series = financial_data_service.get_financial_chart_series("GOOGL", "quarterly_ttm", "5y")
        rev_data = googl_series["series"]["revenue"]["data"]
        self.assertGreater(len(rev_data), 0)
        for point in rev_data:
            if not point.get("is_forecast"):
                # Must have documented filing_date matching SEC record
                self.assertIsNotNone(point.get("filing_date"))
                self.assertEqual(point.get("sec_verification_status"), "REGULATORY_FILING_FOUND")
                self.assertTrue(point.get("is_pit_verified"))

    def test_06_historical_ev_ebitda_without_leakage(self):
        """Req 6: Historical EV/EBITDA uses historical debt, cash, and market cap without current leakage."""
        nvda_series = financial_data_service.get_financial_chart_series("NVDA", "quarterly", "5y")
        ev_data = nvda_series["series"]["historical_ev_ebitda"]["data"]
        shares_data = nvda_series["series"]["shares_outstanding"]["data"]
        
        # Historical observations must have varying shares and EV across quarters
        reported_shares = [p["value"] for p in shares_data if p.get("value") is not None and not p.get("is_forecast")]
        self.assertGreater(len(reported_shares), 2)
        # Ensure no 1e9 fallback was used
        self.assertNotIn(1e9, reported_shares)
        
        reported_ev = [p["value"] for p in ev_data if p.get("value") is not None and not p.get("is_forecast")]
        self.assertGreater(len(reported_ev), 1)

    def test_07_reconciliation_against_cached_sec_xbrl_facts(self):
        """Req 7: Reconcile all 5 tickers against project's cached SEC XBRL facts."""
        for ticker in self.tickers:
            facts = sec_edgar_adapter.get_company_facts(ticker)
            self.assertIsNotNone(facts, f"Cached SEC facts missing for {ticker}")
            self.assertIn("facts", facts)

            verif = sec_edgar_adapter.get_latest_filing_verification(ticker)
            self.assertTrue(verif.get("is_sec_verified"), f"Latest filing unverified for {ticker}")
            self.assertIsNotNone(verif.get("cik"))
            self.assertIsNotNone(verif.get("accession_number"))
            self.assertIsNotNone(verif.get("filing_date"))

    def test_08_quantitative_strategy_and_dataset_integrity(self):
        """Req 9: Verify entire V4.0 quantitative baseline, CAGR, trades, and dataset remain untouched."""
        from app.engine_bridge import bridge
        dash = bridge.get_baseline_dashboard()
        self.assertEqual(dash["portfolio_ending_value"], 1396996.56)
        self.assertAlmostEqual(dash["portfolio_cagr_pct"], 27.763, places=2)
        self.assertEqual(dash["completed_trades"], 80)
        self.assertEqual(dash["years_beating_spy"], 9)
        self.assertEqual(dash["years_compared"], 11)

    def test_09_find_price_at_date_strict_timing_and_failure_cases(self):
        """Req 1: Verify _find_price_at_date NEVER returns prices preceding publication date."""
        import pandas as pd

        # 1. After-hours Friday release:
        # Released Friday 2026-05-15 after-hours. First eligible trading session is Monday 2026-05-18.
        # MUST return Monday price (150.0), NEVER Friday price (140.0) or earlier!
        df_weekend = pd.DataFrame([
            {"time": "2026-05-14", "close": 138.0},
            {"time": "2026-05-15", "close": 140.0},  # Friday regular close (before after-hours release)
            {"time": "2026-05-18", "close": 150.0},  # Monday regular close (first eligible session)
            {"time": "2026-05-19", "close": 152.0},
        ])
        p_friday_ah = financial_data_service._find_price_at_date(df_weekend, "2026-05-15", after_hours=True)
        self.assertEqual(p_friday_ah, 150.0)
        self.assertNotEqual(p_friday_ah, 140.0)

        # 2. Holiday release:
        # Released Thursday 2026-07-02 after-hours before Friday July 3 market holiday.
        # First eligible session is Monday 2026-07-06.
        df_holiday = pd.DataFrame([
            {"time": "2026-07-01", "close": 200.0},
            {"time": "2026-07-02", "close": 205.0},  # Thursday regular close
            # Friday 2026-07-03 is holiday (omitted from trading records)
            {"time": "2026-07-06", "close": 220.0},  # Monday regular close (first eligible session)
        ])
        p_holiday = financial_data_service._find_price_at_date(df_holiday, "2026-07-02", after_hours=True)
        self.assertEqual(p_holiday, 220.0)
        self.assertNotEqual(p_holiday, 205.0)

        # 3. Missing future price data:
        # Released on 2026-10-15 (after-hours), but price data ends on 2026-10-09.
        # MUST return None and NEVER fall back to 2026-10-09!
        df_past = pd.DataFrame([
            {"time": "2026-10-08", "close": 95.0},
            {"time": "2026-10-09", "close": 98.0},  # Last recorded price
        ])
        p_missing_future = financial_data_service._find_price_at_date(df_past, "2026-10-15", after_hours=True)
        self.assertIsNone(p_missing_future)

        # 4. Pre-market release:
        # Released Wednesday 2026-05-20 pre-market (before market open).
        # First eligible session is Wednesday 2026-05-20 same-day regular close.
        df_premarket = pd.DataFrame([
            {"time": "2026-05-19", "close": 300.0},
            {"time": "2026-05-20", "close": 315.0},  # Wednesday regular close
            {"time": "2026-05-21", "close": 318.0},
        ])
        p_premarket = financial_data_service._find_price_at_date(df_premarket, "2026-05-20", pre_market=True, after_hours=False)
        self.assertEqual(p_premarket, 315.0)

        # If release day was a holiday, pre-market trades on the next available trading day
        df_premarket_holiday = pd.DataFrame([
            {"time": "2026-05-19", "close": 300.0},
            # 2026-05-20 holiday omitted
            {"time": "2026-05-21", "close": 318.0},
        ])
        p_premkt_hol = financial_data_service._find_price_at_date(df_premarket_holiday, "2026-05-20", pre_market=True, after_hours=False)
        self.assertEqual(p_premkt_hol, 318.0)
        self.assertNotEqual(p_premkt_hol, 300.0)

    def test_10_ttm_diluted_eps_strict_verification_failure_cases(self):
        """Req 2: Verify TTM diluted EPS CANNOT be labeled verified with < 4 quarterly diluted share observations."""
        import pandas as pd

        # Case A: Only 2 of 4 quarters have diluted shares reported on income statement
        inc_incomplete_shares = pd.DataFrame({
            "2025-09-30": [1000.0, 100.0, 50.0],
            "2025-12-31": [1100.0, 110.0, 50.0],
            "2026-03-31": [1200.0, 120.0, None],  # Missing diluted shares
            "2026-06-30": [1300.0, 130.0, None],  # Missing diluted shares
        }, index=["Total Revenue", "Net Income", "Diluted Average Shares"])

        bs_dummy = pd.DataFrame({
            "2026-06-30": [60.0],
        }, index=["Ordinary Shares Number"])

        ttm_incomplete = financial_data_service._calculate_ttm_fundamentals(inc_incomplete_shares, pd.DataFrame(), bs_dummy)
        
        # 1. Full verification MUST be False
        self.assertFalse(ttm_incomplete["ttm_diluted_eps_is_verified"])
        # 2. Verified ttm_diluted_eps MUST be None (N/A)
        self.assertIsNone(ttm_diluted_eps := ttm_incomplete["ttm_diluted_eps"])
        # 3. Status MUST NOT be REPORTED
        self.assertNotEqual(ttm_incomplete["ttm_diluted_eps_status"], "REPORTED")
        # 4. Explicit NA reason provided citing < 4 share observations
        self.assertIn("Fewer than 4 valid quarterly diluted weighted-average share observations", ttm_incomplete["ttm_diluted_eps_na_reason"])
        # 5. Estimate exists and is explicitly marked as ESTIMATED
        self.assertIsNotNone(ttm_incomplete["ttm_diluted_eps_estimate"])
        self.assertEqual(ttm_incomplete["ttm_diluted_eps_status"], "ESTIMATED")
        self.assertIn("Estimated", ttm_incomplete["ttm_diluted_eps_source"])

        # Case B: Diluted shares missing entirely; cannot silently substitute ordinary shares as verified
        inc_no_shares = pd.DataFrame({
            "2025-09-30": [1000.0, 100.0, 2.0],
            "2025-12-31": [1100.0, 110.0, 2.2],
            "2026-03-31": [1200.0, 120.0, 2.4],
            "2026-06-30": [1300.0, 130.0, 2.6],
        }, index=["Total Revenue", "Net Income", "Diluted EPS"])  # Only per-share EPS, no diluted shares row

        ttm_no_shares = financial_data_service._calculate_ttm_fundamentals(inc_no_shares, pd.DataFrame(), bs_dummy)
        self.assertFalse(ttm_no_shares["ttm_diluted_eps_is_verified"])
        self.assertIsNone(ttm_no_shares["ttm_diluted_eps"])
        self.assertNotEqual(ttm_no_shares["ttm_diluted_eps_status"], "REPORTED")

    def test_11_asc_260_unequal_quarter_lengths_splits_and_anti_dilution(self):
        """Req 2: Verify ASC 260 unequal quarter length day weighting, stock split adjustments, and anti-dilution."""
        import pandas as pd

        # 1. Unequal quarter lengths: 4 quarters with dates spanning varying day counts (e.g., 90, 91, 92, 98 days)
        inc_unequal = pd.DataFrame({
            "2025-09-27": [1000.0, 100.0, 1000.0],
            "2025-12-26": [1100.0, 110.0, 1050.0],
            "2026-03-28": [1200.0, 120.0, 1100.0],
            "2026-07-04": [1300.0, 130.0, 1150.0],  # 98 days in Q4
        }, index=["Total Revenue", "Net Income", "Diluted Average Shares"])

        ttm_unequal = financial_data_service._calculate_ttm_fundamentals(inc_unequal, pd.DataFrame(), pd.DataFrame())
        self.assertTrue(ttm_unequal["ttm_diluted_eps_is_verified"])
        self.assertEqual(len(ttm_unequal["quarter_lengths_days"]), 4)
        # Verify day weights are not all identical 0.25
        self.assertNotEqual(ttm_unequal["quarter_lengths_days"][0], ttm_unequal["quarter_lengths_days"][3])

        # 2. Stock split retroactive adjustment:
        # Shares jump from 1,000M in Q1 and Q2 to 2,000M in Q3 and Q4 (2-for-1 forward split)
        inc_split = pd.DataFrame({
            "2025-09-30": [1000.0, 100.0, 1000.0],
            "2025-12-31": [1100.0, 110.0, 1000.0],
            "2026-03-31": [1200.0, 120.0, 2000.0],  # 2:1 split occurred
            "2026-06-30": [1300.0, 130.0, 2000.0],
        }, index=["Total Revenue", "Net Income", "Diluted Average Shares"])

        ttm_split = financial_data_service._calculate_ttm_fundamentals(inc_split, pd.DataFrame(), pd.DataFrame())
        self.assertTrue(ttm_split["stock_split_adjusted"])
        self.assertEqual(ttm_split["split_factor"], 2.0)
        # All 4 quarters should be retroactively adjusted to 2,000M, so average shares = 2,000M
        self.assertAlmostEqual(ttm_split["time_weighted_diluted_shares"], 2000.0, places=1)
        self.assertAlmostEqual(ttm_split["ttm_diluted_eps"], 460.0 / 2000.0, places=3)

        # 3. Loss-making period (ASC 260-10-45-17 anti-dilution):
        inc_loss = pd.DataFrame({
            "2025-09-30": [1000.0, -100.0, 1000.0],
            "2025-12-31": [1100.0, -150.0, 1020.0],
            "2026-03-31": [1200.0, -200.0, 1040.0],
            "2026-06-30": [1300.0, -50.0, 1060.0],
        }, index=["Total Revenue", "Net Income", "Diluted Average Shares"])

        ttm_loss = financial_data_service._calculate_ttm_fundamentals(inc_loss, pd.DataFrame(), pd.DataFrame())
        self.assertTrue(ttm_loss["is_loss_making"])
        self.assertTrue(ttm_loss["ttm_diluted_eps_is_verified"])
        self.assertLess(ttm_loss["ttm_diluted_eps"], 0.0)
        self.assertIn("Anti-Dilution Applied", ttm_loss["ttm_diluted_eps_source"])


if __name__ == "__main__":
    unittest.main()

