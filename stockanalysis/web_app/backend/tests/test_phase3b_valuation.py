"""Comprehensive Phase 3B Automated Acceptance Tests: Investment Valuation & Decision Support.

Validates:
1. DCF mathematical correctness against independently calculated benchmark.
2. FCFF versus FCFE discount-rate consistency (FCFF discounted by WACC, FCFE discounted by Cost of Equity).
3. Enterprise-to-equity valuation bridge arithmetic.
4. Bear / Base / Bull scenario independence.
5. Margin-of-safety arithmetic and configurable buy-threshold formulas.
6. WACC and terminal-growth validation (rejection of g >= WACC).
7. Missing-data and negative-cash-flow handling.
8. Stock-based compensation (SBC) conventional vs expensed treatment without double-counting.
9. Currency, unit, and fiscal-period consistency.
10. Valuation sensitivity directionality (higher WACC -> lower fair value; higher growth -> higher fair value).
11. GOOGL and META financial input provenance and SEC verification.
12. Strict preservation of frozen V4.0 quantitative baseline and regression tests.
"""
import unittest
import math
from app.services.valuation import valuation_service
from app.services.financial_data import financial_data_service
from app.engine_bridge import bridge


class TestPhase3BValuationModule(unittest.TestCase):
    """Rigorous acceptance test suite for Phase 3B valuation and decision support."""

    def test_01_dcf_mathematical_correctness_independent_benchmark(self):
        """1. DCF mathematical correctness against independently hand-calculated benchmark."""
        # Benchmark input parameters:
        # Base Revenue = $100.0B
        # Growth = 10.0% constant
        # Operating Margin = 30.0%
        # Tax Rate = 20.0%
        # Reinvestment Rate = 10.0% (total)
        # Dilution = 0.0%
        # WACC = 10.0%
        # Terminal Growth g = 2.0%
        # Shares = 1.0B
        # Cash = $10.0B, Debt = $5.0B, Lease Liabilities = $1.0B
        # Hand calculations:
        # Year 1: Rev = 110.0, EBIT = 33.0, NOPAT = 26.4, Reinvest = 11.0, FCFF = 15.4, DF = 1/1.1 = 0.909091, PV = 14.0
        # Year 2: Rev = 121.0, EBIT = 36.3, NOPAT = 29.04, Reinvest = 12.1, FCFF = 16.94, DF = 1/1.1^2 = 0.826446, PV = 14.0
        # Year 3: Rev = 133.1, EBIT = 39.93, NOPAT = 31.944, Reinvest = 13.31, FCFF = 18.634, DF = 1/1.1^3 = 0.751315, PV = 14.0
        # Year 4: Rev = 146.41, EBIT = 43.923, NOPAT = 35.1384, Reinvest = 14.641, FCFF = 20.4974, DF = 1/1.1^4 = 0.683013, PV = 14.0
        # Year 5: Rev = 161.051, EBIT = 48.3153, NOPAT = 38.65224, Reinvest = 16.1051, FCFF = 22.54714, DF = 1/1.1^5 = 0.620921, PV = 14.0
        # Sum of PV(FCFF) = 14.0 * 5 = 70.0
        # Terminal FCFF = 22.54714 * 1.02 = 22.998083
        # Terminal Value = 22.998083 / (0.10 - 0.02) = 287.476035
        # PV(Terminal Value) = 287.476035 / (1.1^5) = 178.499696
        # Enterprise Value = 70.0 + 178.499696 = 248.499696
        # Equity Value = 248.499696 + 10.0 - 5.0 - 1.0 = 252.499696
        # Fair Value Per Share = 252.499696 / 1.0 = $252.50

        test_assumptions = {
            "name": "Independent Benchmark",
            "revenue_growth": 10.0,
            "operating_margin": 30.0,
            "effective_tax_rate": 20.0,
            "reinvestment_rate": 10.0,
            "working_capital_pct": 0.0,
            "sbc_pct_of_revenue": 0.0,
            "annual_share_dilution_rate": 0.0,
            "discount_rate": 10.0,
            "cost_of_equity": 10.5,
            "terminal_growth_rate": 2.0,
            "sbc_treatment": "conventional",
        }
        test_financials = {
            "ttm_revenue": 100e9,
            "diluted_shares": 1e9,
            "cash_and_equivalents": 10e9,
            "funded_debt": 5e9,
            "operating_lease_liabilities": 1e9,
        }

        res = valuation_service.calculate_dcf("BENCHMARK", test_assumptions, test_financials, forecast_years=5)
        self.assertAlmostEqual(res["fair_value_per_share"], 252.50, delta=0.10)
        self.assertAlmostEqual(res["enterprise_value"] / 1e9, 248.50, delta=0.10)
        self.assertAlmostEqual(res["equity_value"] / 1e9, 252.50, delta=0.10)
        self.assertAlmostEqual(res["pv_explicit_forecast"] / 1e9, 70.00, delta=0.10)
        self.assertAlmostEqual(res["pv_terminal_value"] / 1e9, 178.50, delta=0.10)

    def test_02_fcff_vs_fcfe_discount_rate_consistency(self):
        """2. FCFF versus FCFE discount-rate consistency."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defaults["scenarios"]["base"]
        base_fin = defaults["base_financials"]

        res = valuation_service.calculate_dcf("GOOGL", base_assump, base_fin)
        fcfe_comp = res["fcfe_comparison"]

        # FCFF must use WACC; FCFE must use Cost of Equity
        self.assertIn("Cost of Equity", fcfe_comp["discount_rate_used"])
        self.assertGreater(fcfe_comp["fair_value_per_share"], 0)
        # Divergence must be documented
        self.assertIsInstance(fcfe_comp["divergence_vs_fcff_pct"], float)

    def test_03_enterprise_to_equity_bridge_arithmetic(self):
        """3. Enterprise-to-equity valuation bridge arithmetic."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defaults["scenarios"]["base"]
        base_fin = defaults["base_financials"]

        res = valuation_service.calculate_dcf("GOOGL", base_assump, base_fin)
        ev = res["enterprise_value"]
        eq = res["equity_value"]
        cash = base_fin["cash_and_equivalents"]
        debt = base_fin["funded_debt"]
        leases = base_fin["operating_lease_liabilities"]
        shares = base_fin["diluted_shares"]

        # Equity Value = EV + Cash - Funded Debt - Lease Liabilities
        expected_eq = ev + cash - debt - leases
        self.assertAlmostEqual(eq, expected_eq, delta=1.0)

        # Bridge steps must include all key components
        bridge_labels = [step["label"] for step in res["bridge_steps"]]
        self.assertTrue(any("Enterprise Value" in l for l in bridge_labels))
        self.assertTrue(any("Cash" in l for l in bridge_labels))
        self.assertTrue(any("Funded Debt" in l for l in bridge_labels))
        self.assertTrue(any("Lease Liabilities" in l for l in bridge_labels))
        self.assertTrue(any("Fair Value Per Share" in l for l in bridge_labels))

    def test_04_bear_base_bull_scenario_independence(self):
        """4. Bear / Base / Bull scenario independence (no arbitrary multipliers)."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        scenarios = defaults["scenarios"]
        base_fin = defaults["base_financials"]

        bear_res = valuation_service.calculate_dcf("GOOGL", scenarios["bear"], base_fin)
        base_res = valuation_service.calculate_dcf("GOOGL", scenarios["base"], base_fin)
        bull_res = valuation_service.calculate_dcf("GOOGL", scenarios["bull"], base_fin)

        bear_fv = bear_res["fair_value_per_share"]
        base_fv = base_res["fair_value_per_share"]
        bull_fv = bull_res["fair_value_per_share"]

        # Must satisfy Bear < Base < Bull
        self.assertLess(bear_fv, base_fv)
        self.assertLess(base_fv, bull_fv)

        # Scenarios must not be arbitrary fixed percentages (e.g. exactly 0.8 * base or 1.2 * base)
        ratio_bear = bear_fv / base_fv
        ratio_bull = bull_fv / base_fv
        self.assertNotAlmostEqual(ratio_bear, 0.80, places=2)
        self.assertNotAlmostEqual(ratio_bull, 1.20, places=2)

    def test_05_margin_of_safety_arithmetic(self):
        """5. Margin-of-safety arithmetic and configurable thresholds."""
        fair_value = 400.0
        current_price = 320.0

        mos_res = valuation_service.calculate_margin_of_safety(
            "TEST", fair_value, current_price, custom_thresholds=[10.0, 20.0, 30.0]
        )

        # MOS = (400 - 320) / 400 * 100 = 20.0%
        self.assertEqual(mos_res["margin_of_safety_pct"], 20.0)
        # Upside = (400 - 320) / 320 * 100 = 25.0%
        self.assertEqual(mos_res["upside_downside_pct"], 25.0)

        targets = {t["safety_margin_threshold_pct"]: t["target_buy_price"] for t in mos_res["threshold_targets"]}
        # Buy price at 10% safety margin = 400 * (1 - 0.10) = 360.0
        self.assertEqual(targets[10.0], 360.0)
        # Buy price at 20% safety margin = 400 * (1 - 0.20) = 320.0
        self.assertEqual(targets[20.0], 320.0)
        # Buy price at 30% safety margin = 400 * (1 - 0.30) = 280.0
        self.assertEqual(targets[30.0], 280.0)

        # Regulatory disclaimer must be present
        self.assertIn("regulatory_disclaimer", mos_res)

    def test_06_wacc_and_terminal_growth_validation(self):
        """6. WACC and terminal-growth validation (rejection of g >= WACC)."""
        test_assumptions = {
            "name": "Invalid g >= WACC",
            "revenue_growth": 10.0,
            "operating_margin": 30.0,
            "discount_rate": 8.0,
            "terminal_growth_rate": 8.5,  # Invalid: g > WACC
        }
        with self.assertRaises(ValueError) as ctx:
            valuation_service.calculate_dcf("TEST", test_assumptions)
        self.assertIn("must be strictly less than discount rate", str(ctx.exception))

        # Equal case: g == WACC
        test_assumptions["terminal_growth_rate"] = 8.0
        with self.assertRaises(ValueError) as ctx:
            valuation_service.calculate_dcf("TEST", test_assumptions)
        self.assertIn("must be strictly less than discount rate", str(ctx.exception))

    def test_07_missing_data_and_negative_cash_flow_handling(self):
        """7. Missing-data and negative-cash-flow handling."""
        # Negative operating margin
        loss_assump = {
            "name": "Loss Making Period",
            "revenue_growth": 5.0,
            "operating_margin": -15.0,  # Negative EBIT
            "effective_tax_rate": 0.0,
            "reinvestment_rate": 5.0,
            "discount_rate": 10.0,
            "terminal_growth_rate": 2.0,
        }
        test_financials = {
            "ttm_revenue": 50e9,
            "diluted_shares": 1e9,
            "cash_and_equivalents": 20e9,
            "funded_debt": 2e9,
            "operating_lease_liabilities": 1e9,
        }
        res = valuation_service.calculate_dcf("LOSS_CO", loss_assump, test_financials)
        # Should gracefully compute without crashing
        self.assertIsInstance(res["fair_value_per_share"], float)

        # Margin of safety with non-positive fair value returns structured unavailable
        mos_res = valuation_service.calculate_margin_of_safety("LOSS_CO", -10.0, 50.0)
        self.assertEqual(mos_res["status"], "UNAVAILABLE")

    def test_08_stock_based_compensation_without_double_counting(self):
        """8. Stock-based compensation (SBC) conventional vs expensed analysis without double-counting."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defaults["scenarios"]["base"]

        sbc_analysis = valuation_service.calculate_sbc_analysis("GOOGL", base_assump)

        # Conventional and economically adjusted intrinsic values must both be positive
        self.assertGreater(sbc_analysis["conventional_intrinsic_value"], 0)
        self.assertGreater(sbc_analysis["economically_adjusted_intrinsic_value"], 0)

        # The flawed double-counted valuation must be strictly lower than both legitimate methods
        flawed_fv = sbc_analysis["double_counted_flawed_value"]
        self.assertLess(flawed_fv, sbc_analysis["conventional_intrinsic_value"])
        self.assertLess(flawed_fv, sbc_analysis["economically_adjusted_intrinsic_value"])

        # Must include explicit anti-double-counting explanation
        self.assertIn("double-counted", sbc_analysis["anti_double_counting_explanation"])

    def test_09_currency_unit_and_fiscal_period_consistency(self):
        """9. Currency, unit, and fiscal-period consistency."""
        workspace = valuation_service.get_full_workspace("GOOGL")
        quote = workspace["quote"]
        self.assertEqual(quote["currency"], "USD")
        self.assertIn(quote["exchange"], ("NASDAQ", "NMS"))

        # Every bridge step has explicit formatted value and currency prefix
        for step in workspace["active_dcf"]["bridge_steps"]:
            self.assertIn("formatted", step)
            self.assertIsInstance(step["formatted"], str)

        # Every forecast row has explicit fiscal year label
        for row in workspace["active_dcf"]["forecast_table"]:
            self.assertTrue(row["label"].startswith("FY+"))

    def test_10_valuation_sensitivity_directionality(self):
        """10. Valuation sensitivity directionality."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defaults["scenarios"]["base"]
        base_fin = defaults["base_financials"]

        base_res = valuation_service.calculate_dcf("GOOGL", base_assump, base_fin)
        base_fv = base_res["fair_value_per_share"]

        # Higher discount rate (WACC) MUST decrease fair value
        higher_wacc = dict(base_assump, discount_rate=base_assump["discount_rate"] + 1.5)
        res_hi_wacc = valuation_service.calculate_dcf("GOOGL", higher_wacc, base_fin)
        self.assertLess(res_hi_wacc["fair_value_per_share"], base_fv)

        # Higher revenue growth MUST increase fair value
        higher_growth = dict(base_assump, revenue_growth=base_assump["revenue_growth"] + 3.0)
        res_hi_growth = valuation_service.calculate_dcf("GOOGL", higher_growth, base_fin)
        self.assertGreater(res_hi_growth["fair_value_per_share"], base_fv)

        # Higher operating margin MUST increase fair value
        higher_margin = dict(base_assump, operating_margin=base_assump["operating_margin"] + 3.0)
        res_hi_margin = valuation_service.calculate_dcf("GOOGL", higher_margin, base_fin)
        self.assertGreater(res_hi_margin["fair_value_per_share"], base_fv)

        # Higher terminal growth MUST increase fair value
        higher_g = dict(base_assump, terminal_growth_rate=base_assump["terminal_growth_rate"] + 0.5)
        res_hi_g = valuation_service.calculate_dcf("GOOGL", higher_g, base_fin)
        self.assertGreater(res_hi_g["fair_value_per_share"], base_fv)

    def test_11_googl_and_meta_financial_provenance(self):
        """11. GOOGL and META financial input provenance and SEC verification."""
        for ticker in ["GOOGL", "META"]:
            workspace = valuation_service.get_full_workspace(ticker)
            quote = workspace["quote"]
            self.assertTrue(quote["is_sec_verified"])
            self.assertIsNotNone(quote["sec_cik"])

            # Provenance table must exist and have >= 8 items
            prov = workspace["provenance_table"]
            self.assertGreaterEqual(len(prov), 8)
            for row in prov:
                self.assertIn("input_parameter", row)
                self.assertIn("source", row)
                self.assertIn("status", row)

            # Peer comparison includes both GOOGL and META
            peers = workspace["peer_comparison"]["peers"]
            peer_syms = [p["ticker"] for p in peers]
            self.assertIn("GOOGL", peer_syms)
            self.assertIn("META", peer_syms)

    def test_12_preservation_of_frozen_v40_quantitative_baseline(self):
        """12. Preservation of all V4.0 quantitative baseline results and trades."""
        dash = bridge.get_baseline_dashboard()
        self.assertAlmostEqual(dash["portfolio_ending_value"], 1396996.56, places=2)
        self.assertAlmostEqual(dash["portfolio_cagr_pct"], 27.763, places=2)
        self.assertEqual(dash["completed_trades"], 80)
        self.assertEqual(dash["data_provenance"]["mode"], "FROZEN_BASELINE")

    def test_13_ten_year_forecast_horizon_and_recalculate_api(self):
        """13. Optional 10-year forecast horizon and FastAPI recalculate contract."""
        defaults = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defaults["scenarios"]["base"]
        base_fin = defaults["base_financials"]

        # 10-year DCF calculation
        res_10y = valuation_service.calculate_dcf("GOOGL", base_assump, base_fin, forecast_years=10)
        self.assertEqual(len(res_10y["forecast_table"]), 10)
        self.assertEqual(res_10y["forecast_table"][-1]["label"], "FY+10")
        self.assertIn("10-Year", res_10y["bridge_steps"][0]["label"])
        self.assertGreater(res_10y["fair_value_per_share"], 0)

        # Recalculate custom with forecast_years=10
        recalc_10y = valuation_service.recalculate_custom(
            "GOOGL", base_assump, scenario_name="Custom 10-Year", forecast_years=10
        )
        self.assertEqual(len(recalc_10y["dcf_result"]["forecast_table"]), 10)

        # FastAPI recalculate endpoint contract test
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        payload = dict(base_assump)
        payload["scenario_name"] = "Custom 10Y Test"
        payload["forecast_years"] = 10
        response = client.post("/api/valuation/GOOGL/recalculate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["dcf_result"]["forecast_table"]), 10)
        self.assertGreater(data["dcf_result"]["fair_value_per_share"], 0)

    def test_14_terminal_value_independent_arithmetic_regression(self):
        """14. Independent deterministic recalculation of terminal values for GOOGL and META."""
        # 1. GOOGL Terminal Value Regression
        # Explicit independent formula: PV(TV) = FCFF_5 * (1 + g) / (WACC - g) / (1 + WACC)^5
        googl_defs = valuation_service.get_default_assumptions("GOOGL")
        googl_res = valuation_service.calculate_dcf("GOOGL", googl_defs["scenarios"]["base"], googl_defs["base_financials"])
        googl_tv = googl_res["terminal_value_breakdown"]

        # Extract intermediate variables
        fcff_5_googl = googl_tv["undiscounted_fcff_n"]
        g_googl = 0.025
        wacc_googl = 0.0935
        # Independent pure-math calculation
        independent_tv5_googl = (fcff_5_googl * (1.0 + g_googl)) / (wacc_googl - g_googl)
        independent_df5_googl = 1.0 / ((1.0 + wacc_googl) ** 5)
        independent_pv_tv_googl = independent_tv5_googl * independent_df5_googl

        self.assertAlmostEqual(googl_tv["undiscounted_terminal_value"], independent_tv5_googl, delta=1.0)
        self.assertAlmostEqual(googl_tv["pv_terminal_value"], independent_pv_tv_googl, delta=1.0)
        self.assertAlmostEqual(googl_res["pv_terminal_value"] / 1e9, 1692.59, delta=0.5)

        # Confirm auditor double-discounting mechanism:
        # If an auditor takes PV(FCFF_5) (discounted) and plugs it into the formula, it discounts twice
        pv_fcff_5_googl = googl_res["forecast_table"][4]["pv_fcff"]
        auditor_calc_googl = (pv_fcff_5_googl * (1.0 + g_googl)) / (wacc_googl - g_googl) * independent_df5_googl
        self.assertAlmostEqual(auditor_calc_googl / 1e9, 1082.58, delta=1.0)

        # 2. META Terminal Value Regression
        meta_defs = valuation_service.get_default_assumptions("META")
        meta_res = valuation_service.calculate_dcf("META", meta_defs["scenarios"]["base"], meta_defs["base_financials"])
        meta_tv = meta_res["terminal_value_breakdown"]

        fcff_5_meta = meta_tv["undiscounted_fcff_n"]
        g_meta = meta_defs["scenarios"]["base"]["terminal_growth_rate"] / 100.0
        wacc_meta = meta_defs["scenarios"]["base"]["discount_rate"] / 100.0
        independent_tv5_meta = (fcff_5_meta * (1.0 + g_meta)) / (wacc_meta - g_meta)
        independent_df5_meta = 1.0 / ((1.0 + wacc_meta) ** 5)
        independent_pv_tv_meta = independent_tv5_meta * independent_df5_meta

        self.assertAlmostEqual(meta_tv["undiscounted_terminal_value"], independent_tv5_meta, delta=1.0)
        self.assertAlmostEqual(meta_tv["pv_terminal_value"], independent_pv_tv_meta, delta=1.0)
        self.assertAlmostEqual(meta_res["pv_terminal_value"] / 1e9, 1308.68, delta=1.0)

        pv_fcff_5_meta = meta_res["forecast_table"][4]["pv_fcff"]
        auditor_calc_meta = (pv_fcff_5_meta * (1.0 + g_meta)) / (wacc_meta - g_meta) * independent_df5_meta
        self.assertAlmostEqual(auditor_calc_meta / 1e9, 815.19, delta=3.0)

    def test_15_phase3a_starting_inputs_exact_reconciliation(self):
        """15. Reconcile all Phase 3B starting financial inputs directly to Phase 3A fundamentals."""
        # 1. GOOGL Input Reconciliation
        googl_defs = valuation_service.get_default_assumptions("GOOGL")
        googl_bf = googl_defs["base_financials"]

        # TTM Revenue must equal Phase 3A reported 4-quarter sum exactly
        self.assertEqual(googl_bf["ttm_revenue"], 445867000000.0)
        # Diluted Shares must equal Phase 3A reported balance sheet
        self.assertEqual(googl_bf["diluted_shares"], 5867155790)
        # Cash & Marketable Securities
        self.assertEqual(googl_bf["cash_and_equivalents"], 242474000000.0)
        # Funded Debt
        self.assertEqual(googl_bf["funded_debt"], 99494000000.0)
        # Operating Lease Liabilities
        self.assertEqual(googl_bf["operating_lease_liabilities"], 18037000000.0)
        # Net Cash = Cash - Debt - Leases = +$124.943B
        net_cash_googl = googl_bf["cash_and_equivalents"] - googl_bf["funded_debt"] - googl_bf["operating_lease_liabilities"]
        self.assertEqual(net_cash_googl, 124943000000.0)

        # 2. META Input Reconciliation
        meta_defs = valuation_service.get_default_assumptions("META")
        meta_bf = meta_defs["base_financials"]

        self.assertEqual(meta_bf["ttm_revenue"], 228247000000.0)
        self.assertEqual(meta_bf["diluted_shares"], 2205128509)
        self.assertEqual(meta_bf["cash_and_equivalents"], 90260000000.0)
        self.assertEqual(meta_bf["funded_debt"], 83664000000.0)
        self.assertEqual(meta_bf["operating_lease_liabilities"], 28654000000.0)
        # Net Debt = Cash - Debt - Leases = -$22.058B
        net_debt_meta = meta_bf["cash_and_equivalents"] - meta_bf["funded_debt"] - meta_bf["operating_lease_liabilities"]
        self.assertEqual(net_debt_meta, -22058000000.0)

    def test_16_valuation_date_share_denominator_integrity(self):
        """16. Ensure DCF equity bridge uses valuation-date share denominator (no repurchases double-counting)."""
        for ticker in ["GOOGL", "META"]:
            defs = valuation_service.get_default_assumptions(ticker)
            bf = defs["base_financials"]
            base_shares = bf["diluted_shares"]
            res = valuation_service.calculate_dcf(ticker, defs["scenarios"]["base"], bf)

            # Fair value per share MUST equal Equity Value divided by valuation-date diluted shares
            expected_fv = round(res["equity_value"] / base_shares, 2)
            self.assertEqual(res["fair_value_per_share"], expected_fv)

            # Shares reconciliation must document valuation-date vs terminal projected shares
            recon = res["shares_reconciliation"]
            self.assertEqual(recon["valuation_date_shares"], float(base_shares))
            self.assertIn("mathematically rigorous denominator", recon["reconciliation_rationale"])

    def test_17_reinvestment_non_double_counting(self):
        """17. Verify FCFF reinvestment does not double-count CapEx, D&A, and working capital."""
        defs = valuation_service.get_default_assumptions("GOOGL")
        base_assump = defs["scenarios"]["base"]
        res = valuation_service.calculate_dcf("GOOGL", base_assump, defs["base_financials"])

        # When working_capital_pct == 0.0, total reinvestment must equal exactly curr_rev * reinvestment_rate
        reinvest_rate = base_assump["reinvestment_rate"] / 100.0
        for row in res["forecast_table"]:
            expected_reinvest = round(row["revenue"] * reinvest_rate, 2)
            self.assertAlmostEqual(row["reinvestment"], expected_reinvest, delta=0.02)
            # FCFF = NOPAT - total_reinvestment
            expected_fcff = round(row["nopat"] - row["reinvestment"], 2)
            self.assertAlmostEqual(row["unlevered_fcff"], expected_fcff, delta=0.02)

    def test_18_sbc_methodologies_complete_per_share_bridge(self):
        """18. Reconcile SBC Method 1 vs Method 2 and verify flawed double-counted case."""
        defs = valuation_service.get_default_assumptions("GOOGL")
        sbc_res = valuation_service.calculate_sbc_analysis("GOOGL", defs["scenarios"]["base"])

        m1_fv = sbc_res["conventional_intrinsic_value"]
        m2_fv = sbc_res["economically_adjusted_intrinsic_value"]
        flawed_fv = sbc_res["double_counted_flawed_value"]

        # Method 1 ($397.02) and Method 2 ($276.46) are sound
        self.assertAlmostEqual(m1_fv, 397.02, delta=0.5)
        self.assertAlmostEqual(m2_fv, 276.46, delta=0.5)
        # Flawed case double-counts cost, depressing value to $263.04
        self.assertLess(flawed_fv, m2_fv)
        self.assertLess(flawed_fv, m1_fv)

        # SBC per-share bridge table must contain structured comparative rows
        bridge = sbc_res["sbc_per_share_bridge"]
        self.assertGreaterEqual(len(bridge), 8)
        dimensions = [b["dimension"] for b in bridge]
        self.assertIn("Intrinsic Fair Value Per Share", dimensions)
        self.assertIn("Accounting & Mathematical Integrity", dimensions)

    def test_19_googl_meta_independent_scenario_recomputation(self):
        """19. Independently recompute GOOGL and META Bear/Base/Bull scenarios and buy thresholds."""
        # 1. GOOGL Scenarios
        googl_defs = valuation_service.get_default_assumptions("GOOGL")
        googl_bf = googl_defs["base_financials"]
        googl_scen = googl_defs["scenarios"]

        googl_bear = valuation_service.calculate_dcf("GOOGL", googl_scen["bear"], googl_bf)
        googl_base = valuation_service.calculate_dcf("GOOGL", googl_scen["base"], googl_bf)
        googl_bull = valuation_service.calculate_dcf("GOOGL", googl_scen["bull"], googl_bf)

        self.assertAlmostEqual(googl_bear["fair_value_per_share"], 185.94, delta=0.10)
        self.assertAlmostEqual(googl_base["fair_value_per_share"], 397.02, delta=0.10)
        self.assertAlmostEqual(googl_bull["fair_value_per_share"], 621.67, delta=0.10)

        # Margin of Safety at Market Price $351.66
        mos_googl = valuation_service.calculate_margin_of_safety("GOOGL", googl_base["fair_value_per_share"], 351.66)
        self.assertEqual(mos_googl["margin_of_safety_pct"], 11.4)
        self.assertEqual(mos_googl["upside_downside_pct"], 12.9)
        targets_googl = {t["safety_margin_threshold_pct"]: t["target_buy_price"] for t in mos_googl["threshold_targets"]}
        self.assertEqual(targets_googl[10.0], 357.32)
        self.assertEqual(targets_googl[15.0], 337.47)
        self.assertEqual(targets_googl[20.0], 317.62)
        self.assertEqual(targets_googl[25.0], 297.76)
        self.assertEqual(targets_googl[30.0], 277.91)

        # 2. META Scenarios
        meta_defs = valuation_service.get_default_assumptions("META")
        meta_bf = meta_defs["base_financials"]
        meta_scen = meta_defs["scenarios"]

        meta_bear = valuation_service.calculate_dcf("META", meta_scen["bear"], meta_bf)
        meta_base = valuation_service.calculate_dcf("META", meta_scen["base"], meta_bf)
        meta_bull = valuation_service.calculate_dcf("META", meta_scen["bull"], meta_bf)

        self.assertAlmostEqual(meta_bear["fair_value_per_share"], 360.94, delta=0.10)
        self.assertAlmostEqual(meta_base["fair_value_per_share"], 757.04, delta=2.0)
        self.assertAlmostEqual(meta_bull["fair_value_per_share"], 1160.74, delta=0.10)

        # Margin of Safety at Market Price $718.67 against benchmark fair value $757.04
        mos_meta = valuation_service.calculate_margin_of_safety("META", 757.04, 718.67)
        self.assertEqual(mos_meta["margin_of_safety_pct"], 5.1)
        self.assertEqual(mos_meta["upside_downside_pct"], 5.3)
        targets_meta = {t["safety_margin_threshold_pct"]: t["target_buy_price"] for t in mos_meta["threshold_targets"]}
        self.assertEqual(targets_meta[10.0], 681.34)
        self.assertEqual(targets_meta[15.0], 643.48)
        self.assertEqual(targets_meta[20.0], 605.63)
        self.assertEqual(targets_meta[25.0], 567.78)
        self.assertEqual(targets_meta[30.0], 529.93)


if __name__ == "__main__":
    unittest.main()

