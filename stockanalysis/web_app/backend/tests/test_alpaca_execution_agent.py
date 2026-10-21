"""Automated Test Suite for Alpaca Execution Agent Pipeline (Stage D2.3B Architecture).

Validates the full pre-execution and execution pipeline of AlpacaExecutionAgent:
1. Agent initialization defaults to non-operational.
2. Emergency stop blocks order execution.
3. Execution disabled blocks order execution.
4. Notional cap rejection ($500 max).
5. Zero or negative quantity rejection.
6. Non-regular session rejection (outside 9:30 AM - 4:00 PM ET).
7. Wide IEX spread rejection (> 0.5% threshold).
8. Price collar rejection (> 5% from midpoint).
9. Stale quote rejection (> 30s).
10. Non-executing build guard blocks real API submission.
11. Simulated successful order submission with mock client.
12. Ambiguous network timeout triggers quarantine.
"""
import copy
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure sys.path includes PROJECT_ROOT and BACKEND_DIR
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter
from alpaca_adapter.alpaca_execution_agent import AlpacaExecutionAgent


class TestAlpacaExecutionAgent(unittest.TestCase):
    """Validation test suite for AlpacaExecutionAgent."""

    def setUp(self):
        self.mock_adapter = MagicMock(spec=AlpacaPaperAdapter)
        self.agent = AlpacaExecutionAgent(
            agent_id="test_alpaca_agent",
            adapter=self.mock_adapter,
            max_order_notional=500.0,
            max_spread_pct=0.5,
            price_collar_pct=5.0,
            max_quote_age_seconds=30.0,
        )

    # 1. Agent Initialization Defaults
    def test_01_agent_initialization_defaults_to_non_operational(self):
        """Verifies agent defaults to non-operational with execution disabled and emergency stop active."""
        fresh_agent = AlpacaExecutionAgent(agent_id="fresh_agent", adapter=self.mock_adapter)
        self.assertFalse(fresh_agent.is_operational())

    # 2. Emergency Stop Blocks Order Execution
    def test_02_emergency_stop_blocks_order_execution(self):
        """Verifies emergency stop immediately rejects order before market evaluation."""
        self.agent.emergency_stop = True
        self.agent.execution_enabled = True

        res = self.agent.execute_paper_order(
            order_id=1,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("emergency_stop=True", res["reason"])

    # 3. Execution Disabled Blocks Order Execution
    def test_03_execution_disabled_blocks_order_execution(self):
        """Verifies execution disabled flag immediately blocks order."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = False

        res = self.agent.execute_paper_order(
            order_id=2,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("execution_enabled=False", res["reason"])

    # 4. Notional Cap Rejection ($500 max)
    def test_04_notional_cap_rejection(self):
        """Verifies order exceeding $500 notional is rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        # 3 shares at $200.00 = $600.00 > $500.00
        res = self.agent.execute_paper_order(
            order_id=3,
            symbol="AAPL",
            quantity=3,
            limit_price=200.0,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("exceeds maximum permitted limit of $500.00", res["reason"])

    # 5. Zero or Negative Quantity Rejection
    def test_05_negative_or_zero_quantity_rejection(self):
        """Verifies zero or negative quantity is rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        res_zero = self.agent.execute_paper_order(
            order_id=4,
            symbol="AAPL",
            quantity=0,
            limit_price=200.0,
        )
        self.assertEqual(res_zero["status"], "REJECTED")
        self.assertIn("0 <= 0", res_zero["reason"])

    # 6. Non-Regular Session Rejection
    def test_06_non_regular_session_rejection(self):
        """Verifies orders outside regular hours (9:30 AM - 4:00 PM ET) are rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        # Post-market: 21:00 UTC (17:00 ET) on a Wednesday
        post_market_time = datetime(2026, 10, 21, 21, 0, 0, tzinfo=timezone.utc)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.90,
                "ask": 200.10,
                "quote_timestamp": post_market_time.isoformat(),
            }
        }

        res = self.agent.execute_paper_order(
            order_id=5,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
            now_utc=post_market_time,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("POST_MARKET", res["reason"])

    # 7. Wide IEX Spread Rejection (> 0.5% threshold)
    def test_07_wide_iex_spread_rejection(self):
        """Verifies single-venue quotes with spreads > 0.5% of midpoint are rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        # Regular session: 14:30 UTC (10:30 ET)
        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        # Midpoint $200.00, Spread $2.00 (1.0% > 0.5% threshold)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.00,
                "ask": 201.00,
                "quote_timestamp": reg_time.isoformat(),
            }
        }

        res = self.agent.execute_paper_order(
            order_id=6,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
            now_utc=reg_time,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("Wide spread rejection", res["reason"])

    # 8. Price Collar Rejection (> 5% from midpoint)
    def test_08_price_collar_rejection(self):
        """Verifies limit price deviating > 5% from midpoint is rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        # Midpoint $200.00, Spread $0.20 (0.1% <= 0.5%)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.90,
                "ask": 200.10,
                "quote_timestamp": reg_time.isoformat(),
            }
        }

        # Limit price $220.00 (10% deviation > 5% collar)
        res = self.agent.execute_paper_order(
            order_id=7,
            symbol="AAPL",
            quantity=1,
            limit_price=220.0,
            now_utc=reg_time,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("Price collar violation", res["reason"])

    # 9. Stale Quote Rejection (> 30s)
    def test_09_stale_quote_rejection(self):
        """Verifies quotes older than 30 seconds are rejected."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        # Quote from 45 seconds ago
        stale_time = reg_time - timedelta(seconds=45)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.90,
                "ask": 200.10,
                "quote_timestamp": stale_time.isoformat(),
            }
        }

        res = self.agent.execute_paper_order(
            order_id=8,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
            now_utc=reg_time,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("Stale quote", res["reason"])

    # 10. Non-Executing Build Guard Blocks Real Submission
    def test_10_non_executing_build_guard_active(self):
        """Verifies that even with operational flags and valid quote, build guard blocks execution."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.95,
                "ask": 200.05,
                "quote_timestamp": reg_time.isoformat(),
            }
        }

        # Build guard is active in AlpacaPaperAdapter
        res = self.agent.execute_paper_order(
            order_id=9,
            symbol="AAPL",
            quantity=1,
            limit_price=200.0,
            now_utc=reg_time,
        )
        self.assertEqual(res["status"], "REJECTED")
        self.assertIn("NON-EXECUTING BUILD GUARD ACTIVE", res["reason"])

    # 11. Simulated Successful Order Submission
    def test_11_simulated_successful_order_submission(self):
        """Verifies that with mocked operational state, order submits properly via Alpaca client."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.95,
                "ask": 200.05,
                "quote_timestamp": reg_time.isoformat(),
            }
        }

        mock_trading_client = MagicMock()
        mock_order_response = MagicMock()
        mock_order_response.id = "alpaca_broker_order_12345"
        mock_trading_client.submit_order.return_value = mock_order_response
        self.mock_adapter._get_trading_client.return_value = mock_trading_client

        # Temporarily mock NON_EXECUTING_BUILD_GUARD to False to test submission pipeline
        with patch("alpaca_adapter.alpaca_execution_agent.NON_EXECUTING_BUILD_GUARD", False):
            res = self.agent.execute_paper_order(
                order_id=10,
                symbol="AAPL",
                quantity=1,
                limit_price=200.0,
                now_utc=reg_time,
            )
            self.assertEqual(res["status"], "SUBMITTED")
            self.assertEqual(res["broker_order_id"], "alpaca_broker_order_12345")
            self.assertEqual(res["broker"], "alpaca")
            self.assertEqual(res["quantity"], 1)
            self.assertEqual(res["limit_price"], 200.0)
            mock_trading_client.submit_order.assert_called_once()

    # 12. Ambiguous Network Timeout Triggers Quarantine
    def test_12_ambiguous_network_timeout_triggers_quarantine(self):
        """Verifies network timeout during submission triggers QUARANTINED status."""
        self.agent.emergency_stop = False
        self.agent.execution_enabled = True

        reg_time = datetime(2026, 10, 21, 14, 30, 0, tzinfo=timezone.utc)
        self.mock_adapter.get_latest_quotes.return_value = {
            "AAPL": {
                "source": "ALPACA_IEX",
                "symbol": "AAPL",
                "bid": 199.95,
                "ask": 200.05,
                "quote_timestamp": reg_time.isoformat(),
            }
        }

        mock_trading_client = MagicMock()
        mock_trading_client.submit_order.side_effect = TimeoutError("Connection timed out waiting for gateway")
        self.mock_adapter._get_trading_client.return_value = mock_trading_client

        with patch("alpaca_adapter.alpaca_execution_agent.NON_EXECUTING_BUILD_GUARD", False):
            res = self.agent.execute_paper_order(
                order_id=11,
                symbol="AAPL",
                quantity=1,
                limit_price=200.0,
                now_utc=reg_time,
            )
            self.assertEqual(res["status"], "QUARANTINED")
            self.assertIn("Ambiguous submission outcome", res["reason"])


if __name__ == "__main__":
    unittest.main()
