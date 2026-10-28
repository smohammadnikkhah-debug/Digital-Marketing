"""Document STALE_MIXED when a minority of scan rows have older as-of dates."""
from __future__ import annotations

from datetime import date

from app.services.observation_freshness import assess_scan_freshness
from app.services.ticker_integrity import PROPOSED_TICKER_ALIASES, resolve_proposed_alias


class TestStaleMixedFromPartialAsOf:
    def test_two_old_asof_among_mostly_fresh_is_stale_mixed(self):
        rows = [
            {
                "ticker": f"T{i}",
                "market_as_of_date": "2026-10-26",
                "data_freshness": "FRESH",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "signal": "WATCH",
            }
            for i in range(10)
        ]
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
        # Missing-price stubs have no as_of — do not alone create STALE_MIXED
        rows.append(
            {
                "ticker": "SQ",
                "signal": "INSUFFICIENT DATA",
                "validation_status": "MISSING_PRICE_DATA",
            }
        )
        report = assess_scan_freshness(rows, expected_session=date(2026, 10, 26))
        assert report["status"] == "STALE_MIXED"
        assert report["matching_expected_count"] == 10
        assert report["evaluable_count"] == 12
        assert report["fabricated_freshness"] is False

    def test_all_matching_is_fresh(self):
        rows = [
            {
                "ticker": "AAPL",
                "market_as_of_date": "2026-10-26",
                "data_freshness": "FRESH",
                "provenance_mode": "LIVE_SCAN",
                "signal_source": "V40_SCANNER",
                "signal": "BUY CANDIDATE",
            }
        ]
        report = assess_scan_freshness(rows, expected_session=date(2026, 10, 26))
        assert report["status"] == "FRESH"

    def test_proposed_aliases_read_only(self):
        assert PROPOSED_TICKER_ALIASES["SQ"] == "XYZ"
        assert PROPOSED_TICKER_ALIASES["QUALCOMM"] == "QCOM"
        r = resolve_proposed_alias("SQ")
        assert r["proposed_canonical"] == "XYZ"
        assert r["mutate_production"] is False
