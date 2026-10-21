"""IBKR Paper Trading Read-Only Integration Service.

Manages receiving, validating, persisting, and evaluating the state of
the local Windows IBKR Paper Trading Gateway adapter.

Guarantees:
1. Strict read-only integration (no order placement, modification, or cancellation).
2. Segregation from live user portfolio and historical V4.0 quantitative baseline backtest.
3. Durable persistence via existing SystemSetting model (zero database schema migrations).
4. Automated staleness detection (>300s threshold) and explicit connection states.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import DATA_CACHE_DIR
from app.models import SystemSetting

logger = logging.getLogger("stockanalysis.ibkr")

IBKR_SNAPSHOT_ADVISORY_LOCK_ID = 0x53415F49424B52  # 91538337776450 ('SA_IBKR')


IBKR_CACHE_FILE = DATA_CACHE_DIR / "ibkr_paper_cache.json"
STALE_THRESHOLD_SECONDS = 300  # 5 minutes


class IBKRPositionSchema(BaseModel):
    symbol: str
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    position: float
    avg_cost: float
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None


try:
    from pydantic import field_validator
    def validate_paper_field(v):
        if str(v).strip().upper() != "PAPER":
            raise ValueError(
                f"Invalid account type '{v}'. This integration strictly accepts 'PAPER' trading data only. "
                "Live trading accounts are forbidden."
            )
        return "PAPER"

    def validate_account_id_field(v):
        acc = str(v).strip().upper()
        if acc.startswith("U") and not (acc.startswith("DU") or acc.startswith("DF") or "TEST" in acc or "MOCK" in acc or "PAPER" in acc):
            raise ValueError(
                f"CRITICAL SECURITY REJECTION: Account ID '{v}' appears to be a LIVE brokerage account. "
                "Only paper trading accounts (starting with 'DU') are permitted."
            )
        return v

    _field_val_type = field_validator("account_type")(validate_paper_field)
    _field_val_acc = field_validator("account_id")(validate_account_id_field)
except ImportError:
    from pydantic import validator
    def validate_paper_field(cls, v):
        if str(v).strip().upper() != "PAPER":
            raise ValueError(
                f"Invalid account type '{v}'. This integration strictly accepts 'PAPER' trading data only. "
                "Live trading accounts are forbidden."
            )
        return "PAPER"

    def validate_account_id_field(cls, v):
        acc = str(v).strip().upper()
        if acc.startswith("U") and not (acc.startswith("DU") or acc.startswith("DF") or "TEST" in acc or "MOCK" in acc or "PAPER" in acc):
            raise ValueError(
                f"CRITICAL SECURITY REJECTION: Account ID '{v}' appears to be a LIVE brokerage account. "
                "Only paper trading accounts (starting with 'DU') are permitted."
            )
        return v

    _field_val_type = validator("account_type")(validate_paper_field)
    _field_val_acc = validator("account_id")(validate_account_id_field)


class IBKRPaperSyncPayload(BaseModel):
    account_id: str = Field(..., description="IBKR Paper Account identifier (e.g. DU123456)")
    account_type: str = Field(..., description="Must strictly be 'PAPER'")
    currency: str = Field(default="AUD", description="Base account currency")
    net_liquidation: float = Field(default=0.0, ge=0.0, description="Net liquidation must be non-negative")
    total_cash_value: float = Field(default=0.0)
    buying_power: float = Field(default=0.0)
    positions: List[IBKRPositionSchema] = Field(default_factory=list)
    connection_state: str = Field(default="CONNECTED", description="CONNECTED, CONNECTING, DISCONNECTED, ERROR")
    error_message: Optional[str] = None
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of snapshot")
    adapter_version: str = Field(default="1.0.0")
    gateway_managed_accounts: List[str] = Field(default_factory=list, description="Authenticated accounts reported by IBKR Gateway managedAccounts")
    gateway_account_type: Optional[str] = Field(default="PAPER", description="Account type confirmed by IB Gateway")
    gateway_port: Optional[int] = Field(default=4002, description="IB Gateway local socket port (4002/7497 paper)")

    _check_paper = _field_val_type
    _check_acc = _field_val_acc


class IBKRService:
    """Service handling IBKR paper account state, caching, and staleness evaluation."""

    SETTING_KEY = "ibkr_paper_snapshot"
    BOUND_ACCOUNT_KEY = "ibkr_bound_paper_account"
    ENABLE_SETTING_KEY = "ibkr_paper_enabled"
    _admission_lock = threading.Lock()

    def is_integration_enabled(self, db: Optional[Session] = None) -> bool:
        """Determines if paper trading integration is enabled via env or database setting."""
        from app.config import IBKR_PAPER_ENABLED
        if not IBKR_PAPER_ENABLED:
            return False
        if os.getenv("IBKR_PAPER_ENABLED", "true").strip().lower() in ("false", "0", "no"):
            return False
        if db is not None:
            try:
                setting = db.query(SystemSetting).filter(SystemSetting.key == self.ENABLE_SETTING_KEY).first()
                if setting and setting.value and str(setting.value).strip().lower() in ("false", "0", "no", "disabled"):
                    return False
            except Exception:
                pass
        return True

    def __init__(self):
        self._in_memory_cache: Optional[Dict[str, Any]] = None
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Loads cached snapshot from disk if present."""
        try:
            if IBKR_CACHE_FILE.exists():
                with open(IBKR_CACHE_FILE, "r", encoding="utf-8") as f:
                    self._in_memory_cache = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load IBKR disk cache: {e}")

    def _save_to_disk(self, data: Dict[str, Any]) -> None:
        """Persists snapshot to data cache directory."""
        try:
            IBKR_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(IBKR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save IBKR disk cache: {e}")

    def save_paper_snapshot(self, db: Session, payload: IBKRPaperSyncPayload) -> Dict[str, Any]:
        """Atomically validates, stores in authoritative database, and caches outbound paper snapshot."""
        if not self.is_integration_enabled(db):
            raise ValueError("IBKR paper trading integration is administratively soft-disabled (IBKR_PAPER_ENABLED=false). Ingestion rejected.")

        now_utc = datetime.now(timezone.utc)

        # 1. Confirm paper-account identifiers against the authenticated IBKR Gateway account
        if payload.gateway_managed_accounts:
            for acc in payload.gateway_managed_accounts:
                acc_clean = str(acc).strip().upper()
                if acc_clean.startswith("U") and not (
                    acc_clean.startswith("DU") or acc_clean.startswith("DF") or
                    "TEST" in acc_clean or "MOCK" in acc_clean or "PAPER" in acc_clean
                ):
                    raise ValueError(
                        f"CRITICAL SECURITY REJECTION: Gateway managed accounts contains a LIVE brokerage account '{acc}'. "
                        "Only paper trading accounts (starting with 'DU') are permitted."
                    )
            if payload.account_id not in payload.gateway_managed_accounts:
                raise ValueError(
                    f"Account verification failed: Account '{payload.account_id}' is not confirmed in the "
                    f"authenticated IBKR Gateway managed accounts list {payload.gateway_managed_accounts}."
                )

        if payload.gateway_port in (4001, 7496):
            raise ValueError(
                f"CRITICAL SECURITY REJECTION: Gateway socket port {payload.gateway_port} is an Interactive Brokers LIVE trading port. "
                "Only paper trading ports (4002 / 7497) are permitted."
            )

        # 2. Parse incoming timestamp
        try:
            clean_in_ts = payload.timestamp.rstrip("Z")
            if "+" in clean_in_ts or "-" in clean_in_ts[10:]:
                incoming_dt = datetime.fromisoformat(clean_in_ts)
            else:
                incoming_dt = datetime.fromisoformat(clean_in_ts).replace(tzinfo=timezone.utc)
            if incoming_dt.tzinfo is None:
                incoming_dt = incoming_dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            raise ValueError(f"Invalid snapshot timestamp format '{payload.timestamp}': {e}")

        # 3. Clock-skew tolerance check: reject if >60s into future
        if incoming_dt > now_utc + timedelta(seconds=60):
            skew_sec = int((incoming_dt - now_utc).total_seconds())
            raise ValueError(
                f"Clock skew rejection: Incoming snapshot timestamp '{payload.timestamp}' "
                f"is {skew_sec}s in the future (exceeds 60s tolerance limit)."
            )

        # 4. Stale snapshot rejection: reject if older than staleness threshold (300s) upon submission
        # (Allows testing override when os.environ['ALLOW_STALE_TEST_INGEST'] is set)
        if incoming_dt < now_utc - timedelta(seconds=STALE_THRESHOLD_SECONDS) and not (
            payload.connection_state != "CONNECTED" or os.environ.get("ALLOW_STALE_TEST_INGEST") == "1"
        ):
            age_sec = int((now_utc - incoming_dt).total_seconds())
            raise ValueError(
                f"Stale snapshot rejection: Incoming snapshot timestamp '{payload.timestamp}' "
                f"is already stale upon submission ({age_sec}s old > {STALE_THRESHOLD_SECONDS}s threshold)."
            )

        # 5. Authoritative Atomic Database Transaction with Serialization
        with self._admission_lock:
            try:
                # 5a. If running on PostgreSQL, acquire transaction-scoped exclusive advisory lock
                try:
                    bind = db.get_bind()
                    if bind and bind.dialect.name == "postgresql":
                        db.execute(
                            text("SELECT pg_advisory_xact_lock(:lock_id)"),
                            {"lock_id": IBKR_SNAPSHOT_ADVISORY_LOCK_ID}
                        )
                except Exception as lock_err:
                    logger.debug(f"Advisory lock check notice: {lock_err}")

                # 5b. Authoritative Paper Account Identity Binding
                bound_query = db.query(SystemSetting).filter(SystemSetting.key == self.BOUND_ACCOUNT_KEY)
                try:
                    bound_setting = bound_query.with_for_update().first()
                except Exception:
                    bound_setting = bound_query.first()

                if not bound_setting:
                    # Initial admission: automatically bind incoming paper account ID
                    bound_data = {
                        "account_id": payload.account_id,
                        "bound_at": now_utc.isoformat(),
                        "bound_by": "INITIAL_FIRST_ADMISSION"
                    }
                    bound_setting = SystemSetting(
                        key=self.BOUND_ACCOUNT_KEY,
                        value=json.dumps(bound_data),
                        updated_at=now_utc
                    )
                    db.add(bound_setting)
                    authorized_account = payload.account_id
                else:
                    try:
                        bound_data = json.loads(bound_setting.value)
                        authorized_account = bound_data.get("account_id")
                    except Exception:
                        authorized_account = payload.account_id

                # Prevent silent switching to another paper account without administrative approval
                if authorized_account and payload.account_id != authorized_account:
                    raise ValueError(
                        f"Account binding rejection: Incoming paper account '{payload.account_id}' "
                        f"does not match authoritative bound paper account '{authorized_account}'. "
                        f"Ingestion tokens cannot switch accounts. Administrative authorization via "
                        f"POST /api/portfolio/ibkr/bind-account is required to change the bound account."
                    )

                # 5c. Serialized First Snapshot Insert or Update
                query = db.query(SystemSetting).filter(SystemSetting.key == self.SETTING_KEY)
                try:
                    setting = query.with_for_update().first()
                except Exception:
                    setting = query.first()

                if setting and setting.value:
                    try:
                        stored_data = json.loads(setting.value)
                        stored_ts_str = stored_data.get("timestamp")
                        if stored_ts_str:
                            clean_stored = stored_ts_str.rstrip("Z")
                            if "+" in clean_stored or "-" in clean_stored[10:]:
                                stored_dt = datetime.fromisoformat(clean_stored)
                            else:
                                stored_dt = datetime.fromisoformat(clean_stored).replace(tzinfo=timezone.utc)
                            if stored_dt.tzinfo is None:
                                stored_dt = stored_dt.replace(tzinfo=timezone.utc)

                            # Enforce strict snapshot ordering: incoming_timestamp > stored_timestamp
                            if incoming_dt <= stored_dt:
                                if incoming_dt == stored_dt:
                                    raise ValueError(
                                        f"Duplicate snapshot rejection: Incoming timestamp '{payload.timestamp}' "
                                        f"is identical to stored snapshot timestamp."
                                    )
                                else:
                                    raise ValueError(
                                        f"Replay protection rejection: Incoming snapshot timestamp '{payload.timestamp}' "
                                        f"is older than the stored active snapshot timestamp '{stored_ts_str}'."
                                    )
                    except ValueError:
                        raise
                    except Exception as ex:
                        logger.warning(f"Error checking stored snapshot timestamp: {ex}")

                data_dict = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
                data_dict["received_at"] = now_utc.isoformat()
                data_dict["bound_account_id"] = authorized_account

                if not setting:
                    setting = SystemSetting(
                        key=self.SETTING_KEY,
                        value=json.dumps(data_dict),
                        updated_at=now_utc
                    )
                    db.add(setting)
                else:
                    setting.value = json.dumps(data_dict)
                    setting.updated_at = now_utc

                try:
                    db.commit()
                except IntegrityError as ie:
                    db.rollback()
                    logger.warning(f"Integrity collision on first admission: {ie}")
                    # Re-query existing row and evaluate monotonicity
                    existing = db.query(SystemSetting).filter(SystemSetting.key == self.SETTING_KEY).first()
                    if existing and existing.value:
                        stored_ts_str = json.loads(existing.value).get("timestamp")
                        if stored_ts_str:
                            clean_stored = stored_ts_str.rstrip("Z")
                            stored_dt = datetime.fromisoformat(clean_stored).replace(tzinfo=timezone.utc)
                            if incoming_dt <= stored_dt:
                                raise ValueError(
                                    f"Duplicate snapshot rejection: Incoming timestamp '{payload.timestamp}' "
                                    f"collided with concurrently inserted snapshot."
                                )
                            existing.value = json.dumps(data_dict)
                            existing.updated_at = now_utc
                            db.commit()
                    else:
                        raise ValueError(f"Database collision error: {ie}")

                # 6. Synchronize in-memory cache and disk cache AFTER DB transaction commits
                self._in_memory_cache = data_dict
                self._save_to_disk(data_dict)

            except ValueError:
                db.rollback()
                raise
            except Exception as e:
                db.rollback()
                logger.error(f"Authoritative database transaction failed for IBKR snapshot: {e}")
                raise ValueError(f"Database persistence failure: {e}")

        return self.get_paper_account_status(db)

    def bind_paper_account(self, db: Session, target_account_id: str, reason: str = "") -> Dict[str, Any]:
        """Administratively binds the dashboard to an authorized paper trading account."""
        if not self.is_integration_enabled(db):
            raise ValueError("IBKR paper trading integration is administratively soft-disabled (IBKR_PAPER_ENABLED=false).")

        acc_clean = str(target_account_id).strip().upper()
        if not acc_clean:
            raise ValueError("Account ID cannot be empty.")
        if acc_clean.startswith("U") and not (
            acc_clean.startswith("DU") or acc_clean.startswith("DF") or
            "TEST" in acc_clean or "MOCK" in acc_clean or "PAPER" in acc_clean
        ):
            raise ValueError(
                f"CRITICAL SECURITY REJECTION: Live brokerage account '{target_account_id}' cannot be bound. "
                "Only paper accounts (starting with 'DU') are permitted."
            )
        if not (acc_clean.startswith("D") or "TEST" in acc_clean or "MOCK" in acc_clean):
            raise ValueError(f"Invalid account format: Paper accounts must start with 'D' (received '{target_account_id}').")

        now_utc = datetime.now(timezone.utc)
        with self._admission_lock:
            try:
                try:
                    bind = db.get_bind()
                    if bind and bind.dialect.name == "postgresql":
                        db.execute(
                            text("SELECT pg_advisory_xact_lock(:lock_id)"),
                            {"lock_id": IBKR_SNAPSHOT_ADVISORY_LOCK_ID}
                        )
                except Exception as lock_err:
                    logger.debug(f"Advisory lock check notice: {lock_err}")

                bound_query = db.query(SystemSetting).filter(SystemSetting.key == self.BOUND_ACCOUNT_KEY)
                try:
                    bound_setting = bound_query.with_for_update().first()
                except Exception:
                    bound_setting = bound_query.first()

                bound_data = {
                    "account_id": acc_clean,
                    "bound_at": now_utc.isoformat(),
                    "bound_by": "ADMIN_OVERRIDE",
                    "reason": reason or "Administrative account rebind"
                }

                if not bound_setting:
                    bound_setting = SystemSetting(
                        key=self.BOUND_ACCOUNT_KEY,
                        value=json.dumps(bound_data),
                        updated_at=now_utc
                    )
                    db.add(bound_setting)
                else:
                    bound_setting.value = json.dumps(bound_data)
                    bound_setting.updated_at = now_utc

                db.commit()
                if self._in_memory_cache:
                    self._in_memory_cache["bound_account_id"] = acc_clean

                logger.info(f"Administratively bound IBKR paper account to {acc_clean} (reason: {reason})")
                return bound_data
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to administratively bind paper account: {e}")
                raise ValueError(f"Database persistence failure while binding account: {e}")

    def get_paper_account_status(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """Retrieves the latest paper account snapshot with real-time three-tier connectivity states."""
        raw_data = self._in_memory_cache
        bound_account_id = None

        if not self.is_integration_enabled(db):
            return {
                "configured": False,
                "read_only": True,
                "account_type": "PAPER",
                "account_id": "DISABLED",
                "bound_account_id": None,
                "currency": "AUD",
                "adapter_status": "DISABLED",
                "gateway_connection": "DISABLED",
                "freshness_state": "DISABLED",
                "is_cached": False,
                "connection_state": "DISABLED",
                "is_stale": True,
                "staleness_seconds": None,
                "last_sync_timestamp": None,
                "positions_count": 0,
                "warning_message": "IBKR paper trading integration is administratively soft-disabled.",
                "summary": {
                    "net_liquidation": 0.0,
                    "total_cash_value": 0.0,
                    "buying_power": 0.0,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                },
                "positions": [],
            }

        if db is not None:
            try:
                bound_setting = db.query(SystemSetting).filter(SystemSetting.key == self.BOUND_ACCOUNT_KEY).first()
                if bound_setting and bound_setting.value:
                    bound_account_id = json.loads(bound_setting.value).get("account_id")
            except Exception:
                pass

        # If in-memory is empty and db session is provided, attempt db load
        if not raw_data and db is not None:
            try:
                setting = db.query(SystemSetting).filter(SystemSetting.key == self.SETTING_KEY).first()
                if setting and setting.value:
                    raw_data = json.loads(setting.value)
                    self._in_memory_cache = raw_data
            except Exception as e:
                logger.warning(f"Error reading IBKR snapshot from db: {e}")

        # If still no data, return default DISCONNECTED initial state
        if not raw_data:
            return {
                "configured": False,
                "read_only": True,
                "account_type": "PAPER",
                "account_id": "NOT_CONNECTED",
                "bound_account_id": bound_account_id,
                "currency": "AUD",
                "adapter_status": "OFFLINE",
                "gateway_connection": "DISCONNECTED",
                "freshness_state": "NO_DATA",
                "is_cached": False,
                "is_stale": True,
                "staleness_seconds": None,
                "warning_message": (
                    "No IBKR paper trading data received yet. "
                    "Start the Windows IBKR Adapter to connect to IB Gateway (127.0.0.1:4002)."
                ),
                "summary": {
                    "net_liquidation": 0.0,
                    "total_cash_value": 0.0,
                    "buying_power": 0.0,
                    "currency": "AUD",
                },
                "positions": [],
                "positions_count": 0,
                "last_sync_timestamp": None,
                "adapter_version": None,
                "connection_state": "DISCONNECTED",  # backward compatibility alias
            }

        # Calculate staleness
        last_sync_str = raw_data.get("timestamp") or raw_data.get("received_at")
        staleness_seconds = None
        is_stale = False

        if last_sync_str:
            try:
                clean_ts = last_sync_str.rstrip("Z")
                if "+" in clean_ts or "-" in clean_ts[10:]:
                    dt = datetime.fromisoformat(clean_ts)
                else:
                    dt = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                staleness_seconds = max(0, int((now_utc - dt).total_seconds()))
                is_stale = staleness_seconds > STALE_THRESHOLD_SECONDS
            except Exception:
                is_stale = True

        connection_state = raw_data.get("connection_state", "CONNECTED")
        error_message = raw_data.get("error_message")

        # Three-tier status categorization:
        # 1. Gateway connection
        gateway_connection = connection_state
        # 2. Adapter status (push link health)
        adapter_status = "ONLINE" if (staleness_seconds is not None and staleness_seconds <= STALE_THRESHOLD_SECONDS) else "OFFLINE"
        # 3. Freshness state
        if staleness_seconds is None:
            freshness_state = "UNKNOWN"
        elif staleness_seconds <= 60:
            freshness_state = "LIVE_STREAM"
        elif staleness_seconds <= STALE_THRESHOLD_SECONDS:
            freshness_state = "CACHED"
        else:
            freshness_state = "STALE"

        warning_message = None
        if gateway_connection != "CONNECTED":
            warning_message = (
                f"IBKR Gateway is {gateway_connection}: {error_message or 'Gateway connection offline.'}"
            )
        elif is_stale:
            warning_message = (
                f"IBKR Paper account data is STALE (last synced {staleness_seconds}s ago). "
                f"Ensure the Windows IBKR Adapter is running."
            )

        positions = raw_data.get("positions", [])

        return {
            "configured": True,
            "read_only": True,
            "account_type": "PAPER",
            "account_id": raw_data.get("account_id", "PAPER_ACCOUNT"),
            "bound_account_id": bound_account_id or raw_data.get("bound_account_id"),
            "currency": raw_data.get("currency", "AUD"),
            "adapter_status": adapter_status,
            "gateway_connection": gateway_connection,
            "freshness_state": freshness_state,
            "is_cached": True,
            "connection_state": connection_state,  # backward compatibility alias
            "is_stale": is_stale,
            "staleness_seconds": staleness_seconds,
            "warning_message": warning_message,
            "summary": {
                "net_liquidation": raw_data.get("net_liquidation", 0.0),
                "total_cash_value": raw_data.get("total_cash_value", 0.0),
                "buying_power": raw_data.get("buying_power", 0.0),
                "currency": raw_data.get("currency", "AUD"),
            },
            "positions": positions,
            "positions_count": len(positions),
            "last_sync_timestamp": last_sync_str,
            "adapter_version": raw_data.get("adapter_version", "1.0.0"),
        }

    def clear_cache_for_testing(self, db: Optional[Session] = None) -> None:
        """Utility for test suites to reset state."""
        self._in_memory_cache = None
        if IBKR_CACHE_FILE.exists():
            try:
                IBKR_CACHE_FILE.unlink()
            except Exception:
                pass
        if db is not None:
            try:
                db.query(SystemSetting).filter(
                    SystemSetting.key.in_([self.SETTING_KEY, self.BOUND_ACCOUNT_KEY])
                ).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()


ibkr_service = IBKRService()
