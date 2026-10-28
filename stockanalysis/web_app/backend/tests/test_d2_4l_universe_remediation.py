"""D2.4L universe remediation proposal — read-only validation.

Distinguishes legitimate universe exclusions from stale market data.
Does not mutate production universe / DB / historical sessions.
"""
from __future__ import annotations

from datetime import date

from app.services.observation_freshness import assess_scan_freshness
from app.services.ticker_integrity import (
    PROPOSED_RETIRE_FROM_ACTIVE,
    PROPOSED_TICKER_ALIASES,
    investigate_problem_tickers,
    resolve_proposed_alias,
)
from app.services.universe_remediation_proposal import (
    REMEDIATION_ITEMS,
    build_proposal_document,
    filter_active_universe_for_proposal,
    proposed_inactive_tickers,
    write_proposal,
)


def _fresh_row(ticker: str, as_of: str = "2026-10-26") -> dict:
    return {
        "ticker": ticker,
        "market_as_of_date": as_of,
        "data_freshness": "FRESH",
        "provenance_mode": "LIVE_SCAN",
        "signal_source": "V40_SCANNER",
        "signal": "WATCH",
    }


class TestRemediationProposalReadOnly:
    def test_proposal_document_awaiting_approval(self, tmp_path):
        doc = build_proposal_document()
        assert doc["status"] == "PROPOSED_AWAITING_APPROVAL"
        assert doc["production_mutated"] is False
        assert doc["historical_sessions_immutable"] is True
        assert doc["strict_freshness_preserved"] is True
        tickers = {i["ticker"] for i in doc["items"]}
        assert tickers == {"EA", "WBD", "SQ", "MMC", "QUALCOMM"}
        path = write_proposal(tmp_path / "proposal.json")
        assert path.exists()
        assert "PROPOSED_AWAITING_APPROVAL" in path.read_text(encoding="utf-8")

    def test_qualcomm_is_duplicate_of_qcom(self):
        report = investigate_problem_tickers(
            universe_tickers=["QUALCOMM", "QCOM", "AAPL"],
            registry_records={
                "QCOM": {"name": "QUALCOMM Incorporated"},
                "QUALCOMM": {"name": "QUALCOMM"},
            },
        )
        qc = next(f for f in report["findings"] if f["ticker"] == "QUALCOMM")
        assert qc["duplicate_of"] == "QCOM"
        assert qc["proposed_canonical"] == "QCOM"
        assert qc["mutate_production"] is False
        assert resolve_proposed_alias("QUALCOMM")["proposed_canonical"] == "QCOM"

    def test_aliases_include_sq_xyz_and_mmc_mrsh(self):
        assert PROPOSED_TICKER_ALIASES["SQ"] == "XYZ"
        assert PROPOSED_TICKER_ALIASES["MMC"] == "MRSH"
        assert "EA" not in PROPOSED_TICKER_ALIASES
        assert "WBD" not in PROPOSED_TICKER_ALIASES
        assert set(PROPOSED_RETIRE_FROM_ACTIVE) >= {
            "EA",
            "WBD",
            "SQ",
            "MMC",
            "QUALCOMM",
        }

    def test_filter_active_universe_dry_run(self):
        result = filter_active_universe_for_proposal(
            ["AAPL", "EA", "WBD", "SQ", "MMC", "QUALCOMM", "QCOM"]
        )
        assert result["production_mutated"] is False
        assert set(result["excluded"]) == {"EA", "WBD", "SQ", "MMC", "QUALCOMM"}
        assert "QCOM" in result["active_tickers"]
        assert "AAPL" in result["active_tickers"]
        assert "XYZ" in result["active_tickers"]
        assert "MRSH" in result["active_tickers"]
        assert "EA" not in result["active_tickers"]


class TestExclusionVsStaleDistinction:
    def test_exclusions_remove_stale_delisted_allow_fresh(self):
        rows = [_fresh_row(f"T{i}") for i in range(10)]
        rows.append(
            {
                "ticker": "EA",
                "market_as_of_date": "2026-08-04",
                "data_freshness": "INSUFFICIENT_DATA",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "signal": "INSUFFICIENT DATA",
            }
        )
        rows.append(
            {
                "ticker": "WBD",
                "market_as_of_date": "2026-10-05",
                "data_freshness": "INSUFFICIENT_DATA",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "signal": "INSUFFICIENT DATA",
            }
        )
        rows.append({"ticker": "SQ", "signal": "INSUFFICIENT DATA"})
        rows.append({"ticker": "MMC", "signal": "INSUFFICIENT DATA"})
        rows.append({"ticker": "QUALCOMM", "signal": "INSUFFICIENT DATA"})

        baseline = assess_scan_freshness(rows, expected_session=date(2026, 10, 26))
        assert baseline["status"] == "STALE_MIXED"

        remapped = assess_scan_freshness(
            rows,
            expected_session=date(2026, 10, 26),
            exclude_tickers=proposed_inactive_tickers(),
        )
        assert remapped["status"] == "FRESH"
        assert remapped["evaluable_count"] == 10
        assert remapped["matching_expected_count"] == 10
        assert set(remapped["excluded_tickers"]) == {
            "EA",
            "WBD",
            "SQ",
            "MMC",
            "QUALCOMM",
        }

    def test_stale_active_ticker_still_stale_after_exclusions(self):
        rows = [_fresh_row(f"T{i}") for i in range(8)]
        rows.append(_fresh_row("AAPL", as_of="2026-10-20"))  # stale but still listed
        rows.append(
            {
                "ticker": "EA",
                "market_as_of_date": "2026-08-04",
                "signal": "INSUFFICIENT DATA",
            }
        )
        remapped = assess_scan_freshness(
            rows,
            expected_session=date(2026, 10, 26),
            exclude_tickers=["EA"],
        )
        assert remapped["status"] == "STALE_MIXED"
        assert remapped["excluded_tickers"] == ["EA"]
        assert remapped["evaluable_count"] == 9
        assert remapped["matching_expected_count"] == 8

    def test_each_item_has_evidence_and_recommendation(self):
        for item in REMEDIATION_ITEMS:
            assert item["recommendation"]
            assert item["evidence"]
            assert item["preserve_historical_ticker"] == item["ticker"]
            assert item["action_if_approved"]
