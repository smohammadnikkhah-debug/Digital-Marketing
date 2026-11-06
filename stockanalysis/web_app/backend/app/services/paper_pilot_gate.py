"""Stage D2.6 — Controlled one-order Alpaca paper pilot gate (preparation only).

Hard invariants for this stage:
- Never submits, approves, or claims broker orders.
- Never flips TRADING_EXECUTION_ENABLED / ALPACA_EXECUTION_ENABLED / emergency stop.
- At most one pilot order may ever be prepared for authorization.
- Manual approval is mandatory; no retries, no batch execution.
- Historical observation proposal prices are never treated as executable quotes.

Reuse: soak ledger, session_bundle evidence, USER_POLICY classifier, AlpacaReadOnlyClient,
order proposal sizing rules, observation safety asserts.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import (
    ALPACA_ENV,
    ALPACA_EXECUTION_ENABLED,
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    IBKR_EXECUTION_ENABLED,
    INVESTMENT_ELIGIBILITY_MODE,
    LIVE_TRADING_ENABLED,
    PAPER_BROKER,
    TRADING_EXECUTION_ENABLED,
    V40_STRATEGY_VERSION,
)
from app.services.alpaca_readonly import AlpacaReadOnlyClient, try_load_readonly_client
from app.services.candidate_ranking import RANKING_METHOD_ID, describe_ranking_methodology
from app.services.observation_safety import assert_observation_safety
from app.services.order_execution_service import (
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED
from app.services.paper_pilot_bundle import select_current_session_pilot_bundle
from app.services.paper_pilot_safety import (
    evaluate_candidate_execution_safety,
    extract_broker_quote_timestamp,
    validate_quote_for_pilot,
    validate_signal_for_pilot,
    validate_us_regular_session,
)
from app.services.user_policy_eligibility import classify_user_policy

logger = logging.getLogger("stockanalysis.paper_pilot_gate")

PILOT_STAGE = "D2.6"
PILOT_MAX_ORDERS = 1
PILOT_AUTO_SUBMIT = False
PILOT_AUTO_RETRY = False
PILOT_BATCH_EXECUTION = False

SOAK_LEDGER_PATH = DATA_CACHE_DIR / "observation" / "soak_ledger.json"
EVIDENCE_DIR = DATA_CACHE_DIR / "evidence"

# Exact Alpaca paper submission surface (documented; not called in D2.6)
ALPACA_PAPER_TRADING_BASE = "https://paper-api.alpaca.markets"
ALPACA_PAPER_ORDERS_ENDPOINT = "https://paper-api.alpaca.markets/v2/orders"
ALPACA_PAPER_SUBMIT_SDK = (
    "TradingClient(paper=True, url_override=https://paper-api.alpaca.markets)"
    ".submit_order(LimitOrderRequest(...))"
)


@dataclass
class PilotGateState:
    """Immutable preparation state — submission remains impossible while guards hold."""

    stage: str = PILOT_STAGE
    max_orders: int = PILOT_MAX_ORDERS
    auto_submit: bool = PILOT_AUTO_SUBMIT
    auto_retry: bool = PILOT_AUTO_RETRY
    batch_execution: bool = PILOT_BATCH_EXECUTION
    submissions_attempted: int = 0


def load_soak_ledger(path: Path = SOAK_LEDGER_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {"error": "SOAK_LEDGER_MISSING", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def assess_soak_prerequisite(ledger: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Final D2.4L pair must be complete before any paper execution authorization."""
    ledger = ledger if ledger is not None else load_soak_ledger()
    if ledger.get("error"):
        return {
            "prerequisite_met": False,
            "reason_code": ledger.get("error"),
            "soak_complete": False,
            "completed_pair_ids": [],
            "target_completed_pairs": 3,
            "remaining": "Create/restore soak_ledger.json and complete 3 observation pairs",
            "ledger": ledger,
        }

    completed = list(ledger.get("completed_pair_ids") or [])
    target = int(ledger.get("target_completed_pairs") or 3)
    soak_complete = bool(ledger.get("soak_complete")) and len(completed) >= target
    # Also accept explicit length match even if flag lagging
    if len(completed) >= target:
        soak_complete = True

    remaining = None
    if not soak_complete:
        remaining = (
            f"Need {target - len(completed)} more completed observation pair(s). "
            "Keep all execution flags disabled. Soak remains a separate "
            "authorization prerequisite from current-session pilot bundles."
        )

    return {
        "prerequisite_met": soak_complete,
        "reason_code": "SOAK_COMPLETE" if soak_complete else "SOAK_INCOMPLETE",
        "soak_complete": soak_complete,
        "completed_pair_ids": completed,
        "completed_pair_count": len(completed),
        "target_completed_pairs": target,
        "remaining": remaining,
        "sessions_recorded": len(ledger.get("sessions") or []),
        "updated_at_utc": ledger.get("updated_at_utc"),
    }


