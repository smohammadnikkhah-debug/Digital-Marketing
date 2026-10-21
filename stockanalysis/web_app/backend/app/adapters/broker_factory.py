"""Broker Factory and Registry (Stage D2.3A.2).

Provides decoupled factory methods to instantiate configured broker adapters.

Invariants:
1. EXPLICIT SELECTION: Selected via environment variables (PAPER_BROKER, LIVE_BROKER).
2. FAIL-CLOSED: Rejects unsupported or malformed broker configurations.
3. NO AUTOMATIC FALLBACK: If Alpaca is configured but fails, raises error immediately.
   Never silently falls back to IBKR or any other broker.
4. SAFE DEFAULTS: Execution is disabled by default (TRADING_EXECUTION_ENABLED=False).
"""
import os
import sys
import logging
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.adapters.broker_base import BaseBrokerAdapter, BrokerProvider
from app.adapters.alpaca_adapter import BackendAlpacaAdapter
from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter

logger = logging.getLogger("BrokerFactory")

SUPPORTED_PAPER_BROKERS = {
    BrokerProvider.ALPACA.value,
    BrokerProvider.IBKR.value,
}

SUPPORTED_LIVE_BROKERS = {
    BrokerProvider.IBKR.value,
}


def get_configured_paper_broker_name() -> str:
    """Returns the configured paper broker name from environment."""
    return os.getenv("PAPER_BROKER", "alpaca").strip().lower()


def get_configured_live_broker_name() -> str:
    """Returns the configured live broker name from environment."""
    return os.getenv("LIVE_BROKER", "ibkr").strip().lower()


def is_trading_execution_enabled() -> bool:
    """Returns whether trading execution is globally enabled."""
    return os.getenv("TRADING_EXECUTION_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def is_live_trading_enabled() -> bool:
    """Returns whether live trading execution is enabled."""
    return os.getenv("LIVE_TRADING_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def get_paper_broker_adapter(
    broker_name: Optional[str] = None,
    alpaca_kwargs: Optional[dict] = None,
) -> BaseBrokerAdapter:
    """Instantiates and returns the configured paper broker adapter.

    Raises:
        ValueError: If broker_name is unrecognized or unsupported.
        RuntimeError: If configuration or initialization fails.
    """
    selected = (broker_name or get_configured_paper_broker_name()).strip().lower()

    if selected not in SUPPORTED_PAPER_BROKERS:
        raise ValueError(
            f"Configuration Error: Invalid PAPER_BROKER '{selected}'. "
            f"Supported providers: {sorted(SUPPORTED_PAPER_BROKERS)}. "
            "Fail-closed: No automatic fallback permitted."
        )

    if selected == BrokerProvider.ALPACA.value:
        try:
            adapter = AlpacaPaperAdapter(**(alpaca_kwargs or {}), auto_load_env=True)
            return BackendAlpacaAdapter(adapter=adapter)
        except Exception as exc:
            # STRICT REQUIREMENT: Never silently fall back to IBKR!
            logger.error(f"Alpaca adapter initialization failed: {exc}")
            raise RuntimeError(
                f"Alpaca paper adapter configuration failure: {exc}. "
                "Automatic fallback to IBKR is strictly prohibited."
            ) from exc

    elif selected == BrokerProvider.IBKR.value:
        # IBKR Paper Adapter placeholder/wrapper
        from app.adapters.ibkr_adapter import IBKRPaperReader
        # In StockAnalysis, IBKR paper adapter communicates via push API or local gateway
        class BackendIBKRAdapter(BaseBrokerAdapter):
            @property
            def provider_name(self) -> str:
                return BrokerProvider.IBKR.value

            @property
            def is_paper(self) -> bool:
                return True

            @property
            def is_execution_enabled(self) -> bool:
                return False

            def get_account_summary(self):
                from app.services.ibkr_service import ibkr_service
                return ibkr_service.get_cached_snapshot() or {"status": "NO_SNAPSHOT"}

            def get_positions(self):
                from app.services.ibkr_service import ibkr_service
                snap = ibkr_service.get_cached_snapshot()
                return snap.get("positions", []) if snap else []

            def get_orders(self, status=None):
                return []

            def get_latest_quotes(self, symbols):
                return {}

        return BackendIBKRAdapter()

    raise ValueError(f"Unhandled paper broker: {selected}")


def get_live_broker_adapter(broker_name: Optional[str] = None) -> BaseBrokerAdapter:
    """Instantiates live broker adapter, strictly requiring LIVE_TRADING_ENABLED=True."""
    selected = (broker_name or get_configured_live_broker_name()).strip().lower()

    if not is_live_trading_enabled():
        raise PermissionError(
            "CRITICAL SECURITY GUARD: Live trading is strictly disabled. "
            "LIVE_TRADING_ENABLED must be explicitly set to 'true'."
        )

    if selected not in SUPPORTED_LIVE_BROKERS:
        raise ValueError(
            f"Unsupported live broker '{selected}'. Supported live providers: {sorted(SUPPORTED_LIVE_BROKERS)}."
        )

    raise NotImplementedError("Live broker execution is not implemented or authorized in Stage D2.3A.2.")
