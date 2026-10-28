"""V4.0 Autonomous BUY Decision Engine (Stage D2.4C).

Converts authoritative scanner BUY CANDIDATE signals into deterministic
classifications: BUY_READY | WAIT | BLOCKED | NO_ACTION.

Does not submit broker orders. Does not invent new technical indicators.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence  # Sequence used by DecisionContext overlays

from app.config import (
    DEFAULT_MAX_POSITIONS,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
    RISK_UI_SIGNAL_SOURCE,
)
from app.services.market_data_service import (
    ALLOWED_EXECUTION_PROVIDERS,
    DISALLOWED_EXECUTION_PROVIDERS,
    MarketDataService,
    market_data_service,
)
from app.services.order_execution_service import (
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.shariah_eligibility import ELIGIBLE, classify_execution_eligibility
from app.services.us_session_freshness import evaluate_signal_session_freshness

# Decision classifications
BUY_READY = "BUY_READY"
WAIT = "WAIT"
BLOCKED = "BLOCKED"
NO_ACTION = "NO_ACTION"

VALID_V40_ENTRY_RULES = frozenset({
    "CROSS",
    "MA50_AT_CROSS",
    "ROC20_AT_CROSS",
    "DELAYED_MA50",
    "DELAYED_STACK",
})

VALID_BUY_SIGNALS = frozenset({"BUY CANDIDATE", "BUY"})


@dataclass
class AccountSnapshot:
    """Paper-account state for decisioning. Never use V4.0 simulated holdings."""
    broker: str
    account_id: str
    cash: float
    equity: float
    positions: List[Dict[str, Any]] = field(default_factory=list)
    open_orders: List[Dict[str, Any]] = field(default_factory=list)
    daily_orders_count: int = 0
    daily_notional_sum: float = 0.0
    snapshot_fresh: bool = False
    connection_ok: bool = False
    as_of_utc: Optional[str] = None


@dataclass
class DecisionContext:
    account: Optional[AccountSnapshot]
    broker_quote: Optional[Dict[str, Any]] = None
    emergency_stop: bool = True
    execution_enabled: bool = False
    trading_execution_enabled: bool = False
    max_order_notional_usd: float = DEFAULT_MAX_ORDER_NOTIONAL_USD
    max_daily_orders: int = DEFAULT_MAX_DAILY_ORDERS
    max_daily_notional_usd: float = DEFAULT_MAX_DAILY_NOTIONAL_USD
    max_open_orders: int = DEFAULT_MAX_OPEN_ORDERS
    max_positions: int = DEFAULT_MAX_POSITIONS
    max_portfolio_exposure_pct: float = 100.0  # equal-slot implies <= 100%
    now_utc: Optional[datetime] = None
    # When True (D2.4D dry-run investment path): classify opportunity without
    # emergency-stop / account / quote gates so BUY_READY stays visible while
    # execution readiness is tracked separately.
    investment_mode: bool = False
    # D2.4G optional overlays (never invent verification)
    shariah_evidence_records: Optional[Sequence[Any]] = None
    personal_restrictions_config: Optional[Dict[str, Any]] = None
    watchlist_shariah_meta: Optional[Dict[str, str]] = None
    # D2.4H: USER_POLICY | SHARIAH_STRICT | None (legacy VERIFIED gate for tests)
    eligibility_mode: Optional[str] = None
    # D2.4I: isolated dry-run sizing may ignore cash-session WAIT only.
    # Does not bypass policy, quote, account, or portfolio risk gates.
    allow_off_session_sizing: bool = False


@dataclass
class BuyDecision:
    classification: str
    reason_codes: List[str]
    ticker: str
    signal_id: str
    decided_at: str
    strategy_version: str
    entry_rule: Optional[str]
    signal: Optional[str]
    market_as_of_date: Optional[str]
    expected_session_date: Optional[str]
    broker: Optional[str] = None
    account_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_signal_id(signal: Dict[str, Any]) -> str:
    """Deterministic identity for a scanner signal instance."""
    ticker = str(signal.get("ticker") or "").strip().upper()
    as_of = str(signal.get("market_as_of_date") or signal.get("as_of") or "")[:10]
    entry = str(signal.get("entry_rule") or "")
    version = str(signal.get("strategy_version") or V40_STRATEGY_VERSION)
    scan_ts = str(signal.get("scan_completed_at") or "")
    raw = f"{ticker}|{as_of}|{entry}|{version}|{scan_ts}|{signal.get('signal')}"
    return "sig_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class BuyDecisionEngine:
    """Deterministic V4.0 BUY decision classifier."""

    def __init__(self, mds: Optional[MarketDataService] = None):
        self.mds = mds or market_data_service

    def evaluate(self, signal: Dict[str, Any], ctx: DecisionContext) -> BuyDecision:
        now = ctx.now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        ticker = str(signal.get("ticker") or "").strip().upper()
        signal_id = build_signal_id(signal)
        strategy_version = str(signal.get("strategy_version") or "")
        entry_rule = signal.get("entry_rule")
        sig_label = signal.get("signal")
        market_as_of = signal.get("market_as_of_date") or signal.get("as_of")

        base_kwargs = dict(
            ticker=ticker or "UNKNOWN",
            signal_id=signal_id,
            decided_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            strategy_version=strategy_version or V40_STRATEGY_VERSION,
            entry_rule=str(entry_rule) if entry_rule else None,
            signal=str(sig_label) if sig_label else None,
            market_as_of_date=str(market_as_of)[:10] if market_as_of else None,
            expected_session_date=None,
            broker=(ctx.account.broker if ctx.account else None),
            account_id=(ctx.account.account_id if ctx.account else None),
        )

        reasons: List[str] = []

        # --- Source / shape gates → NO_ACTION or BLOCKED ---
        source = str(signal.get("signal_source") or "").strip()
        if source == RISK_UI_SIGNAL_SOURCE or signal.get("not_a_v40_scanner_signal"):
            return BuyDecision(
                classification=NO_ACTION,
                reason_codes=["RISK_UI_SIGNAL_REJECTED"],
                **base_kwargs,
            )
        if source != V40_SIGNAL_SOURCE:
            return BuyDecision(
                classification=NO_ACTION,
                reason_codes=["NON_V40_SIGNAL_SOURCE"],
                **base_kwargs,
            )

        if signal.get("provenance_mode") == "FROZEN_BASELINE" or signal.get("data_freshness") == "FROZEN_BASELINE":
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["FROZEN_BASELINE_SIGNAL"],
                **base_kwargs,
            )
        if signal.get("is_fresh_analysis") is not True:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["NOT_FRESH_ANALYSIS"],
                **base_kwargs,
            )

        if sig_label not in VALID_BUY_SIGNALS:
            return BuyDecision(
                classification=NO_ACTION,
                reason_codes=["NOT_BUY_CANDIDATE"],
                **base_kwargs,
                details={"observed_signal": sig_label},
            )

        if not strategy_version or (
            strategy_version != V40_STRATEGY_VERSION
            and not str(strategy_version).startswith("V4.0 Baseline")
        ):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INVALID_STRATEGY_VERSION"],
                **base_kwargs,
            )

        if not entry_rule or str(entry_rule) not in VALID_V40_ENTRY_RULES:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INVALID_ENTRY_RULE"],
                **base_kwargs,
            )

        validation = str(signal.get("validation_status") or "").upper()
        freshness = str(signal.get("data_freshness") or "").upper()
        if validation in ("INSUFFICIENT_DATA",) or freshness in ("INSUFFICIENT_DATA",):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INSUFFICIENT_HISTORY"],
                **base_kwargs,
            )
        if validation in ("STALE_BARS",) or freshness in ("STALE",):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["STALE_MARKET_DATA"],
                **base_kwargs,
            )
        if signal.get("ma250") is None:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["MISSING_MA250"],
                **base_kwargs,
            )

        # Session freshness (US calendar — not raw hours)
        is_fresh, fresh_code, as_of_d, expected_d = evaluate_signal_session_freshness(
            market_as_of, now_utc=now
        )
        base_kwargs["expected_session_date"] = expected_d.isoformat() if expected_d else None
        base_kwargs["market_as_of_date"] = as_of_d.isoformat() if as_of_d else base_kwargs["market_as_of_date"]
        if not is_fresh:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=[fresh_code],
                **base_kwargs,
            )
        reasons.append(fresh_code)

        # Shariah metadata (never inferred / never rewritten)
        shariah_meta = classify_execution_eligibility(signal.get("shariah_status"))
        stored_status = str(signal.get("shariah_status") or "").strip().upper()

        # D2.4G combined eligibility (evidence + personal restrictions)
        from app.services.investment_eligibility import evaluate_investment_eligibility

        inv_elig = evaluate_investment_eligibility(
            ticker,
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

        # --- Investment-only path (D2.4D): opportunity visible without execution gates ---
        if ctx.investment_mode:
            reasons.append("INVESTMENT_MODE")
            reasons.append("V40_BUY_CONFIRMED")
            return BuyDecision(
                classification=BUY_READY,
                reason_codes=reasons,
                **base_kwargs,
                details={
                    "shariah": shariah_meta,
                    "shariah_status_stored": stored_status or "NOT VERIFIED",
                    "investment_eligibility": inv_elig,
                    "user_policy_status": inv_elig.get("user_policy_status"),
                    "investment_mode": True,
                },
            )

        # Fail closed for executable path (mode-aware).
        if not inv_elig.get("execution_eligible"):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=list(inv_elig.get("reason_codes") or ["INVESTMENT_ELIGIBILITY_BLOCKED"]),
                **base_kwargs,
                details={"shariah": shariah_meta, "investment_eligibility": inv_elig},
            )

        mode = (ctx.eligibility_mode or "").strip().upper()
        if mode == "USER_POLICY":
            reasons.append("USER_POLICY_ALLOWED")
            reasons.append("INVESTMENT_ELIGIBILITY_OK")
        else:
            # Preserve prior VERIFIED-only invariant for LEGACY / SHARIAH_STRICT
            if stored_status != "VERIFIED" and inv_elig.get("shariah_status") != "VERIFIED":
                return BuyDecision(
                    classification=BLOCKED,
                    reason_codes=["SHARIAH_NOT_VERIFIED"],
                    **base_kwargs,
                    details={"shariah": shariah_meta, "investment_eligibility": inv_elig},
                )
            if not shariah_meta.get("execution_eligible") and inv_elig.get("shariah_status") != "VERIFIED":
                return BuyDecision(
                    classification=BLOCKED,
                    reason_codes=["SHARIAH_NOT_ELIGIBLE"],
                    **base_kwargs,
                    details={"shariah": shariah_meta, "investment_eligibility": inv_elig},
                )
            reasons.append("SHARIAH_ELIGIBLE")
            reasons.append("PERSONAL_ALLOWED")
            reasons.append("INVESTMENT_ELIGIBILITY_OK")

        # Guards / account
        if ctx.emergency_stop:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["EMERGENCY_STOP_ACTIVE"],
                **base_kwargs,
            )
        if ctx.execution_enabled or ctx.trading_execution_enabled:
            # D2.4C never enables submission; if flags flipped unexpectedly, still block auto path
            # (proposal stage remains non-submitting; classification stays honest)
            reasons.append("EXECUTION_FLAGS_NOTED_NON_SUBMITTING")

        if ctx.account is None:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["ACCOUNT_DATA_UNAVAILABLE"],
                **base_kwargs,
            )
        acct = ctx.account
        if not acct.account_id or not acct.broker:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["ACCOUNT_IDENTITY_MISSING"],
                **base_kwargs,
            )
        if not acct.snapshot_fresh or not acct.connection_ok:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["ACCOUNT_SNAPSHOT_STALE"],
                **base_kwargs,
            )

        # Existing long position → no duplicate buy (cash-only add not in scope)
        held_qty = 0.0
        for p in acct.positions:
            if str(p.get("symbol") or p.get("ticker") or "").upper() == ticker:
                held_qty = float(p.get("qty") or p.get("position") or p.get("quantity") or 0.0)
                break
        if held_qty > 0:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["EXISTING_LONG_POSITION"],
                **base_kwargs,
                details={"held_qty": held_qty},
            )

        open_for_symbol = [
            o for o in acct.open_orders
            if str(o.get("symbol") or "").upper() == ticker
        ]
        if open_for_symbol:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["CONFLICTING_OPEN_ORDER"],
                **base_kwargs,
                details={"open_orders": len(open_for_symbol)},
            )

        # Capacity / exposure
        if acct.daily_orders_count >= ctx.max_daily_orders:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["DAILY_ORDER_LIMIT_REACHED"],
                **base_kwargs,
            )
        if len(acct.open_orders) >= ctx.max_open_orders:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["MAX_OPEN_ORDERS_REACHED"],
                **base_kwargs,
            )

        position_count = sum(
            1 for p in acct.positions
            if float(p.get("qty") or p.get("position") or p.get("quantity") or 0) > 0
        )
        if position_count >= ctx.max_positions:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["MAX_POSITIONS_REACHED"],
                **base_kwargs,
            )

        if acct.cash is None or acct.equity is None or acct.cash < 0 or acct.equity <= 0:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INVALID_ACCOUNT_BALANCES"],
                **base_kwargs,
            )

        # Market session for proposal readiness
        session, session_detail = self.mds.get_market_session(now)
        if session == "CLOSED" and not ctx.allow_off_session_sizing:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["MARKET_CLOSED"],
                **base_kwargs,
                details={"session": session, "session_detail": session_detail},
            )
        if session in ("PRE_MARKET", "POST_MARKET") and not ctx.allow_off_session_sizing:
            # Regular-session cash equity policy only
            return BuyDecision(
                classification=WAIT,
                reason_codes=["OUTSIDE_REGULAR_SESSION"],
                **base_kwargs,
                details={"session": session, "session_detail": session_detail},
            )

        # Broker quote required — never Yahoo research prices
        quote = ctx.broker_quote
        if not quote:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["BROKER_QUOTE_UNAVAILABLE"],
                **base_kwargs,
            )

        q_source = str(quote.get("source") or "").upper()
        if q_source in DISALLOWED_EXECUTION_PROVIDERS or "YAHOO" in q_source:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["DISALLOWED_QUOTE_PROVIDER"],
                **base_kwargs,
                details={"quote_source": q_source},
            )
        if q_source not in ALLOWED_EXECUTION_PROVIDERS:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["UNTRUSTED_QUOTE_PROVIDER"],
                **base_kwargs,
                details={"quote_source": q_source},
            )
        if quote.get("is_synthetic") or quote.get("is_delayed"):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["QUOTE_NOT_EXECUTABLE"],
                **base_kwargs,
            )

        try:
            ask = float(quote["ask"])
            bid = float(quote["bid"])
        except (KeyError, TypeError, ValueError):
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INVALID_QUOTE_PRICES"],
                **base_kwargs,
            )
        if ask <= 0 or bid <= 0 or ask < bid:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INVALID_QUOTE_PRICES"],
                **base_kwargs,
            )

        # Equal-slot sizing preview (cash-only, long-only)
        slot_budget = min(
            float(acct.cash),
            float(acct.equity) / max(int(ctx.max_positions), 1),
            float(ctx.max_order_notional_usd),
        )
        remaining_daily = float(ctx.max_daily_notional_usd) - float(acct.daily_notional_sum)
        if remaining_daily <= 0:
            return BuyDecision(
                classification=WAIT,
                reason_codes=["DAILY_NOTIONAL_LIMIT_REACHED"],
                **base_kwargs,
            )
        slot_budget = min(slot_budget, remaining_daily)

        # Exposure cap
        invested = max(0.0, float(acct.equity) - float(acct.cash))
        exposure_pct = (invested / float(acct.equity)) * 100.0 if acct.equity else 100.0
        if exposure_pct >= float(ctx.max_portfolio_exposure_pct):
            return BuyDecision(
                classification=WAIT,
                reason_codes=["PORTFOLIO_EXPOSURE_LIMIT"],
                **base_kwargs,
                details={"exposure_pct": round(exposure_pct, 2)},
            )

        if slot_budget < ask:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INSUFFICIENT_CASH_FOR_ONE_SHARE"],
                **base_kwargs,
                details={"slot_budget": round(slot_budget, 2), "ask": ask},
            )

        qty = int(slot_budget // ask)
        if qty < 1:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["QUANTITY_ZERO"],
                **base_kwargs,
            )

        limit_price = round(ask, 2)
        notional = round(qty * limit_price, 2)
        if notional > ctx.max_order_notional_usd + 1e-9:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["NOTIONAL_EXCEEDS_MAX_ORDER"],
                **base_kwargs,
            )
        if notional > acct.cash + 1e-9:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["INSUFFICIENT_CASH"],
                **base_kwargs,
            )

        # Collar / spread check via market data service (limit at ask should pass).
        # Off-session dry-run sizing: skip REGULAR-session gate and use wider
        # IEX post-market collar/spread tolerances for SIMULATED sizing only.
        # Executable / actionable path keeps strict defaults.
        off = bool(ctx.allow_off_session_sizing)
        q_kwargs = {
            "quote_payload": quote,
            "limit_price": limit_price,
            "action": "BUY",
            "now_utc": now,
            "require_regular_session": not off,
        }
        if off:
            # Post-market IEX quotes often carry last-session timestamps and wider
            # books; dry-run sizing may use last-session quotes without authorizing
            # live submission (actionable remains False / emergency stop intact).
            q_kwargs["max_price_collar_pct"] = 50.0
            q_kwargs["max_spread_pct"] = 25.0
            q_kwargs["max_quote_age"] = 60 * 60 * 24  # 24h last-session allowance
        q_res = self.mds.validate_quote(**q_kwargs)
        if not q_res.is_valid:
            return BuyDecision(
                classification=BLOCKED,
                reason_codes=["QUOTE_VALIDATION_FAILED"],
                **base_kwargs,
                details={"quote_failures": q_res.failure_reasons},
            )
        reasons.append("QUOTE_VALIDATED")
        if off:
            reasons.append("OFF_SESSION_DRY_RUN_SIZING")
        reasons.append("SIZING_OK")
        reasons.append("V40_BUY_CONFIRMED")

        return BuyDecision(
            classification=BUY_READY,
            reason_codes=reasons,
            **base_kwargs,
            details={
                "proposed_quantity": qty,
                "proposed_limit_price": limit_price,
                "proposed_notional": notional,
                "slot_budget": round(slot_budget, 2),
                "entry_rule": entry_rule,
                "quote_source": q_source,
                "shariah": shariah_meta,
                "limit_price_policy": "BUY_AT_ASK",
                "off_session_dry_run_sizing": off,
                "actionable": False if off else None,
            },
        )


buy_decision_engine = BuyDecisionEngine()
