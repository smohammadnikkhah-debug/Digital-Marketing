"""Transactional IBKR Paper Order Execution Controller (Stage D2.2).

Replaces legacy JSON persistence with transactional PostgreSQL tables:
- stockanalysis.paper_orders (with versioning, optimistic concurrency, and unique client_order_id)
- stockanalysis.paper_order_events (append-only immutable audit trail)
- stockanalysis.paper_execution_claims (atomic distributed lease/claim mechanics)

Key Invariants:
1. STRICTLY NON-EXECUTING IN STAGE D2.2:
   - Order placement to IBKR Gateway socket is disabled and simulated.
2. DATABASE-ENFORCED IDEMPOTENCY:
   - Unique constraint on client_order_id prevents duplicate order proposals.
3. ROW-LEVEL LOCKING & OPTIMISTIC CONCURRENCY:
   - All state transitions use transactional locks and version tracking.
4. APPEND-ONLY AUDIT EVENTS:
   - Immutable event log written in the same transaction as state changes.
5. RECONCILIATION & UNKNOWN QUARANTINE:
   - Ambiguous submission outcomes set requires_manual_reconciliation=True and block auto-retry.
6. CONFIGURABLE RISK POLICY & NY EXCHANGE CALENDAR:
   - US trading day (America/New_York), market holiday and early close checks.
"""
import copy
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional, Any, Tuple, Union
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_

from app.config import (
    DATA_CACHE_DIR,
    IBKR_EXECUTION_ENABLED,
    IBKR_EMERGENCY_STOP,
    ROLLING_PRICE_CACHE_DIR,
    PRICE_CACHE_DIR,
)
from app.models import (
    SystemSetting,
    PaperOrder,
    PaperOrderEvent,
    PaperExecutionClaim,
)
from app.services.ibkr_service import ibkr_service, STALE_THRESHOLD_SECONDS
from app.services.market_data_service import market_data_service, MarketQuote

logger = logging.getLogger("stockanalysis.execution")

ORDERS_SETTING_KEY = "ibkr_paper_orders"
EXECUTION_SETTINGS_KEY = "ibkr_execution_settings"
ORDERS_CACHE_FILE = DATA_CACHE_DIR / "ibkr_paper_orders_cache.json"

NY_TZ = ZoneInfo("America/New_York")

# Paper-Account Identity Validation Invariants (D2.3A.1 & Stage D2 Multi-Broker)
IBKR_PAPER_ACCOUNT_REGEX = re.compile(r"^(DU|DF)[A-Z0-9]{3,28}$")
ALPACA_PAPER_ACCOUNT_REGEX = re.compile(r"^(PA[A-Z0-9]{5,28}|[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})$", re.IGNORECASE)
PAPER_ACCOUNT_REGEX = IBKR_PAPER_ACCOUNT_REGEX  # Backward compatibility alias

# D2.1 & D2.2 Risk Settings Initial Defaults
DEFAULT_MAX_ORDER_NOTIONAL_USD = 500.0
DEFAULT_MAX_DAILY_ORDERS = 5
DEFAULT_MAX_DAILY_NOTIONAL_USD = 2500.0
DEFAULT_MAX_OPEN_ORDERS = 1

# Hard safety ceilings (cannot be bypassed by UI input)
HARD_CEILING_MAX_ORDER_NOTIONAL = 25000.0
HARD_FLOOR_MAX_ORDER_NOTIONAL = 10.0
HARD_CEILING_MAX_DAILY_ORDERS = 50
HARD_FLOOR_MAX_DAILY_ORDERS = 1
HARD_CEILING_MAX_DAILY_NOTIONAL = 100000.0
HARD_FLOOR_MAX_DAILY_NOTIONAL = 50.0
HARD_CEILING_MAX_OPEN_ORDERS = 10
HARD_FLOOR_MAX_OPEN_ORDERS = 1

OPEN_ORDER_STATUSES = {
    "AWAITING_APPROVAL",
    "APPROVED",
    "CLAIMED",
    "SUBMITTING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
    "UNKNOWN",
}

TERMINAL_ORDER_STATUSES = {
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
}


