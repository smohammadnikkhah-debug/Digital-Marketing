"""Broker Provider Abstraction Base (Stage D2.3A.2).

Defines the unified broker interface for StockAnalysis.
Supports multi-broker architectures (Alpaca for Paper Trading, IBKR for Production).

Guarantees:
1. Code-level read-only guards: Any mutation method raises PermissionError by default.
2. Explicit provider identification: 'alpaca' or 'ibkr'.
3. Fail-closed error handling: No implicit or silent fallbacks.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any


class BrokerProvider(str, Enum):
    ALPACA = "alpaca"
    IBKR = "ibkr"


class BaseBrokerAdapter(ABC):
    """Abstract base class for all broker adapter implementations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the broker provider name ('alpaca' or 'ibkr')."""
        pass

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """True if connected to paper trading environment."""
        pass

    @property
    @abstractmethod
    def is_execution_enabled(self) -> bool:
        """True if order execution is enabled."""
        pass

    @abstractmethod
    def get_account_summary(self) -> Dict[str, Any]:
        """Returns normalized account balance, status, equity, and cash."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns list of normalized active positions."""
        pass

    @abstractmethod
    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns list of normalized orders."""
        pass

    @abstractmethod
    def get_latest_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Returns normalized top-of-book market quotes."""
        pass

    # -------------------------------------------------------------------------
    # Default Code-Level Guards Against Mutation
    # -------------------------------------------------------------------------

    def submit_order(self, *args, **kwargs):
        """Strict default guard: blocks order submission."""
        raise PermissionError(
            f"EXECUTION GUARD: Order submission is disabled on broker '{self.provider_name}'."
        )

    def replace_order(self, *args, **kwargs):
        """Strict default guard: blocks order modification."""
        raise PermissionError(
            f"EXECUTION GUARD: Order replacement is disabled on broker '{self.provider_name}'."
        )

    def cancel_order(self, *args, **kwargs):
        """Strict default guard: blocks order cancellation."""
        raise PermissionError(
            f"EXECUTION GUARD: Order cancellation is disabled on broker '{self.provider_name}'."
        )
