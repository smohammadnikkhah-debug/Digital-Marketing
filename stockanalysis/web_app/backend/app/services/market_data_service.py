"""Trusted Market Data and Price Validation Service (Stage D2.2).

Enforces strict quote validation for order execution decisions:
1. Rejects delayed, stale, missing, synthetic, or cost-basis-derived prices.
2. Identifies provider and licensing suitability (Yahoo Finance is identified as delayed/research-only).
3. Enforces executable Bid/Ask qualification and configurable maximum quote age.
4. Validates price collar against current executable midpoint.
5. Employs New York exchange calendar for market session qualification.
"""
import os
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field

from app.cli import (
    is_us_market_holiday,
    is_us_market_early_close,
)

logger = logging.getLogger("market_data_service")
NY_TZ = ZoneInfo("America/New_York")

# Providers certified for execution decisions
ALLOWED_EXECUTION_PROVIDERS = {
    "IBKR_STREAMING_L1",
    "IBKR_TICK_BY_TICK",
    "SIMULATED_REALTIME",
    "ALPACA_IEX",
}

# Providers explicitly prohibited from driving execution decisions
DISALLOWED_EXECUTION_PROVIDERS = {
    "YAHOO_FINANCE",
    "YFINANCE_DELAYED",
    "HISTORICAL_CLOSE",
    "COST_BASIS",
    "SYNTHETIC",
}

DEFAULT_MAX_QUOTE_AGE_SECONDS = 30.0
DEFAULT_PRICE_COLLAR_PCT = 5.0
DEFAULT_MAX_SPREAD_PCT = 0.5


class MarketQuote(BaseModel):
    source: str = Field(..., description="Market data provider identifier")
    symbol: str = Field(..., description="US equity ticker symbol")
    con_id: Optional[int] = Field(default=None, description="IBKR contract ID if qualified")
    bid: float = Field(..., description="Current executable bid price")
    ask: float = Field(..., description="Current executable ask price")
    last: Optional[float] = Field(default=None, description="Last traded price")
    quote_timestamp: str = Field(..., description="Exchange quote emission timestamp (ISO 8601 UTC)")
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    market_session: Optional[str] = Field(default=None, description="REGULAR, PRE_MARKET, POST_MARKET, or CLOSED")
    is_delayed: bool = Field(default=False, description="True if quote has exchange latency delay (e.g. 15min)")
    is_synthetic: bool = Field(default=False, description="True if price is calculated, interpolated or cost-basis")


class QuoteValidationResult(BaseModel):
    is_valid: bool
    quote: Optional[Dict[str, Any]] = None
    failure_reasons: List[str] = Field(default_factory=list)
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    midpoint: Optional[float] = None
    collar_pct: Optional[float] = None
    quote_age_seconds: Optional[float] = None
    market_session: Optional[str] = None


