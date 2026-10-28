"""Autonomous BUY pipeline dry run (Stage D2.4D).

V4.0 active snapshot → validation → investment decision → execution readiness
→ simulated order proposal → decision journal.

Never places broker orders. Never approves. Never bypasses emergency stops.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import (
    IBKR_EMERGENCY_STOP,
    PAPER_BROKER,
    TRADING_EXECUTION_ENABLED,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
)
from app.services.buy_decision_engine import (
    BUY_READY,
    AccountSnapshot,
    BuyDecisionEngine,
    DecisionContext,
    buy_decision_engine,
)
from app.services.decision_journal import DecisionJournal, decision_journal
from app.services.execution_readiness import classify_execution_readiness
from app.services.order_proposal_engine import (
    STAGE_APPROVAL_ENABLED,
    STAGE_SUBMISSION_ENABLED,
    OrderProposalEngine,
    build_idempotency_key,
    order_proposal_engine,
)
from app.services.shariah_eligibility import classify_execution_eligibility
from app.services.shariah_monitor import build_shariah_universe_report

logger = logging.getLogger("stockanalysis.buy_pipeline_dry_run")


class BuyPipelineDryRun:
    """End-to-end evaluate-only orchestration over a V4.0 signal snapshot."""

    def __init__(
        self,
        decision_engine: Optional[BuyDecisionEngine] = None,
        proposal_engine: Optional[OrderProposalEngine] = None,
        journal: Optional[DecisionJournal] = None,
    ):
        self.decision_engine = decision_engine or buy_decision_engine
        self.proposal_engine = proposal_engine or order_proposal_engine
        self.journal = journal or decision_journal
        self.submissions_attempted = 0

    def load_snapshot_signals(
        self,
        *,
        db: Optional[Session] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve signals from explicit list, snapshot dict, or active DB snapshot."""
        if signals is not None:
            return {
                "snapshot_id": (snapshot or {}).get("snapshot_id"),
                "market_as_of_date": (snapshot or {}).get("market_as_of_date"),
                "signals": list(signals),
                "source": "explicit",
            }
        if snapshot and snapshot.get("signals") is not None:
            return {
                "snapshot_id": snapshot.get("snapshot_id"),
                "market_as_of_date": snapshot.get("market_as_of_date"),
                "signals": list(snapshot.get("signals") or []),
                "source": "snapshot_dict",
            }
        from app.services.snapshot_service import snapshot_service

        active = snapshot_service.get_active_snapshot(db)
        if not active:
            return {
                "snapshot_id": None,
                "market_as_of_date": None,
                "signals": [],
                "source": "empty",
            }
        return {
            "snapshot_id": active.get("snapshot_id"),
            "market_as_of_date": active.get("market_as_of_date"),
            "signals": list(active.get("signals") or []),
            "source": "active_snapshot",
        }

    def _simulate_proposal(
        self,
        signal: Dict[str, Any],
        investment: Dict[str, Any],
        ctx: DecisionContext,
    ) -> Optional[Dict[str, Any]]:
        """Build a simulated LIMIT proposal using fixtures/account+quote. No persistence."""
        if investment.get("classification") != BUY_READY:
            return None

        # D2.4G/H: proposals require mode-aware investment eligibility
        from app.services.investment_eligibility import evaluate_investment_eligibility

        inv_elig = evaluate_investment_eligibility(
            str(signal.get("ticker") or ""),
            shariah_status=signal.get("shariah_status"),
            evidence_records=ctx.shariah_evidence_records,
            watchlist_meta=ctx.watchlist_shariah_meta,
            personal_config=ctx.personal_restrictions_config,
            sector=signal.get("sector"),
            industry=signal.get("industry"),
            name=signal.get("name") or signal.get("company_name"),
            as_of=(ctx.now_utc.date() if ctx.now_utc else None),
            eligibility_mode=ctx.eligibility_mode,
        )
        mode = (ctx.eligibility_mode or "").strip().upper()
        if mode != "USER_POLICY":
            shariah_stored = str(signal.get("shariah_status") or "").strip().upper()
            if shariah_stored != "VERIFIED":
                return None
        if not inv_elig.get("proposal_permitted"):
            return None

        # Need account + quote for sizing; fail soft → no proposal (still journal opportunity)
        if ctx.account is None or not ctx.broker_quote:
            return None

        # Use full executable evaluation for sizing numbers (does not submit)
        exec_ctx = DecisionContext(
            account=ctx.account,
            broker_quote=ctx.broker_quote,
            emergency_stop=False,  # sizing math only; readiness tracked separately
            execution_enabled=False,
            trading_execution_enabled=False,
            max_order_notional_usd=ctx.max_order_notional_usd,
            max_daily_orders=ctx.max_daily_orders,
            max_daily_notional_usd=ctx.max_daily_notional_usd,
            max_open_orders=ctx.max_open_orders,
            max_positions=ctx.max_positions,
            max_portfolio_exposure_pct=ctx.max_portfolio_exposure_pct,
            now_utc=ctx.now_utc,
            investment_mode=False,
            shariah_evidence_records=ctx.shariah_evidence_records,
            personal_restrictions_config=ctx.personal_restrictions_config,
            watchlist_shariah_meta=ctx.watchlist_shariah_meta,
            eligibility_mode=ctx.eligibility_mode,
            allow_off_session_sizing=True,  # D2.4I isolated sizing; still enforces quote/cash/risk
        )
        sized = self.decision_engine.evaluate(signal, exec_ctx)
        if sized.classification != BUY_READY:
            return {
                "status": "SIZING_BLOCKED",
                "reason_codes": sized.reason_codes,
                "details": sized.details,
            }

        details = sized.details or {}
        acct = ctx.account
        invested = max(0.0, float(acct.equity) - float(acct.cash))
        exposure_pct = (invested / float(acct.equity) * 100.0) if acct.equity else 0.0
        idem = build_idempotency_key(
            ticker=sized.ticker,
            market_as_of=sized.market_as_of_date or "",
            entry_rule=sized.entry_rule or "",
            strategy_version=sized.strategy_version or V40_STRATEGY_VERSION,
            account_id=acct.account_id,
            broker=acct.broker,
            signal_id=sized.signal_id,
        )
        return {
            "status": "SIMULATED",
            "symbol": sized.ticker,
            "action": "BUY",
            "order_type": "LIMIT",
            "proposed_limit_price": details.get("proposed_limit_price"),
            "proposed_quantity": details.get("proposed_quantity"),
            "proposed_notional": details.get("proposed_notional"),
            "available_cash": round(float(acct.cash), 2),
            "portfolio_equity": round(float(acct.equity), 2),
            "portfolio_exposure_pct": round(exposure_pct, 2),
            "risk_limits": {
                "max_order_notional_usd": ctx.max_order_notional_usd,
                "max_daily_orders": ctx.max_daily_orders,
                "max_daily_notional_usd": ctx.max_daily_notional_usd,
                "max_open_orders": ctx.max_open_orders,
                "max_positions": ctx.max_positions,
                "max_portfolio_exposure_pct": ctx.max_portfolio_exposure_pct,
            },
            "idempotency_key": idem,
            "broker": acct.broker,
            "account_id": acct.account_id,
            "limit_price_policy": details.get("limit_price_policy", "BUY_AT_ASK"),
            "submission_attempted": False,
            "approval_attempted": False,
        }

    def evaluate_signal(
        self,
        signal: Dict[str, Any],
        ctx: DecisionContext,
        *,
        run_id: str,
        persist_journal: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate one snapshot signal through the dry-run pipeline."""
        # Enrich industry/name from universe registry for USER_POLICY evidence (read-only)
        signal = dict(signal)
        if not signal.get("industry") or not signal.get("sector"):
            try:
                from app.services.universe_manager import universe_manager

                stock = universe_manager.get_stock(str(signal.get("ticker") or "")) or {}
                signal.setdefault("industry", stock.get("industry") or "")
                signal.setdefault("sector", stock.get("sector") or "")
                signal.setdefault("name", stock.get("name") or signal.get("ticker"))
            except Exception:
                pass

        # 1) Investment decision (visible even when execution disabled)
        inv_ctx = DecisionContext(
            account=ctx.account,
            broker_quote=ctx.broker_quote,
            emergency_stop=ctx.emergency_stop,
            execution_enabled=ctx.execution_enabled,
            trading_execution_enabled=ctx.trading_execution_enabled,
            max_order_notional_usd=ctx.max_order_notional_usd,
            max_daily_orders=ctx.max_daily_orders,
            max_daily_notional_usd=ctx.max_daily_notional_usd,
            max_open_orders=ctx.max_open_orders,
            max_positions=ctx.max_positions,
            max_portfolio_exposure_pct=ctx.max_portfolio_exposure_pct,
            now_utc=ctx.now_utc,
            investment_mode=True,
            shariah_evidence_records=ctx.shariah_evidence_records,
            personal_restrictions_config=ctx.personal_restrictions_config,
            watchlist_shariah_meta=ctx.watchlist_shariah_meta,
            eligibility_mode=ctx.eligibility_mode,
        )
        investment = self.decision_engine.evaluate(signal, inv_ctx).to_dict()

        # 2) Execution readiness (guards intact)
        readiness = classify_execution_readiness(
            signal=signal,
            ctx=ctx,
            investment_classification=investment["classification"],
        )

        from app.services.investment_eligibility import evaluate_investment_eligibility

        inv_elig = evaluate_investment_eligibility(
            str(signal.get("ticker") or ""),
            shariah_status=signal.get("shariah_status"),
            evidence_records=ctx.shariah_evidence_records,
            watchlist_meta=ctx.watchlist_shariah_meta,
            personal_config=ctx.personal_restrictions_config,
            sector=signal.get("sector"),
            industry=signal.get("industry"),
            name=signal.get("name") or signal.get("company_name"),
            as_of=(ctx.now_utc.date() if ctx.now_utc else None),
            eligibility_mode=ctx.eligibility_mode,
        )
        shariah_meta = classify_execution_eligibility(signal.get("shariah_status"))
        stored_shariah = str(signal.get("shariah_status") or "").strip().upper()
        mode = (ctx.eligibility_mode or "").strip().upper()
        if mode == "USER_POLICY":
            blocked_by_shariah = False  # Shariah optional in USER_POLICY
            blocked_by_personal = investment["classification"] == BUY_READY and (
                inv_elig.get("user_policy_status") != "ALLOWED"
            )
        else:
            blocked_by_shariah = investment["classification"] == BUY_READY and (
                stored_shariah != "VERIFIED" or not inv_elig.get("execution_eligible")
            )
            blocked_by_personal = investment["classification"] == BUY_READY and (
                inv_elig.get("personal_restriction_status") != "ALLOWED"
            )

        # 3) Simulated proposal (never submit)
        simulated = None
        if investment["classification"] == BUY_READY and inv_elig.get("proposal_permitted"):
            simulated = self._simulate_proposal(signal, investment, ctx)

        assert STAGE_APPROVAL_ENABLED is False
        assert STAGE_SUBMISSION_ENABLED is False
        self.submissions_attempted = 0

        entry = {
            "stage": "D2.4D",
            "signal_id": investment.get("signal_id"),
            "ticker": investment.get("ticker"),
            "strategy_version": investment.get("strategy_version") or V40_STRATEGY_VERSION,
            "signal_source": signal.get("signal_source"),
            "v40_signal": signal.get("signal"),
            "entry_rule": investment.get("entry_rule"),
            "market_as_of_date": investment.get("market_as_of_date"),
            "evaluated_at": investment.get("decided_at"),
            "investment_decision": {
                "classification": investment.get("classification"),
                "reason_codes": investment.get("reason_codes"),
            },
            "execution_readiness": readiness,
            "shariah_status": signal.get("shariah_status"),
            "shariah_eligibility": shariah_meta,
            "investment_eligibility": inv_elig,
            "eligibility_mode": mode or None,
            "user_policy_status": inv_elig.get("user_policy_status"),
            "personal_restriction_status": inv_elig.get("personal_restriction_status"),
            "blocked_by_shariah": blocked_by_shariah,
            "blocked_by_user_policy": bool(
                mode == "USER_POLICY"
                and investment["classification"] == BUY_READY
                and inv_elig.get("user_policy_status") != "ALLOWED"
            ),
            "blocked_by_personal_restriction": blocked_by_personal,
            "blocked_by_operational_restrictions": readiness.get("execution_readiness")
            in ("EMERGENCY_STOP", "DISABLED", "ACCOUNT_UNAVAILABLE", "DATA_UNAVAILABLE"),
            "simulated_proposal": simulated if isinstance(simulated, dict) and simulated.get("status") == "SIMULATED" else None,
            "sizing_block": simulated if isinstance(simulated, dict) and simulated.get("status") == "SIZING_BLOCKED" else None,
            "submission_attempted": False,
            "approval_attempted": False,
            "trading_execution_enabled_env": bool(TRADING_EXECUTION_ENABLED),
            "ibkr_emergency_stop_env": bool(IBKR_EMERGENCY_STOP),
        }

        if persist_journal:
            entry = self.journal.append(run_id, entry)
        return entry

    def run(
        self,
        *,
        ctx: DecisionContext,
        db: Optional[Session] = None,
        signals: Optional[List[Dict[str, Any]]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
        watchlist_meta: Optional[Dict[str, Dict[str, str]]] = None,
        run_id: Optional[str] = None,
        persist_journal: bool = True,
    ) -> Dict[str, Any]:
        """Run dry-run across snapshot signals + Shariah universe report."""
        now = ctx.now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        ctx.now_utc = now

        run_id = run_id or f"dryrun_{now.strftime('%Y%m%dT%H%M%SZ')}"
        loaded = self.load_snapshot_signals(db=db, signals=signals, snapshot=snapshot)
        sigs = loaded["signals"]

        # D2.4F: overlay WatchlistStock Shariah when caller did not supply meta.
        # Never invents VERIFIED — empty watchlist yields unchanged NOT VERIFIED defaults.
        if watchlist_meta is None and db is not None:
            from app.services.shariah_store import (
                attach_watchlist_shariah_to_signals,
                load_watchlist_shariah,
            )

            watchlist_meta = load_watchlist_shariah(db)
            sigs = attach_watchlist_shariah_to_signals(sigs, watchlist_meta)
        elif watchlist_meta:
            from app.services.shariah_store import attach_watchlist_shariah_to_signals

            sigs = attach_watchlist_shariah_to_signals(sigs, watchlist_meta)

        # Reject frozen/malformed from *executable proposals* but still evaluate for journal
        results = [
            self.evaluate_signal(s, ctx, run_id=run_id, persist_journal=persist_journal)
            for s in sigs
            if s
        ]

        shariah_report = build_shariah_universe_report(sigs, watchlist_meta=watchlist_meta)
        journal_summary = self.journal.summary(run_id) if persist_journal else {}

        buy_ready = [r for r in results if r["investment_decision"]["classification"] == BUY_READY]
        proposals = [r for r in results if r.get("simulated_proposal")]

        return {
            "stage": "D2.4D",
            "run_id": run_id,
            "evaluated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "snapshot_id": loaded.get("snapshot_id"),
            "snapshot_market_as_of_date": loaded.get("market_as_of_date"),
            "signals_source": loaded.get("source"),
            "signals_evaluated": len(results),
            "investment_buy_ready_count": len(buy_ready),
            "simulated_proposal_count": len(proposals),
            "submission_attempted": False,
            "approval_attempted": False,
            "submissions_attempted": self.submissions_attempted,
            "paper_broker": PAPER_BROKER,
            "results": results,
            "shariah_report": shariah_report,
            "journal_summary": journal_summary,
            "invariants": {
                "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
                "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
                "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
                "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
                "v40_signal_source": V40_SIGNAL_SOURCE,
            },
        }


buy_pipeline_dry_run = BuyPipelineDryRun()
