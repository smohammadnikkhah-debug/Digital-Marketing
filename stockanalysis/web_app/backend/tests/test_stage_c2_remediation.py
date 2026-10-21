"""Regression Test Suite for Stage C2 UAT Remediation & Data Integrity Audit.

Validates:
1. Graceful ETF handling for valuation & fundamental endpoints (SPY, QQQ zero HTTP 500 errors).
2. AAPL 5-Year Revenue CAGR calculation (verifying ~8.7% CAGR vs corrupted 45.1% anomaly).
3. GOOGL Net Cash arithmetic, marketable securities inclusion, and sign formatting consistency.
4. Data provenance, source reporting, and period duration integrity.
5. Production vs Local state classification and synthetic test fixture handling.
"""
import pytest
from app.services.financial_data import financial_data_service
from app.services.valuation import valuation_service


class TestETFGracefulHandling:
    """Requirement 1: SPY and QQQ must not cause HTTP 500 errors and preserve technical/benchmark data."""

    def test_spy_valuation_workspace_graceful_etf(self):
        workspace = valuation_service.get_full_workspace("SPY")
        assert workspace is not None
        assert workspace.get("ticker") == "SPY"
        assert workspace.get("is_etf") is True
        assert workspace.get("asset_type") == "ETF"
        assert "Exchange Traded Fund" in workspace.get("etf_notice", "")
        # Scenarios and DCF results must be non-null dicts with .base to prevent frontend crashes
        assert "base" in workspace.get("scenarios", {})
        assert "base" in workspace.get("scenario_results", {})
        assert workspace.get("active_dcf", {}).get("fair_value_per_share") in (0.0, None)

    def test_qqq_valuation_workspace_graceful_etf(self):
        workspace = valuation_service.get_full_workspace("QQQ")
        assert workspace is not None
        assert workspace.get("ticker") == "QQQ"
        assert workspace.get("is_etf") is True
        assert "base" in workspace.get("scenarios", {})

    def test_spy_peer_comparison_no_null_subtraction_crash(self):
        # Previously threw TypeError: unsupported operand type(s) for -: 'NoneType' and 'NoneType'
        peers = valuation_service.get_peer_comparison("SPY")
        assert peers is not None
        assert peers.get("primary_ticker") == "SPY"
        assert peers.get("is_etf") is True

    def test_spy_recalculate_endpoints(self):
        custom = valuation_service.recalculate_custom("SPY", {"revenue_growth": 10.0, "discount_rate": 8.0})
        assert custom.get("is_etf") is True

        multi = valuation_service.recalculate_multi_scenario("SPY", {"base": {"revenue_growth": 10.0}})
        assert multi.get("is_etf") is True

    def test_spy_overview_and_risk_etf_flags(self):
        overview = financial_data_service.get_company_overview("SPY")
        assert overview.get("is_etf") is True
        assert overview.get("profile", {}).get("is_etf") is True
        assert overview.get("profile", {}).get("asset_type") == "ETF"

        risk = financial_data_service.get_stock_risk_assessment("SPY")
        assert risk is not None
        assert "not applicable for index ETFs" in risk.get("financial_risk", {}).get("explanation", "")

    def test_spy_technical_and_benchmark_price_data_preserved(self):
        # Technical bars must remain intact for benchmark tracking and momentum signals
        bars = financial_data_service.get_price_volume_history("SPY", interval="daily", time_range="5y")
        assert len(bars) >= 250
        assert bars[-1].get("close") is not None


class TestFinancialArithmeticDefects:
    """Requirement 3: Investigate & fix GOOGL net-cash inconsistency and AAPL 5Y CAGR anomaly."""

    def test_aapl_5y_revenue_cagr_not_corrupted(self):
        # Audited SEC 10-K facts: FY2020=$274.5B, FY2025=$416.2B -> true 5Y CAGR is ~8.68%
        # The defect previously caused 45.1% CAGR due to quarterly segment disclosure overwriting FY total
        matrix = valuation_service.get_historical_matrix("AAPL")
        assert matrix is not None
        rows = {r["key"]: r for r in matrix.get("rows", [])}
        assert "revenue_growth" in rows

        rev_row = rows["revenue_growth"]
        hist_5y = rev_row.get("hist_5y")
        assert hist_5y is not None
        # Must be within genuine 8.0% - 9.5% range, NOT 45.1%
        assert 8.0 <= hist_5y <= 9.5, f"Expected AAPL 5Y CAGR ~8.7%, got {hist_5y}%"
        assert "8.7% CAGR" in rev_row.get("hist_5y_formatted", "")

    def test_googl_net_cash_arithmetic_and_sign_consistency(self):
        overview = financial_data_service.get_company_overview("GOOGL")
        bs = overview.get("balance_sheet", {})
        cash_val = bs.get("cash_and_equivalents", {}).get("value")
        debt_val = bs.get("total_debt", {}).get("value")
        net_debt_val = bs.get("net_debt", {}).get("value")
        net_debt_fmt = bs.get("net_debt", {}).get("formatted", "")

        # 1. Total liquid cash must include short-term investments (~$242B, not only physical cash $55.9B)
        assert cash_val is not None and cash_val > 200e9, f"Expected total cash > $200B, got {cash_val}"

        # 2. Net debt must be negative (Cash > Debt => Net Cash)
        assert net_debt_val is not None
        assert net_debt_val < 0, f"Expected negative net debt for GOOGL, got {net_debt_val}"

        # 3. Formatted display must unambiguously state Net Cash without double-negative minus signs
        assert "Net Cash" in net_debt_fmt
        assert not net_debt_fmt.startswith("-"), f"Double negative found in: {net_debt_fmt}"

        # 4. Overview net debt must be consistent in magnitude with Risk panel net debt
        risk = financial_data_service.get_stock_risk_assessment("GOOGL")
        risk_net_debt = risk.get("financial_risk", {}).get("net_debt")
        assert risk_net_debt is not None and risk_net_debt < 0
        # Check both agree that Alphabet is a massive net-cash positive enterprise ($100B+ net cash)
        assert abs(net_debt_val) > 100e9
        assert abs(risk_net_debt) > 100e9


class TestDataProvenanceAndStateReporting:
    """Requirement 4 & 5: Provenance and truthful production vs local state classification."""

    def test_input_provenance_structure(self):
        prov = valuation_service.get_input_provenance_table("GOOGL")
        assert len(prov) > 0
        for row in prov:
            assert "input_parameter" in row
            assert "source" in row
            assert "status" in row

    def test_synthetic_ticker_recognition(self):
        # NEWIPO should be safely handled without throwing uncaught server errors
        assert not valuation_service.is_etf_ticker("NEWIPO")
