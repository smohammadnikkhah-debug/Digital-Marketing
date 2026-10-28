"""Stage D2.4H — USER_POLICY investment eligibility."""
from __future__ import annotations

from app.services.investment_eligibility import evaluate_investment_eligibility
from app.services.order_proposal_engine import STAGE_SUBMISSION_ENABLED
from app.services.user_policy_eligibility import (
    MODE_USER_POLICY,
    POLICY_ALLOWED,
    POLICY_EXCLUDED,
    POLICY_REVIEW,
    classify_user_policy,
    classify_universe_user_policy,
    propose_spus_addition,
)


class TestFourExclusions:
    def test_bank_excluded(self):
        r = classify_user_policy("JPM", name="JPMorgan Chase & Co.", sector="Financial Services", industry="Banks - Diversified")
        assert r["user_policy_status"] == POLICY_EXCLUDED
        assert "POLICY_EXCLUDED_BANKING_LENDING" in r["reason_codes"]

    def test_capital_markets_excluded_as_related_finance(self):
        r = classify_user_policy("GS", name="Goldman Sachs", sector="Financial Services", industry="Capital Markets")
        assert r["user_policy_status"] == POLICY_EXCLUDED

    def test_tobacco_mo_blocked(self):
        r = classify_user_policy("MO", name="Altria Group, Inc.", sector="Consumer Defensive", industry="Tobacco")
        assert r["user_policy_status"] == POLICY_EXCLUDED
        assert "POLICY_EXCLUDED_TOBACCO" in r["reason_codes"]

    def test_weapons_defence_excluded(self):
        r = classify_user_policy("LMT", name="Lockheed Martin", sector="Industrials", industry="Aerospace & Defense")
        assert r["user_policy_status"] == POLICY_EXCLUDED
        assert "POLICY_EXCLUDED_WEAPONS_DEFENCE" in r["reason_codes"]

    def test_airline_industry_excluded(self):
        r = classify_user_policy("AAL", name="American Airlines", sector="Industrials", industry="Airlines")
        assert r["user_policy_status"] == POLICY_EXCLUDED
        assert "POLICY_EXCLUDED_AIRLINES" in r["reason_codes"]


class TestVisaAndFinancialNuance:
    def test_visa_allowed_as_payment_network(self):
        r = classify_user_policy("V", name="Visa Inc.", sector="Financial Services", industry="Credit Services")
        assert r["user_policy_status"] == POLICY_ALLOWED
        assert "POLICY_PAYMENT_NETWORK_ALLOWED" in r["reason_codes"]
        assert r["proposal_permitted"] is True

    def test_mastercard_allowed(self):
        r = classify_user_policy("MA", sector="Financial Services", industry="Credit Services")
        assert r["user_policy_status"] == POLICY_ALLOWED

    def test_capital_one_lender_excluded(self):
        r = classify_user_policy("COF", name="Capital One", sector="Financial Services", industry="Credit Services")
        assert r["user_policy_status"] == POLICY_EXCLUDED

    def test_insurer_not_auto_bank(self):
        r = classify_user_policy("CB", name="Chubb", sector="Financial Services", industry="Insurance - Property & Casualty")
        assert r["user_policy_status"] == POLICY_ALLOWED

    def test_sector_alone_does_not_exclude_tech(self):
        r = classify_user_policy("AAPL", name="Apple", sector="Technology", industry="Consumer Electronics")
        assert r["user_policy_status"] == POLICY_ALLOWED
        assert r["sector_used_as_sole_basis"] is False


