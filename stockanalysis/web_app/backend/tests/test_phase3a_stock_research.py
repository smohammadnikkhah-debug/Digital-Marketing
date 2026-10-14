"""Phase 3A Automated Acceptance Test Suite: Advanced Individual Stock Research.

Verifies:
1. Intelligent stock search: "Goo" returns Alphabet Inc. GOOGL and GOOG.
2. Fuzzy matching and typo tolerance ("Alpabet" -> Alphabet, "Google" -> GOOG/GOOGL).
3. Non-watchlist stock research capability (e.g. DIS).
4. Financial information panels: Valuation, Cash Flow, Margins, Balance Sheet, Dividends, Profitability.
5. Reporting period, currency, and documented source metadata.
6. Explicit N/A reasons for missing metrics (no fabricated data).
7. Global frequency filters: Quarterly, Quarterly TTM, Annually with rolling 4-quarter TTM derivation.
8. Historical P/E and EV/EBITDA multiples with period-appropriate financials and prices.
9. Transparent four-section risk assessment (Trend, Valuation, Financial, Market) with methodology and evidence.
10. Adding to watchlist does not mutate frozen baseline files.
"""
import unittest
from fastapi.testclient import TestClient
from pathlib import Path
import pandas as pd

from app.main import app
from app.config import BASELINE_EXCEL_PATH, V40_ENGINE_DIR
from app.services.security_master import search_symbols
from app.services.financial_data import financial_data_service