def get_us_trading_date(dt_input: Any) -> str:
    """Converts a UTC datetime or ISO timestamp string to official US trading date (America/New_York) YYYY-MM-DD."""
    if isinstance(dt_input, str):
        clean_str = dt_input.rstrip("Z")
        parsed = datetime.fromisoformat(clean_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    elif isinstance(dt_input, datetime):
        parsed = dt_input if dt_input.tzinfo is not None else dt_input.replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.now(timezone.utc)
    ny_dt = parsed.astimezone(NY_TZ)
    return ny_dt.strftime("%Y-%m-%d")


def get_us_daily_metrics(orders: Union[Dict[str, Any], List[Any]], target_date_ny: str) -> Dict[str, Any]:
    """Calculates cumulative daily metrics for the given US trading day. Supports list of dicts, dict of dicts, or PaperOrder objects."""
    if isinstance(orders, dict):
        order_list = list(orders.values())
    else:
        order_list = list(orders)

    daily_orders = []
    for o in order_list:
        if isinstance(o, dict):
            c_at = o.get("created_at")
            if c_at:
                o_ny = get_us_trading_date(c_at)
                if o_ny == target_date_ny:
                    daily_orders.append(o)
        else:
            c_at = getattr(o, "created_at", None)
            if c_at:
                o_ny = get_us_trading_date(c_at)
                if o_ny == target_date_ny:
                    daily_orders.append(o)

    total_daily_count = len(daily_orders)
    total_daily_notional = 0.0
    for o in daily_orders:
        if isinstance(o, dict):
            total_daily_notional += float(o.get("estimated_notional", 0.0))
        else:
            total_daily_notional += float(getattr(o, "estimated_notional", 0.0))

    open_orders = []
    for o in order_list:
        st = o.get("status") if isinstance(o, dict) else getattr(o, "status", None)
        if st in OPEN_ORDER_STATUSES:
            open_orders.append(o)

    return {
        "us_trading_date": target_date_ny,
        "daily_orders_count": total_daily_count,
        "daily_notional_sum": round(total_daily_notional, 2),
        "open_orders_count": len(open_orders),
    }


class PaperOrderProposal(BaseModel):
    symbol: str = Field(..., description="US equity symbol (e.g. AAPL, NVDA)")
    action: str = Field(..., description="BUY or SELL")
    order_type: str = Field(default="LIMIT", description="LIMIT only")
    quantity: float = Field(..., gt=0, description="Number of shares")
    limit_price: float = Field(..., gt=0, description="Limit price in USD")
    currency: str = Field(default="USD", description="Currency (USD only)")
    broker: str = Field(default="ibkr", description="Target broker ('ibkr' or 'alpaca')")
    account_id: Optional[str] = Field(default=None, description="Paper account ID")
    client_idempotency_key: Optional[str] = Field(default=None, description="Client idempotency key")
    notes: Optional[str] = Field(default="", description="Operator notes or signal reference")
    market_quote: Optional[Dict[str, Any]] = Field(default=None, description="Executable quote for validation")

    @field_validator("broker")
    @classmethod
    def validate_broker(cls, v: str) -> str:
        clean = (v or "ibkr").strip().lower()
        if clean not in ("ibkr", "alpaca"):
            raise ValueError(f"Invalid broker '{v}'. Only 'ibkr' and 'alpaca' are permitted.")
        return clean

    @field_validator("account_id")
    @classmethod
    def validate_paper_account(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean = str(v).strip().upper()
        if clean.startswith("U") and not (clean.startswith("DU") or clean.startswith("DF")):
            raise ValueError(f"CRITICAL SAFETY REJECTION: LIVE account '{clean}' is strictly rejected. Only paper accounts are permitted.")
        if not (IBKR_PAPER_ACCOUNT_REGEX.match(clean) or ALPACA_PAPER_ACCOUNT_REGEX.match(clean)):
            raise ValueError(f"Invalid paper account identifier '{clean}'. Must match IBKR (^(DU|DF)...) or Alpaca (^PA... / UUID).")
        return clean


class OrderExecutionService:
    """Transactional order lifecycle controller and risk evaluation engine."""

    def __init__(self):
        self._lock = threading.RLock()
        self._agent_heartbeats: Dict[str, Dict[str, Any]] = {}
        self._settings_cache: Optional[Dict[str, Any]] = None
        self._orders_cache: Dict[str, Any] = {}

    def get_bound_paper_account_id(self, db: Optional[Session] = None, broker: str = "ibkr") -> Optional[str]:
        """Returns authoritative bound paper account ID for the specified broker."""
        broker_clean = str(broker or "ibkr").strip().lower()
        if broker_clean == "ibkr":
            return ibkr_service.get_bound_paper_account_id(db)
        elif broker_clean == "alpaca":
            if db is not None:
                try:
                    setting = db.query(SystemSetting).filter(SystemSetting.key == "alpaca_bound_paper_account").first()
                    if setting and setting.value:
                        data = json.loads(setting.value)
                        acc = data.get("account_id") or data.get("account_number")
                        if acc:
                            return str(acc).strip().upper()
                except Exception as ex:
                    logger.warning(f"Error querying bound alpaca account from DB: {ex}")
            try:
                from alpaca_adapter.alpaca_paper_adapter import AlpacaPaperAdapter
                adapter = AlpacaPaperAdapter(auto_load_env=True)
                acc = adapter.get_authenticated_account_id()
                if acc:
                    return acc.strip().upper()
            except Exception as ex:
                logger.warning(f"Could not retrieve authenticated Alpaca paper account: {ex}")
            return None
        return None

    # =========================================================================
    # Settings Management (Durably Persisted in Supabase)
    # =========================================================================

    def get_execution_settings(self, db: Session) -> Dict[str, Any]:
        """Loads execution settings with fallback to initial defaults."""
        with self._lock:
            if self._settings_cache is not None:
                return copy.deepcopy(self._settings_cache)

            row = db.query(SystemSetting).filter(SystemSetting.key == EXECUTION_SETTINGS_KEY).first()
            if row and row.value:
                try:
                    data = json.loads(row.value)
                    self._settings_cache = data
                    return copy.deepcopy(data)
                except Exception as exc:
                    logger.error(f"Failed to parse execution settings JSON: {exc}")

            defaults = {
                "emergency_stop": True,
                "execution_enabled": False,
                "approval_timeout_minutes": 15,
                "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
                "max_daily_orders": DEFAULT_MAX_DAILY_ORDERS,
                "max_daily_notional_usd": DEFAULT_MAX_DAILY_NOTIONAL_USD,
                "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
                "manual_approval_required": True,
                "paper_trading_only": True,
                "us_equities_only": True,
                "limit_orders_only": True,
                "long_only": True,
                "max_price_collar_pct": 5.0,
                "stage": "D2.2",
                "is_non_executing": True,
                "history": [],
            }
            self._save_settings_to_db(db, defaults)
            self._settings_cache = defaults
            return copy.deepcopy(defaults)

    def update_execution_settings(self, db: Session, updates: Dict[str, Any], actor: str = "ADMIN") -> Dict[str, Any]:
        """Updates execution settings (emergency stop, execution enabled, risk settings, etc.)."""
        with self._lock:
            current = self.get_execution_settings(db)
            for k, v in updates.items():
                if k not in ("history",):
                    current[k] = v
            self._save_settings_to_db(db, current)
            self._settings_cache = current
            return copy.deepcopy(current)

    def _save_settings_to_db(self, db: Session, settings: Dict[str, Any]):
        """Persists settings into SystemSetting."""
        row = db.query(SystemSetting).filter(SystemSetting.key == EXECUTION_SETTINGS_KEY).first()
        val_str = json.dumps(settings)
        if row:
            row.value = val_str
            row.updated_at = datetime.utcnow()
        else:
            row = SystemSetting(
                key=EXECUTION_SETTINGS_KEY,
                value=val_str,
                updated_at=datetime.utcnow()
            )
            db.add(row)
        db.commit()

    def update_risk_settings(self, db: Session, updates: Dict[str, Any], actor: str = "ADMIN") -> Dict[str, Any]:
        """Atomically updates administrator risk parameters with bounds validation and audit diff history."""
        with self._lock:
            current = self.get_execution_settings(db)
            prev_values = {
                "max_order_notional_usd": current.get("max_order_notional_usd", DEFAULT_MAX_ORDER_NOTIONAL_USD),
                "max_daily_orders": current.get("max_daily_orders", DEFAULT_MAX_DAILY_ORDERS),
                "max_daily_notional_usd": current.get("max_daily_notional_usd", DEFAULT_MAX_DAILY_NOTIONAL_USD),
                "max_open_orders": current.get("max_open_orders", DEFAULT_MAX_OPEN_ORDERS),
            }
            new_values = {}

            # Bounds & Hard Ceilings Validation
            if "max_order_notional_usd" in updates and updates["max_order_notional_usd"] is not None:
                val = float(updates["max_order_notional_usd"])
                if val < HARD_FLOOR_MAX_ORDER_NOTIONAL or val > HARD_CEILING_MAX_ORDER_NOTIONAL:
                    raise ValueError(
                        f"max_order_notional_usd (${val:.2f}) must be between "
                        f"${HARD_FLOOR_MAX_ORDER_NOTIONAL:.2f} and ${HARD_CEILING_MAX_ORDER_NOTIONAL:.2f} USD."
                    )
                new_values["max_order_notional_usd"] = round(val, 2)

            if "max_daily_orders" in updates and updates["max_daily_orders"] is not None:
                val_orders = int(updates["max_daily_orders"])
                if val_orders < HARD_FLOOR_MAX_DAILY_ORDERS or val_orders > HARD_CEILING_MAX_DAILY_ORDERS:
                    raise ValueError(
                        f"max_daily_orders ({val_orders}) must be between "
                        f"{HARD_FLOOR_MAX_DAILY_ORDERS} and {HARD_CEILING_MAX_DAILY_ORDERS} orders."
                    )
                new_values["max_daily_orders"] = val_orders

            if "max_daily_notional_usd" in updates and updates["max_daily_notional_usd"] is not None:
                val_notional = float(updates["max_daily_notional_usd"])
                if val_notional < HARD_FLOOR_MAX_DAILY_NOTIONAL or val_notional > HARD_CEILING_MAX_DAILY_NOTIONAL:
                    raise ValueError(
                        f"max_daily_notional_usd (${val_notional:.2f}) must be between "
                        f"${HARD_FLOOR_MAX_DAILY_NOTIONAL:.2f} and ${HARD_CEILING_MAX_DAILY_NOTIONAL:.2f} USD."
                    )
                new_values["max_daily_notional_usd"] = round(val_notional, 2)

            if "max_open_orders" in updates and updates["max_open_orders"] is not None:
                val_open = int(updates["max_open_orders"])
                if val_open < HARD_FLOOR_MAX_OPEN_ORDERS or val_open > HARD_CEILING_MAX_OPEN_ORDERS:
                    raise ValueError(
                        f"max_open_orders ({val_open}) must be between "
                        f"{HARD_FLOOR_MAX_OPEN_ORDERS} and {HARD_CEILING_MAX_OPEN_ORDERS} orders."
                    )
                new_values["max_open_orders"] = val_open

            # Cross-field consistency
            eff_max_order = new_values.get("max_order_notional_usd", prev_values["max_order_notional_usd"])
            eff_max_daily = new_values.get("max_daily_notional_usd", prev_values["max_daily_notional_usd"])
            if eff_max_order > eff_max_daily:
                raise ValueError(
                    f"Invalid configuration: max_order_notional_usd (${eff_max_order:.2f}) "
                    f"cannot exceed max_daily_notional_usd (${eff_max_daily:.2f})."
                )

            reason = str(updates.get("reason", "")).strip()
            if not reason or len(reason) < 3:
                raise ValueError("A valid reason (minimum 3 characters) is required for audit history.")

            # Record diff in audit history
            diff_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "updated_by": actor,
                "reason": reason,
                "previous_values": prev_values,
                "new_values": new_values,
            }
            history = current.get("history", [])
            history.append(diff_entry)

            current.update(new_values)
            current["history"] = history

            self._save_settings_to_db(db, current)
            self._settings_cache = current
            logger.info("Administrator %s updated risk settings: %s (Reason: '%s')", actor, new_values, reason)
            return copy.deepcopy(current)

    def toggle_emergency_stop(self, db: Session, active: bool, actor: str = "ADMIN", reason: str = "") -> Dict[str, Any]:
        """Engages or disarms the master Emergency Stop (Kill Switch)."""
        with self._lock:
            settings = self.get_execution_settings(db)
            prev_state = settings.get("emergency_stop", True)
            settings["emergency_stop"] = bool(active)

            history = settings.get("history", [])
            history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "updated_by": actor,
                "action": "EMERGENCY_STOP_ENGAGED" if active else "EMERGENCY_STOP_DISARMED",
                "reason": reason or f"Operator toggled emergency stop to {active}",
                "from_state": prev_state,
                "to_state": bool(active),
            })
            settings["history"] = history

            self._save_settings_to_db(db, settings)
            self._settings_cache = settings
            logger.warning("Master Emergency Stop set to %s by %s. Reason: %s", active, actor, reason)
            return copy.deepcopy(settings)

    # =========================================================================
    # Agent Heartbeat & Diagnostics
    # =========================================================================

    def record_agent_heartbeat(
        self, agent_id: str, payload: Dict[str, Any], db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Records agent heartbeat, caching in-memory and persisting durably to system_settings."""
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            record = {
                "agent_id": agent_id,
                "last_heartbeat": now_iso,
                "client_id": payload.get("client_id", 22),
                "gateway_host": payload.get("gateway_host", "127.0.0.1"),
                "gateway_port": payload.get("gateway_port", 4002),
                "gateway_connected": payload.get("gateway_connected", False),
                "managed_accounts": payload.get("managed_accounts", []),
                "active_account": payload.get("active_account", ""),
                "is_paper": payload.get("is_paper", True),
                "non_executing_guard": payload.get("non_executing_guard", True),
                "status": payload.get("status", "HEALTHY"),
                "details": payload.get("details", {}),
            }
            self._agent_heartbeats[agent_id] = record

            # Multi-worker & process-restart safe durable persistence
            if db is not None:
                try:
                    setting_key = f"ibkr_agent_heartbeat:{agent_id}"[:50]
                    setting_val = json.dumps(record)
                    row = db.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
                    if row:
                        row.value = setting_val
                    else:
                        row = SystemSetting(key=setting_key, value=setting_val)
                        db.add(row)
                    db.commit()
                except Exception as ex:
                    logger.warning(f"Could not persist agent heartbeat to database: {ex}")
                    try:
                        db.rollback()
                    except Exception:
                        pass

            return copy.deepcopy(record)

    def get_agent_status(
        self, agent_id: str = "windows_execution_agent_1", db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Returns the diagnostics and status of the execution agent, checking memory and durable storage."""
        with self._lock:
            record = self._agent_heartbeats.get(agent_id)

            # Fallback to durable storage if in-memory cache is empty or after container restart
            if not record and db is not None:
                try:
                    setting_key = f"ibkr_agent_heartbeat:{agent_id}"[:50]
                    row = db.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
                    if row and row.value:
                        loaded = json.loads(row.value)
                        if isinstance(loaded, dict) and "last_heartbeat" in loaded:
                            record = loaded
                            self._agent_heartbeats[agent_id] = record
                except Exception as ex:
                    logger.warning(f"Could not load agent heartbeat from database: {ex}")

            if not record:
                return {
                    "agent_id": agent_id,
                    "is_active": False,
                    "status": "OFFLINE",
                    "gateway_connected": False,
                    "last_heartbeat": None,
                    "staleness_seconds": None,
                    "is_stale": True,
                    "warning_message": "No heartbeat received from Windows Execution Agent.",
                }
            now = datetime.now(timezone.utc)
            hb_dt = datetime.fromisoformat(record["last_heartbeat"].replace("Z", "+00:00"))
            staleness = (now - hb_dt).total_seconds()
            is_stale = staleness > 60.0
            status = "STALE" if is_stale else record.get("status", "HEALTHY")

            out = copy.deepcopy(record)
            out["staleness_seconds"] = round(staleness, 1)
            out["is_stale"] = is_stale
            out["status"] = status
            out["is_active"] = not is_stale
            return out

    # =========================================================================
    # Metrics & Quotas from PostgreSQL
    # =========================================================================

    def get_us_daily_metrics_from_db(self, db: Session, target_date_ny: str) -> Dict[str, Any]:
        """Calculates cumulative daily metrics from PostgreSQL for the US trading day.

        Anti-bypass counting rules:
        - All orders created on target_date_ny count towards daily_orders_count and daily_notional_sum,
          including REJECTED, CANCELLED, EXPIRED, and UNKNOWN.
        - Open orders count includes all active in-flight orders regardless of creation date.
        """
        # Load all orders and filter by America/New_York date conversion
        all_orders = db.query(PaperOrder).all()

        daily_orders = []
        for o in all_orders:
            if o.created_at:
                o_ny = get_us_trading_date(o.created_at)
                if o_ny == target_date_ny:
                    daily_orders.append(o)

        total_daily_count = len(daily_orders)
        total_daily_notional = round(sum(float(o.estimated_notional) for o in daily_orders), 2)

        open_orders = [o for o in all_orders if o.status in OPEN_ORDER_STATUSES]
        total_open_count = len(open_orders)

        return {
            "us_trading_date": target_date_ny,
            "daily_orders_count": total_daily_count,
            "daily_notional_sum": total_daily_notional,
            "open_orders_count": total_open_count,
        }

    # =========================================================================
    # Automated Risk Evaluation Engine
    # =========================================================================

    def evaluate_order_risk(
        self,
        db: Session,
        proposal: PaperOrderProposal,
        settings: Dict[str, Any],
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Performs 13 automated risk invariant checks on proposed order."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        checks = []
        failed_reasons = []

        # 1. Master Emergency Stop
        emergency_stop = settings.get("emergency_stop", True)
        ch_stop = not emergency_stop
        checks.append({
            "name": "emergency_stop",
            "passed": ch_stop,
            "detail": "Emergency Stop disarmed" if ch_stop else "Master Emergency Stop is ACTIVE on server"
        })
        if not ch_stop:
            failed_reasons.append("Emergency Stop is currently active.")

        # 2. Paper Account Binding & Live Brokerage Shield
        target_broker = getattr(proposal, "broker", "ibkr") or "ibkr"
        target_broker = target_broker.strip().lower()
        bound_account = self.get_bound_paper_account_id(db, broker=target_broker)

        if target_broker == "ibkr":
            paper_status = ibkr_service.get_paper_account_status(db)
            account_id = str(paper_status.get("account_id", "")).strip().upper()
            ch_paper = (
                bool(bound_account) and
                bool(IBKR_PAPER_ACCOUNT_REGEX.match(account_id)) and
                account_id == bound_account and
                not (account_id.startswith("U") and not (account_id.startswith("DU") or account_id.startswith("DF")))
            )
        elif target_broker == "alpaca":
            account_id = (proposal.account_id or bound_account or "").strip().upper()
            ch_paper = (
                bool(bound_account) and
                bool(ALPACA_PAPER_ACCOUNT_REGEX.match(account_id)) and
                account_id == bound_account and
                not (account_id.startswith("U") and not (account_id.startswith("DU") or account_id.startswith("DF")))
            )
        else:
            ch_paper = False
            account_id = ""

        checks.append({
            "name": "paper_account_only",
            "passed": ch_paper,
            "detail": f"Account '{account_id}' verified as paper (matches bound {bound_account} on broker {target_broker})" if ch_paper else f"Account '{account_id}' is live, invalid, or does not match bound account '{bound_account}' for {target_broker}"
        })
        if not ch_paper:
            failed_reasons.append(f"Account '{account_id}' is not an authorized paper trading account matching bound account '{bound_account}' for {target_broker}.")

        # 3. US Equities Asset Class
        sym = proposal.symbol.strip().upper()
        ch_sym = len(sym) >= 1 and len(sym) <= 5 and sym.isalpha()
        checks.append({
            "name": "us_equities_only",
            "passed": ch_sym,
            "detail": f"Symbol '{sym}' validated as US equity format" if ch_sym else f"Symbol '{sym}' invalid"
        })
        if not ch_sym:
            failed_reasons.append("Unsupported instrument type or invalid symbol.")

        # 4. Limit Orders Only
        ch_type = proposal.order_type.upper() == "LIMIT"
        checks.append({
            "name": "limit_orders_only",
            "passed": ch_type,
            "detail": "Order type is LIMIT" if ch_type else f"Order type '{proposal.order_type}' rejected; LIMIT required"
        })
        if not ch_type:
            failed_reasons.append("Market and stop orders are not permitted in Stage D2.1.")

        # 5. Long-Only Restriction
        ch_action = proposal.action.upper() in ("BUY", "SELL")
        checks.append({
            "name": "long_only",
            "passed": ch_action,
            "detail": f"Action '{proposal.action}' is permitted" if ch_action else "Invalid action"
        })
        if not ch_action:
            failed_reasons.append("Invalid action; only BUY and SELL are permitted")

        # 6. Holdings Check (No Naked Shorting)
        positions = paper_status.get("positions", [])
        current_holding = 0.0
        for p in positions:
            if p.get("symbol", "").upper() == sym:
                current_holding = float(p.get("position", 0.0))
                break

        if proposal.action.upper() == "SELL":
            ch_holding = current_holding >= proposal.quantity
            checks.append({
                "name": "holdings_available",
                "passed": ch_holding,
                "detail": f"Holding {current_holding:.1f} shares >= sell qty {proposal.quantity:.1f}" if ch_holding
                else f"Insufficient shares: holding {current_holding:.1f} < requested {proposal.quantity:.1f} (Short selling prohibited)"
            })
            if not ch_holding:
                if current_holding <= 0:
                    failed_reasons.append("Short selling is forbidden: No verified long holdings.")
                else:
                    failed_reasons.append("Sell quantity exceeds verified portfolio holdings.")
        else:
            checks.append({
                "name": "holdings_available",
                "passed": True,
                "detail": f"BUY order: current holding is {current_holding:.1f} shares"
            })

        # 7. Single Order Notional Limit
        estimated_notional = round(proposal.quantity * proposal.limit_price, 2)
        max_order_notional = float(settings.get("max_order_notional_usd", DEFAULT_MAX_ORDER_NOTIONAL_USD))
        ch_notional = estimated_notional <= max_order_notional
        checks.append({
            "name": "max_order_notional",
            "passed": ch_notional,
            "detail": f"Est. notional ${estimated_notional:.2f} <= max limit ${max_order_notional:.2f}" if ch_notional
            else f"Est. notional ${estimated_notional:.2f} exceeds max order limit ${max_order_notional:.2f}"
        })
        if not ch_notional:
            failed_reasons.append(f"Order notional (${estimated_notional:.2f}) exceeds single-order risk ceiling (${max_order_notional:.2f}).")

        # 8. Daily Orders Limit (US Trading Day America/New_York)
        target_date_ny = get_us_trading_date(now_utc)
        daily_metrics = self.get_us_daily_metrics_from_db(db, target_date_ny)
        max_daily_orders = int(settings.get("max_daily_orders", DEFAULT_MAX_DAILY_ORDERS))
        current_daily_orders = daily_metrics["daily_orders_count"]
        ch_daily_count = current_daily_orders < max_daily_orders
        checks.append({
            "name": "max_daily_orders",
            "passed": ch_daily_count,
            "detail": f"Daily orders ({current_daily_orders}/{max_daily_orders} for US day {target_date_ny})" if ch_daily_count
            else f"Daily order count reached limit ({current_daily_orders}/{max_daily_orders} for US day {target_date_ny})"
        })
        if not ch_daily_count:
            failed_reasons.append(
                f"Daily order limit reached: Daily new-order count limit ({max_daily_orders}) reached for US trading date {target_date_ny} "
                f"({current_daily_orders} orders recorded)"
            )

        # 9. Aggregate Daily Notional Limit
        max_daily_notional = float(settings.get("max_daily_notional_usd", DEFAULT_MAX_DAILY_NOTIONAL_USD))
        current_daily_notional = daily_metrics["daily_notional_sum"]
        projected_daily_notional = round(current_daily_notional + estimated_notional, 2)
        ch_daily_notional = projected_daily_notional <= max_daily_notional
        checks.append({
            "name": "max_daily_notional",
            "passed": ch_daily_notional,
            "detail": f"Projected daily notional ${projected_daily_notional:.2f} <= limit ${max_daily_notional:.2f}" if ch_daily_notional
            else f"Projected daily notional ${projected_daily_notional:.2f} exceeds limit ${max_daily_notional:.2f}"
        })
        if not ch_daily_notional:
            failed_reasons.append(
                f"Daily aggregate notional limit exceeded: Aggregate daily notional limit (${max_daily_notional:.2f}) would be exceeded "
                f"(current: ${current_daily_notional:.2f}, proposed: ${estimated_notional:.2f})"
            )

        # 10. Simultaneous Open Orders Limit
        max_open_orders = int(settings.get("max_open_orders", DEFAULT_MAX_OPEN_ORDERS))
        current_open_orders = daily_metrics["open_orders_count"]
        ch_open_orders = current_open_orders < max_open_orders
        checks.append({
            "name": "max_open_orders",
            "passed": ch_open_orders,
            "detail": f"Open orders ({current_open_orders}/{max_open_orders})" if ch_open_orders
            else f"Simultaneous open orders reached limit ({current_open_orders}/{max_open_orders})"
        })
        if not ch_open_orders:
            failed_reasons.append(
                f"Simultaneous open order limit reached: Maximum simultaneous open orders limit ({max_open_orders}) reached "
                f"({current_open_orders} open orders active)"
            )

        # 11. USD Cash Solvency (for BUY)
        summary = paper_status.get("summary", {}) if isinstance(paper_status.get("summary"), dict) else {}
        available_cash = float(summary.get("total_cash_value", paper_status.get("total_cash_value", 0.0)))
        if proposal.action.upper() == "BUY":
            ch_cash = available_cash >= estimated_notional
            checks.append({
                "name": "cash_solvency",
                "passed": ch_cash,
                "detail": f"Available cash ${available_cash:.2f} >= required notional ${estimated_notional:.2f}" if ch_cash
                else f"Insufficient USD cash: available ${available_cash:.2f} < required ${estimated_notional:.2f}"
            })
            if not ch_cash:
                failed_reasons.append("Insufficient cash in paper account to cover notional.")
        else:
            checks.append({
                "name": "cash_solvency",
                "passed": True,
                "detail": f"SELL order: cash check skipped (available: ${available_cash:.2f})"
            })

        # 12. Snapshot Freshness & Adapter Connectivity
        is_stale = paper_status.get("is_stale", True)
        gw_conn = paper_status.get("gateway_connection") or paper_status.get("connection_state", "DISCONNECTED")
        ch_fresh = (not is_stale) and (gw_conn in ("CONNECTED", "SYNCED", "OK"))
        checks.append({
            "name": "snapshot_freshness",
            "passed": ch_fresh,
            "detail": "Snapshot fresh and Gateway connected" if ch_fresh
            else f"IBKR snapshot stale ({is_stale}) or Gateway disconnected ({gw_conn})"
        })
        if not ch_fresh:
            if is_stale:
                failed_reasons.append("Market snapshot is stale.")
            if gw_conn not in ("CONNECTED", "SYNCED", "OK"):
                failed_reasons.append("Gateway connection state is DISCONNECTED.")

        # 13. Market Session & Quote Validation (with Price Collar)
        if proposal.market_quote:
            collar_pct = float(settings.get("max_price_collar_pct", 5.0))
            q_res = market_data_service.validate_quote(
                quote_payload=proposal.market_quote,
                limit_price=proposal.limit_price,
                action=proposal.action,
                max_price_collar_pct=collar_pct,
                now_utc=now_utc,
            )
            ch_quote = q_res.is_valid
            checks.append({
                "name": "quote_validation_contract",
                "passed": ch_quote,
                "detail": "Executable quote validated within collar" if ch_quote
                else f"Quote validation failed: {'; '.join(q_res.failure_reasons)}"
            })
            if not ch_quote:
                failed_reasons.extend(q_res.failure_reasons)
        else:
            # Fallback to local snapshot market price if no explicit streaming quote provided
            mkt_price = float(proposal.limit_price)
            for p in positions:
                if p.get("symbol", "").upper() == sym:
                    mkt_price = float(p.get("market_price", proposal.limit_price))
                    break

            collar_pct = float(settings.get("max_price_collar_pct", 5.0))
            if mkt_price > 0:
                dev = abs(proposal.limit_price - mkt_price) / mkt_price * 100.0
                ch_collar = dev <= collar_pct
                checks.append({
                    "name": "price_collar",
                    "passed": ch_collar,
                    "detail": f"Price deviation {dev:.2f}% <= max collar {collar_pct:.1f}%" if ch_collar
                    else f"Limit price ${proposal.limit_price:.2f} deviates {dev:.2f}% from market ${mkt_price:.2f} (> {collar_pct:.1f}%)"
                })
                if not ch_collar:
                    failed_reasons.append(f"Limit price violates price collar (+/-{collar_pct:.1f}% from ${mkt_price:.2f})")
            else:
                checks.append({"name": "price_collar", "passed": True, "detail": "Price collar evaluated"})

        all_passed = len(failed_reasons) == 0
        return {
            "passed": all_passed,
            "evaluated_at": now_utc.isoformat(),
            "checks": checks,
            "failure_reasons": failed_reasons,
            "failed_reasons": failed_reasons,
        }

    # =========================================================================
    # Model ORM Serialization
    # =========================================================================

    @staticmethod
    def _order_to_dict(order: PaperOrder, events: Optional[List[PaperOrderEvent]] = None) -> Dict[str, Any]:
        """Converts PaperOrder ORM object and events into backward-compatible API dictionary."""
        audit_trail = []
        if events:
            for ev in events:
                audit_trail.append({
                    "timestamp": ev.created_at.isoformat() if ev.created_at else "",
                    "action": ev.action,
                    "actor": ev.actor,
                    "from_status": ev.from_status,
                    "to_status": ev.to_status,
                    "reason": ev.reason or "",
                })

        risk_check = None
        if order.risk_check_json:
            try:
                risk_check = json.loads(order.risk_check_json)
            except Exception:
                pass

        execution_report = None
        if order.execution_report_json:
            try:
                execution_report = json.loads(order.execution_report_json)
            except Exception:
                pass

        market_quote = None
        if order.market_quote_json:
            try:
                market_quote = json.loads(order.market_quote_json)
            except Exception:
                pass

        return {
            "order_id": order.order_id,
            "client_idempotency_key": order.client_order_id,
            "account_id": order.account_id,
            "symbol": order.symbol,
            "action": order.action,
            "order_type": order.order_type,
            "quantity": float(order.quantity),
            "limit_price": float(order.limit_price),
            "currency": order.currency,
            "estimated_notional": float(order.estimated_notional),
            "filled_quantity": float(order.filled_quantity),
            "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price is not None else None,
            "status": order.status,
            "version": order.version,
            "proposed_by": order.proposed_by,
            "created_at": order.created_at.isoformat() if order.created_at else "",
            "updated_at": order.updated_at.isoformat() if order.updated_at else "",
            "approved_by": order.approved_by,
            "approved_at": order.approved_at.isoformat() if order.approved_at else None,
            "approval_expires_at": order.approval_expires_at.isoformat() if order.approval_expires_at else None,
            "claimed_by_agent": order.claimed_by_agent,
            "claimed_at": order.claimed_at.isoformat() if order.claimed_at else None,
            "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "requires_manual_reconciliation": bool(order.requires_manual_reconciliation),
            "can_auto_resubmit": bool(order.can_auto_resubmit),
            "notes": order.notes or "",
            "risk_check": risk_check,
            "execution_report": execution_report,
            "market_quote": market_quote,
            "audit_trail": audit_trail,
        }

    # =========================================================================
    # Transactional Order Lifecycle Operations
    # =========================================================================

    def propose_order(self, db: Session, proposal: PaperOrderProposal, actor: str = "ADMIN") -> Dict[str, Any]:
        """Proposes a new paper order and executes risk invariant checks transactionally."""
        now_utc = datetime.now(timezone.utc)
        settings = self.get_execution_settings(db)

        # Explicit Paper Account Binding Check (D2.3A.1 & Stage D2 Multi-Broker)
        target_broker = getattr(proposal, "broker", "ibkr") or "ibkr"
        target_broker = target_broker.strip().lower()
        bound_account = self.get_bound_paper_account_id(db, broker=target_broker)

        if target_broker == "ibkr":
            if not bound_account or not IBKR_PAPER_ACCOUNT_REGEX.match(bound_account):
                raise ValueError(
                    "No valid IBKR paper account is explicitly bound in system settings. "
                    "Automatic fallback to an unbound account is strictly forbidden."
                )
        elif target_broker == "alpaca":
            if not bound_account or not ALPACA_PAPER_ACCOUNT_REGEX.match(bound_account):
                raise ValueError(
                    "No valid Alpaca paper account is authenticated or explicitly bound in system settings. "
                    "Automatic fallback to an unbound account is strictly forbidden."
                )

        if proposal.account_id:
            if proposal.account_id != bound_account:
                raise ValueError(
                    f"Proposed account '{proposal.account_id}' does not match explicitly bound "
                    f"paper account '{bound_account}' for broker '{target_broker}'. Cross-account submission is strictly forbidden."
                )
            target_account = proposal.account_id
        else:
            target_account = bound_account

        # 1. Database-enforced idempotency check
        client_key = proposal.client_idempotency_key or f"prop_{uuid.uuid4().hex[:12]}"
        existing = db.query(PaperOrder).filter(PaperOrder.client_order_id == client_key).first()
        if existing:
            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == existing.order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            logger.info("Idempotent proposal matched existing order %s (key=%s)", existing.order_id, client_key)
            return self._order_to_dict(existing, events)

        # 2. Risk Evaluation
        risk_report = self.evaluate_order_risk(db, proposal, settings, now_utc=now_utc)
        passed = risk_report.get("passed", False)
        status = "AWAITING_APPROVAL" if passed else "REJECTED"

        order_id = f"ORD-{now_utc.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        estimated_notional = round(proposal.quantity * proposal.limit_price, 2)

        # 3. Transactional Insert
        order = PaperOrder(
            order_id=order_id,
            client_order_id=client_key,
            broker=target_broker,
            account_id=target_account,
            symbol=proposal.symbol.strip().upper(),
            action=proposal.action.upper(),
            order_type="LIMIT",
            quantity=float(proposal.quantity),
            limit_price=float(proposal.limit_price),
            currency=proposal.currency.upper(),
            estimated_notional=estimated_notional,
            filled_quantity=0.0,
            status=status,
            version=1,
            proposed_by=actor,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            requires_manual_reconciliation=False,
            can_auto_resubmit=False,
            notes=proposal.notes or "",
            risk_check_json=json.dumps(risk_report),
            market_quote_json=json.dumps(proposal.market_quote) if proposal.market_quote else None,
        )
        db.add(order)

        # Append-only audit events
        ev1 = PaperOrderEvent(
            order_id=order_id,
            event_sequence=1,
            from_status=None,
            to_status="DRAFT",
            action="ORDER_PROPOSED",
            actor=actor,
            reason=proposal.notes or "Order proposal initiated",
            created_at=datetime.utcnow(),
        )
        db.add(ev1)

        ev2 = PaperOrderEvent(
            order_id=order_id,
            event_sequence=2,
            from_status="DRAFT",
            to_status=status,
            action="RISK_CHECK_PASSED" if passed else "RISK_CHECK_FAILED",
            actor="RISK_ENGINE",
            reason="All automated risk invariants passed" if passed else f"Risk invariants failed: {'; '.join(risk_report.get('failed_reasons', []))}",
            created_at=datetime.utcnow(),
        )
        db.add(ev2)

        db.commit()
        db.refresh(order)

        events = [ev1, ev2]
        logger.info("Order %s proposed: status=%s, notional=$%.2f", order_id, status, estimated_notional)
        return self._order_to_dict(order, events)

    def approve_order(self, db: Session, order_id: str, actor: str = "ADMIN") -> Dict[str, Any]:
        """Explicitly approves an order, transitioning AWAITING_APPROVAL -> APPROVED with row lock."""
        now_utc = datetime.now(timezone.utc)
        settings = self.get_execution_settings(db)

        # 1. Row-level locking to prevent concurrent approvals or racing changes
        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        if order.status != "AWAITING_APPROVAL":
            raise ValueError(f"Cannot approve order in status '{order.status}' (AWAITING_APPROVAL required).")

        # Bound paper account identity check (D2.3A.1 & D2.3A.2 hardening)
        target_broker = getattr(order, "broker", "ibkr") or "ibkr"
        bound_account = self.get_bound_paper_account_id(db, broker=target_broker)
        if not bound_account:
            raise ValueError(f"No valid {target_broker} paper account is currently bound in system settings. Approval is rejected.")
        if order.account_id != bound_account:
            raise ValueError(
                f"Cannot approve order {order_id}: order account '{order.account_id}' does not match "
                f"currently bound paper account '{bound_account}' for broker '{target_broker}'. Cross-account approval is strictly forbidden."
            )

        # 2. Emergency Stop Guard
        if settings.get("emergency_stop", True):
            raise ValueError("Master Emergency Stop is ACTIVE on the server. Order approval is prohibited.")

        # 3. Immediate Enforcement of Lowered Limits at Approval Time
        # (An order proposed under prior higher limits MUST be blocked if limits were lowered since proposal)
        notional = float(order.estimated_notional)
        current_max_order = float(settings.get("max_order_notional_usd", DEFAULT_MAX_ORDER_NOTIONAL_USD))
        if notional > current_max_order:
            raise ValueError(
                f"Cannot approve order {order_id}: order notional (${notional:.2f}) exceeds "
                f"current configured single-order maximum limit (${current_max_order:.2f})."
            )

        target_date_ny = get_us_trading_date(now_utc)
        daily_metrics = self.get_us_daily_metrics_from_db(db, target_date_ny)
        current_max_daily_notional = float(settings.get("max_daily_notional_usd", DEFAULT_MAX_DAILY_NOTIONAL_USD))
        if daily_metrics["daily_notional_sum"] > current_max_daily_notional:
            raise ValueError(
                f"Cannot approve order {order_id}: aggregate daily notional (${daily_metrics['daily_notional_sum']:.2f}) "
                f"exceeds currently configured daily limit (${current_max_daily_notional:.2f})."
            )

        current_max_open = int(settings.get("max_open_orders", DEFAULT_MAX_OPEN_ORDERS))
        if daily_metrics["open_orders_count"] > current_max_open:
            raise ValueError(
                f"Cannot approve order {order_id}: simultaneous open orders ({daily_metrics['open_orders_count']}) "
                f"exceeds currently configured open limit ({current_max_open})."
            )

        timeout_minutes = int(settings.get("approval_timeout_minutes", 15))
        expires_at = datetime.utcnow() + timedelta(minutes=timeout_minutes)

        prev_status = order.status
        order.status = "APPROVED"
        order.approved_by = actor
        order.approved_at = datetime.utcnow()
        order.approval_expires_at = expires_at
        order.version += 1
        order.updated_at = datetime.utcnow()

        # Fetch latest sequence
        last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
        new_ev = PaperOrderEvent(
            order_id=order_id,
            event_sequence=last_ev + 1,
            from_status=prev_status,
            to_status="APPROVED",
            action="ORDER_APPROVED",
            actor=actor,
            reason=f"Approved by administrator. Approval valid for {timeout_minutes} minutes.",
            created_at=datetime.utcnow(),
        )
        db.add(new_ev)

        db.commit()
        db.refresh(order)

        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        logger.info("Order %s approved by %s, expires at %s (version=%d)", order_id, actor, expires_at, order.version)
        return self._order_to_dict(order, events)

    def reject_order(self, db: Session, order_id: str, reason: str = "Operator rejected", actor: str = "ADMIN") -> Dict[str, Any]:
        """Explicitly rejects an order in AWAITING_APPROVAL."""
        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        if order.status != "AWAITING_APPROVAL":
            raise ValueError(f"Cannot reject order in status '{order.status}'.")

        prev_status = order.status
        order.status = "REJECTED"
        order.version += 1
        order.updated_at = datetime.utcnow()

        last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
        new_ev = PaperOrderEvent(
            order_id=order_id,
            event_sequence=last_ev + 1,
            from_status=prev_status,
            to_status="REJECTED",
            action="REJECTED",
            actor=actor,
            reason=reason or "Operator rejected",
            created_at=datetime.utcnow(),
        )
        db.add(new_ev)

        db.commit()
        db.refresh(order)

        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        logger.info("Order %s rejected by %s: '%s'", order_id, actor, reason)
        return self._order_to_dict(order, events)

    def cancel_order(self, db: Session, order_id: str, reason: str = "Operator cancelled", actor: str = "ADMIN") -> Dict[str, Any]:
        """Cancels an order before submission to broker."""
        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        if order.status not in ("DRAFT", "AWAITING_APPROVAL", "APPROVED"):
            raise ValueError(f"Cannot cancel order in status '{order.status}'.")

        prev_status = order.status
        order.status = "CANCELLED"
        order.version += 1
        order.updated_at = datetime.utcnow()

        # Release any claim
        active_claim = db.query(PaperExecutionClaim).filter(
            PaperExecutionClaim.order_id == order_id,
            PaperExecutionClaim.is_active == True
        ).first()
        if active_claim:
            active_claim.is_active = False
            active_claim.released_at = datetime.utcnow()
            active_claim.release_reason = f"Cancelled by {actor}"

        last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
        new_ev = PaperOrderEvent(
            order_id=order_id,
            event_sequence=last_ev + 1,
            from_status=prev_status,
            to_status="CANCELLED",
            action="CANCELLED",
            actor=actor,
            reason=reason or "Operator cancelled",
            created_at=datetime.utcnow(),
        )
        db.add(new_ev)

        db.commit()
        db.refresh(order)

        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        logger.info("Order %s cancelled by %s: '%s'", order_id, actor, reason)
        return self._order_to_dict(order, events)

    def claim_order(
        self,
        db: Session,
        order_id: str,
        agent_id: str,
        agent_account: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically claims an approved order for execution by agent using transactional row lock."""
        with self._lock:
            now = datetime.utcnow()
            settings = self.get_execution_settings(db)

            # Row-level locking to prevent concurrent claiming by multiple agents
            order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
            if not order:
                raise ValueError(f"Order '{order_id}' not found.")

            # Validate order account against bound paper account (D2.3A.1 & D2.3A.2)
            target_broker = getattr(order, "broker", "ibkr") or "ibkr"
            bound_account = self.get_bound_paper_account_id(db, broker=target_broker)
            if not bound_account or order.account_id != bound_account:
                raise ValueError(
                    f"Order account '{order.account_id}' does not match active bound paper account '{bound_account}'."
                )

            # Validate claiming agent account identity
            if agent_account is not None:
                clean_agent_acc = str(agent_account).strip().upper()
                if target_broker == "ibkr":
                    if clean_agent_acc.startswith("U") and not (clean_agent_acc.startswith("DU") or clean_agent_acc.startswith("DF")):
                        raise ValueError(f"CRITICAL SAFETY REJECTION: LIVE account '{clean_agent_acc}' is strictly forbidden from claiming orders.")
                    if not IBKR_PAPER_ACCOUNT_REGEX.match(clean_agent_acc):
                        raise ValueError(f"Agent account '{clean_agent_acc}' is not a valid IBKR paper account identifier.")
                elif target_broker == "alpaca":
                    if not ALPACA_PAPER_ACCOUNT_REGEX.match(clean_agent_acc):
                        raise ValueError(f"Agent account '{clean_agent_acc}' is not a valid Alpaca paper account identifier.")
                if clean_agent_acc != order.account_id:
                    raise ValueError(
                        f"Agent account '{clean_agent_acc}' does not match order account '{order.account_id}'. "
                        "Cross-account claiming is strictly forbidden."
                    )

            if order.status != "APPROVED":
                raise ValueError(f"Cannot claim order in status '{order.status}' (APPROVED required).")

            # Approval Expiration check
            if order.approval_expires_at and order.approval_expires_at < now:
                order.status = "EXPIRED"
                order.version += 1
                last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
                ev = PaperOrderEvent(
                    order_id=order_id,
                    event_sequence=last_ev + 1,
                    from_status="APPROVED",
                    to_status="EXPIRED",
                    action="EXPIRED",
                    actor="SYSTEM",
                    reason="Approval expired before claim",
                    created_at=datetime.utcnow(),
                )
                db.add(ev)
                db.commit()
                raise ValueError(f"Order '{order_id}' approval window expired at {order.approval_expires_at.isoformat()}.")

            # Emergency Stop check
            if settings.get("emergency_stop", True):
                raise ValueError("Master Emergency Stop is ACTIVE on the server. Order claim rejected.")

            # Check existing active claim
            existing_claim = db.query(PaperExecutionClaim).filter(
                PaperExecutionClaim.order_id == order_id,
                PaperExecutionClaim.is_active == True
            ).first()
            if existing_claim:
                raise ValueError(f"Order '{order_id}' is already claimed by agent '{existing_claim.agent_id}'.")

            prev_status = order.status
            order.status = "CLAIMED"
            order.claimed_by_agent = agent_id
            order.claimed_at = now
            order.version += 1
            order.updated_at = now

            claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
            claim = PaperExecutionClaim(
                claim_id=claim_id,
                order_id=order_id,
                agent_id=agent_id,
                broker=target_broker,
                claimed_at=now,
                lease_expires_at=now + timedelta(minutes=5),
                is_active=True,
            )
            db.add(claim)

            last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
            new_ev = PaperOrderEvent(
                order_id=order_id,
                event_sequence=last_ev + 1,
                from_status=prev_status,
                to_status="CLAIMED",
                action="ORDER_CLAIMED",
                actor=agent_id,
                reason=f"Claimed by execution agent '{agent_id}' under lease {claim_id}",
                created_at=now,
            )
            db.add(new_ev)

            db.commit()
            db.refresh(order)

            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            logger.info("Order %s claimed by agent %s under claim %s", order_id, agent_id, claim_id)
            return self._order_to_dict(order, events)

    def report_execution_status(
        self,
        db: Session,
        order_id: str,
        agent_id: str,
        target_status: str,
        details: Optional[Dict[str, Any]] = None,
        report_details: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Reports execution agent lifecycle updates (SUBMITTING, SUBMITTED, PARTIALLY_FILLED, FILLED, UNKNOWN, REJECTED)."""
        if details is None:
            details = report_details or {}
        now = datetime.utcnow()
        settings = self.get_execution_settings(db)

        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        # Lease ownership check
        if order.claimed_by_agent != agent_id and target_status not in ("UNKNOWN",):
            raise ValueError(f"Agent '{agent_id}' does not own active lease on order '{order_id}' (owned by '{order.claimed_by_agent}').")

        # Idempotency guard: If already in target status, return success without duplicate event
        if order.status == target_status:
            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            return self._order_to_dict(order, events)

        # Pre-submission Emergency Stop Check
        if target_status in ("SUBMITTING", "SUBMITTED") and settings.get("emergency_stop", True):
            target_status = "UNKNOWN"
            details["quarantine_reason"] = "Emergency Stop engaged during in-flight submission"

        prev_status = order.status
        order.status = target_status
        order.version += 1
        order.updated_at = now

        # Update specific fields based on target status
        if target_status == "SUBMITTED":
            order.submitted_at = now
            order.execution_report_json = json.dumps(details)

        elif target_status == "PARTIALLY_FILLED":
            filled_qty = float(details.get("filled_quantity", order.filled_quantity))
            avg_price = float(details.get("avg_fill_price", order.avg_fill_price or order.limit_price))
            order.filled_quantity = min(float(order.quantity), filled_qty)
            order.avg_fill_price = avg_price
            order.execution_report_json = json.dumps(details)

        elif target_status == "FILLED":
            order.filled_quantity = float(order.quantity)
            order.avg_fill_price = float(details.get("avg_fill_price", order.avg_fill_price or order.limit_price))
            order.completed_at = now
            order.execution_report_json = json.dumps(details)
            # Release claim
            claim = db.query(PaperExecutionClaim).filter(
                PaperExecutionClaim.order_id == order_id,
                PaperExecutionClaim.is_active == True
            ).first()
            if claim:
                claim.is_active = False
                claim.released_at = now
                claim.release_reason = "Order filled"

        elif target_status == "UNKNOWN":
            order.requires_manual_reconciliation = True
            order.can_auto_resubmit = False
            order.execution_report_json = json.dumps(details)

        elif target_status == "REJECTED":
            order.execution_report_json = json.dumps(details)
            claim = db.query(PaperExecutionClaim).filter(
                PaperExecutionClaim.order_id == order_id,
                PaperExecutionClaim.is_active == True
            ).first()
            if claim:
                claim.is_active = False
                claim.released_at = now
                claim.release_reason = "Order rejected"

        last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
        new_ev = PaperOrderEvent(
            order_id=order_id,
            event_sequence=last_ev + 1,
            from_status=prev_status,
            to_status=target_status,
            action=f"REPORT_{target_status}",
            actor=agent_id,
            reason=details.get("reason", f"Reported transition to {target_status}"),
            event_data_json=json.dumps(details),
            created_at=now,
        )
        db.add(new_ev)

        db.commit()
        db.refresh(order)

        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        logger.info("Order %s transitioned %s -> %s by agent %s", order_id, prev_status, target_status, agent_id)
        return self._order_to_dict(order, events)

    def reconcile_order(
        self,
        db: Session,
        order_id: str,
        resolution_status: str,
        reason: str = "Manual administrator reconciliation",
        actor: str = "ADMIN"
    ) -> Dict[str, Any]:
        """Manually reconciles and releases an order from UNKNOWN quarantine."""
        if resolution_status not in ("FILLED", "CANCELLED", "REJECTED"):
            raise ValueError(f"Resolution status must be FILLED, CANCELLED, or REJECTED (got '{resolution_status}').")

        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).with_for_update().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found.")

        if not order.requires_manual_reconciliation and order.status != "UNKNOWN":
            raise ValueError(f"Order '{order_id}' is not in UNKNOWN quarantine state.")

        prev_status = order.status
        order.status = resolution_status
        order.requires_manual_reconciliation = False
        order.can_auto_resubmit = False
        order.version += 1
        order.updated_at = datetime.utcnow()

        if resolution_status == "FILLED":
            order.filled_quantity = float(order.quantity)
            order.completed_at = datetime.utcnow()

        # Release active claim
        claim = db.query(PaperExecutionClaim).filter(
            PaperExecutionClaim.order_id == order_id,
            PaperExecutionClaim.is_active == True
        ).first()
        if claim:
            claim.is_active = False
            claim.released_at = datetime.utcnow()
            claim.release_reason = f"Reconciled as {resolution_status} by {actor}"

        last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order_id).scalar() or 0
        new_ev = PaperOrderEvent(
            order_id=order_id,
            event_sequence=last_ev + 1,
            from_status=prev_status,
            to_status=resolution_status,
            action="RECONCILED",
            actor=actor,
            reason=f"Administrator manual reconciliation: {reason}",
            created_at=datetime.utcnow(),
        )
        db.add(new_ev)

        db.commit()
        db.refresh(order)

        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        logger.info("Order %s manually reconciled %s -> %s by %s: '%s'", order_id, prev_status, resolution_status, actor, reason)
        return self._order_to_dict(order, events)

    def sweep_expired_approvals(self, db: Session) -> int:
        """Sweeps and marks any APPROVED orders whose 15-minute window has elapsed."""
        now = datetime.utcnow()
        expired_orders = db.query(PaperOrder).filter(
            PaperOrder.status == "APPROVED",
            PaperOrder.approval_expires_at < now
        ).with_for_update().all()

        count = 0
        for order in expired_orders:
            prev_status = order.status
            order.status = "EXPIRED"
            order.version += 1
            order.updated_at = now

            last_ev = db.query(func.max(PaperOrderEvent.event_sequence)).filter(PaperOrderEvent.order_id == order.order_id).scalar() or 0
            ev = PaperOrderEvent(
                order_id=order.order_id,
                event_sequence=last_ev + 1,
                from_status=prev_status,
                to_status="EXPIRED",
                action="EXPIRED",
                actor="SYSTEM",
                reason=f"Approval window expired at {order.approval_expires_at.isoformat()}",
                created_at=now,
            )
            db.add(ev)
            count += 1

        # Also sweep expired claims
        expired_claims = db.query(PaperExecutionClaim).filter(
            PaperExecutionClaim.is_active == True,
            PaperExecutionClaim.lease_expires_at < now
        ).all()
        for cl in expired_claims:
            cl.is_active = False
            cl.released_at = now
            cl.release_reason = "Lease expired"

        if count > 0:
            db.commit()
            logger.info("Swept %d expired approved paper order(s).", count)
        return count

    def poll_orders_for_agent(self, db: Session) -> List[Dict[str, Any]]:
        """Returns all currently approved orders ready for execution agent polling."""
        self.sweep_expired_approvals(db)
        settings = self.get_execution_settings(db)
        if settings.get("emergency_stop", True):
            return []

        orders = db.query(PaperOrder).filter(PaperOrder.status == "APPROVED").order_by(PaperOrder.created_at.asc()).all()
        res = []
        for o in orders:
            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == o.order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            res.append(self._order_to_dict(o, events))
        return res

    def poll_approved_orders(self, db: Session, agent_id: str = "windows_execution_agent_1") -> Dict[str, Any]:
        """Wrapper for agent polling returning structured response envelope."""
        orders = self.poll_orders_for_agent(db)
        settings = self.get_execution_settings(db)
        return {
            "success": True,
            "agent_id": agent_id,
            "emergency_stop": settings.get("emergency_stop", True),
            "count": len(orders),
            "orders": orders,
        }

    def list_orders(self, db: Session, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all paper orders with their audit trails."""
        self.sweep_expired_approvals(db)
        query = db.query(PaperOrder)
        if status_filter and status_filter.upper() != "ALL":
            query = query.filter(PaperOrder.status == status_filter.upper())

        orders = query.order_by(PaperOrder.created_at.desc()).all()
        res = []
        for o in orders:
            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == o.order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            res.append(self._order_to_dict(o, events))
        return res

    def get_order(self, db: Session, order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves order detail with full audit trail."""
        self.sweep_expired_approvals(db)
        order = db.query(PaperOrder).filter(PaperOrder.order_id == order_id).first()
        if not order:
            return None
        events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
        return self._order_to_dict(order, events)

    def _load_orders_from_db(self, db: Session) -> Dict[str, Any]:
        """Legacy helper for test suite compatibility: loads orders as a dict keyed by order_id."""
        orders = db.query(PaperOrder).all()
        out = {}
        for o in orders:
            events = db.query(PaperOrderEvent).filter(PaperOrderEvent.order_id == o.order_id).order_by(PaperOrderEvent.event_sequence.asc()).all()
            out[o.order_id] = self._order_to_dict(o, events)
        return out

    def _save_orders_to_db(self, db: Session, orders: Dict[str, Any]) -> None:
        """Legacy helper for test suite compatibility: updates DB from orders dict."""
        for oid, o_data in orders.items():
            order = db.query(PaperOrder).filter(PaperOrder.order_id == oid).first()
            if not order:
                continue
            if "status" in o_data:
                order.status = o_data["status"]
            if "approval_expires_at" in o_data:
                val = o_data["approval_expires_at"]
                if isinstance(val, str):
                    order.approval_expires_at = datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
                elif isinstance(val, datetime):
                    order.approval_expires_at = val.replace(tzinfo=None) if val.tzinfo else val
            if "claimed_by_agent" in o_data:
                order.claimed_by_agent = o_data["claimed_by_agent"]
            order.updated_at = datetime.utcnow()
        db.commit()

    # =========================================================================
    # Legacy Migration Helper (D2.1 JSON -> D2.2 PostgreSQL)
    # =========================================================================

    def migrate_d21_json_orders_to_db(self, db: Session) -> int:
        """Non-destructively migrates legacy D2.1 JSON orders into PostgreSQL tables."""
        row = db.query(SystemSetting).filter(SystemSetting.key == ORDERS_SETTING_KEY).first()
        if not row or not row.value:
            return 0

        try:
            legacy_dict = json.loads(row.value)
            count = 0
            bound_acc = ibkr_service.get_bound_paper_account_id(db) or "DUR257161"
            for oid, o_data in legacy_dict.items():
                existing = db.query(PaperOrder).filter(PaperOrder.order_id == oid).first()
                if not existing:
                    order_broker = str(o_data.get("broker") or "ibkr").lower()
                    target_acc = str(o_data.get("account_id") or bound_acc).strip().upper()
                    if order_broker == "ibkr" and not IBKR_PAPER_ACCOUNT_REGEX.match(target_acc):
                        raise ValueError(f"Legacy order '{oid}' contains invalid paper account '{target_acc}'.")
                    elif order_broker == "alpaca" and not ALPACA_PAPER_ACCOUNT_REGEX.match(target_acc):
                        raise ValueError(f"Legacy order '{oid}' contains invalid paper account '{target_acc}'.")

                    order = PaperOrder(
                        order_id=oid,
                        client_order_id=o_data.get("client_idempotency_key") or oid,
                        broker=order_broker,
                        account_id=target_acc,
                        symbol=o_data.get("symbol", "AAPL"),
                        action=o_data.get("action", "BUY"),
                        order_type="LIMIT",
                        quantity=float(o_data.get("quantity", 1.0)),
                        limit_price=float(o_data.get("limit_price", 100.0)),
                        currency=o_data.get("currency", "USD"),
                        estimated_notional=float(o_data.get("estimated_notional", 100.0)),
                        filled_quantity=float(o_data.get("filled_quantity", 0.0)),
                        status=o_data.get("status", "DRAFT"),
                        version=1,
                        proposed_by=o_data.get("proposed_by", "ADMIN"),
                        created_at=datetime.fromisoformat(o_data["created_at"].replace("Z", "+00:00")) if o_data.get("created_at") else datetime.utcnow(),
                        updated_at=datetime.fromisoformat(o_data["updated_at"].replace("Z", "+00:00")) if o_data.get("updated_at") else datetime.utcnow(),
                        approved_by=o_data.get("approved_by"),
                        notes=o_data.get("notes", ""),
                        risk_check_json=json.dumps(o_data["risk_check"]) if o_data.get("risk_check") else None,
                        execution_report_json=json.dumps(o_data["execution_report"]) if o_data.get("execution_report") else None,
                    )
                    db.add(order)

                    # Reconstruct events
                    seq = 1
                    for audit in o_data.get("audit_trail", []):
                        ev = PaperOrderEvent(
                            order_id=oid,
                            event_sequence=seq,
                            from_status=audit.get("from_status"),
                            to_status=audit.get("to_status", o_data.get("status")),
                            action=audit.get("action", "STATUS_CHANGE"),
                            actor=audit.get("actor", "SYSTEM"),
                            reason=audit.get("reason", ""),
                            created_at=datetime.fromisoformat(audit["timestamp"].replace("Z", "+00:00")) if audit.get("timestamp") else datetime.utcnow(),
                        )
                        db.add(ev)
                        seq += 1
                    count += 1

            if count > 0:
                db.commit()
                logger.info("Migrated %d legacy D2.1 JSON orders into PostgreSQL tables.", count)
            return count
        except Exception as exc:
            db.rollback()
            logger.error(f"Error migrating legacy D2.1 orders: {exc}")
            raise


order_execution_service = OrderExecutionService()
