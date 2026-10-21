"""IBKR Paper Trading API Router.

Provides secure, read-only endpoints to:
1. Retrieve current IBKR paper trading account snapshot, cash, buying power, and positions.
2. Ingest authenticated outbound push payloads from the local Windows IBKR Adapter.
3. Check adapter link health, gateway connection state, and cache freshness.
"""
import hmac
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.config import IBKR_INGESTION_KEY, STOCKANALYSIS_ADMIN_KEY, IBKR_EXECUTION_KEY
from app.services.ibkr_service import (
    ibkr_service,
    IBKRPaperSyncPayload,
)
import copy
from app.services.order_execution_service import (
    order_execution_service,
    PaperOrderProposal,
    get_us_trading_date,
    HARD_CEILING_MAX_ORDER_NOTIONAL,
    HARD_FLOOR_MAX_ORDER_NOTIONAL,
    HARD_CEILING_MAX_DAILY_ORDERS,
    HARD_FLOOR_MAX_DAILY_ORDERS,
    HARD_CEILING_MAX_DAILY_NOTIONAL,
    HARD_FLOOR_MAX_DAILY_NOTIONAL,
    HARD_CEILING_MAX_OPEN_ORDERS,
    HARD_FLOOR_MAX_OPEN_ORDERS,
)
from app.services.market_data_service import market_data_service

router = APIRouter(prefix="/api/portfolio/ibkr", tags=["IBKR Paper Integration"])


def verify_ibkr_execution_authorization(
    authorization: Optional[str] = Header(None),
    x_ibkr_execution_key: Optional[str] = Header(None, alias="X-IBKR-Execution-Key"),
) -> bool:
    """Enforces dedicated machine-to-machine execution credential authorization.

    Accepts:
    1. 'X-IBKR-Execution-Key: <IBKR_EXECUTION_KEY>'
    2. 'Authorization: Bearer <IBKR_EXECUTION_KEY>'

    Administrator credentials, ingestion credentials, and anonymous access are strictly rejected with 401.
    Uses constant-time comparison to prevent timing attacks.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_ibkr_execution_key:
        token = x_ibkr_execution_key.strip()

    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    expected_exec_key = (os.environ.get("IBKR_EXECUTION_KEY") or IBKR_EXECUTION_KEY or "").strip()

    if env == "production":
        from app.config import KNOWN_DEV_EXECUTION_KEYS
        if not expected_exec_key or expected_exec_key in KNOWN_DEV_EXECUTION_KEYS:
            raise HTTPException(
                status_code=500,
                detail="Security Configuration Failure: IBKR_EXECUTION_KEY is unconfigured, empty, or using an insecure development value in production."
            )

    if token and expected_exec_key and hmac.compare_digest(token, expected_exec_key):
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Valid dedicated IBKR execution credential required.",
    )


def verify_ibkr_ingestion_authorization(
    authorization: Optional[str] = Header(None),
    x_ibkr_ingest_key: Optional[str] = Header(None, alias="X-IBKR-Ingest-Key"),
) -> bool:
    """Enforces dedicated ingestion credential authorization for adapter pushes.

    Accepts:
    1. 'X-IBKR-Ingest-Key: <IBKR_INGESTION_KEY>'
    2. 'Authorization: Bearer <IBKR_INGESTION_KEY>'

    Administrator credentials and anonymous access are strictly rejected with 401.
    Uses constant-time comparison to prevent timing attacks.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_ibkr_ingest_key:
        token = x_ibkr_ingest_key.strip()

    env = os.environ.get("ENVIRONMENT", "development").strip().lower()
    expected_ingest_key = (os.environ.get("IBKR_INGESTION_KEY") or IBKR_INGESTION_KEY or "").strip()

    if env == "production":
        from app.config import KNOWN_DEV_INGEST_KEYS
        if not expected_ingest_key or expected_ingest_key in KNOWN_DEV_INGEST_KEYS:
            raise HTTPException(
                status_code=500,
                detail="Security Configuration Failure: IBKR_INGESTION_KEY is unconfigured, empty, or using an insecure development value in production."
            )

    if token and expected_ingest_key and hmac.compare_digest(token, expected_ingest_key):
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Valid dedicated IBKR ingestion credential required.",
    )


