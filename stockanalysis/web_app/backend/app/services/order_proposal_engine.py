"""Broker-independent paper order proposal engine (Stage D2.4C).

Separates:
1. Decision evaluation (BuyDecisionEngine)
2. Proposal generation (this module)
3. Approval — disabled / not invoked
4. Broker submission — disabled / not invoked

Never falls back to a weaker order path on failure.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import (
    PAPER_BROKER,
    TRADING_EXECUTION_ENABLED,
    V40_STRATEGY_VERSION,
)
from app.services.buy_decision_engine import (
    BUY_READY,
    BuyDecision,
    BuyDecisionEngine,
    DecisionContext,
    buy_decision_engine,
)
from app.services.order_execution_service import (
    PaperOrderProposal,
    order_execution_service,
)

logger = logging.getLogger("stockanalysis.order_proposal_engine")

# Hard stage invariant — D2.4C never auto-approves or submits
STAGE_APPROVAL_ENABLED = False
STAGE_SUBMISSION_ENABLED = False


def build_idempotency_key(
    *,
    ticker: str,
    market_as_of: str,
    entry_rule: str,
    strategy_version: str,
    account_id: str,
    broker: str,
    signal_id: str,
) -> str:
    """Deterministic client key across retries / refreshes for the same session signal."""
    raw = "|".join(
        [
            "v40buy",
            ticker.strip().upper(),
            str(market_as_of)[:10],
            str(entry_rule),
            str(strategy_version),
            str(account_id).strip().upper(),
            str(broker).strip().lower(),
            str(signal_id),
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"v40buy_{digest}"


class OrderProposalEngine:
    """Generates LIMIT BUY proposals from BUY_READY decisions only."""

    def __init__(self, decision_engine: Optional[BuyDecisionEngine] = None):
        self.decision_engine = decision_engine or buy_decision_engine
        self.execution = order_execution_service
        self.submissions_attempted = 0  # always stays 0 in D2.4C

    def evaluate_signal(self, signal: Dict[str, Any], ctx: DecisionContext) -> BuyDecision:
        return self.decision_engine.evaluate(signal, ctx)

    def build_proposal_payload(
        self,
        decision: BuyDecision,
        quote: Dict[str, Any],
        broker: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a PaperOrderProposal-compatible dict. Raises if decision is not BUY_READY."""
        if decision.classification != BUY_READY:
            raise ValueError(
                f"Refusing proposal generation for classification={decision.classification}"
            )
        details = decision.details or {}
        qty = int(details.get("proposed_quantity") or 0)
        limit_price = float(details.get("proposed_limit_price") or 0)
        if qty < 1 or limit_price <= 0:
            raise ValueError("BUY_READY decision missing valid quantity/limit_price")

        broker_name = (broker or decision.broker or PAPER_BROKER or "alpaca").strip().lower()
        acct = (account_id or decision.account_id or "").strip().upper()
        if not acct:
            raise ValueError("Account id required for proposal")

        idem = build_idempotency_key(
            ticker=decision.ticker,
            market_as_of=decision.market_as_of_date or "",
            entry_rule=decision.entry_rule or "",
            strategy_version=decision.strategy_version or V40_STRATEGY_VERSION,
            account_id=acct,
            broker=broker_name,
            signal_id=decision.signal_id,
        )
        notes = (
            f"D2.4C V4.0 research proposal | signal_id={decision.signal_id} | "
            f"entry={decision.entry_rule} | as_of={decision.market_as_of_date} | "
            f"reasons={','.join(decision.reason_codes)}"
        )
        return {
            "symbol": decision.ticker,
            "action": "BUY",
            "order_type": "LIMIT",
            "quantity": float(qty),
            "limit_price": float(limit_price),
            "currency": "USD",
            "broker": broker_name,
            "account_id": acct,
            "client_idempotency_key": idem,
            "notes": notes,
            "market_quote": quote,
            "decision": decision.to_dict(),
        }

    def process_signal(
        self,
        signal: Dict[str, Any],
        ctx: DecisionContext,
        *,
        db: Optional[Session] = None,
        persist: bool = False,
        actor: str = "D2_4C_DECISION_ENGINE",
    ) -> Dict[str, Any]:
        """Evaluate → optionally persist proposal. Never approves or submits.

        persist=True requires db and will call propose_order (AWAITING_APPROVAL or REJECTED).
        Approval and broker submission are hard-disabled in this stage.
        """
        decision = self.evaluate_signal(signal, ctx)
        result: Dict[str, Any] = {
            "decision": decision.to_dict(),
            "proposal": None,
            "persisted_order": None,
            "approval_attempted": False,
            "submission_attempted": False,
            "stage": "D2.4C",
            "trading_execution_enabled_env": bool(TRADING_EXECUTION_ENABLED),
        }

        if decision.classification != BUY_READY:
            return result

        if not ctx.broker_quote:
            # Should not happen for BUY_READY, but fail closed
            decision.classification = "BLOCKED"
            decision.reason_codes = list(decision.reason_codes) + ["PROPOSAL_MISSING_QUOTE"]
            result["decision"] = decision.to_dict()
            return result

        try:
            payload = self.build_proposal_payload(
                decision,
                quote=ctx.broker_quote,
                broker=ctx.account.broker if ctx.account else None,
                account_id=ctx.account.account_id if ctx.account else None,
            )
        except ValueError as exc:
            result["decision"]["classification"] = "BLOCKED"
            result["decision"]["reason_codes"] = list(decision.reason_codes) + ["PROPOSAL_BUILD_FAILED"]
            result["error"] = str(exc)
            return result

        result["proposal"] = {
            k: v for k, v in payload.items() if k != "decision"
        }

        if not persist:
            return result

        if db is None:
            result["error"] = "persist=True requires a database session"
            result["decision"]["classification"] = "BLOCKED"
            result["decision"]["reason_codes"] = list(decision.reason_codes) + ["DB_UNAVAILABLE"]
            return result

        # Stage hard stops — never approve / submit even if env flags flip
        if STAGE_APPROVAL_ENABLED or STAGE_SUBMISSION_ENABLED:
            raise RuntimeError("D2.4C invariant violated: approval/submission must remain disabled")
        if TRADING_EXECUTION_ENABLED:
            logger.warning(
                "TRADING_EXECUTION_ENABLED is true but D2.4C will not submit; proposal-only path continues"
            )

        proposal = PaperOrderProposal(
            symbol=payload["symbol"],
            action=payload["action"],
            order_type="LIMIT",
            quantity=payload["quantity"],
            limit_price=payload["limit_price"],
            currency="USD",
            broker=payload["broker"],
            account_id=payload["account_id"],
            client_idempotency_key=payload["client_idempotency_key"],
            notes=payload["notes"],
            market_quote=payload["market_quote"],
        )
        order = self.execution.propose_order(db, proposal, actor=actor)
        result["persisted_order"] = order
        result["approval_attempted"] = False
        result["submission_attempted"] = False
        self.submissions_attempted = 0
        return result

    def process_signals(
        self,
        signals: List[Dict[str, Any]],
        ctx: DecisionContext,
        *,
        db: Optional[Session] = None,
        persist: bool = False,
    ) -> List[Dict[str, Any]]:
        return [self.process_signal(s, ctx, db=db, persist=persist) for s in signals]


order_proposal_engine = OrderProposalEngine()
