"""Stage D2.3B.6 — freshness aggregation, reliability metrics, timezone/session helpers."""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent
for _root in (_BACKEND_DIR.parent.parent.parent, _BACKEND_DIR.parent.parent):
    if (_root / "alpaca_adapter").exists() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("ENVIRONMENT", "development")

from alpaca_adapter.alpaca_verification import (
    _aggregate_verdicts,
    _evaluate_sample_quotes,
    _freshness_pass_from_payload,
    build_evidence_from_samples,
    compute_symbol_reliability,
    reprocess_evidence_file,
)
from alpaca_adapter.schedule_d2_3b6_sessions import build_plan, next_us_trading_day
from app.services.market_data_service import market_data_service


def _regular_now() -> datetime:
    return datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)


def _q(sym: str, bid: float, ask: float, age: float = 1.0, now: datetime | None = None) -> dict:
    now = now or _regular_now()
    q_ts = now - timedelta(seconds=age)
    return {
        "symbol": sym,
        "source": "ALPACA_IEX",
        "feed": "iex",
        "bid": bid,
        "ask": ask,
        "midpoint": (bid + ask) / 2.0,
        "spread": ask - bid,
        "quote_timestamp": q_ts.isoformat(),
        "received_at": now.isoformat(),
        "is_delayed": False,
        "is_synthetic": False,
        "is_two_sided": True,
        "meets_30s_freshness": age <= 30,
    }


class TestFreshnessAggregationD236(unittest.TestCase):
    def test_01_freshness_true_when_spread_fails(self):
        """Historical bug: wide spread must not force all_fresh_within_30s=false."""
        now = _regular_now()
        # MSFT-like wide spread, fresh age
        wide = _q("MSFT", 529.32, 533.31, age=3.0, now=now)
        tight = _q("SPY", 760.59, 760.63, age=0.5, now=now)
        sample = _evaluate_sample_quotes(
            {"MSFT": wide, "SPY": tight}, 1, now, expected_symbols=["MSFT", "SPY"]
        )
        self.assertEqual(sample["execution_suitability_verdict"], "FAIL")
        self.assertTrue(sample["all_fresh_within_30s"])
        agg = _aggregate_verdicts([sample], ["MSFT", "SPY"])
        self.assertTrue(agg["all_fresh_within_30s"])
        self.assertEqual(agg["overall_execution_suitability"], "FAIL")
        evidence = build_evidence_from_samples([sample], ["MSFT", "SPY"])
        self.assertTrue(evidence["execution_freshness_contract"]["all_fresh_within_30s"])
        self.assertEqual(evidence["execution_freshness_contract"]["verdict"], "PASS")
        self.assertEqual(
            evidence["execution_suitability_contract"]["overall_execution_suitability"], "FAIL"
        )

    def test_02_freshness_false_on_stale_independent_of_spread(self):
        now = _regular_now()
        stale = _q("AAPL", 200.0, 200.10, age=45.0, now=now)
        sample = _evaluate_sample_quotes({"AAPL": stale}, 1, now, expected_symbols=["AAPL"])
        self.assertFalse(sample["all_fresh_within_30s"])
        agg = _aggregate_verdicts([sample], ["AAPL"])
        self.assertFalse(agg["all_fresh_within_30s"])

    def test_03_missing_timestamp_fail_closed(self):
        payload = {
            "received": True,
            "quote": {"bid": 1, "ask": 2},
            "execution_suitability": {
                "failure_reasons": [],
                "quote_age_seconds": None,
            },
        }
        ok, age = _freshness_pass_from_payload(payload)
        self.assertFalse(ok)
        self.assertIsNone(age)

    def test_04_unparseable_timestamp_fail_closed(self):
        payload = {
            "received": True,
            "quote": {"quote_timestamp": "not-a-time"},
            "execution_suitability": {
                "failure_reasons": ["Unparseable quote timestamp 'not-a-time': boom"],
                "quote_age_seconds": None,
            },
        }
        self.assertFalse(_freshness_pass_from_payload(payload)[0])

    def test_05_spread_boundary_half_percent(self):
        now = _regular_now()
        # Exactly 0.5%: midpoint 200, spread 1.0
        at_limit = _q("AAPL", 199.5, 200.5, age=1.0, now=now)
        over = _q("AAPL", 199.4, 200.6, age=1.0, now=now)
        s_ok = _evaluate_sample_quotes({"AAPL": at_limit}, 1, now, ["AAPL"])
        s_bad = _evaluate_sample_quotes({"AAPL": over}, 1, now, ["AAPL"])
        self.assertEqual(s_ok["execution_suitability_verdict"], "PASS")
        self.assertEqual(s_bad["execution_suitability_verdict"], "FAIL")


