"""IBKR Paper Trading API Router.

Provides secure, read-only endpoints to:
1. Retrieve current IBKR paper trading account snapshot, cash, buying power, and positions.
2. Ingest authenticated outbound push payloads from the local Windows IBKR Adapter.
3. Check adapter link health, gateway connection state, and cache freshness.
"""
import hmac
import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.config import IBKR_INGESTION_KEY, STOCKANALYSIS_ADMIN_KEY
from app.services.ibkr_service import (
    ibkr_service,
    IBKRPaperSyncPayload,
)

router = APIRouter(prefix="/api/portfolio/ibkr", tags=["IBKR Paper Integration"])


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
    expected_ingest_key = (IBKR_INGESTION_KEY or os.environ.get("IBKR_INGESTION_KEY", "")).strip()

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
    expected_secret = (STOCKANALYSIS_ADMIN_KEY or os.environ.get("STOCKANALYSIS_ADMIN_KEY", "")).strip()
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
