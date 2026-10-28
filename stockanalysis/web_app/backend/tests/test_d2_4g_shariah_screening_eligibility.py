"""Stage D2.4G — Shariah screening evidence + personal restrictions + eligibility."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext, buy_decision_engine
from app.services.investment_eligibility import evaluate_investment_eligibility
from app.services.order_proposal_engine import STAGE_SUBMISSION_ENABLED
from app.services.personal_restrictions import (
    RESTRICT_ALLOWED,
    RESTRICT_EXCLUDED,
    RESTRICT_REVIEW,
    assess_personal_restriction,
    default_personal_restrictions_config,
)
from app.services.shariah_evidence import (
    ShariahEvidenceRecord,
    resolve_ticker_evidence,
    validate_evidence_record,
)
from app.services.shariah_review_workflow import (
    build_universe_monitoring_report,
    stage_local_manual_review,
)
from app.services.ticker_integrity import resolve_proposed_alias

AS_OF = date(2026, 10, 27)


def _complete_verified(ticker: str = "AAPL", **overrides) -> ShariahEvidenceRecord:
    rec = ShariahEvidenceRecord(
        ticker=ticker,
        status="VERIFIED",
        company_identifier="Apple Inc.",
        methodology_provider="Independent Screener X",
        business_activity_assessment="Core business permissible; no haram primary activity",
        financial_ratio_assessment="Debt and interest income within stated thresholds",
        source_reference="https://example.invalid/screen/AAPL",
        assessment_date="2026-01-15",
        expiry_or_review_date="2027-01-15",
        reviewer_or_authority="Compliance Board",
        rationale="Full screen completed",
    )
    for k, v in overrides.items():
        setattr(rec, k, v)
    return rec


def _signal(ticker="AAPL", **overrides):
    sig = {
        "ticker": ticker,
        "signal": "BUY CANDIDATE",
        "signal_source": V40_SIGNAL_SOURCE,
        "strategy_version": V40_STRATEGY_VERSION,
        "entry_rule": "CROSS",
        "exit_rule": "MA250_3CLOSE",
        "is_fresh_analysis": True,
        "provenance_mode": "LIVE_SCAN",
        "market_as_of_date": "2026-10-24",
        "as_of": "2026-10-24",
        "validation_status": "OK",
        "data_freshness": "FRESH",
        "ma250": 180.0,
        "close": 200.0,
        "shariah_status": "NOT VERIFIED",
    }
    sig.update(overrides)
    return sig


class TestEvidenceValidation:
    def test_verified_complete_evidence(self):
        v = validate_evidence_record(_complete_verified(), as_of=AS_OF)
        assert v["is_valid_for_execution"] is True
        assert v["effective_status"] == "VERIFIED"
        assert v["evidence_quality"] == "VALID"

    def test_missing_evidence(self):
        r = resolve_ticker_evidence("MSFT", [], as_of=AS_OF)
        assert r["evidence_quality"] == "MISSING"
        assert r["is_valid_for_execution"] is False

    def test_expired_evidence(self):
        rec = _complete_verified(expiry_or_review_date="2025-01-01")
        v = validate_evidence_record(rec, as_of=AS_OF)
        assert v["evidence_quality"] == "EXPIRED"
        assert v["is_valid_for_execution"] is False

    def test_incomplete_verified_missing_fields(self):
        rec = ShariahEvidenceRecord(
            ticker="AAPL",
            status="VERIFIED",
            source_reference="x",
            assessment_date="2026-01-01",
        )
        v = validate_evidence_record(rec, as_of=AS_OF)
        assert v["evidence_quality"] == "INCOMPLETE"
        assert v["is_valid_for_execution"] is False

    def test_non_compliant_evidence(self):
        rec = ShariahEvidenceRecord(
            ticker="JPM",
            status="NON-COMPLIANT",
            source_reference="screen",
            assessment_date="2026-01-01",
            rationale="Conventional banking",
        )
        v = validate_evidence_record(rec, as_of=AS_OF)
        assert v["effective_status"] == "NON-COMPLIANT"
        assert v["is_valid_for_execution"] is False

    def test_research_shortlist_not_verification(self):
        rec = _complete_verified(is_research_shortlist=True)
        v = validate_evidence_record(rec, as_of=AS_OF)
        assert v["evidence_quality"] == "RESEARCH_SHORTLIST_NOT_VERIFICATION"
        assert v["is_valid_for_execution"] is False

    def test_conflicting_assessments(self):
        records = [
            _complete_verified("AAPL"),
            ShariahEvidenceRecord(
                ticker="AAPL",
                status="NON-COMPLIANT",
                source_reference="other",
                assessment_date="2026-02-01",
            ),
        ]
        # Make non-compliant also "valid" as documented non-compliance
        r = resolve_ticker_evidence("AAPL", records, as_of=AS_OF)
        assert r["conflict"] is True
        assert r["is_valid_for_execution"] is False
        assert r["evidence_quality"] == "CONFLICTING"

    def test_duplicate_records_prefer_valid_verified(self):
        incomplete = ShariahEvidenceRecord(ticker="AAPL", status="VERIFIED", source_reference="x")
        complete = _complete_verified("AAPL")
        r = resolve_ticker_evidence("AAPL", [incomplete, complete], as_of=AS_OF)
        assert r["duplicate_count"] == 2
        assert r["is_valid_for_execution"] is True
        assert r["conflict"] is False

    def test_ticker_alias_sq_to_xyz(self):
        assert resolve_proposed_alias("SQ")["proposed_canonical"] == "XYZ"
        rec = _complete_verified("XYZ")
        r = resolve_ticker_evidence("SQ", [rec], as_of=AS_OF)
        assert r["ticker"] == "XYZ"
        assert r["is_valid_for_execution"] is True


class TestPersonalRestrictions:
    def test_default_allowed(self):
        a = assess_personal_restriction("AAPL")
        assert a["personal_restriction_status"] == RESTRICT_ALLOWED
        assert a["sector_used_for_classification"] is False

    def test_explicit_exclusion_with_evidence(self):
        cfg = default_personal_restrictions_config()
        cfg["ticker_overrides"]["JPM"] = {
            "status": "EXCLUDED",
            "category_tags": ["conventional_banking_lending"],
            "evidence_note": "Primary business is conventional interest-based banking",
            "rationale": "Personal banking exclusion",
        }
        a = assess_personal_restriction("JPM", config=cfg, sector="Financial Services")
        assert a["personal_restriction_status"] == RESTRICT_EXCLUDED
        assert a["sector_used_for_classification"] is False

    def test_sector_alone_does_not_exclude(self):
        a = assess_personal_restriction("XOM", sector="Energy")
        assert a["personal_restriction_status"] == RESTRICT_ALLOWED

    def test_exclusion_without_evidence_becomes_review(self):
        cfg = default_personal_restrictions_config()
        cfg["ticker_overrides"]["BA"] = {"status": "EXCLUDED"}
        a = assess_personal_restriction("BA", config=cfg)
        assert a["personal_restriction_status"] == RESTRICT_REVIEW


class TestCombinedEligibility:
    def test_fail_closed_missing_evidence_strict(self):
        e = evaluate_investment_eligibility(
            "AMD",
            shariah_status="NOT VERIFIED",
            evidence_records=[],
            personal_config=default_personal_restrictions_config(),
            require_complete_evidence=True,
            as_of=AS_OF,
        )
        assert e["execution_eligible"] is False
        assert "SHARIAH_NOT_VERIFIED" in e["reason_codes"]

    def test_verified_plus_allowed(self):
        e = evaluate_investment_eligibility(
            "AAPL",
            evidence_records=[_complete_verified()],
            personal_config=default_personal_restrictions_config(),
            require_complete_evidence=True,
            as_of=AS_OF,
        )
        assert e["execution_eligible"] is True
        assert e["proposal_permitted"] is True

    def test_verified_but_personally_excluded(self):
        cfg = default_personal_restrictions_config()
        cfg["ticker_overrides"]["AAPL"] = {
            "status": "EXCLUDED",
            "category_tags": ["pork"],
            "evidence_note": "User-specified personal exclusion for testing",
        }
        e = evaluate_investment_eligibility(
            "AAPL",
            evidence_records=[_complete_verified()],
            personal_config=cfg,
            require_complete_evidence=True,
            as_of=AS_OF,
        )
        assert e["execution_eligible"] is False
        assert "PERSONAL_EXCLUDED" in e["reason_codes"]

    def test_unresolved_mandatory_checks(self):
        e = evaluate_investment_eligibility(
            "AAPL",
            evidence_records=[_complete_verified()],
            personal_config=default_personal_restrictions_config(),
            unresolved_mandatory_checks=["financial_ratio_refresh"],
            require_complete_evidence=True,
            as_of=AS_OF,
        )
        assert e["execution_eligible"] is False
        assert "UNRESOLVED_MANDATORY_SCREENING_CHECKS" in e["reason_codes"]

    def test_expired_blocks_even_if_status_verified(self):
        e = evaluate_investment_eligibility(
            "AAPL",
            evidence_records=[_complete_verified(expiry_or_review_date="2020-01-01")],
            personal_config=default_personal_restrictions_config(),
            require_complete_evidence=True,
            as_of=AS_OF,
        )
        assert e["execution_eligible"] is False
        assert "SHARIAH_EVIDENCE_EXPIRED" in e["reason_codes"]


class TestMonitoringAndWorkflow:
    def test_monitoring_report_and_buy_queue(self):
        rows = [
            {"ticker": "AMD", "signal": "BUY CANDIDATE", "shariah_status": "NOT VERIFIED"},
            {"ticker": "MSFT", "signal": "WATCH", "shariah_status": "NOT VERIFIED"},
            {
                "ticker": "AAPL",
                "signal": "BUY CANDIDATE",
                "shariah_status": "VERIFIED",
            },
        ]
        report = build_universe_monitoring_report(
            universe_rows=rows,
            evidence_records=[_complete_verified("AAPL")],
            personal_config=default_personal_restrictions_config(),
            buy_priority_tickers=["AMD", "AAPL"],
        )
        assert report["counts"]["shariah_VERIFIED"] == 1
        assert report["counts"]["shariah_NOT_VERIFIED"] == 2
        assert report["counts"]["execution_ELIGIBLE"] == 1
        assert any(r["ticker"] == "AMD" for r in report["buy_candidates_review_queue"])
        assert any(r["ticker"] == "AMD" for r in report["shariah_blocked_buy_opportunities"])
        assert report["broker_submissions"] == 0
        assert report["production_writes"] is False

    def test_local_manual_review_does_not_auto_approve(self, tmp_path: Path, monkeypatch):
        import app.services.shariah_review_workflow as wf

        monkeypatch.setattr(wf, "SHARIAH_DIR", tmp_path)
        monkeypatch.setattr(wf, "LOCAL_REVIEWS_PATH", tmp_path / "local_manual_reviews.jsonl")
        row = stage_local_manual_review(
            {
                "ticker": "AMD",
                "action": "REVIEW_NOTE",
                "notes": "Need provider screen",
                "proposed_status": "VERIFIED",
                "reviewer": "local-tester",
            }
        )
        assert row["auto_approved"] is False
        assert row["production_written"] is False
        assert row["is_independent_verification"] is False


class TestProposalGateAndNoSubmissions:
    def test_decision_engine_blocks_without_evidence_in_strict_ctx(self):
        from datetime import datetime, timezone

        from app.services.us_session_freshness import last_completed_us_equity_session

        now = datetime(2026, 10, 27, 20, 0, 0, tzinfo=timezone.utc)  # after US cash close
        as_of = last_completed_us_equity_session(now).isoformat()
        ctx = DecisionContext(
            account=AccountSnapshot(
                broker="alpaca",
                account_id="PA1234",
                cash=10000,
                equity=10000,
                snapshot_fresh=True,
                connection_ok=True,
            ),
            broker_quote={
                "source": "ALPACA_IEX",
                "bid": 199,
                "ask": 200,
                "quote_timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "received_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_delayed": False,
                "is_synthetic": False,
            },
            emergency_stop=False,
            execution_enabled=False,
            trading_execution_enabled=False,
            now_utc=now,
            investment_mode=False,
            shariah_evidence_records=[],  # strict overlay
            personal_restrictions_config=default_personal_restrictions_config(),
        )
        d = buy_decision_engine.evaluate(
            _signal(shariah_status="VERIFIED", market_as_of_date=as_of, as_of=as_of),
            ctx,
        )
        assert d.classification == "BLOCKED"
        assert "SHARIAH_EVIDENCE_INCOMPLETE" in d.reason_codes or "SHARIAH_NOT_VERIFIED" in d.reason_codes

    def test_zero_broker_submissions_invariant(self):
        assert STAGE_SUBMISSION_ENABLED is False
