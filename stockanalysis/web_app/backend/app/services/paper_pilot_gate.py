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
            "Await unattended next_session for pair opened by latest post_close "
            "(currently 2026-10-28→2026-10-29). Keep all execution flags disabled."
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


def _latest_post_close_bundle() -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    """Prefer soak-ledger post_close evidence; fall back to newest d2_4l_*post_close bundle."""
    ledger = load_soak_ledger()
    sessions = ledger.get("sessions") or []
    post_closes = [s for s in sessions if s.get("mode") == "post_close" and s.get("eligible")]
    if post_closes:
        latest = post_closes[-1]
        evidence = Path(latest.get("evidence_dir") or "")
        bundle_path = evidence / "session_bundle.json"
        if bundle_path.exists():
            return bundle_path, json.loads(bundle_path.read_text(encoding="utf-8"))

    candidates = sorted(EVIDENCE_DIR.glob("d2_4l_*/session_bundle.json"), reverse=True)
    for path in candidates:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("mode") == "post_close":
            return path, data
    return None, None


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
) -> Dict[str, Any]:
    """Highest scan-ranked ALLOWED BUY with fresh signal and live whole-share ≤ cap."""
    bundle_path, bundle = _latest_post_close_bundle()
    if not bundle:
        return {"selected": False, "reason_code": "NO_POST_CLOSE_BUNDLE"}

    freshness = (bundle.get("freshness") or {}).get("status")
    if freshness != "FRESH":
        return {
            "selected": False,
            "reason_code": "BUNDLE_NOT_FRESH",
            "freshness": freshness,
            "bundle_path": str(bundle_path),
        }

    allowed = list_allowed_buy_candidates(bundle)
    if not allowed:
        return {"selected": False, "reason_code": "NO_ALLOWED_BUY_CANDIDATES", "bundle_path": str(bundle_path)}

    own_client = client is None
    if client is None:
        client, status = try_load_readonly_client()
        if client is None:
            return {"selected": False, "reason_code": status or "ALPACA_UNAVAILABLE"}

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
            sizing = size_whole_share_limit(ask=ask, max_order_notional_usd=max_order_notional_usd, cash=cash)
            if not sizing.get("ok"):
                skipped.append(
                    {
                        "ticker": ticker,
                        "scan_rank": row["scan_rank"],
                        "ask": ask,
                        "bid": bid,
                        "quote_source": q.get("source"),
                        "reason_codes": sizing.get("reason_codes"),
                        "research_close": row.get("signal_close"),
                    }
                )
                continue
            # Fresh signal gate
            if str(row.get("data_freshness") or "").upper() != "FRESH":
                skipped.append({**row, "reason_codes": ["SIGNAL_NOT_FRESH"]})
                continue
            return {
                "selected": True,
                "reason_code": "OK",
                "ranking_method": RANKING_METHOD_ID,
                "ranking_notes": describe_ranking_methodology(),
                "bundle_path": str(bundle_path),
                "trading_day": bundle.get("trading_day"),
                "bundle_freshness": freshness,
                "candidate": row,
                "live_quote": {
                    "bid": bid,
                    "ask": ask,
                    "source": q.get("source"),
                    "timestamp": q.get("timestamp") or q.get("asof") or q.get("t"),
                    "is_two_sided": q.get("is_two_sided"),
                    "meets_30s_freshness": q.get("meets_30s_freshness"),
                    "note": (
                        "Limit priced from this live Alpaca quote ask — "
                        "not from historical observation proposal prices."
                    ),
                },
                "sizing": sizing,
                "account_cash": cash,
                "account_id_redacted": (
                    f"****{(snap.account_id or '')[-4:]}" if snap.account_id and len(snap.account_id) > 4 else "****"
                ),
                "skipped_higher_rank": skipped,
            }
        return {
            "selected": False,
            "reason_code": "NO_AFFORDABLE_ALLOWED_CANDIDATE",
            "bundle_path": str(bundle_path),
            "skipped": skipped,
            "allowed_count": len(allowed),
        }
    finally:
        if own_client:
            pass  # client has no close(); GC is fine


