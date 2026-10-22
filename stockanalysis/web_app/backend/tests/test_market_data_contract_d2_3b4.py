"""Stage D2.3B.4 market-data contract regression tests (safe local / no network).

Covers:
- Max execution spread 0.5%
- Max quote age 30s
- Positive uncrossed bid/ask
- Regular US session gate
- Material future-timestamp rejection
- Separate feed-connectivity vs execution-suitability verdicts
- MSFT 0.751% overnight failure case
- Multi-sample aggregate FAIL when any sample fails
"""
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DM_ROOT = _BACKEND_DIR.parent.parent.parent
if str(_DM_ROOT) not in sys.path:
    sys.path.insert(0, str(_DM_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("ENVIRONMENT", "development")

from app.services.market_data_service import (
    market_data_service,
    DEFAULT_MAX_SPREAD_PCT,
    DEFAULT_MAX_QUOTE_AGE_SECONDS,
)
from alpaca_adapter.alpaca_verification import (
    _evaluate_sample_quotes,
    _aggregate_verdicts,
)


def _regular_now() -> datetime:
    # Wednesday 2026-10-21 14:30 UTC = 10:30 ET (REGULAR)
    return datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)


def _quote(
    symbol: str = "AAPL",
    bid: float = 199.95,
    ask: float = 200.05,
    age_seconds: float = 1.0,
    now: datetime | None = None,
    future_skew_seconds: float = 0.0,
) -> dict:
    now = now or _regular_now()
    if future_skew_seconds > 0:
        q_ts = now + timedelta(seconds=future_skew_seconds)
    else:
        q_ts = now - timedelta(seconds=age_seconds)
    return {
        "source": "ALPACA_IEX",
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "quote_timestamp": q_ts.isoformat(),
        "received_at": now.isoformat(),
        "is_delayed": False,
        "is_synthetic": False,
    }


class TestMarketDataContractD23B4(unittest.TestCase):
    def test_01_max_spread_threshold_is_half_percent(self):
        self.assertEqual(DEFAULT_MAX_SPREAD_PCT, 0.5)
        self.assertEqual(DEFAULT_MAX_QUOTE_AGE_SECONDS, 30.0)

    def test_02_msft_0751_spread_fails_execution_suitability(self):
        """Overnight MSFT case: 0.751% must FAIL execution suitability."""
        # Midpoint 531.315, spread 3.99 ≈ 0.751%
        q = _quote(symbol="MSFT", bid=529.32, ask=533.31, age_seconds=3.89)
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Wide spread rejection" in r for r in res.failure_reasons))
        self.assertGreater(res.spread_pct, 0.5)

    def test_03_spread_at_or_below_half_percent_passes(self):
        # 0.05% spread
        q = _quote(bid=200.00, ask=200.10)
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertTrue(res.is_valid, res.failure_reasons)

    def test_04_stale_quote_over_30s_fails(self):
        q = _quote(age_seconds=45)
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Stale quote" in r for r in res.failure_reasons))

    def test_05_crossed_or_non_positive_bid_ask_fails(self):
        crossed = _quote(bid=201.0, ask=200.0)
        res = market_data_service.evaluate_execution_suitability(crossed, now_utc=_regular_now())
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Crossed" in r for r in res.failure_reasons))

        zero_bid = _quote(bid=0.0, ask=200.0)
        res2 = market_data_service.evaluate_execution_suitability(zero_bid, now_utc=_regular_now())
        self.assertFalse(res2.is_valid)

    def test_06_non_regular_session_fails_execution_but_feed_may_pass(self):
        post = datetime(2026, 10, 21, 21, 0, 0, tzinfo=timezone.utc)  # 17:00 ET
        q = _quote(now=post, age_seconds=1.0)
        exec_res = market_data_service.evaluate_execution_suitability(q, now_utc=post)
        self.assertFalse(exec_res.is_valid)
        self.assertTrue(any("POST_MARKET" in r for r in exec_res.failure_reasons))

        feed = market_data_service.evaluate_feed_connectivity(q, now_utc=post)
        self.assertTrue(feed.is_connected)
        self.assertEqual(feed.verdict, "PASS")

    def test_07_material_future_timestamp_rejected(self):
        q = _quote(future_skew_seconds=5.0)
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertFalse(res.is_valid)
        self.assertTrue(any("future-dated" in r.lower() for r in res.failure_reasons))

        feed = market_data_service.evaluate_feed_connectivity(q, now_utc=_regular_now())
        self.assertFalse(feed.is_connected)

    def test_08_minor_future_skew_within_tolerance_allowed(self):
        q = _quote(future_skew_seconds=0.5)
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertTrue(res.is_valid, res.failure_reasons)

    def test_09_separate_verdicts_on_wide_spread(self):
        """Wide spread fails execution suitability but can still prove feed connectivity."""
        q = _quote(symbol="MSFT", bid=529.32, ask=533.31)
        feed = market_data_service.evaluate_feed_connectivity(q, now_utc=_regular_now())
        exec_res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertTrue(feed.is_connected)
        self.assertEqual(feed.verdict, "PASS")
        self.assertFalse(exec_res.is_valid)

    def test_10_multi_sample_aggregate_fails_when_any_sample_fails(self):
        good = _quote(bid=200.0, ask=200.10)
        bad = _quote(symbol="MSFT", bid=529.32, ask=533.31)
        s1 = _evaluate_sample_quotes({"AAPL": good, "MSFT": good}, 1, _regular_now())
        # Force MSFT bad on sample 2
        s2 = _evaluate_sample_quotes({"AAPL": good, "MSFT": bad}, 2, _regular_now())
        s3 = _evaluate_sample_quotes({"AAPL": good, "MSFT": good}, 3, _regular_now())
        agg = _aggregate_verdicts([s1, s2, s3])
        self.assertEqual(agg["feed_connectivity_verdict"], "PASS")
        self.assertEqual(agg["execution_suitability_verdict"], "FAIL")
        self.assertEqual(agg["overall_execution_suitability"], "FAIL")
        self.assertIn("MSFT", agg["failing_symbols"])

    def test_11_multi_sample_aggregate_pass_requires_all_samples(self):
        good_a = _quote(symbol="AAPL", bid=345.41, ask=345.62)
        good_s = _quote(symbol="SPY", bid=766.33, ask=766.42)
        samples = [
            _evaluate_sample_quotes({"AAPL": good_a, "SPY": good_s}, i, _regular_now())
            for i in (1, 2, 3)
        ]
        agg = _aggregate_verdicts(samples)
        self.assertEqual(agg["sample_count"], 3)
        self.assertEqual(agg["feed_connectivity_verdict"], "PASS")
        self.assertEqual(agg["overall_execution_suitability"], "PASS")

    def test_12_yahoo_rejected_for_execution(self):
        q = _quote()
        q["source"] = "YAHOO_FINANCE"
        res = market_data_service.evaluate_execution_suitability(q, now_utc=_regular_now())
        self.assertFalse(res.is_valid)


if __name__ == "__main__":
    unittest.main()