class TestEtfsAndSpus:
    def test_spy_not_auto_approved(self):
        r = classify_user_policy("SPY", name="SPDR S&P 500 ETF Trust", sector="ETFs", industry="Large Blend ETF")
        # D2.4I may resolve SPY to EXCLUDED via fund-exposure evidence; never ALLOWED.
        assert r["user_policy_status"] in (POLICY_REVIEW, POLICY_EXCLUDED)
        assert r["proposal_permitted"] is False

    def test_xlp_not_auto_approved(self):
        r = classify_user_policy("XLP", name="Consumer Staples Select Sector SPDR Fund", sector="ETFs", industry="Sector Staples ETF")
        assert r["user_policy_status"] in (POLICY_REVIEW, POLICY_EXCLUDED)
        assert r["proposal_permitted"] is False

    def test_spus_allowed_with_fund_evidence(self):
        r = classify_user_policy(
            "SPUS",
            name="SP Funds S&P 500 Sharia Industry Exclusions ETF",
            sector="ETFs",
            industry="Large Blend ETF",
        )
        assert r["user_policy_status"] == POLICY_ALLOWED
        assert "POLICY_ETF_FUND_SCREEN_ALLOWED" in r["reason_codes"]

    def test_propose_spus_no_production_mutation(self):
        p = propose_spus_addition(current_tickers=["SPY", "AAPL", "MO"])
        assert p["production_mutated"] is False
        assert p["duplicate"] is False
        assert p["action"] == "PROPOSE_ADD"


class TestReviewRequiredAndFailClosed:
    def test_ambiguous_equity_industry_review(self):
        r = classify_user_policy("XYZ1", sector="Technology", industry="Equity")
        assert r["user_policy_status"] == POLICY_REVIEW

    def test_unknown_without_industry_review(self):
        r = classify_user_policy("UNKN", sector="Technology", industry="")
        assert r["user_policy_status"] == POLICY_REVIEW
        assert r["proposal_permitted"] is False

    def test_brkb_diversified_review(self):
        r = classify_user_policy("BRK-B", industry="Insurance - Diversified", sector="Financial Services")
        assert r["user_policy_status"] == POLICY_REVIEW


class TestCombinedEligibilityMode:
    def test_user_policy_mode_allows_without_shariah(self):
        e = evaluate_investment_eligibility(
            "V",
            shariah_status="NOT VERIFIED",
            name="Visa Inc.",
            sector="Financial Services",
            industry="Credit Services",
            eligibility_mode=MODE_USER_POLICY,
        )
        assert e["execution_eligible"] is True
        assert e["shariah_required"] is False
        assert e["user_policy_status"] == POLICY_ALLOWED

    def test_user_policy_blocks_mo(self):
        e = evaluate_investment_eligibility(
            "MO",
            shariah_status="NOT VERIFIED",
            name="Altria",
            sector="Consumer Defensive",
            industry="Tobacco",
            eligibility_mode=MODE_USER_POLICY,
        )
        assert e["execution_eligible"] is False
        assert e["user_policy_status"] == POLICY_EXCLUDED

    def test_user_policy_blocks_spy(self):
        e = evaluate_investment_eligibility(
            "SPY",
            sector="ETFs",
            industry="Large Blend ETF",
            name="SPDR S&P 500 ETF Trust",
            eligibility_mode=MODE_USER_POLICY,
        )
        assert e["execution_eligible"] is False
        assert e["user_policy_status"] in (POLICY_REVIEW, POLICY_EXCLUDED)

    def test_no_broker_submissions(self):
        assert STAGE_SUBMISSION_ENABLED is False

    def test_universe_counts_shape(self):
        report = classify_universe_user_policy(
            [
                {"ticker": "V", "name": "Visa", "sector": "Financial Services", "industry": "Credit Services"},
                {"ticker": "MO", "name": "Altria", "sector": "Consumer Defensive", "industry": "Tobacco"},
                {"ticker": "SPY", "name": "SPY", "sector": "ETFs", "industry": "Large Blend ETF"},
            ]
        )
        assert report["counts"][POLICY_ALLOWED] == 1
        # SPY may be EXCLUDED (D2.4I fund evidence) or REVIEW; MO is EXCLUDED
        assert report["counts"][POLICY_EXCLUDED] >= 1
        assert report["counts"][POLICY_ALLOWED] + report["counts"][POLICY_EXCLUDED] + report["counts"][POLICY_REVIEW] == 3
        assert report["shariah_certification"] is False
        assert report["production_mutated"] is False