def build_order_preview(selection: Dict[str, Any]) -> Dict[str, Any]:
    """Single LIMIT order preview — preparation artifact only."""
    if not selection.get("selected"):
        return {"preview_ready": False, "reason_code": selection.get("reason_code")}

    c = selection["candidate"]
    sizing = selection["sizing"]
    quote = selection["live_quote"]
    atr = c.get("atr14")
    qty = int(sizing["qty"])
    limit_price = float(sizing["limit_price"])
    notional = float(sizing["notional"])
    atr_dollar = round(float(atr) * qty, 2) if atr is not None else None

    return {
        "preview_ready": True,
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
        "live_quote": quote,
        "safety_checks_that_must_pass_before_submit": [
            "D2.4L soak_complete == True (3 completed pairs)",
            "IBKR_EMERGENCY_STOP remains True until explicitly authorized otherwise for paper path",
            "Explicit human authorization to enable paper submission for ONE order only",
            "ALPACA_ENV == paper and trading URL is paper-api.alpaca.markets (not api.alpaca.markets)",
            "USER_POLICY status ALLOWED re-checked at approval time",
            "Live Alpaca quote ask > 0 and whole-share qty >= 1 under $500",
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
        "execution_status": "PREVIEW_ONLY_NOT_SUBMITTED",
    }


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


def run_d2_6_readiness(*, write_evidence: bool = True) -> Dict[str, Any]:
    """Full D2.6 preparation assessment — never submits orders."""
    gate = verify_pilot_gate_invariants()
    soak = assess_soak_prerequisite()

    client, client_status = try_load_readonly_client()
    alpaca_report = None
    endpoint_check = {
        "configured_trading_url": None,
        "is_paper_endpoint": None,
        "orders_endpoint": ALPACA_PAPER_ORDERS_ENDPOINT,
        "sdk_submit_path": ALPACA_PAPER_SUBMIT_SDK,
        "submit_invoked": False,
        "submit_blocked": None,
    }
    selection: Dict[str, Any] = {"selected": False, "reason_code": "ALPACA_UNAVAILABLE"}
    if client is not None:
        alpaca_report = client.validate_readonly()
        endpoint_check["configured_trading_url"] = getattr(client.adapter, "trading_url", None)
        url = str(endpoint_check["configured_trading_url"] or "").lower().rstrip("/")
        endpoint_check["is_paper_endpoint"] = url.startswith("https://paper-api.alpaca.markets")
        endpoint_check["live_endpoint_rejected"] = url.startswith("https://api.alpaca.markets")
        endpoint_check["submit_blocked"] = bool(alpaca_report.get("order_submission_blocked"))
        selection = select_pilot_candidate(client=client)
    else:
        selection = {"selected": False, "reason_code": client_status}

    preview = build_order_preview(selection)
    tracking = assess_tracking_readiness(client)

    # GO only if soak complete AND preview ready AND gate intact AND submit still blocked in prep
    blockers: List[str] = []
    if not soak.get("prerequisite_met"):
        blockers.append(soak.get("remaining") or "Soak incomplete")
    if not gate.get("passed"):
        blockers.append(f"Pilot gate failures: {gate.get('failures')}")
    if not preview.get("preview_ready"):
        blockers.append(f"No order preview: {preview.get('reason_code') or selection.get('reason_code')}")
    if alpaca_report and not alpaca_report.get("order_submission_blocked", True):
        blockers.append("Order submission unexpectedly unblocked during preparation")
    if alpaca_report and not alpaca_report.get("connected"):
        blockers.append(f"Alpaca not connected: {alpaca_report.get('error')}")

    # During D2.6 prep, recommendation is NO-GO for execution even if preview exists,
    # until soak + explicit authorization. If soak incomplete → hard NO-GO.
    if not soak.get("prerequisite_met"):
        recommendation = "NO-GO"
    elif blockers:
        recommendation = "NO-GO"
    else:
        # Soak met + preview ready + gates intact → CONDITIONAL GO pending human auth
        recommendation = "CONDITIONAL GO"

    result = {
        "stage": PILOT_STAGE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "recommendation": recommendation,
        "blockers": blockers,
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
            "1. Wait for unattended D2.4L next_session to complete pair "
            "2026-10-28→2026-10-29 and confirm soak_complete=true / "
            "completed_pair_ids length == 3 in soak_ledger.json"
        )
    else:
        steps.append("1. Confirm soak_ledger.json shows 3 completed pairs (already met)")
    steps.extend(
        [
            "2. Re-run paper_pilot_gate.run_d2_6_readiness() and confirm preview_ready with a live session quote",
            "3. Explicit written authorization for ONE Alpaca paper LIMIT order only",
            "4. Bind/confirm Alpaca paper account in settings; keep LIVE_TRADING_ENABLED=false",
            "5. Temporarily enable paper submission path for a single manually approved order "
            "(ALPACA_EXECUTION_ENABLED + controlled STAGE_SUBMISSION / non-executing guard change) "
            "— do not enable batch or auto-retry",
            "6. propose_order → manual approve_order → single submit → immediately restore execution-disabled defaults",
            "7. Monitor Alpaca blotter + PaperOrder lifecycle + unrealized P&L vs SPY",
        ]
    )
    if recommendation == "NO-GO":
        steps.insert(0, "0. DO NOT authorize execution — prerequisites/blockers remain")
    return steps
