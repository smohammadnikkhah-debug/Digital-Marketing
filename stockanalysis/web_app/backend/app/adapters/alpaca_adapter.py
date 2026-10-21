"""Alpaca Broker Adapter for Backend Integration (Stage D2.3A.2).

Implements BaseBrokerAdapter using AlpacaPaperAdapter.
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.adapters.broker_base import BaseBrokerAdapter, BrokerProvider
from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter, NON_EXECUTING_BUILD_GUARD


class BackendAlpacaAdapter(BaseBrokerAdapter):
    """Backend wrapper for Alpaca Paper Trading Adapter."""

    def __init__(self, adapter: Optional[AlpacaPaperAdapter] = None):
        self._adapter = adapter or AlpacaPaperAdapter(auto_load_env=True)

    @property
    def provider_name(self) -> str:
        return BrokerProvider.ALPACA.value

    @property
    def is_paper(self) -> bool:
        return self._adapter.env == "paper"

    @property
    def is_execution_enabled(self) -> bool:
        # Non-executing build guard is active; execution is disabled
        return not NON_EXECUTING_BUILD_GUARD

    def get_account_summary(self) -> Dict[str, Any]:
        return self._adapter.get_account_summary()

    def get_authenticated_account_id(self) -> str:
        return self._adapter.get_authenticated_account_id()

    def get_positions(self) -> List[Dict[str, Any]]:
        return self._adapter.get_positions()

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._adapter.get_orders(status=status)

    def get_latest_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        return self._adapter.get_latest_quotes(symbols)

    def submit_order(self, *args, **kwargs):
        return self._adapter.submit_order(*args, **kwargs)

    def replace_order(self, *args, **kwargs):
        return self._adapter.replace_order(*args, **kwargs)

    def cancel_order(self, *args, **kwargs):
        return self._adapter.cancel_order(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<BackendAlpacaAdapter wrapped={repr(self._adapter)}>"