class TestPhase3AStockResearch(unittest.TestCase):
    """Phase 3A Acceptance Criteria Test Suite."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_search_goo_returns_alphabet_listings(self):
        """Acceptance Criteria 1: Searching 'Goo' returns appropriate Alphabet listings."""
        response = self.client.get("/api/research/search?q=Goo")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

        symbols = [item["symbol"] for item in data]
        self.assertTrue("GOOG" in symbols or "GOOGL" in symbols, f"Expected GOOG or GOOGL in {symbols}")

        goog_item = next(item for item in data if item["symbol"] in ("GOOG", "GOOGL"))
        self.assertIn("Alphabet", goog_item["name"])
        self.assertEqual(goog_item["currency"], "USD")
        self.assertIn("exchange", goog_item)

    def test_02_search_fuzzy_typo_and_alias_tolerance(self):
        """Fuzzy matching for typos ('Alpabet') and common aliases ('Google', 'Facebook')."""
        # Alias 'Google'
        res_alias = self.client.get("/api/research/search?q=Google")
        self.assertEqual(res_alias.status_code, 200)
        alias_symbols = [x["symbol"] for x in res_alias.json()]
        self.assertTrue("GOOGL" in alias_symbols or "GOOG" in alias_symbols)

        # Typo 'Alpabet'
        res_typo = self.client.get("/api/research/search?q=Alpabet")
        self.assertEqual(res_typo.status_code, 200)
        typo_symbols = [x["symbol"] for x in res_typo.json()]
        self.assertTrue("GOOGL" in typo_symbols or "GOOG" in typo_symbols)

        # Alias 'Facebook' -> META
        res_fb = self.client.get("/api/research/search?q=Facebook")
        self.assertEqual(res_fb.status_code, 200)
        fb_symbols = [x["symbol"] for x in res_fb.json()]
        self.assertIn("META", fb_symbols)

    def test_03_research_stock_outside_watchlist(self):
        """Acceptance Criteria 2: A stock outside the existing 28-stock watchlist can be researched."""
        # DIS is not in the baseline 28-stock universe
        response = self.client.get("/api/research/DIS/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["profile"]["symbol"], "DIS")
        self.assertIn("Disney", data["profile"]["name"])
        self.assertIn("valuation", data)
        self.assertIn("cash_flow", data)
        self.assertIn("margins_and_growth", data)
        self.assertIn("balance_sheet", data)
        self.assertIn("dividends", data)
        self.assertIn("profitability", data)

    def test_04_financial_panels_have_documented_source_and_period(self):
        """Acceptance Criteria 3: Financial metrics match documented source, period, and currency."""
        response = self.client.get("/api/research/GOOGL/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check Valuation Panel
        mkt_cap = data["valuation"]["market_cap"]
        self.assertIsNotNone(mkt_cap["formatted"])
        self.assertIn("USD", mkt_cap["currency"])
        self.assertIn("source", mkt_cap)
        self.assertIn("period", mkt_cap)

        # Check Cash Flow Panel
        fcf = data["cash_flow"]["free_cash_flow"]
        self.assertIsNotNone(fcf["formatted"])
        self.assertIn("period", fcf)
        self.assertIn("source", fcf)

        # Check Margins Panel
        op_margin = data["margins_and_growth"]["operating_margin"]
        self.assertIsNotNone(op_margin["formatted"])
        self.assertEqual(op_margin["currency"], "%")

    def test_05_missing_data_never_zero_or_fabricated(self):
        """Acceptance Criteria 7: Missing data displays explicit N/A with reason."""
        response = self.client.get("/api/research/GOOGL/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check fields that can have explicit N/A reasons
        pay_date = data["dividends"]["payment_date"]
        self.assertIsNotNone(pay_date["na_reason"])
        self.assertIn("N/A", pay_date["na_reason"])

    def test_06_frequency_filters_across_compatible_charts(self):
        """Acceptance Criteria 4: Quarterly, Quarterly TTM, and Annually filters work."""
        for freq in ["quarterly", "quarterly_ttm", "annually"]:
            res = self.client.get(f"/api/research/GOOGL/financial-history?frequency={freq}&range=5y")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["frequency"], freq)
            self.assertIn("revenue", data["series"])
            self.assertIn("eps", data["series"])
            self.assertIn("fcf", data["series"])
            self.assertIn("operating_margin", data["series"])
            self.assertIn("net_profit_margin", data["series"])
            self.assertIn("historical_pe", data["series"])
            self.assertIn("historical_ev_ebitda", data["series"])
            self.assertIn("shares_outstanding", data["series"])

            # Verify series has data points
            rev_pts = data["series"]["revenue"]["data"]
            self.assertGreater(len(rev_pts), 0)
            # Verify forecast flag distinction exists
            self.assertIn("is_forecast", rev_pts[0])

    def test_07_historical_pe_uses_period_appropriate_data(self):
        """Acceptance Criteria 5: Historical P/E uses period-appropriate earnings data."""
        res = self.client.get("/api/research/GOOGL/financial-history?frequency=annually&range=5y")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        pe_pts = data["series"]["historical_pe"]["data"]
        self.assertGreater(len(pe_pts), 0)
        for pt in pe_pts:
            if pt["value"] is not None:
                self.assertGreater(pt["value"], 5.0)
                self.assertLess(pt["value"], 150.0)

    def test_08_all_four_risk_sections_provide_traceable_calculations(self):
        """Acceptance Criteria 6: All four risk sections provide traceable calculations and methodology."""
        res = self.client.get("/api/research/GOOGL/risk")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        for section in ["trend_risk", "valuation_risk", "financial_risk", "market_risk"]:
            self.assertIn(section, data)
            sec = data[section]
            self.assertIn("methodology", sec)
            self.assertIn("evidence", sec)
            self.assertIn("data_date", sec)
            self.assertIn("explanation", sec)
            self.assertGreater(len(sec["methodology"]), 10)
            self.assertGreater(len(sec["evidence"]), 10)

        # Trend risk V4.0 rule
        self.assertIn(data["trend_risk"]["technical_signal"], ["BUY CANDIDATE", "WATCH", "HOLD", "EXIT", "AVOID"])
        # Market risk Beta vs SPY
        self.assertIsNotNone(data["market_risk"]["beta_vs_spy_252d"])
        # Valuation compression sensitivity
        self.assertIn("multiple_compression_sensitivity", data["valuation_risk"])

    def test_09_adding_to_watchlist_preserves_frozen_baseline(self):
        """Acceptance Criteria 8: Adding a stock to watchlist does not modify frozen V4.0 baseline."""
        # 1. Check baseline excel exists and record file modification time
        excel_path = BASELINE_EXCEL_PATH
        mtime_before = excel_path.stat().st_mtime

        # 2. Add DIS to watchlist via research endpoint
        res = self.client.post("/api/research/DIS/add-to-watchlist")
        self.assertEqual(res.status_code, 200)

        # 3. Verify excel file remained untouched
        mtime_after = excel_path.stat().st_mtime
        self.assertEqual(mtime_before, mtime_after)

    def test_10_no_brokerage_execution_endpoints(self):
        """Acceptance Criteria 10: Verify no live brokerage execution endpoints exist."""
        forbidden_paths = [
            "/api/orders/execute",
            "/api/broker/trade",
            "/api/alpaca/buy",
            "/api/interactive_brokers/order"
        ]
        for path in forbidden_paths:
            res = self.client.post(path)
            self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
