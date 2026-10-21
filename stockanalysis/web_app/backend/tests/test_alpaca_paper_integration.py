"""Automated Test Suite for Alpaca Paper Trading Integration (Stage D2.3A.2).

Covers all 15 validation requirements specified for Stage D2.3A.2:
1. Valid Alpaca paper credentials.
2. Invalid or missing credentials.
3. Correct paper endpoint enforcement.
4. Rejection of live Alpaca endpoints.
5. Account balance retrieval.
6. IEX quote retrieval.
7. Stale or missing quotes.
8. One-sided or invalid bid/ask.
9. Broker selection and invalid-provider failure.
10. No automatic fallback to IBKR.
11. Cash-only risk enforcement.
12. Order submission guard.
13. Order cancellation and replacement guards.
14. Secret redaction.
15. Existing IBKR regression tests.
"""
import copy
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from alpaca_adapter.alpaca_paper_adapter import (
    AlpacaPaperAdapter,
    NON_EXECUTING_BUILD_GUARD,
    ALLOWED_PAPER_TRADING_ENDPOINTS,
    DISALLOWED_LIVE_ENDPOINTS,
)
from app.adapters.broker_base import BrokerProvider, BaseBrokerAdapter
from app.adapters.broker_factory import (
    get_paper_broker_adapter,
    get_live_broker_adapter,
    get_configured_paper_broker_name,
)
from app.adapters.alpaca_adapter import BackendAlpacaAdapter
from app.services.market_data_service import (
    market_data_service,
    MarketQuote,
    QuoteValidationResult,
    ALLOWED_EXECUTION_PROVIDERS,
)


