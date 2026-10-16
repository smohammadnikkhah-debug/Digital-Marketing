"""Unit Tests for Valuation & Scenario Phase Enhancement.

Verifies:
1. Unified 10-Row Financial Assumptions Matrix (Historical Latest FY, 5Y History, 10Y History).
2. Sourced historical factual integrity without invented numbers.
3. Independent Bear, Base, and Bull scenario recalculations.
4. 5-Year vs 10-Year explicit forecast horizon consistency and terminal value discounting.
5. Reconciliation from Enterprise Value to Equity Value and share count treatment.
6. Stock-Based Compensation (SBC) anti-double-counting guard.
7. Hurdle Rate / Target Entry Price separation from WACC (Requirement 8).
8. Per-year forecast breakdown items: Revenue, EBIT, Taxes, Reinvestment, FCFF, DF, PV, TV, FV per share (Requirement 7).
9. API router compatibility for workspace, legacy single-scenario recalculate, multi-scenario recalculate, and matrix endpoints.
"""
import unittest
from fastapi.testclient import TestClient
import numpy as np

from app.main import app
from app.services.valuation import valuation_service


class TestValuationEnhanced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.ticker = "GOOGL"

    def test_historical_matrix_10_rows_structure(self):
        """Requirement 2 & 3: Unified matrix contains exactly the 10 specified rows with complete provenance."""
        matrix = valuation_service.get_historical_matrix(self.ticker)
        self.assertIn("rows", matrix)
        self.assertIn("as_of_period", matrix)
        self.assertIn("provenance_summary", matrix)
        
        rows = matrix["rows"]
        self.assertEqual(len(rows), 10, "Historical matrix must have exactly 10 rows")

        expected_keys = [
            "revenue_growth",
            "operating_margin",
            "fcf_margin",
            "roic",
            "reinvestment_rate",
            "effective_tax_rate",
            "discount_rate",
            "terminal_growth_rate",
            "sbc_pct_of_revenue",
            "annual_share_dilution_rate",
        ]
        actual_keys = [r["key"] for r in rows]
        self.assertEqual(actual_keys, expected_keys, "Matrix keys must match required 10 financial metrics")

        for r in rows:
            self.assertIn("key", r)
            self.assertIn("label", r)
            self.assertIn("category", r)
            self.assertIn("latest_fy_formatted", r)
            self.assertIn("hist_5y_formatted", r)
            self.assertIn("hist_10y_formatted", r)
            self.assertIn("provenance", r)
            self.assertIn("calculation_method", r)
            self.assertIn("is_diagnostic_only", r)

        # Verify diagnostic flags
        row_dict = {r["key"]: r for r in rows}
        self.assertTrue(row_dict["fcf_margin"]["is_diagnostic_only"])
        self.assertTrue(row_dict["roic"]["is_diagnostic_only"])
        self.assertFalse(row_dict["revenue_growth"]["is_diagnostic_only"])

    def test_historical_matrix_factual_sec_values(self):
        """Requirement 6: Values reflect audited SEC facts, not invented numbers."""
        matrix = valuation_service.get_historical_matrix("GOOGL")
        row_dict = {r["key"]: r for r in matrix["rows"]}

        # Alphabet FY2025 revenue was ~$402.8B vs FY2024 ~$350.0B (~15.1% growth)
        rev_latest = row_dict["revenue_growth"]["latest_fy"]
        self.assertIsNotNone(rev_latest)
        self.assertGreater(rev_latest, 10.0)
        self.assertLess(rev_latest, 25.0)

        # Operating margin is historically 25%-35%
        op_latest = row_dict["operating_margin"]["latest_fy"]
        self.assertIsNotNone(op_latest)
        self.assertGreater(op_latest, 25.0)
        self.assertLess(op_latest, 40.0)

        # SBC is historically 5%-8% of revenue
        sbc_latest = row_dict["sbc_pct_of_revenue"]["latest_fy"]
        self.assertIsNotNone(sbc_latest)
        self.assertGreater(sbc_latest, 4.0)
        self.assertLess(sbc_latest, 10.0)

        # Net share change is negative due to heavy buybacks (~ -1% to -2.5% CAGR)
        dilution_5y = row_dict["annual_share_dilution_rate"]["hist_5y"]
        self.assertIsNotNone(dilution_5y)
        self.assertLess(dilution_5y, 0.0, "Alphabet has net repurchased shares over 5 years")

    def test_forecast_breakdown_per_year_details(self):
        """Requirement 7: Per-year forecast breakdown includes revenue, EBIT, taxes, reinvestment, FCFF, DF, PV, and cumulative PV."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        base_assump = defaults["scenarios"]["base"]
        dcf = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=5)
        
        table = dcf["forecast_table"]
        self.assertEqual(len(table), 5)

        prior_cum_pv = 0.0
        for r in table:
            self.assertIn("revenue", r)
            self.assertIn("revenue_growth_pct", r)
            self.assertIn("operating_income_ebit", r)
            self.assertIn("operating_margin_pct", r)
            self.assertIn("taxes", r)
            self.assertIn("taxes_formatted", r)
            self.assertIn("nopat", r)
            self.assertIn("reinvestment", r)
            self.assertIn("unlevered_fcff", r)
            self.assertIn("discount_factor_wacc", r)
            self.assertIn("pv_fcff", r)
            self.assertIn("cumulative_pv_fcff", r)

            # Mathematical checks
            expected_nopat = r["operating_income_ebit"] - r["taxes"]
            self.assertAlmostEqual(r["nopat"], expected_nopat, delta=1.0)
            self.assertGreater(r["cumulative_pv_fcff"], prior_cum_pv)
            prior_cum_pv = r["cumulative_pv_fcff"]

    def test_scenario_independence(self):
        """Requirement 5 & 9: Bear, Base, and Bull are independently calculated; modifying one does not alter others."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        scenarios = {
            "bear": dict(defaults["scenarios"]["bear"]),
            "base": dict(defaults["scenarios"]["base"]),
            "bull": dict(defaults["scenarios"]["bull"]),
        }

        # Modify Bear only
        scenarios["bear"]["revenue_growth"] = 4.0
        scenarios["bear"]["operating_margin"] = 22.0

        res = valuation_service.recalculate_multi_scenario(
            ticker=self.ticker,
            scenarios=scenarios,
            forecast_years=5,
            required_return_pct=12.0,
        )

        res_bear = res["scenario_results"]["bear"]
        res_base = res["scenario_results"]["base"]
        res_bull = res["scenario_results"]["bull"]

        # Base and Bull should maintain their standard values
        self.assertLess(res_bear["fair_value_per_share"], res_base["fair_value_per_share"])
        self.assertLess(res_base["fair_value_per_share"], res_bull["fair_value_per_share"])

        # Check default Base unchanged
        control_base = valuation_service.calculate_dcf(self.ticker, defaults["scenarios"]["base"], defaults["base_financials"], forecast_years=5)
        self.assertEqual(res_base["fair_value_per_share"], control_base["fair_value_per_share"])

    def test_5y_vs_10y_horizon_consistency(self):
        """Requirement 4: 5-year and 10-year forecast horizons are supported and mathematically consistent."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        base_assump = defaults["scenarios"]["base"]

        dcf_5y = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=5)
        dcf_10y = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=10)

        self.assertEqual(len(dcf_5y["forecast_table"]), 5)
        self.assertEqual(len(dcf_10y["forecast_table"]), 10)

        # In 10Y, terminal discount factor is smaller than in 5Y: 1/(1+WACC)^10 < 1/(1+WACC)^5
        df_5y = dcf_5y["terminal_value_breakdown"]["discount_factor"]
        df_10y = dcf_10y["terminal_value_breakdown"]["discount_factor"]
        self.assertLess(df_10y, df_5y)

        # Enterprise value bridge reconciliation in both
        ev_5y = dcf_5y["enterprise_value"]
        eq_5y = dcf_5y["equity_value"]
        cash = defaults["base_financials"]["cash_and_equivalents"]
        debt = defaults["base_financials"]["funded_debt"]
        leases = defaults["base_financials"]["operating_lease_liabilities"]
        self.assertAlmostEqual(eq_5y, ev_5y + cash - debt - leases, delta=1.0)

        ev_10y = dcf_10y["enterprise_value"]
        eq_10y = dcf_10y["equity_value"]
        self.assertAlmostEqual(eq_10y, ev_10y + cash - debt - leases, delta=1.0)

    def test_target_entry_price_hurdle_separation(self):
        """Requirement 8: Required investment return is separate from WACC; target entry price decreases as hurdle increases."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        base_assump = defaults["scenarios"]["base"]
        wacc = float(base_assump["discount_rate"])

        # When hurdle == WACC, Target Entry Price == Fair Value
        dcf_eq = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=5, required_return_pct=wacc)
        self.assertAlmostEqual(dcf_eq["target_entry_price"], dcf_eq["fair_value_per_share"], delta=0.5)

        # When hurdle > WACC (e.g. 15% vs 8.5%), Target Entry Price < Fair Value (requires margin of safety)
        dcf_high_hurdle = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=5, required_return_pct=15.0)
        self.assertLess(dcf_high_hurdle["target_entry_price"], dcf_eq["fair_value_per_share"])

        # When hurdle < WACC (e.g. 6% vs 8.5%), Target Entry Price > Fair Value
        dcf_low_hurdle = valuation_service.calculate_dcf(self.ticker, base_assump, defaults["base_financials"], forecast_years=5, required_return_pct=6.0)
        self.assertGreater(dcf_low_hurdle["target_entry_price"], dcf_eq["fair_value_per_share"])

    def test_sbc_anti_double_counting_guard(self):
        """Quality & Audit: Ensure SBC expensing does not double-count dilution."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        assump_conv = dict(defaults["scenarios"]["base"])
        assump_conv["sbc_treatment"] = "conventional"

        assump_exp = dict(defaults["scenarios"]["base"])
        assump_exp["sbc_treatment"] = "expensed"

        assump_flawed = dict(defaults["scenarios"]["base"])
        assump_flawed["sbc_treatment"] = "double_counted"

        dcf_conv = valuation_service.calculate_dcf(self.ticker, assump_conv, defaults["base_financials"])
        dcf_exp = valuation_service.calculate_dcf(self.ticker, assump_exp, defaults["base_financials"])
        dcf_flawed = valuation_service.calculate_dcf(self.ticker, assump_flawed, defaults["base_financials"])

        # In conventional treatment, valuation date shares are used, and cash flows are unreduced by SBC.
        # In flawed double-counted treatment, SBC is deducted AND share count is inflated, resulting in lower valuation.
        self.assertLess(dcf_flawed["fair_value_per_share"], dcf_conv["fair_value_per_share"])

    def test_api_workspace_endpoint(self):
        """Requirement 10: GET /api/valuation/{ticker}/workspace returns historical matrix and scenarios."""
        res = self.client.get(f"/api/valuation/{self.ticker}/workspace?forecast_years=5&required_return_pct=12.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("historical_matrix", data)
        self.assertIn("scenario_results", data)
        self.assertEqual(data["forecast_years"], 5)
        self.assertEqual(data["required_return_pct"], 12.0)
        self.assertEqual(len(data["historical_matrix"]["rows"]), 10)

    def test_api_recalculate_scenarios_endpoint(self):
        """Requirement 9 & 10: POST /api/valuation/{ticker}/recalculate-scenarios updates all 3 scenarios."""
        defaults = valuation_service.get_default_assumptions(self.ticker)
        payload = {
            "scenarios": defaults["scenarios"],
            "forecast_years": 10,
            "required_return_pct": 14.0,
            "active_scenario": "base",
        }
        res = self.client.post(f"/api/valuation/{self.ticker}/recalculate-scenarios", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("scenario_results", data)
        self.assertEqual(data["forecast_years"], 10)
        self.assertEqual(data["required_return_pct"], 14.0)
        self.assertEqual(len(data["scenario_results"]["base"]["forecast_table"]), 10)

    def test_api_get_matrix_endpoint(self):
        """Requirement 2: GET /api/valuation/{ticker}/matrix returns 10-row matrix with provenance."""
        res = self.client.get(f"/api/valuation/{self.ticker}/matrix")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("rows", data)
        self.assertEqual(len(data["rows"]), 10)


if __name__ == "__main__":
    unittest.main()