def verify_admin_authorization(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Enforces administrator authorization on sensitive administrative and financial endpoints.

    Accepts:
    1. 'X-Admin-Key: <STOCKANALYSIS_ADMIN_KEY>'
    2. 'Authorization: Bearer <STOCKANALYSIS_ADMIN_KEY>'

    Ingestion credentials (IBKR_INGESTION_KEY) and anonymous access are strictly rejected with 401.
    """
    expected_secret = (os.environ.get("STOCKANALYSIS_ADMIN_KEY") or STOCKANALYSIS_ADMIN_KEY or "").strip()
    if not expected_secret:
        raise HTTPException(
            status_code=500,
            detail="Server administrator authentication key is not configured.",
        )

    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_admin_key:
        token = x_admin_key.strip()

    if token and hmac.compare_digest(token, expected_secret):
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Valid administrator credentials required.",
    )


@router.get("", response_model=Dict[str, Any], dependencies=[Depends(verify_admin_authorization)])
def get_ibkr_paper_account(db: Session = Depends(get_db)):
    """Retrieve full read-only snapshot of IBKR paper trading account.

    Restricted to authorized Mozarex administrators.
    """
    return ibkr_service.get_paper_account_status(db)


@router.get("/status", response_model=Dict[str, Any], dependencies=[Depends(verify_admin_authorization)])
def get_ibkr_paper_status(db: Session = Depends(get_db)):
    """Lightweight link, gateway connection, and staleness status check.

    Restricted to authorized Mozarex administrators.
    """
    status_data = ibkr_service.get_paper_account_status(db)
    return {
        "configured": status_data["configured"],
        "read_only": status_data["read_only"],
        "account_type": status_data["account_type"],
        "account_id": status_data["account_id"],
        "currency": status_data["currency"],
        "adapter_status": status_data.get("adapter_status", "OFFLINE"),
        "gateway_connection": status_data.get("gateway_connection", "DISCONNECTED"),
        "freshness_state": status_data.get("freshness_state", "UNKNOWN"),
        "is_cached": status_data.get("is_cached", False),
        "connection_state": status_data["connection_state"],
        "is_stale": status_data["is_stale"],
        "staleness_seconds": status_data["staleness_seconds"],
        "last_sync_timestamp": status_data["last_sync_timestamp"],
        "positions_count": status_data["positions_count"],
        "warning_message": status_data["warning_message"],
    }


@router.post("/sync", response_model=Dict[str, Any])
def sync_ibkr_paper_snapshot(
    payload: IBKRPaperSyncPayload,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_ibkr_ingestion_authorization),
):
    """Receive and persist authenticated outbound paper trading snapshot from Windows adapter.

    Requires valid ingestion authorization (via X-IBKR-Ingest-Key or Bearer token).
    """
    if payload.account_type != "PAPER":
        raise HTTPException(
            status_code=400,
            detail="Forbidden: Only 'PAPER' trading account data is supported by this integration."
        )

    try:
        res = ibkr_service.save_paper_snapshot(db, payload)
        return {
            "success": True,
            "message": f"Successfully ingested paper snapshot for {payload.account_id}",
            "status": res,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class IBKRBindAccountRequest(BaseModel):
    account_id: str = Field(..., description="Target paper account ID to bind (must start with 'DU' or 'D')")
    reason: Optional[str] = Field(default="Administrative account rebind", description="Reason for binding")


@router.post("/bind-account", dependencies=[Depends(verify_admin_authorization)])
def bind_paper_account(
    req: IBKRBindAccountRequest,
    db: Session = Depends(get_db)
):
    """Administratively authorizes and binds the active paper account ID.

    Requires administrative privileges (STOCKANALYSIS_ADMIN_KEY).
    Ingestion tokens are strictly forbidden from calling this endpoint.
    Live brokerage accounts ('U...') are strictly rejected.
    """
    try:
        res = ibkr_service.bind_paper_account(db, target_account_id=req.account_id, reason=req.reason)
        return {
            "status": "SUCCESS",
            "message": f"Successfully bound authorized paper account to {res['account_id']}",
            "bound_account": res
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# STAGE D2.1: CONTROLLED PAPER ORDER EXECUTION FOUNDATION ENDPOINTS
# =============================================================================

class OrderActionReasonRequest(BaseModel):
    reason: Optional[str] = Field(default="", description="Operator justification or cancellation reason")


class EmergencyStopRequest(BaseModel):
    active: bool = Field(..., description="True to engage master Emergency Stop, False to disarm")
    reason: Optional[str] = Field(default="", description="Operator reason for toggling emergency stop")


class UpdateRiskSettingsRequest(BaseModel):
    max_order_notional_usd: Optional[float] = Field(default=None, description="Maximum notional per single order in USD")
    max_daily_orders: Optional[int] = Field(default=None, description="Maximum new orders per US trading day")
    max_daily_notional_usd: Optional[float] = Field(default=None, description="Maximum aggregate daily new-order notional in USD")
    max_open_orders: Optional[int] = Field(default=None, description="Maximum simultaneous open orders")
    reason: str = Field(..., min_length=3, description="Operator reason for updating risk settings")


class ClaimOrderRequest(BaseModel):
    agent_id: str = Field(default="windows_execution_agent_1", description="Identifier of calling execution agent")
    account_id: Optional[str] = Field(default=None, description="Active paper account ID of the calling execution agent")


class ReportExecutionStatusRequest(BaseModel):
    agent_id: str = Field(..., description="Identifier of execution agent submitting report")
    target_status: str = Field(..., description="Target order status (SUBMITTING, SUBMITTED, FILLED, REJECTED, UNKNOWN)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics or error report payload")


class ReconcileOrderRequest(BaseModel):
    resolution_status: str = Field(..., description="Target resolution status: FILLED, CANCELLED, or REJECTED")
    reason: Optional[str] = Field(default="Administrator manual reconciliation", description="Reason for reconciliation")


class AgentHeartbeatRequest(BaseModel):
    agent_id: str = Field(default="windows_execution_agent_1", description="Identifier of the execution agent")
    client_id: int = Field(default=22, description="IBKR Client ID")
    gateway_host: str = Field(default="127.0.0.1", description="IBKR Gateway host")
    gateway_port: int = Field(default=4002, description="IBKR Gateway port")
    gateway_connected: bool = Field(default=False, description="Whether connected to IBKR Gateway")
    managed_accounts: List[str] = Field(default_factory=list, description="Managed accounts from IBKR")
    active_account: str = Field(default="", description="Active account ID")
    is_paper: bool = Field(default=True, description="Whether active account is paper")
    non_executing_guard: bool = Field(default=True, description="Whether build guard is active")
    status: str = Field(default="HEALTHY", description="HEALTHY, DEGRADED, OFFLINE")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional diagnostic details")


# -----------------------------------------------------------------------------
# Administrator Order Management Endpoints (Requires Admin Session / Key)
# -----------------------------------------------------------------------------

@router.post("/orders/propose", dependencies=[Depends(verify_admin_authorization)])
def propose_paper_order(
    proposal: PaperOrderProposal,
    db: Session = Depends(get_db)
):
    """Proposes a new paper limit order and immediately evaluates risk invariants.

    If risk checks pass, transitions DRAFT -> AWAITING_APPROVAL.
    If risk checks fail, transitions DRAFT -> REJECTED.
    """
    try:
        order = order_execution_service.propose_order(db, proposal, actor="ADMIN")
        return {
            "success": True,
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/orders", dependencies=[Depends(verify_admin_authorization)])
def list_paper_orders(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Lists all paper orders with their risk evaluation reports and audit trails."""
    orders = order_execution_service.list_orders(db, status_filter=status)
    return {
        "success": True,
        "count": len(orders),
        "orders": orders
    }


@router.get("/orders/{order_id}", dependencies=[Depends(verify_admin_authorization)])
def get_paper_order_detail(
    order_id: str,
    db: Session = Depends(get_db)
):
    """Retrieves full details and immutable audit trail for a specific order."""
    order = order_execution_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    return {
        "success": True,
        "order": order
    }


@router.post("/orders/{order_id}/approve", dependencies=[Depends(verify_admin_authorization)])
def approve_paper_order(
    order_id: str,
    db: Session = Depends(get_db)
):
    """Explicitly approves an order, transitioning AWAITING_APPROVAL -> APPROVED.

    Sets 15-minute approval expiration window. Fails if Emergency Stop is active.
    """
    try:
        order = order_execution_service.approve_order(db, order_id, actor="ADMIN")
        return {
            "success": True,
            "message": f"Order {order_id} approved. Valid for execution.",
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/reject", dependencies=[Depends(verify_admin_authorization)])
def reject_paper_order(
    order_id: str,
    req: OrderActionReasonRequest,
    db: Session = Depends(get_db)
):
    """Rejects an order in AWAITING_APPROVAL state."""
    try:
        order = order_execution_service.reject_order(db, order_id, reason=req.reason, actor="ADMIN")
        return {
            "success": True,
            "message": f"Order {order_id} rejected.",
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(verify_admin_authorization)])
def cancel_paper_order(
    order_id: str,
    req: OrderActionReasonRequest,
    db: Session = Depends(get_db)
):
    """Cancels an order prior to execution."""
    try:
        order = order_execution_service.cancel_order(db, order_id, reason=req.reason, actor="ADMIN")
        return {
            "success": True,
            "message": f"Order {order_id} cancelled.",
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/{order_id}/reconcile", dependencies=[Depends(verify_admin_authorization)])
def reconcile_paper_order(
    order_id: str,
    req: ReconcileOrderRequest,
    db: Session = Depends(get_db)
):
    """Manually reconciles an order quarantined in UNKNOWN status."""
    try:
        order = order_execution_service.reconcile_order(
            db,
            order_id=order_id,
            resolution_status=req.resolution_status,
            reason=req.reason or "Manual administrator reconciliation",
            actor="ADMIN"
        )
        return {
            "success": True,
            "message": f"Order {order_id} reconciled to {req.resolution_status}.",
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/execution/settings", dependencies=[Depends(verify_admin_authorization)])
def get_execution_settings(db: Session = Depends(get_db)):
    """Retrieves current server-side execution, emergency stop, and risk policy settings."""
    settings = order_execution_service.get_execution_settings(db)
    now_utc = datetime.now(timezone.utc)
    target_date_ny = get_us_trading_date(now_utc)
    daily_metrics = order_execution_service.get_us_daily_metrics_from_db(db, target_date_ny)

    settings_out = copy.deepcopy(settings)
    settings_out["us_trading_date"] = target_date_ny
    settings_out["current_daily_orders_count"] = daily_metrics["daily_orders_count"]
    settings_out["current_daily_notional_sum"] = daily_metrics["daily_notional_sum"]
    settings_out["current_open_orders_count"] = daily_metrics["open_orders_count"]
    settings_out["hard_ceilings"] = {
        "max_order_notional_usd": HARD_CEILING_MAX_ORDER_NOTIONAL,
        "floor_order_notional_usd": HARD_FLOOR_MAX_ORDER_NOTIONAL,
        "max_daily_orders": HARD_CEILING_MAX_DAILY_ORDERS,
        "floor_daily_orders": HARD_FLOOR_MAX_DAILY_ORDERS,
        "max_daily_notional_usd": HARD_CEILING_MAX_DAILY_NOTIONAL,
        "floor_daily_notional_usd": HARD_FLOOR_MAX_DAILY_NOTIONAL,
        "max_open_orders": HARD_CEILING_MAX_OPEN_ORDERS,
        "floor_open_orders": HARD_FLOOR_MAX_OPEN_ORDERS,
    }

    return {
        "success": True,
        "settings": settings_out
    }


@router.post("/execution/settings", dependencies=[Depends(verify_admin_authorization)])
def update_execution_risk_settings(
    req: UpdateRiskSettingsRequest,
    db: Session = Depends(get_db)
):
    """Updates administrator-managed risk policy settings with bounds validation and audit history."""
    try:
        updated = order_execution_service.update_risk_settings(
            db,
            updates=req.model_dump(exclude_unset=True),
            actor="ADMIN"
        )
        return {
            "success": True,
            "message": "Risk settings successfully updated.",
            "settings": updated
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execution/emergency-stop", dependencies=[Depends(verify_admin_authorization)])
def toggle_emergency_stop(
    req: EmergencyStopRequest,
    db: Session = Depends(get_db)
):
    """Toggles master server-side Emergency Stop (Kill Switch)."""
    settings = order_execution_service.toggle_emergency_stop(
        db,
        active=req.active,
        actor="ADMIN",
        reason=req.reason
    )
    return {
        "success": True,
        "emergency_stop": settings.get("emergency_stop", True),
        "settings": settings
    }


# -----------------------------------------------------------------------------
# Dedicated Execution Agent Endpoints (Requires IBKR_EXECUTION_KEY)
# -----------------------------------------------------------------------------

@router.get("/execution/orders/poll", dependencies=[Depends(verify_ibkr_execution_authorization)])
def poll_approved_orders_for_agent(
    agent_id: str = "windows_execution_agent_1",
    db: Session = Depends(get_db)
):
    """Polled outbound by Windows Execution Agent to retrieve approved orders ready for execution."""
    res = order_execution_service.poll_approved_orders(db, agent_id=agent_id)
    return res


@router.post("/execution/orders/{order_id}/claim", dependencies=[Depends(verify_ibkr_execution_authorization)])
def claim_order_for_agent(
    order_id: str,
    req: ClaimOrderRequest,
    db: Session = Depends(get_db)
):
    """Atomically claims an APPROVED order. Double-claiming or claiming expired orders is rejected."""
    try:
        order = order_execution_service.claim_order(
            db,
            order_id,
            agent_id=req.agent_id,
            agent_account=req.account_id,
        )
        return {
            "success": True,
            "message": f"Order {order_id} atomically claimed by {req.agent_id}",
            "order": order
        }
    except ValueError as e:
        err_msg = str(e)
        status_code = 409 if (
            "already claimed" in err_msg.lower() or
            "claim collision" in err_msg.lower() or
            "expired" in err_msg.lower() or
            "cannot claim order in status" in err_msg.lower() or
            "approved required" in err_msg.lower()
        ) else 400
        raise HTTPException(status_code=status_code, detail=err_msg)


@router.post("/execution/orders/{order_id}/report", dependencies=[Depends(verify_ibkr_execution_authorization)])
def report_order_execution_status(
    order_id: str,
    req: ReportExecutionStatusRequest,
    db: Session = Depends(get_db)
):
    """Execution agent reports order execution progress or outcome (SUBMITTING, SUBMITTED, FILLED, UNKNOWN)."""
    try:
        order = order_execution_service.report_execution_status(
            db,
            order_id=order_id,
            agent_id=req.agent_id,
            target_status=req.target_status,
            report_details=req.details
        )
        return {
            "success": True,
            "order": order
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/execution/agent/heartbeat", dependencies=[Depends(verify_ibkr_execution_authorization)])
def record_agent_heartbeat(
    req: AgentHeartbeatRequest,
    db: Session = Depends(get_db)
):
    """Endpoint for Windows execution agent to report heartbeat and diagnostics."""
    record = order_execution_service.record_agent_heartbeat(req.agent_id, req.model_dump(), db=db)
    return {
        "success": True,
        "heartbeat": record
    }


@router.get("/execution/agent/status", dependencies=[Depends(verify_admin_authorization)])
def get_execution_agent_status(
    agent_id: str = "windows_execution_agent_1",
    db: Session = Depends(get_db)
):
    """Retrieves execution agent connectivity and heartbeat health."""
    status_data = order_execution_service.get_agent_status(agent_id=agent_id, db=db)
    return {
        "success": True,
        "agent": status_data
    }


@router.get("/execution/market-data/status", dependencies=[Depends(verify_admin_authorization)])
def get_market_data_status():
    """Retrieves trusted market data feed diagnostics and readiness."""
    diagnostics = market_data_service.get_data_provider_diagnostics()
    return {
        "success": True,
        "diagnostics": diagnostics
    }


@router.post("/migration/d21-reconcile", dependencies=[Depends(verify_admin_authorization)])
def reconcile_d21_migration(db: Session = Depends(get_db)):
    """Non-destructively reconciles legacy D2.1 JSON orders into PostgreSQL tables."""
    migrated_count = order_execution_service.migrate_d21_json_orders_to_db(db)
    return {
        "success": True,
        "migrated_orders": migrated_count,
        "message": f"Migrated {migrated_count} legacy D2.1 orders."
    }