class TestSymbolReliabilityD236(unittest.TestCase):
    def test_01_pass_rates_exclude_missing_samples(self):
        now = _regular_now()
        good = _evaluate_sample_quotes(
            {"AAPL": _q("AAPL", 200, 200.1, now=now)}, 1, now, ["AAPL"]
        )
        missing = _evaluate_sample_quotes({}, 2, now, ["AAPL"])
        rel = compute_symbol_reliability([good, missing], ["AAPL"])["AAPL"]
        self.assertEqual(rel["samples_attempted"], 2)
        self.assertEqual(rel["samples_received"], 1)
        self.assertEqual(rel["samples_missing_or_invalid"], 1)
        self.assertEqual(rel["execution_suitability_pass_count"], 1)
        self.assertEqual(rel["execution_suitability_pass_pct"], 100.0)

    def test_02_historical_d235_reprocess_freshness_true(self):
        path = (
            Path(__file__).resolve().parents[3]
            / "alpaca_adapter"
            / "evidence"
            / "iex_validation_20261024_0045.json"
        )
        if not path.exists():
            # DM layout: parents[3] is stockanalysis; go up to Digital Marketing
            path = (
                Path(__file__).resolve().parents[4]
                / "alpaca_adapter"
                / "evidence"
                / "iex_validation_20261024_0045.json"
            )
        if not path.exists():
            self.skipTest("D2.3B.5 evidence file not present")
        rebuilt = reprocess_evidence_file(path)
        # All individual quotes were fresh; aggregate freshness must be True
        self.assertTrue(rebuilt["execution_freshness_contract"]["all_fresh_within_30s"])
        self.assertEqual(rebuilt["execution_freshness_contract"]["verdict"], "PASS")
        # Overall suitability still FAIL due to wide spreads
        self.assertEqual(
            rebuilt["execution_suitability_contract"]["overall_execution_suitability"], "FAIL"
        )
        aapl = rebuilt["symbol_reliability"]["AAPL"]
        self.assertEqual(aapl["samples_attempted"], 3)
        self.assertEqual(aapl["samples_received"], 3)
        self.assertEqual(aapl["freshness_pass_count"], 3)
        self.assertEqual(aapl["freshness_pass_pct"], 100.0)
        self.assertLess(aapl["execution_suitability_pass_pct"], 100.0)


class TestSessionTimezoneD236(unittest.TestCase):
    def test_01_next_trading_day_skips_weekend(self):
        # Friday -> Monday
        d = next_us_trading_day(date(2026, 10, 23))
        self.assertEqual(d, date(2026, 10, 26))

    def test_02_plan_converts_ny_to_melbourne(self):
        plan = build_plan(date(2026, 10, 26))
        self.assertEqual(plan["us_trading_day"], "2026-10-26")
        s15 = plan["sessions"][0]
        self.assertEqual(s15["session_id"], "open_plus_15")
        self.assertIn("2026-10-26T09:45:00", s15["ny_local"])
        self.assertIn("2026-10-27T00:45:00", s15["melbourne_local"])
        s60 = plan["sessions"][1]
        self.assertIn("2026-10-26T10:30:00", s60["ny_local"])
        self.assertIn("2026-10-27T01:30:00", s60["melbourne_local"])
        s180 = plan["sessions"][2]
        self.assertIn("2026-10-26T12:30:00", s180["ny_local"])
        self.assertIn("2026-10-27T03:30:00", s180["melbourne_local"])

    def test_03_regular_session_and_holiday_detection(self):
        # Regular Wednesday open
        reg = datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc)
        self.assertEqual(market_data_service.get_market_session(reg)[0], "REGULAR")
        # Weekend
        sat = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
        self.assertEqual(market_data_service.get_market_session(sat)[0], "CLOSED")


class TestNoOrderSubmissionD236(unittest.TestCase):
    def test_01_adapter_submit_blocked(self):
        from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter, NON_EXECUTING_BUILD_GUARD

        self.assertTrue(NON_EXECUTING_BUILD_GUARD)
        adapter = AlpacaPaperAdapter(
            api_key="PK_TEST",
            secret_key="SK_TEST",
            trading_url="https://paper-api.alpaca.markets",
            auto_load_env=False,
        )
        with self.assertRaises(PermissionError):
            adapter.submit_order()


if __name__ == "__main__":
    unittest.main()