class TestAlpacaPaperIntegration(unittest.TestCase):
    """Validation test suite for Alpaca Paper Trading Integration."""

    def setUp(self):
        # Load real test env from alpaca_adapter/.env
        self.adapter = AlpacaPaperAdapter(auto_load_env=True)

    # -------------------------------------------------------------------------
    # 1. Valid Alpaca Paper Credentials
    # -------------------------------------------------------------------------
    def test_01_valid_alpaca_paper_credentials(self):
        """Verifies that valid Alpaca paper credentials authenticate successfully."""
        self.assertTrue(bool(self.adapter.api_key), "ALPACA_API_KEY must be configured.")
        self.assertTrue(bool(self.adapter.secret_key), "ALPACA_SECRET_KEY must be configured.")
        self.assertEqual(self.adapter.env, "paper")

        # Test live authentication call
        summary = self.adapter.get_account_summary()
        self.assertEqual(summary["broker"], "alpaca")
        self.assertEqual(summary["account_type"], "PAPER")
        self.assertEqual(summary["status"], "ACTIVE")
        self.assertEqual(summary["currency"], "USD")

    # -------------------------------------------------------------------------
    # 2. Invalid or Missing Credentials
    # -------------------------------------------------------------------------
    def test_02_invalid_or_missing_credentials(self):
        """Verifies that missing or invalid credentials raise explicit errors."""
        # Missing API Key
        adapter_missing_key = AlpacaPaperAdapter(
            api_key="",
            secret_key="some_secret",
            auto_load_env=False,
        )
        with self.assertRaises(ValueError) as ctx:
            adapter_missing_key.get_account_summary()
        self.assertIn("credentials missing", str(ctx.exception).lower())

        # Missing Secret Key
        adapter_missing_sec = AlpacaPaperAdapter(
            api_key="some_key",
            secret_key="",
            auto_load_env=False,
        )
        with self.assertRaises(ValueError) as ctx:
            adapter_missing_sec.get_account_summary()
        self.assertIn("credentials missing", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # 3. Correct Paper Endpoint Enforcement
    # -------------------------------------------------------------------------
    def test_03_correct_paper_endpoint_enforcement(self):
        """Verifies that only valid paper-api.alpaca.markets endpoints are accepted."""
        for endpoint in ALLOWED_PAPER_TRADING_ENDPOINTS:
            adapter = AlpacaPaperAdapter(
                trading_url=endpoint,
                api_key="PK_TEST",
                secret_key="SEC_TEST",
                auto_load_env=False,
            )
            self.assertIn("paper", adapter.trading_url)

    # -------------------------------------------------------------------------
    # 4. Rejection of Live Alpaca Endpoints
    # -------------------------------------------------------------------------
    def test_04_rejection_of_live_alpaca_endpoints(self):
        """Verifies that live Alpaca endpoints are strictly rejected."""
        for endpoint in DISALLOWED_LIVE_ENDPOINTS:
            with self.assertRaises(ValueError) as ctx:
                AlpacaPaperAdapter(
                    trading_url=endpoint,
                    api_key="PK_TEST",
                    secret_key="SEC_TEST",
                    auto_load_env=False,
                )
            self.assertIn("strictly forbidden", str(ctx.exception))

        # Rejection of non-paper URL
        with self.assertRaises(ValueError) as ctx:
            AlpacaPaperAdapter(
                trading_url="https://arbitrary-broker.com/api",
                api_key="PK_TEST",
                secret_key="SEC_TEST",
                auto_load_env=False,
            )
        self.assertIn("does not contain 'paper'", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Account Balance Retrieval
    # -------------------------------------------------------------------------
    def test_05_account_balance_retrieval(self):
        """Verifies accurate normalized retrieval of account equity, cash, and balances."""
        summary = self.adapter.get_account_summary()
        self.assertIn("equity", summary)
        self.assertIn("cash", summary)
        self.assertIn("buying_power_leveraged", summary)
        self.assertIn("cash_available_for_risk", summary)

        self.assertGreaterEqual(summary["equity"], 0.0)
        self.assertGreaterEqual(summary["cash"], 0.0)
        self.assertEqual(summary["account_id"], "***REDACTED***")
        self.assertFalse(summary["trading_blocked"])

    # -------------------------------------------------------------------------
    # 6. IEX Quote Retrieval
    # -------------------------------------------------------------------------
    def test_06_iex_quote_retrieval(self):
        """Verifies top-of-book quote retrieval for AAPL, MSFT, and SPY from IEX."""
        quotes = self.adapter.get_latest_quotes(["AAPL", "MSFT", "SPY"])
        for sym in ["AAPL", "MSFT", "SPY"]:
            self.assertIn(sym, quotes)
            q = quotes[sym]
            self.assertEqual(q["source"], "ALPACA_IEX")
            self.assertEqual(q["feed"], "iex")
            self.assertFalse(q["is_consolidated_nbbo"])
            self.assertGreater(q["bid"], 0.0)
            self.assertGreater(q["ask"], 0.0)
            self.assertGreaterEqual(q["ask"], q["bid"])
            self.assertIsNotNone(q["midpoint"])
            self.assertIsNotNone(q["quote_timestamp"])

    # -------------------------------------------------------------------------
    # 7. Stale or Missing Quotes
    # -------------------------------------------------------------------------
    def test_07_stale_or_missing_quotes(self):
        """Verifies market data service rejects quotes older than 30 seconds."""
        now_utc = datetime(2026, 10, 21, 14, 0, 0, tzinfo=timezone.utc)  # Regular session Wednesday

        # Stale quote: 60s old (> 30s threshold)
        stale_ts = (now_utc - timedelta(seconds=60)).isoformat()
        payload = {
            "source": "ALPACA_IEX",
            "symbol": "AAPL",
            "bid": 200.0,
            "ask": 200.50,
            "quote_timestamp": stale_ts,
        }
        res = market_data_service.validate_quote(
            payload,
            limit_price=200.25,
            now_utc=now_utc,
            max_quote_age=30.0,
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(any("stale" in f.lower() for f in res.failure_reasons))

        # Fresh quote: 5s old (<= 30s threshold)
        fresh_ts = (now_utc - timedelta(seconds=5)).isoformat()
        payload_fresh = copy.deepcopy(payload)
        payload_fresh["quote_timestamp"] = fresh_ts
        res_fresh = market_data_service.validate_quote(
            payload_fresh,
            limit_price=200.25,
            now_utc=now_utc,
            max_quote_age=30.0,
        )
        self.assertTrue(res_fresh.is_valid)

    # -------------------------------------------------------------------------
    # 8. One-Sided or Invalid Bid/Ask
    # -------------------------------------------------------------------------
    def test_08_one_sided_or_invalid_bid_ask(self):
        """Verifies rejection of one-sided, negative, zero, or crossed quotes."""
        now_utc = datetime(2026, 10, 21, 14, 0, 0, tzinfo=timezone.utc)
        fresh_ts = now_utc.isoformat()

        # Zero Bid
        res1 = market_data_service.validate_quote(
            {"source": "ALPACA_IEX", "symbol": "AAPL", "bid": 0.0, "ask": 200.0, "quote_timestamp": fresh_ts},
            limit_price=200.0,
            now_utc=now_utc,
        )
        self.assertFalse(res1.is_valid)
        self.assertTrue(any("bid" in f.lower() for f in res1.failure_reasons))

        # Crossed Market (Bid > Ask)
        res2 = market_data_service.validate_quote(
            {"source": "ALPACA_IEX", "symbol": "AAPL", "bid": 205.0, "ask": 200.0, "quote_timestamp": fresh_ts},
            limit_price=202.0,
            now_utc=now_utc,
        )
        self.assertFalse(res2.is_valid)
        self.assertTrue(any("crossed" in f.lower() for f in res2.failure_reasons))

    # -------------------------------------------------------------------------
    # 9. Broker Selection and Invalid Provider Failure
    # -------------------------------------------------------------------------
    def test_09_broker_selection_and_invalid_provider_failure(self):
        """Verifies broker factory instantiates valid brokers and fails closed on invalid."""
        # Alpaca
        adapter_alpaca = get_paper_broker_adapter("alpaca")
        self.assertEqual(adapter_alpaca.provider_name, "alpaca")
        self.assertTrue(adapter_alpaca.is_paper)

        # IBKR
        adapter_ibkr = get_paper_broker_adapter("ibkr")
        self.assertEqual(adapter_ibkr.provider_name, "ibkr")
        self.assertTrue(adapter_ibkr.is_paper)

        # Invalid Provider - Fail Closed
        with self.assertRaises(ValueError) as ctx:
            get_paper_broker_adapter("robinhood")
        self.assertIn("Invalid PAPER_BROKER", str(ctx.exception))
        self.assertIn("Fail-closed", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 10. No Automatic Fallback to IBKR
    # -------------------------------------------------------------------------
    def test_10_no_automatic_fallback_to_ibkr(self):
        """Verifies system raises error when Alpaca fails rather than falling back to IBKR."""
        with patch("app.adapters.broker_factory.AlpacaPaperAdapter", side_effect=ValueError("Alpaca credentials missing")):
            with self.assertRaises(RuntimeError) as ctx:
                get_paper_broker_adapter("alpaca")
            self.assertIn("Automatic fallback to IBKR is strictly prohibited", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 11. Cash-Only Risk Enforcement
    # -------------------------------------------------------------------------
    def test_11_cash_only_risk_enforcement(self):
        """Verifies risk calculations use available cash, never leveraged buying power."""
        summary = self.adapter.get_account_summary()
        cash = summary["cash"]
        leveraged_bp = summary["buying_power_leveraged"]
        cash_for_risk = summary["cash_available_for_risk"]

        # In Alpaca margin accounts, leveraged buying power is 4x cash ($400,000 for $100,000 cash)
        self.assertGreater(leveraged_bp, cash)
        # Cash available for risk must strictly equal cash, rejecting leverage
        self.assertEqual(cash_for_risk, cash)

    # -------------------------------------------------------------------------
    # 12. Order Submission Guard
    # -------------------------------------------------------------------------
    def test_12_order_submission_guard(self):
        """Verifies that order submission raises PermissionError at code level."""
        self.assertTrue(NON_EXECUTING_BUILD_GUARD)
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.submit_order(symbol="AAPL", qty=1, side="buy")
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", str(ctx.exception))

        # Also via BackendAlpacaAdapter
        backend_adapter = BackendAlpacaAdapter(self.adapter)
        with self.assertRaises(PermissionError) as ctx:
            backend_adapter.submit_order(symbol="AAPL", qty=1, side="buy")
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 13. Order Cancellation and Replacement Guards
    # -------------------------------------------------------------------------
    def test_13_order_cancellation_and_replacement_guards(self):
        """Verifies that replace and cancel methods raise PermissionError."""
        with self.assertRaises(PermissionError) as ctx:
            self.adapter.replace_order(order_id="test-123", qty=2)
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            self.adapter.cancel_order(order_id="test-123")
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            self.adapter.cancel_all_orders()
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", str(ctx.exception))

        with self.assertRaises(PermissionError) as ctx:
            self.adapter.transfer_funds(amount=1000)
        self.assertIn("Fund transfers and account funding are strictly prohibited", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 14. Secret Redaction
    # -------------------------------------------------------------------------
    def test_14_secret_redaction(self):
        """Verifies that API keys, secrets, and account numbers are never exposed in string outputs."""
        adapter_repr = repr(self.adapter)
        # Check raw keys are NOT in repr
        self.assertNotIn(self.adapter.api_key, adapter_repr)
        self.assertNotIn(self.adapter.secret_key, adapter_repr)
        self.assertIn("CONFIGURED", adapter_repr)

        # Check account summary masks account ID
        summary = self.adapter.get_account_summary()
        self.assertEqual(summary["account_id"], "***REDACTED***")
        self.assertNotIn("id", summary.get("raw_account", {}))

    # -------------------------------------------------------------------------
    # 15. Existing IBKR Regression Tests
    # -------------------------------------------------------------------------
    def test_15_existing_ibkr_regression_tests(self):
        """Verifies that existing IBKR adapter and services remain fully intact."""
        from app.services.ibkr_service import ibkr_service
        self.assertIsNotNone(ibkr_service)

        from app.adapters.ibkr_adapter import IBKRPaperReader
        reader = IBKRPaperReader()
        with self.assertRaises(PermissionError):
            reader.placeOrder(1, None, None)
        with self.assertRaises(PermissionError):
            reader.cancelOrder(1, None)
        with self.assertRaises(PermissionError):
            reader.reqGlobalCancel()


if __name__ == "__main__":
    unittest.main()