def _latest_post_close_bundle(
    *,
    now_utc: Optional[datetime] = None,
) -> Tuple[Optional[Path], Optional[Dict[str, Any]], Dict[str, Any]]:
    """Session-aware pilot bundle selection (D2.6C).

    Returns (path, bundle, selection_meta). Never silently returns an older
    session as current — missing current → CURRENT_SESSION_BUNDLE_MISSING.
    """
    selection = select_current_session_pilot_bundle(now_utc=now_utc)
    if not selection.get("ok"):
        return None, None, selection
    path_raw = selection.get("bundle_path")
    bundle = selection.get("bundle")
    path = Path(path_raw) if path_raw else None
    return path, bundle, selection


def list_allowed_buy_candidates(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Preserve scan order among USER_POLICY ALLOWED BUY CANDIDATES."""
    signals = {str(s.get("ticker") or "").upper(): s for s in (bundle.get("signals") or [])}
    rows: List[Dict[str, Any]] = []
    for i, c in enumerate(bundle.get("buy_candidates") or []):
        ticker = str(c.get("ticker") or "").upper()
        policy = str(c.get("policy") or "").upper()
        if policy != "ALLOWED":
            continue
        sig = signals.get(ticker) or {}
        # Re-validate policy independently (do not trust bundle alone)
        pol = classify_user_policy(
            ticker=ticker,
            sector=sig.get("sector"),
            industry=sig.get("industry"),
            name=sig.get("name") or sig.get("company_name"),
        )
        if pol.get("user_policy_status") != "ALLOWED":
            continue
        if str(sig.get("signal") or "").upper() != "BUY CANDIDATE":
            continue
        rows.append(
            {
                "scan_rank": i + 1,
                "ticker": ticker,
                "policy": "ALLOWED",
                "policy_detail": pol,
                "entry_rule": c.get("entry_rule") or sig.get("entry_rule"),
                "exit_rule": sig.get("exit_rule"),
                "signal_close": float(sig["close"]) if sig.get("close") is not None else None,
                "research_signal_price": c.get("signal_price"),
                "atr14": sig.get("atr14"),
                "ma50": sig.get("ma50"),
                "ma250": sig.get("ma250"),
                "roc20_pct": sig.get("roc20_pct"),
                "sector": sig.get("sector"),
                "industry": sig.get("industry"),
                "name": sig.get("name"),
                "market_as_of_date": sig.get("market_as_of_date"),
                "data_freshness": sig.get("data_freshness"),
                "strategy_version": sig.get("strategy_version"),
                "signal_source": sig.get("signal_source"),
            }
        )
    return rows


def size_whole_share_limit(
    *,
    ask: float,
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD,
    cash: float,
) -> Dict[str, Any]:
    """Cash-only whole-share sizing from a live ask — never from a historical proposal."""
    if ask <= 0:
        return {"ok": False, "reason_codes": ["INVALID_ASK"], "qty": 0, "limit_price": None, "notional": 0.0}
    budget = min(float(max_order_notional_usd), float(cash))
    qty = int(budget // ask)
    if qty < 1:
        return {
            "ok": False,
            "reason_codes": ["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
            "qty": 0,
            "limit_price": round(ask, 2),
            "notional": 0.0,
            "ask": ask,
            "budget": budget,
        }
    limit_price = round(ask, 2)
    notional = round(qty * limit_price, 2)
    if notional > max_order_notional_usd + 1e-9:
        return {
            "ok": False,
            "reason_codes": ["NOTIONAL_EXCEEDS_CAP"],
            "qty": qty,
            "limit_price": limit_price,
            "notional": notional,
        }
    return {
        "ok": True,
        "reason_codes": ["SIZING_OK"],
        "qty": qty,
        "limit_price": limit_price,
        "notional": notional,
        "ask": ask,
        "budget": budget,
        "max_order_notional_usd": max_order_notional_usd,
    }


def select_pilot_candidate(
    *,
    client: Optional[AlpacaReadOnlyClient] = None,
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD,
    now_utc: Optional[datetime] = None,
    bundle_selection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Highest scan-ranked ALLOWED BUY with fresh signal, safe quote, and whole-share ≤ cap.

    Ranking method is unchanged (D2E_BUY_READY_SEQUENCE_THEN_TICKER). Quote / signal
    hard failures are recorded on skipped_higher_rank before lower ranks are tried.
    Market-session failures do not discard research selection, but they block
    preview_ready via build_order_preview / run_d2_6_readiness.

    Bundle source is session-aware (D2.6C): required completed US session only.
    """
    now = now_utc or datetime.now(timezone.utc)
    if bundle_selection is None:
        bundle_path, bundle, bundle_selection = _latest_post_close_bundle(now_utc=now)
    else:
        bundle_path = (
            Path(bundle_selection["bundle_path"])
            if bundle_selection.get("bundle_path")
            else None
        )
        bundle = bundle_selection.get("bundle")

    if not bundle:
        return {
            "selected": False,
            "reason_code": bundle_selection.get("reason_code")
            or "CURRENT_SESSION_BUNDLE_MISSING",
            "reason_codes": list(bundle_selection.get("reason_codes") or ["CURRENT_SESSION_BUNDLE_MISSING"]),
            "bundle_selection": bundle_selection,
            "required_completed_session": bundle_selection.get("required_completed_session"),
        }

    freshness = (bundle.get("freshness") or {}).get("status")
    if freshness != "FRESH":
        return {
            "selected": False,
            "reason_code": "BUNDLE_NOT_FRESH",
            "freshness": freshness,
            "bundle_path": str(bundle_path) if bundle_path else None,
            "bundle_selection": bundle_selection,
        }

    allowed = list_allowed_buy_candidates(bundle)
    if not allowed:
        return {
            "selected": False,
            "reason_code": "NO_ALLOWED_BUY_CANDIDATES",
            "bundle_path": str(bundle_path) if bundle_path else None,
            "bundle_selection": bundle_selection,
        }

    own_client = client is None
    if client is None:
        client, status = try_load_readonly_client()
        if client is None:
            return {"selected": False, "reason_code": status or "ALPACA_UNAVAILABLE"}

    session_v = validate_us_regular_session(now_utc=now)
    research_fallback: Optional[Dict[str, Any]] = None

    try:
        snap = client.get_account_snapshot()
        cash = float(snap.cash or 0)
        skipped: List[Dict[str, Any]] = []
        for row in allowed:
            ticker = row["ticker"]
            quotes = client.get_quotes([ticker]) or {}
            q = quotes.get(ticker) or {}
            try:
                ask = float(q.get("ask") or 0)
                bid = float(q.get("bid") or 0)
            except (TypeError, ValueError):
                ask, bid = 0.0, 0.0

            quote_ts = extract_broker_quote_timestamp(q)
            live_quote = {
                "bid": bid,
                "ask": ask,
                "source": q.get("source"),
                "quote_timestamp": quote_ts,
                # Legacy key retained for evidence compatibility; broker emission time only
                "timestamp": quote_ts,
                "is_two_sided": q.get("is_two_sided"),
                "meets_30s_freshness": q.get("meets_30s_freshness"),
                "received_at": q.get("received_at"),
                "note": (
                    "Limit priced from this live Alpaca quote ask — "
                    "not from historical observation proposal prices. "
                    "Freshness uses quote_timestamp only (never received_at / wall clock)."
                ),
            }

            sizing = size_whole_share_limit(
                ask=ask, max_order_notional_usd=max_order_notional_usd, cash=cash
            )
            if not sizing.get("ok"):
                skipped.append(
                    {
                        "ticker": ticker,
                        "scan_rank": row["scan_rank"],
                        "ask": ask,
                        "bid": bid,
                        "quote_source": q.get("source"),
                        "quote_timestamp": quote_ts,
                        "reason_codes": list(sizing.get("reason_codes") or []),
                        "research_close": row.get("signal_close"),
                    }
                )
                continue

            safety = evaluate_candidate_execution_safety(
                quote=live_quote,
                candidate=row,
                bundle=bundle,
                now_utc=now,
            )
            quote_v = safety["quote_validation"]
            signal_v = safety["signal_validation"]
            # Quote + signal are hard selection gates; market session is preview-only
            hard_blockers = list(quote_v.get("reason_codes") or []) + list(
                signal_v.get("reason_codes") or []
            )
            if hard_blockers:
                skipped.append(
                    {
                        "ticker": ticker,
                        "scan_rank": row["scan_rank"],
                        "ask": ask,
                        "bid": bid,
                        "quote_source": q.get("source"),
                        "quote_timestamp": quote_ts,
                        "spread_pct": quote_v.get("spread_pct"),
                        "reason_codes": hard_blockers,
                        "quote_validation": quote_v,
                        "signal_validation": signal_v,
                        "research_close": row.get("signal_close"),
                        "market_as_of_date": row.get("market_as_of_date"),
                    }
                )
                # Keep first affordable research candidate for closed-session display
                if research_fallback is None:
                    research_fallback = {
                        "selected": True,
                        "reason_code": "RESEARCH_ONLY_SAFETY_BLOCKED",
                        "ranking_method": RANKING_METHOD_ID,
                        "ranking_notes": describe_ranking_methodology(),
                        "bundle_path": str(bundle_path) if bundle_path else None,
                        "trading_day": bundle.get("trading_day"),
                        "bundle_freshness": freshness,
                        "bundle_selection": bundle_selection,
                        "candidate": row,
                        "live_quote": live_quote,
                        "sizing": sizing,
                        "execution_safety": safety,
                        "account_cash": cash,
                        "account_id_redacted": (
                            f"****{(snap.account_id or '')[-4:]}"
                            if snap.account_id and len(snap.account_id) > 4
                            else "****"
                        ),
                        "skipped_higher_rank": list(skipped),
                        "evaluated_at_utc": now.astimezone(timezone.utc).isoformat()
                        if now.tzinfo
                        else now.replace(tzinfo=timezone.utc).isoformat(),
                    }
                continue

            # Attach current session validation (may still block preview if closed)
            safety = {
                **safety,
                "session_validation": session_v,
                "reason_codes": list(session_v.get("reason_codes") or []),
                "ok": bool(session_v.get("ok")),
            }
            return {
                "selected": True,
                "reason_code": "OK" if safety.get("ok") else "SELECTED_SESSION_BLOCKED",
                "ranking_method": RANKING_METHOD_ID,
                "ranking_notes": describe_ranking_methodology(),
                "bundle_path": str(bundle_path) if bundle_path else None,
                "trading_day": bundle.get("trading_day"),
                "bundle_freshness": freshness,
                "bundle_selection": bundle_selection,
                "candidate": row,
                "live_quote": {
                    **live_quote,
                    "spread_pct": quote_v.get("spread_pct"),
                    "quote_age_seconds": quote_v.get("quote_age_seconds"),
                },
                "sizing": sizing,
                "execution_safety": safety,
                "account_cash": cash,
                "account_id_redacted": (
                    f"****{(snap.account_id or '')[-4:]}"
                    if snap.account_id and len(snap.account_id) > 4
                    else "****"
                ),
                "skipped_higher_rank": skipped,
                "evaluated_at_utc": now.astimezone(timezone.utc).isoformat()
                if now.tzinfo
                else now.replace(tzinfo=timezone.utc).isoformat(),
            }

        if research_fallback is not None:
            research_fallback["skipped_higher_rank"] = skipped
            # Prefer showing research when market closed with only quote/signal failures elsewhere
            return research_fallback

        return {
            "selected": False,
            "reason_code": "NO_AFFORDABLE_ALLOWED_CANDIDATE",
            "bundle_path": str(bundle_path) if bundle_path else None,
            "bundle_selection": bundle_selection,
            "skipped": skipped,
            "allowed_count": len(allowed),
            "session_validation": session_v,
        }
    finally:
        if own_client:
            pass  # client has no close(); GC is fine


def build_order_preview(
    selection: Dict[str, Any],
    *,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Single LIMIT order preview — preparation artifact only.

    preview_ready requires quote, US regular session, and signal safety to pass.
    """
    if not selection.get("selected"):
        return {
            "preview_ready": False,
            "reason_code": selection.get("reason_code"),
            "reason_codes": [selection.get("reason_code")] if selection.get("reason_code") else [],
            "execution_status": "PREVIEW_BLOCKED_NO_CANDIDATE",
        }

    now = now_utc or datetime.now(timezone.utc)
    c = selection["candidate"]
    sizing = selection["sizing"]
    quote = dict(selection.get("live_quote") or {})
    atr = c.get("atr14")
    qty = int(sizing["qty"])
    limit_price = float(sizing["limit_price"])
    notional = float(sizing["notional"])
    atr_dollar = round(float(atr) * qty, 2) if atr is not None else None

    safety = selection.get("execution_safety")
    if not safety:
        safety = evaluate_candidate_execution_safety(
            quote=quote,
            candidate=c,
            bundle={"trading_day": selection.get("trading_day")},
            now_utc=now,
        )

    safety_ok = bool(safety.get("ok"))
    reason_codes = list(safety.get("reason_codes") or [])
    quote_v = safety.get("quote_validation") or validate_quote_for_pilot(quote, now_utc=now)
    session_v = safety.get("session_validation") or validate_us_regular_session(now_utc=now)
    signal_v = safety.get("signal_validation") or validate_signal_for_pilot(
        c, bundle={"trading_day": selection.get("trading_day")}, now_utc=now
    )

    preview_ready = safety_ok and not reason_codes
    if not preview_ready and not reason_codes:
        reason_codes = ["EXECUTION_SAFETY_FAILED"]

    payload = {
        "preview_ready": preview_ready,
        "reason_code": None if preview_ready else (reason_codes[0] if reason_codes else "NOT_READY"),
        "reason_codes": reason_codes,
        "stage": PILOT_STAGE,
        "order": {
            "ticker": c["ticker"],
            "side": "BUY",
            "order_type": "LIMIT",
            "time_in_force": "DAY",
            "quantity": qty,
            "limit_price": limit_price,
            "notional": notional,
            "currency": "USD",
            "broker": "alpaca",
            "env": "paper",
        },
        "signal_rationale": {
            "signal": "BUY CANDIDATE",
            "entry_rule": c.get("entry_rule"),
            "exit_rule": c.get("exit_rule"),
            "strategy_version": c.get("strategy_version") or V40_STRATEGY_VERSION,
            "signal_source": c.get("signal_source"),
            "market_as_of_date": c.get("market_as_of_date"),
            "research_close": c.get("signal_close"),
            "ma50": c.get("ma50"),
            "ma250": c.get("ma250"),
            "roc20_pct": c.get("roc20_pct"),
            "atr14": atr,
            "explanation": (
                f"{c['ticker']} is a V4.0 BUY CANDIDATE under entry rule "
                f"{c.get('entry_rule')} with exit rule {c.get('exit_rule')}. "
                "Pilot limit is the current Alpaca ask (whole shares), not a prior proposal print."
            ),
        },
        "policy_decision": {
            "mode": INVESTMENT_ELIGIBILITY_MODE,
            "status": "ALLOWED",
            "detail": c.get("policy_detail"),
        },
        "stop_loss_risk_plan": {
            "fixed_stop_price": None,
            "fixed_stop_available": False,
            "exit_rule": c.get("exit_rule"),
            "exit_rule_meaning": (
                "Strategy exits via the walk-forward-selected MA250 rule "
                "(MA250_3CLOSE or MA250_ATR3) — not a broker stop ticket."
            ),
            "atr14": atr,
            "approx_1x_atr_dollar_risk_on_position": atr_dollar,
            "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
            "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
            "pilot_max_orders": PILOT_MAX_ORDERS,
            "note": "Do not invent a stop price; use strategy exit rule + $500 hard cap as risk bound.",
        },
        "live_quote": {
            **quote,
            "spread_pct": quote_v.get("spread_pct"),
            "quote_age_seconds": quote_v.get("quote_age_seconds"),
        },
        "execution_safety": {
            "ok": safety_ok,
            "reason_codes": reason_codes,
            "quote_validation": quote_v,
            "session_validation": session_v,
            "signal_validation": signal_v,
        },
        "safety_checks_that_must_pass_before_submit": [
            "D2.4L soak_complete == True (3 completed pairs)",
            "IBKR_EMERGENCY_STOP remains True until explicitly authorized otherwise for paper path",
            "Explicit human authorization to enable paper submission for ONE order only",
            "ALPACA_ENV == paper and trading URL is paper-api.alpaca.markets (not api.alpaca.markets)",
            "USER_POLICY status ALLOWED re-checked at approval time",
            "Live Alpaca quote ask > 0 and whole-share qty >= 1 under $500",
            "Broker quote_timestamp present, timezone-aware, ≤30s old, not materially future",
            "Bid/ask valid and spread ≤ 1% of midpoint",
            "US regular trading session (America/New_York calendar; holidays/early closes)",
            "Signal market_as_of equals last completed US equity session (strategy carry-forward)",
            "Account cash >= notional; open_orders == 0; daily caps not exceeded",
            "No existing long position in ticker",
            "STAGE path: propose → AWAITING_APPROVAL → manual approve → single submit (no auto-retry)",
            "can_auto_resubmit must remain False",
            "LIVE_TRADING_ENABLED must remain False",
        ],
        "submission_endpoint_documented": {
            "trading_base": ALPACA_PAPER_TRADING_BASE,
            "orders_rest": ALPACA_PAPER_ORDERS_ENDPOINT,
            "sdk_path": ALPACA_PAPER_SUBMIT_SDK,
            "called_in_d2_6": False,
        },
        "execution_status": (
            "PREVIEW_ONLY_NOT_SUBMITTED" if preview_ready else "PREVIEW_BLOCKED_SAFETY"
        ),
    }
    return payload


def verify_pilot_gate_invariants(state: Optional[PilotGateState] = None) -> Dict[str, Any]:
    """Strict one-order, manually approved, non-submitting gate verification."""
    state = state or PilotGateState()
    safety = assert_observation_safety(phase="d2_6_pilot_prep", submissions_attempted=state.submissions_attempted)
    failures: List[str] = list(safety.get("failures") or [])

    if state.max_orders != 1:
        failures.append("PILOT_MAX_ORDERS must be 1")
    if state.auto_submit or state.auto_retry or state.batch_execution:
        failures.append("Pilot auto-submit/retry/batch must be False")
    if STAGE_APPROVAL_ENABLED or STAGE_SUBMISSION_ENABLED:
        failures.append("Stage approval/submission must stay False during preparation")
    if TRADING_EXECUTION_ENABLED or ALPACA_EXECUTION_ENABLED or IBKR_EXECUTION_ENABLED:
        failures.append("Broker/trading execution flags must stay False during preparation")
    if LIVE_TRADING_ENABLED:
        failures.append("LIVE_TRADING_ENABLED must stay False")
    if not IBKR_EMERGENCY_STOP:
        failures.append("Emergency stop must remain engaged during preparation")
    if PAPER_BROKER != "alpaca":
        failures.append(f"Unexpected PAPER_BROKER={PAPER_BROKER}")
    if ALPACA_ENV != "paper":
        failures.append(f"ALPACA_ENV must be paper (got {ALPACA_ENV})")

    return {
        "gate_id": "D2_6_ONE_ORDER_MANUAL_APPROVAL",
        "passed": len(failures) == 0,
        "failures": failures,
        "state": {
            "stage": state.stage,
            "max_orders": state.max_orders,
            "auto_submit": state.auto_submit,
            "auto_retry": state.auto_retry,
            "batch_execution": state.batch_execution,
            "submissions_attempted": state.submissions_attempted,
        },
        "flags": {
            "IBKR_EMERGENCY_STOP": IBKR_EMERGENCY_STOP,
            "TRADING_EXECUTION_ENABLED": TRADING_EXECUTION_ENABLED,
            "ALPACA_EXECUTION_ENABLED": ALPACA_EXECUTION_ENABLED,
            "IBKR_EXECUTION_ENABLED": IBKR_EXECUTION_ENABLED,
            "LIVE_TRADING_ENABLED": LIVE_TRADING_ENABLED,
            "STAGE_APPROVAL_ENABLED": STAGE_APPROVAL_ENABLED,
            "STAGE_SUBMISSION_ENABLED": STAGE_SUBMISSION_ENABLED,
            "PAPER_BROKER": PAPER_BROKER,
            "ALPACA_ENV": ALPACA_ENV,
            "INVESTMENT_ELIGIBILITY_MODE": INVESTMENT_ELIGIBILITY_MODE,
        },
        "limits": {
            "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
            "max_daily_orders": DEFAULT_MAX_DAILY_ORDERS,
            "max_daily_notional_usd": DEFAULT_MAX_DAILY_NOTIONAL_USD,
            "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
            "pilot_max_orders": PILOT_MAX_ORDERS,
        },
        "observation_safety": safety,
        "manual_approval_required": True,
        "automatic_submission_permitted": False,
    }


def assess_tracking_readiness(client: Optional[AlpacaReadOnlyClient] = None) -> Dict[str, Any]:
    """Confirm order/fill/position/P&L/benchmark observation surfaces exist (read-only)."""
    from app.models import PaperOrder  # local import to keep module light when unused
    from app.database import SessionLocal

    db_orders = 0
    try:
        db = SessionLocal()
        try:
            db_orders = db.query(PaperOrder).count()
        finally:
            db.close()
    except Exception as exc:
        db_orders = -1
        db_error = f"{type(exc).__name__}: {exc}"
    else:
        db_error = None

    alpaca_positions = None
    alpaca_orders = None
    alpaca_pnl_fields = None
    if client is not None:
        try:
            positions = client.adapter.get_positions() or []
            orders = client.adapter.get_orders(status="all") or []
            alpaca_positions = len(positions)
            alpaca_orders = len(orders)
            # Position payload includes unrealized_pl when holdings exist
            alpaca_pnl_fields = ["unrealized_pl", "unrealized_plpc", "avg_entry_price", "market_value"]
        except Exception as exc:
            alpaca_positions = f"error:{exc}"

    return {
        "paper_orders_table_available": db_error is None,
        "paper_orders_count": db_orders,
        "paper_orders_error": db_error,
        "lifecycle_states_supported": [
            "DRAFT",
            "AWAITING_APPROVAL",
            "APPROVED",
            "SUBMITTED",
            "PARTIAL_FILL",
            "FILLED",
            "CANCELLED",
            "REJECTED",
        ],
        "alpaca_positions_count": alpaca_positions,
        "alpaca_orders_visible_count": alpaca_orders,
        "alpaca_position_pnl_fields": alpaca_pnl_fields,
        "benchmark_tracking": {
            "spy_in_universe": True,
            "observation_performance_module": "app.services.observation_performance",
            "v40_excel_annual_vs_spy": True,
            "note": "Pilot P&L vs SPY can use Alpaca position unrealized_pl plus SPY bar cache; no live paper fills yet.",
        },
        "fill_approximation_available": True,
        "real_broker_fills_to_date": 0,
    }


def run_d2_6_readiness(
    *,
    write_evidence: bool = True,
    now_utc: Optional[datetime] = None,
    client: Optional[AlpacaReadOnlyClient] = None,
    selection: Optional[Dict[str, Any]] = None,
    soak_ledger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full D2.6 preparation assessment — never submits orders.

    Optional client/selection/now_utc/soak_ledger enable deterministic tests.
    """
    now = now_utc or datetime.now(timezone.utc)
    gate = verify_pilot_gate_invariants()
    soak = assess_soak_prerequisite(soak_ledger)

    alpaca_report = None
    endpoint_check = {
        "configured_trading_url": None,
        "is_paper_endpoint": None,
        "orders_endpoint": ALPACA_PAPER_ORDERS_ENDPOINT,
        "sdk_submit_path": ALPACA_PAPER_SUBMIT_SDK,
        "submit_invoked": False,
        "submit_blocked": None,
    }
    own_client = client is None and selection is None
    client_status = None
    if selection is None:
        if client is None:
            client, client_status = try_load_readonly_client()
        if client is not None:
            alpaca_report = client.validate_readonly()
            endpoint_check["configured_trading_url"] = getattr(client.adapter, "trading_url", None)
            url = str(endpoint_check["configured_trading_url"] or "").lower().rstrip("/")
            endpoint_check["is_paper_endpoint"] = url.startswith("https://paper-api.alpaca.markets")
            endpoint_check["live_endpoint_rejected"] = url.startswith("https://api.alpaca.markets")
            endpoint_check["submit_blocked"] = bool(alpaca_report.get("order_submission_blocked"))
            selection = select_pilot_candidate(client=client, now_utc=now)
        else:
            selection = {"selected": False, "reason_code": client_status or "ALPACA_UNAVAILABLE"}

    preview = build_order_preview(selection, now_utc=now)
    tracking = assess_tracking_readiness(client if not own_client or client is not None else client)

    safety = preview.get("execution_safety") or selection.get("execution_safety") or {}
    safety_codes = list(preview.get("reason_codes") or safety.get("reason_codes") or [])

    # GO only if soak complete AND preview ready AND gate intact AND submit still blocked in prep
    blockers: List[str] = []
    if not soak.get("prerequisite_met"):
        blockers.append(soak.get("remaining") or "Soak incomplete")
    if not gate.get("passed"):
        blockers.append(f"Pilot gate failures: {gate.get('failures')}")
    bundle_sel = selection.get("bundle_selection") or {}
    bundle_codes = list(selection.get("reason_codes") or bundle_sel.get("reason_codes") or [])
    if selection.get("reason_code") == "CURRENT_SESSION_BUNDLE_MISSING" or (
        "CURRENT_SESSION_BUNDLE_MISSING" in bundle_codes
    ):
        blockers.append("CURRENT_SESSION_BUNDLE_MISSING")
    if not selection.get("selected"):
        blockers.append(
            f"No pilot candidate selected: {selection.get('reason_code') or 'NO_CANDIDATE'}"
        )
    if not preview.get("preview_ready"):
        detail = preview.get("reason_code") or selection.get("reason_code") or "NOT_READY"
        if safety_codes:
            blockers.append(f"Order preview not execution-ready: {', '.join(safety_codes)}")
        else:
            blockers.append(f"No order preview: {detail}")
    # Surface each hard safety code explicitly in the JSON blockers list
    for code in safety_codes:
        if code not in blockers:
            blockers.append(code)
    for code in bundle_codes:
        if code not in blockers:
            blockers.append(code)
    if alpaca_report and not alpaca_report.get("order_submission_blocked", True):
        blockers.append("Order submission unexpectedly unblocked during preparation")
    if alpaca_report and not alpaca_report.get("connected"):
        blockers.append(f"Alpaca not connected: {alpaca_report.get('error')}")

    # Any hard safety failure or missing preview → NO-GO. CONDITIONAL GO only when
    # all technical/market-data prerequisites passed (human auth still outstanding).
    hard_fail = (
        not soak.get("prerequisite_met")
        or not gate.get("passed")
        or not selection.get("selected")
        or not preview.get("preview_ready")
        or bool(safety_codes)
        or bool(blockers)
    )
    recommendation = "NO-GO" if hard_fail else "CONDITIONAL GO"

    result = {
        "stage": PILOT_STAGE,
        "generated_at_utc": now.astimezone(timezone.utc).isoformat()
        if now.tzinfo
        else now.replace(tzinfo=timezone.utc).isoformat(),
        "recommendation": recommendation,
        "blockers": blockers,
        "safety_reason_codes": safety_codes,
        "bundle_selection": bundle_sel
        or selection.get("bundle_selection")
        or {"reason_code": selection.get("reason_code")},
        "required_completed_session": (
            bundle_sel.get("required_completed_session")
            or selection.get("required_completed_session")
        ),
        "soak_prerequisite": soak,
        "pilot_gate": gate,
        "alpaca_readonly": alpaca_report,
        "endpoint_verification": endpoint_check,
        "candidate_selection": selection,
        "order_preview": preview,
        "tracking": tracking,
        "execution_attempted": False,
        "submissions_attempted": 0,
        "authorization_steps_remaining": _authorization_steps(soak, recommendation),
    }

    if write_evidence:
        out_dir = EVIDENCE_DIR / f"d2_6_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "d2_6_readiness.json"
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        result["evidence_path"] = str(out_path)

    return result


def _authorization_steps(soak: Dict[str, Any], recommendation: str) -> List[str]:
    steps = []
    if not soak.get("prerequisite_met"):
        steps.append(
            "1. Confirm soak_ledger.json shows completed_pair_ids length == 3 "
            "(soak remains a separate prerequisite from current-session bundles)"
        )
    else:
        steps.append("1. Confirm soak_ledger.json shows 3 completed pairs (already met)")
    steps.extend(
        [
            "2. Ensure a validated post-close bundle exists for required_completed_session "
            "(scheduled-window observation preferred; catch-up is not auto-promoted)",
            "3. Re-run paper_pilot_gate.run_d2_6_readiness() during US RTH with a fresh "
            "narrow-spread Alpaca quote and confirm preview_ready",
            "4. Explicit written authorization for ONE Alpaca paper LIMIT order only",
            "5. Bind/confirm Alpaca paper account in settings; keep LIVE_TRADING_ENABLED=false",
            "6. Temporarily enable paper submission path for a single manually approved order "
            "(ALPACA_EXECUTION_ENABLED + controlled STAGE_SUBMISSION / non-executing guard change) "
            "— do not enable batch or auto-retry",
            "7. propose_order → manual approve_order → single submit → immediately restore execution-disabled defaults",
            "8. Monitor Alpaca blotter + PaperOrder lifecycle + unrealized P&L vs SPY",
        ]
    )
    if recommendation == "NO-GO":
        steps.insert(0, "0. DO NOT authorize execution — prerequisites/blockers remain")
    return steps