class MarketDataService:
    """Validates trusted market quotes against executable contracts and price collars."""

    def __init__(self, max_quote_age_seconds: float = DEFAULT_MAX_QUOTE_AGE_SECONDS):
        self.max_quote_age_seconds = max_quote_age_seconds

    @staticmethod
    def get_market_session(dt_utc: Optional[datetime] = None) -> Tuple[str, str]:
        """Determines the New York market session for the given UTC timestamp."""
        if dt_utc is None:
            dt_utc = datetime.now(timezone.utc)
        elif dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)

        dt_ny = dt_utc.astimezone(NY_TZ)
        ny_date = dt_ny.date()

        # Check weekend or holiday
        is_holiday, hol_name = is_us_market_holiday(ny_date)
        if is_holiday:
            return "CLOSED", f"Market Closed: {hol_name}"

        # Check early close
        is_early, early_name = is_us_market_early_close(ny_date)
        close_hour = 13 if is_early else 16
        close_minute = 0

        minute_of_day = dt_ny.hour * 60 + dt_ny.minute
        open_minute = 9 * 60 + 30          # 09:30 ET
        close_minute_total = close_hour * 60 + close_minute  # 16:00 or 13:00 ET
        pre_market_start = 4 * 60          # 04:00 ET
        post_market_end = (close_hour + 4) * 60  # 20:00 or 17:00 ET

        if open_minute <= minute_of_day < close_minute_total:
            detail = f"Regular Trading Session (Early Close at {close_hour}:00 ET)" if is_early else "Regular Trading Session"
            return "REGULAR", detail
        elif pre_market_start <= minute_of_day < open_minute:
            return "PRE_MARKET", "Pre-Market Extended Trading"
        elif close_minute_total <= minute_of_day < post_market_end:
            return "POST_MARKET", "Post-Market Extended Trading"
        else:
            return "CLOSED", "Market Closed (Outside Trading Hours)"

    def validate_quote(
        self,
        quote_payload: Dict[str, Any],
        limit_price: float,
        action: str = "BUY",
        max_quote_age: Optional[float] = None,
        max_price_collar_pct: float = DEFAULT_PRICE_COLLAR_PCT,
        max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
        now_utc: Optional[datetime] = None,
    ) -> QuoteValidationResult:
        """Validates market data payload against the quote-validation contract."""
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        max_age = max_quote_age if max_quote_age is not None else self.max_quote_age_seconds
        failures: List[str] = []

        # 1. Parse into model
        try:
            quote = MarketQuote(**quote_payload)
        except Exception as exc:
            return QuoteValidationResult(
                is_valid=False,
                quote=quote_payload,
                failure_reasons=[f"Malformed market quote payload: {exc}"],
            )

        source_upper = quote.source.strip().upper()

        # 2. Provider Source & Licensing Qualification
        if source_upper in DISALLOWED_EXECUTION_PROVIDERS:
            failures.append(
                f"Market data provider '{quote.source}' is unlicensed/delayed for execution decisions. "
                "Only real-time streaming quotes are permitted."
            )
        elif source_upper not in ALLOWED_EXECUTION_PROVIDERS:
            failures.append(
                f"Unrecognized market data provider '{quote.source}'. Allowed providers: {sorted(ALLOWED_EXECUTION_PROVIDERS)}"
            )

        # 3. Explicit delayed and synthetic checks
        if quote.is_delayed:
            failures.append("Exchange-delayed quote rejected. Execution requires real-time quotes.")
        if quote.is_synthetic:
            failures.append("Synthetic or cost-basis-derived price rejected. Direct market quotes required.")

        # 4. Bid / Ask numeric integrity
        if quote.bid <= 0:
            failures.append(f"Invalid bid price (${quote.bid:.2f} <= 0).")
        if quote.ask <= 0:
            failures.append(f"Invalid ask price (${quote.ask:.2f} <= 0).")
        if quote.bid > quote.ask:
            failures.append(f"Crossed market quote: Bid (${quote.bid:.2f}) > Ask (${quote.ask:.2f}).")
        if quote.last is not None and quote.last <= 0:
            failures.append(f"Invalid last price (${quote.last:.2f} <= 0).")

        # 5. Quote Age & Freshness
        quote_age_sec = None
        try:
            q_time_clean = quote.quote_timestamp.strip().replace(" ", "T")
            if not (q_time_clean.endswith("Z") or "+" in q_time_clean or "-" in q_time_clean[10:]):
                q_time_clean += "Z"
            q_dt = datetime.fromisoformat(q_time_clean.replace("Z", "+00:00"))
            quote_age_sec = max(0.0, (now_utc - q_dt).total_seconds())

            if quote_age_sec > max_age:
                failures.append(
                    f"Stale quote: Market quote is stale: age {quote_age_sec:.1f}s exceeds maximum allowed threshold of {max_age:.1f}s."
                )
        except Exception as exc:
            failures.append(f"Unparseable quote timestamp '{quote.quote_timestamp}': {exc}")

        # 6. Market Session Check
        session, session_detail = self.get_market_session(now_utc)
        if session != "REGULAR":
            failures.append(
                f"Order execution blocked: US equity markets are currently in '{session}' state ({session_detail})."
            )

        # 7. Price Collar Validation
        midpoint = None
        collar_pct = None
        if quote.bid > 0 and quote.ask >= quote.bid:
            midpoint = (quote.bid + quote.ask) / 2.0
            if midpoint > 0:
                collar_pct = abs(limit_price - midpoint) / midpoint * 100.0
                if collar_pct > max_price_collar_pct:
                    failures.append(
                        f"Price collar violation: limit price ${limit_price:.2f} deviates {collar_pct:.2f}% "
                        f"from executable quote midpoint ${midpoint:.2f} (max permitted: &plusmn;{max_price_collar_pct:.1f}%)."
                    )

                # 8. Spread Width Gate (Critical for single-venue IEX books)
                spread = quote.ask - quote.bid
                spread_pct = (spread / midpoint) * 100.0
                if source_upper == "ALPACA_IEX" and spread_pct > max_spread_pct:
                    failures.append(
                        f"Wide spread rejection: IEX quote spread is ${spread:.2f} ({spread_pct:.2f}% of midpoint), "
                        f"exceeding maximum permitted single-venue spread threshold of {max_spread_pct:.2f}%."
                    )

        is_valid = len(failures) == 0
        return QuoteValidationResult(
            is_valid=is_valid,
            quote=quote.model_dump(),
            failure_reasons=failures,
            midpoint=midpoint,
            collar_pct=collar_pct,
            quote_age_seconds=quote_age_sec,
            market_session=session,
        )

    @staticmethod
    def get_data_provider_diagnostics() -> Dict[str, Any]:
        """Returns the market data provider status, licensing suitability and execution readiness."""
        return {
            "v40_scanner_provider": "Yahoo Finance (yfinance)",
            "v40_scanner_type": "Auto-Adjusted End-of-Day OHLCV Bars (15-20 min delayed)",
            "is_licensed_for_execution": False,
            "execution_readiness": "BLOCKED",
            "alpaca_iex_provider": {
                "source": "ALPACA_IEX",
                "feed": "iex",
                "venue_type": "NON_CONSOLIDATED_SINGLE_VENUE",
                "is_consolidated_nbbo": False,
                "readiness": "CONNECTED_READ_ONLY",
                "suitability": "Top-of-book paper trading market data. Subject to strict 30s freshness and positive two-sided bid/ask.",
            },
            "reason": (
                "V4.0 research engine uses delayed Yahoo Finance data, which is unlicensed and unsuitable for execution. "
                "Alpaca paper adapter provides real-time single-venue IEX Level 1 quotes (non-consolidated, not NBBO). "
                "Order execution remains disabled by Stage D2.3A.2 non-executing build guard."
            ),
            "allowed_execution_providers": sorted(ALLOWED_EXECUTION_PROVIDERS),
            "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
            "price_collar_pct": DEFAULT_PRICE_COLLAR_PCT,
        }


market_data_service = MarketDataService()
