"""Stage D2.4J — paper-trading pilot readiness gates (deterministic)."""
from __future__ import annotations

from app.config import IBKR_EMERGENCY_STOP, TRADING_EXECUTION_ENABLED
from app.services.candidate_ranking import (
    RANKING_METHOD_ID,
    describe_ranking_methodology,
    rank_candidates,
    rank_key,
)
from app.services.order_execution_service import DEFAULT_MAX_ORDER_NOTIONAL_USD
from app.services.order_proposal_engine import STAGE_SUBMISSION_ENABLED
from app.services.policy_evidence_audit import (
    FOUR_EXCLUSION_RULES,
    audit_pilot_policy_classifications,
)
from app.services.quote_integrity_audit import (
    assess_whole_share_affordability,
    audit_high_ask_candidates,
    audit_symbol_quote,
)


class TestSafetyPreserved:
    def test_no_submission_and_stops(self):
        assert STAGE_SUBMISSION_ENABLED is False
        assert IBKR_EMERGENCY_STOP is True
        assert TRADING_EXECUTION_ENABLED is False

    def test_order_cap_preserved(self):
        assert DEFAULT_MAX_ORDER_NOTIONAL_USD == 500.0


class TestCandidateRanking:
    def test_methodology_rejects_share_price_priority(self):
        m = describe_ranking_methodology()
        assert m["method_id"] == RANKING_METHOD_ID
        assert m["uses_share_price"] is False
        assert m["invents_investment_score"] is False
        assert m["v40_live_rank_available"] is False
        assert "lower ask" in " ".join(m["explicitly_removed"]).lower() or any(
            "share-price" in x.lower() or "ask" in x.lower() for x in m["explicitly_removed"]
        )

    def test_rank_key_ignores_ask(self):
        cheap = {
            "ticker": "KMI",
            "simulated_proposal": {"status": "SIMULATED"},
            "quote": {"ask": 34.0},
        }
        expensive = {
            "ticker": "ZS",
            "simulated_proposal": {"status": "SIMULATED"},
            "quote": {"ask": 270.0},
        }
        seq = {"ZS": 8, "KMI": 26}
        assert rank_key(expensive, scan_sequence=seq) < rank_key(cheap, scan_sequence=seq)

    def test_rank_candidates_preserves_d2e_sequence(self):
        rows = [
            {
                "ticker": "KMI",
                "simulated_proposal": {"status": "SIMULATED"},
                "quote": {"ask": 34.0},
            },
            {
                "ticker": "ZS",
                "simulated_proposal": {"status": "SIMULATED"},
                "quote": {"ask": 270.0},
            },
            {
                "ticker": "PYPL",
                "simulated_proposal": {"status": "SIMULATED"},
                "quote": {"ask": 57.0},
            },
        ]
        buy_ready = [
            {"ticker": "ZS"},
            {"ticker": "PYPL"},
            {"ticker": "KMI"},
        ]
        ranked = rank_candidates(rows, buy_ready_details=buy_ready)
        assert [r["ticker"] for r in ranked] == ["ZS", "PYPL", "KMI"]
        assert ranked[0]["pilot_rank"] == 1
        assert ranked[0]["pilot_ranking_method"] == RANKING_METHOD_ID


class TestQuoteIntegrity:
    def test_whole_share_gate_rejects_ask_above_500(self):
        for ask in (549.94, 554.33, 954.24):
            aff = assess_whole_share_affordability(ask=ask, max_order_notional_usd=500.0)
            assert aff["affordable_one_whole_share"] is False
            assert aff["whole_share_qty"] == 0
            assert aff["fractional_shares_enabled"] is False
            assert aff["expected_reason_if_blocked"] == "INSUFFICIENT_CASH_FOR_ONE_SHARE"

    def test_whole_share_gate_allows_ask_under_500(self):
        aff = assess_whole_share_affordability(ask=34.12, max_order_notional_usd=500.0)
        assert aff["affordable_one_whole_share"] is True
        assert aff["whole_share_qty"] >= 1

    def test_amd_msft_mu_cap_rejection_from_d2i_shape(self):
        rows = [
            {
                "ticker": "AMD",
                "quote": {"ask": 549.94, "bid": 505.69, "source": "ALPACA_IEX", "symbol": "AMD"},
                "sizing_block": {
                    "status": "SIZING_BLOCKED",
                    "reason_codes": ["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
                    "details": {"slot_budget": 500.0, "ask": 549.94},
                },
            },
            {
                "ticker": "MSFT",
                "quote": {"ask": 554.33, "bid": 500.46, "source": "ALPACA_IEX", "symbol": "MSFT"},
                "sizing_block": {
                    "status": "SIZING_BLOCKED",
                    "reason_codes": ["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
                    "details": {"slot_budget": 500.0, "ask": 554.33},
                },
            },
            {
                "ticker": "MU",
                "quote": {"ask": 954.24, "bid": 863.27, "source": "ALPACA_IEX", "symbol": "MU"},
                "sizing_block": {
                    "status": "SIZING_BLOCKED",
                    "reason_codes": ["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
                    "details": {"slot_budget": 500.0, "ask": 954.24},
                },
            },
        ]
        report = audit_high_ask_candidates(rows)
        assert report["all_whole_share_cap_rejections_confirmed"] is True
        assert report["fractional_shares_enabled"] is False
        assert report["any_symbol_mismatch"] is False

    def test_symbol_mismatch_flagged(self):
        r = audit_symbol_quote(
            "AMD",
            quote={"symbol": "AMZN", "ask": 549.94, "bid": 505.0, "source": "ALPACA_IEX"},
            sizing_block={
                "reason_codes": ["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
            },
        )
        assert r["symbol_identity_ok"] is False


class TestPolicyEvidence:
    def test_four_exclusion_rules_present(self):
        assert len(FOUR_EXCLUSION_RULES) == 4
        cats = {r["category"] for r in FOUR_EXCLUSION_RULES}
        assert "conventional_banking_lending" in cats
        assert "airlines" in cats
        assert "weapons_defence" in cats
        assert "tobacco" in cats

    def test_crm_pltr_soxx_spy_xlp_classifications(self):
        report = audit_pilot_policy_classifications(ensure_overlays=True)
        assert report["all_match_expectations"] is True
        by_t = {r["ticker"]: r for r in report["classifications"]}
        assert by_t["CRM"]["actual_status"] == "ALLOWED"
        assert by_t["PLTR"]["actual_status"] == "EXCLUDED"
        assert "MILITARY_DEFENCE_EXPOSURE" in (by_t["PLTR"]["reason_codes"] or [])
        assert by_t["SOXX"]["actual_status"] == "ALLOWED"
        assert by_t["SPY"]["actual_status"] == "EXCLUDED"
        assert by_t["XLP"]["actual_status"] == "EXCLUDED"
        for t in ("CRM", "PLTR", "SOXX", "SPY", "XLP"):
            assert by_t[t]["four_exclusion_rules_mapping"]
            assert by_t[t]["evidence_note"] or by_t[t]["evidence_source"]
