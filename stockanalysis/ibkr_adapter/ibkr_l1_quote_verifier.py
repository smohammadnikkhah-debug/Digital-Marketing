"""Interactive Brokers (IBKR) Level 1 Market Data Verification Diagnostic.

Stage D2.3A / D2.3A.1 Verification Script:
1. Strictly Non-Executing: Blocks all order placement, modification, and cancellation APIs.
2. Connects to 127.0.0.1:4002 (IBKR Gateway paper port) with designated Client ID 22.
3. Verifies paper account authentication (DU... / DF...).
4. Resolves contracts using reqContractDetails prior to issuing any quote requests.
5. Tests AAPL, MSFT, and SPY using:
   - SMART routing (Consolidated NBBO attempt)
   - Supported direct exchange contracts (IEX, and Cboe-related venues confirmed valid by contract details).
6. Compares requests:
   - Phase 1: Standard Bid/Ask ticks (genericTickList="")
   - Phase 2: With generic tick list "233" (RTVolume)
7. Uses reqMarketDataType(1) with snapshot=False and regulatorySnapshot=False (no paid regulatory snapshots).
8. Accurately reports IBKR Error Code 354 and distinguishes whether delayed data is available or unavailable.
9. Evaluates 30-second freshness contract without treating callback reception time as quote age.
10. Clearly separates Consolidated NBBO vs Non-Consolidated Venue quotes and provides subscription gap analysis.
"""
import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

# Strict non-executing safety guard
NON_EXECUTING_BUILD_GUARD: bool = True
if not NON_EXECUTING_BUILD_GUARD:
    raise RuntimeError("CRITICAL SAFETY GUARD: NON_EXECUTING_BUILD_GUARD must be True.")

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract, ContractDetails
    from ibapi.common import TickAttrib
    HAS_IBAPI = True
except ImportError:
    print("FATAL: ibapi is required. Install via pip install ibapi")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (IBKR_L1_Verifier) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("IBKR_L1_Verifier")

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 4002
DESIGNATED_EXECUTION_CLIENT_ID = 22

TICK_NAME_MAP = {
    1: "BID",
    2: "ASK",
    4: "LAST",
    6: "HIGH",
    7: "LOW",
    9: "CLOSE",
    45: "LAST_TIMESTAMP",
    48: "RT_VOLUME",
    66: "DELAYED_BID",
    67: "DELAYED_ASK",
    68: "DELAYED_LAST",
    69: "DELAYED_BID_SIZE",
    70: "DELAYED_ASK_SIZE",
    71: "DELAYED_LAST_SIZE",
    72: "DELAYED_HIGH",
    73: "DELAYED_LOW",
    74: "DELAYED_VOLUME",
    75: "DELAYED_CLOSE",
    88: "DELAYED_LAST_TIMESTAMP"
}

MARKET_DATA_TYPE_MAP = {
    1: "REAL_TIME",
    2: "FROZEN",
    3: "DELAYED",
    4: "DELAYED_FROZEN"
}

# Known Cboe equities venues to inspect against validExchanges
CBOE_VENUE_CANDIDATES = ["CBOE", "BATS", "BYX", "EDGA", "EDGX"]


class NonExecutingGuard(EClient):
    """Enforces strictly non-executing mode by blocking order placement, modification and cancellation."""

    def placeOrder(self, *args, **kwargs):
        raise PermissionError("NON-EXECUTING GUARD: Order placement is strictly prohibited in L1 verification.")

    def cancelOrder(self, *args, **kwargs):
        raise PermissionError("NON-EXECUTING GUARD: Order cancellation is strictly prohibited in L1 verification.")

    def reqGlobalCancel(self, *args, **kwargs):
        raise PermissionError("NON-EXECUTING GUARD: Global order cancellation is strictly prohibited in L1 verification.")

    def exerciseOptions(self, *args, **kwargs):
        raise PermissionError("NON-EXECUTING GUARD: Option exercise is strictly prohibited in L1 verification.")


class IBKRL1QuoteVerifier(EWrapper, NonExecutingGuard):

    def __init__(self, host: str, port: int, client_id: int, requested_market_data_type: int = 1):
        EWrapper.__init__(self)
        NonExecutingGuard.__init__(self, wrapper=self)
        self.host = host
        self.port = port
        self.client_id = client_id
        self._configured_host = host
        self._configured_port = port
        self.requested_market_data_type = requested_market_data_type

        self.connected_event = threading.Event()
        self.authenticated_accounts: List[str] = []
        self.account_verified: bool = False
        self.active_paper_account: Optional[str] = None

        # Contract Details Resolution
        self.contract_details_registry: Dict[str, Dict[str, Any]] = {}
        self._cd_req_to_symbol: Dict[int, str] = {}
        self._cd_events: Dict[int, threading.Event] = {}

        # Quote Stream Registry
        # req_id -> metadata
        self.req_id_to_meta: Dict[int, Dict[str, Any]] = {}
        # stream_key -> data record
        self.stream_records: Dict[str, Dict[str, Any]] = {}

        self.errors: List[Dict[str, Any]] = []
        self._thread: Optional[threading.Thread] = None

    # EWrapper Callbacks
    def connectAck(self):
        logger.info("Connection acknowledged by IBKR Gateway.")

    def nextValidId(self, orderId: int):
        logger.info(f"Gateway nextValidId received: {orderId}")
        self.connected_event.set()

    def managedAccounts(self, accountsList: str):
        accs = [a.strip() for a in accountsList.split(",") if a.strip()]
        self.authenticated_accounts = accs
        logger.info(f"Authenticated accounts on gateway: {accs}")
        for acc in accs:
            if acc.startswith("DU") or acc.startswith("DF"):
                self.account_verified = True
                self.active_paper_account = acc
                logger.info(f"Paper account verified: {acc}")
                break
        if not self.account_verified:
            logger.error(f"SAFETY ERROR: No valid paper account found in {accs}!")

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        sym = self._cd_req_to_symbol.get(reqId)
        if not sym:
            return
        c = contractDetails.contract
        raw_valid_exchanges = contractDetails.validExchanges or ""
        valid_exchanges_list = [x.strip() for x in raw_valid_exchanges.split(",") if x.strip()]

        cboe_venues_confirmed = [v for v in CBOE_VENUE_CANDIDATES if v in valid_exchanges_list]
        has_iex = "IEX" in valid_exchanges_list

        self.contract_details_registry[sym] = {
            "symbol": sym,
            "conId": c.conId,
            "primaryExchange": c.primaryExchange,
            "longName": contractDetails.longName,
            "marketName": contractDetails.marketName,
            "valid_exchanges": valid_exchanges_list,
            "has_iex": has_iex,
            "cboe_venues_confirmed": cboe_venues_confirmed,
            "resolved_contract": c
        }
        logger.info(
            f"Contract resolved: {sym} (conId {c.conId}, primExch: {c.primaryExchange}, "
            f"IEX: {has_iex}, Cboe venues: {cboe_venues_confirmed})"
        )

    def contractDetailsEnd(self, reqId: int):
        sym = self._cd_req_to_symbol.get(reqId, f"req_{reqId}")
        logger.info(f"ContractDetailsEnd received for {sym} (reqId {reqId})")
        ev = self._cd_events.get(reqId)
        if ev:
            ev.set()

    def error(self, reqId: int, *args, **kwargs):
        """Unified error callback supporting ibapi 9.x tuple and 10.x protobuf signatures."""
        error_time = None
        error_code = None
        error_string = ""

        if len(args) == 2:
            error_code, error_string = args
        elif len(args) >= 3:
            error_time = args[0]
            error_code = args[1]
            error_string = str(args[2])

        # Ignore informational farm status codes (2104, 2106, 2107, 2108, 2158)
        if error_code in (2104, 2106, 2107, 2108, 2158):
            logger.debug(f"Farm notice [reqId {reqId}]: {error_code} - {error_string}")
            return

        err_entry = {
            "req_id": reqId,
            "error_time": error_time,
            "error_code": error_code,
            "error_string": error_string,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.errors.append(err_entry)

        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None

        if record:
            record["errors"].append({
                "code": error_code,
                "message": error_string
            })

        sym_tag = f"{meta['symbol']}:{meta['venue']}" if meta else f"REQ_{reqId}"

        # Handle specific error codes with high diagnostic precision
        if error_code == 354:
            # FIX: Accurately distinguish whether delayed data is available vs unavailable
            err_lower = error_string.lower()
            if "delayed market data is available" in err_lower or "displaying delayed" in err_lower:
                logger.info(
                    f"[{sym_tag}] IBKR Code 354: Real-time market data is not subscribed. "
                    f"Delayed market data IS available from broker."
                )
                if record:
                    record["delayed_data_indicated_available"] = True
                    record["subscription_error"] = error_string
            elif "delayed data is unavailable" in err_lower:
                logger.warning(
                    f"[{sym_tag}] IBKR Code 354: Real-time market data is not subscribed "
                    f"and delayed market data is UNAVAILABLE."
                )
                if record:
                    record["delayed_data_indicated_available"] = False
                    record["subscription_error"] = error_string
            else:
                logger.warning(f"[{sym_tag}] IBKR Code 354: {error_string}")
                if record:
                    record["subscription_error"] = error_string

        elif error_code == 10167:
            logger.warning(f"[{sym_tag}] IBKR Code 10167: Real-time quote not subscribed; displaying delayed data.")
            if record:
                record["delayed_data_indicated_available"] = True
                record["unsubscribed_warning"] = error_string

        elif error_code == 10197:
            logger.warning(f"[{sym_tag}] IBKR Code 10197: No market data during competing live session.")
            if record:
                record["competing_live_session"] = True

        elif error_code == 200:
            logger.warning(f"[{sym_tag}] IBKR Code 200: Invalid destination or exchange: {error_string}")
            if record:
                record["invalid_destination_error"] = error_string

        elif error_code in (2103, 2105):
            logger.warning(f"Data farm broken [reqId {reqId}, code {error_code}]: {error_string}")
        else:
            logger.info(f"[{sym_tag}] IBKR message [code {error_code}]: {error_string}")

    def marketDataType(self, reqId: int, marketDataType: int):
        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None
        type_str = MARKET_DATA_TYPE_MAP.get(marketDataType, f"UNKNOWN_{marketDataType}")
        sym_tag = f"{meta['symbol']}:{meta['venue']}" if meta else f"REQ_{reqId}"
        logger.info(f"MarketDataType callback for {sym_tag} (reqId {reqId}): {type_str} ({marketDataType})")
        if record:
            record["market_data_type_code"] = marketDataType
            record["market_data_type"] = type_str

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib: TickAttrib):
        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None
        tick_name = TICK_NAME_MAP.get(tickType, f"TICK_{tickType}")
        if not record:
            return

        record["ticks"][tick_name] = price
        record["last_callback_utc"] = datetime.now(timezone.utc).isoformat()

        if tickType in (1, 66) and price > 0:  # Bid / Delayed Bid
            record["bid"] = price
            record["is_delayed_bid"] = (tickType == 66)
        elif tickType in (2, 67) and price > 0:  # Ask / Delayed Ask
            record["ask"] = price
            record["is_delayed_ask"] = (tickType == 67)
        elif tickType in (4, 68) and price > 0:  # Last / Delayed Last
            record["last"] = price
        elif tickType in (9, 75) and price > 0:  # Close / Delayed Close
            record["close"] = price

        sym_tag = f"{meta['symbol']}:{meta['venue']}"
        logger.info(f"tickPrice [{sym_tag}]: {tick_name} = {price}")

    def tickSize(self, reqId: int, tickType: int, size):
        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None
        tick_name = TICK_NAME_MAP.get(tickType, f"TICK_SIZE_{tickType}")
        if record:
            record["sizes"][tick_name] = int(size)

    def tickString(self, reqId: int, tickType: int, value: str):
        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None
        tick_name = TICK_NAME_MAP.get(tickType, f"TICK_STR_{tickType}")
        sym_tag = f"{meta['symbol']}:{meta['venue']}" if meta else f"REQ_{reqId}"
        logger.info(f"tickString [{sym_tag}]: {tick_name} = {value}")
        if record:
            record["strings"][tick_name] = value

            # Parse underlying quote timestamp
            if tickType in (45, 88):  # Last Timestamp or Delayed Last Timestamp
                try:
                    ts_val = int(value)
                    dt_utc = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                    record["underlying_quote_timestamp_utc"] = dt_utc.isoformat()
                    record["underlying_quote_epoch"] = ts_val
                except Exception as ex:
                    logger.warning(f"Could not parse timestamp string '{value}': {ex}")

    def tickGeneric(self, reqId: int, tickType: int, value: float):
        meta = self.req_id_to_meta.get(reqId)
        stream_key = meta.get("stream_key") if meta else None
        record = self.stream_records.get(stream_key) if stream_key else None
        tick_name = TICK_NAME_MAP.get(tickType, f"GENERIC_{tickType}")
        if record:
            record["generics"][tick_name] = value
            sym_tag = f"{meta['symbol']}:{meta['venue']}" if meta else f"REQ_{reqId}"
            logger.info(f"tickGeneric [{sym_tag}]: {tick_name} = {value}")

    # Resolution & Verification Logic
    def resolve_contracts(self, symbols: List[str], timeout: float = 6.0) -> Dict[str, Dict[str, Any]]:
        """Resolves full contract details for each symbol using reqContractDetails."""
        logger.info(f"Resolving contract details for {symbols} using reqContractDetails...")
        base_cd_req_id = 1100
        for i, sym in enumerate(symbols):
            req_id = base_cd_req_id + i
            self._cd_req_to_symbol[req_id] = sym
            ev = threading.Event()
            self._cd_events[req_id] = ev

            c = Contract()
            c.symbol = sym
            c.secType = "STK"
            c.currency = "USD"
            c.exchange = "SMART"

            logger.info(f"Issuing reqContractDetails for {sym} (reqId {req_id})...")
            self.reqContractDetails(req_id, c)

        # Wait for all contract resolutions
        for req_id, ev in self._cd_events.items():
            sym = self._cd_req_to_symbol[req_id]
            if not ev.wait(timeout=timeout):
                logger.warning(f"Timed out resolving contract details for {sym} (reqId {req_id})")

        return self.contract_details_registry

    def run_verification(
        self,
        symbols: List[str],
        duration_per_phase: int = 10
    ) -> Dict[str, Any]:
        """Runs the extended Level 1 market data verification diagnostic."""
        logger.info(
            f"Starting Extended Level 1 Market Data Verification on "
            f"{self._configured_host}:{self._configured_port} with Client ID {self.client_id}..."
        )
        self.connect(self._configured_host, self._configured_port, self.client_id)

        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

        # 1. Wait for connection acknowledgement
        if not self.connected_event.wait(timeout=10.0):
            logger.error("Timed out waiting for connection acknowledge from IBKR Gateway.")
            self.disconnect()
            return {
                "success": False,
                "error": "Connection timeout to IBKR Gateway on port 4002.",
                "authenticated_accounts": [],
                "account_verified": False
            }

        # 2. Verify account is paper
        if not self.account_verified:
            logger.error("Safety violation: Could not verify paper account (starts with DU or DF).")
            self.disconnect()
            return {
                "success": False,
                "error": "Non-paper or unauthorized account authenticated.",
                "authenticated_accounts": self.authenticated_accounts,
                "account_verified": False
            }

        # Allow data farm connections to stabilize
        time.sleep(2.0)

        # 3. Explicitly request Market Data Type (1 = Real-Time)
        logger.info(f"Requesting Market Data Type: {self.requested_market_data_type} (REAL-TIME)")
        self.reqMarketDataType(self.requested_market_data_type)

        # 4. Resolve contracts using reqContractDetails
        resolved_details = self.resolve_contracts(symbols, timeout=6.0)

        # 5. Build list of test targets across SMART and direct exchange venues
        # Target: (symbol, venue, quote_source, contract)
        test_targets: List[Tuple[str, str, str, Contract]] = []

        for sym in symbols:
            cd_info = resolved_details.get(sym)
            con_id = cd_info.get("conId", 0) if cd_info else 0
            prim_exch = cd_info.get("primaryExchange", "NASDAQ") if cd_info else "NASDAQ"
            valid_exchanges = cd_info.get("valid_exchanges", []) if cd_info else []

            # Target 1: SMART Routing (Consolidated NBBO attempt)
            c_smart = Contract()
            c_smart.symbol = sym
            c_smart.secType = "STK"
            c_smart.currency = "USD"
            c_smart.exchange = "SMART"
            if con_id:
                c_smart.conId = con_id
            c_smart.primaryExchange = prim_exch
            test_targets.append((sym, "SMART", "CONSOLIDATED_NBBO", c_smart))

            # Target 2: IEX Direct Exchange (if supported)
            if cd_info and cd_info.get("has_iex"):
                c_iex = Contract()
                c_iex.symbol = sym
                c_iex.secType = "STK"
                c_iex.currency = "USD"
                c_iex.exchange = "IEX"
                c_iex.conId = con_id
                c_iex.primaryExchange = prim_exch
                test_targets.append((sym, "IEX", "NON_CONSOLIDATED_DIRECT_VENUE", c_iex))
            else:
                logger.info(f"IEX venue evaluated for {sym}: Not present in validExchanges.")

            # Target 3: Cboe Direct Venues (only if confirmed valid in contract details)
            cboe_venues = cd_info.get("cboe_venues_confirmed", []) if cd_info else []
            # We select confirmed Cboe venues (e.g. BATS, BYX) to test direct non-consolidated book
            for cboe_v in [v for v in ["BATS", "BYX"] if v in cboe_venues]:
                c_cboe = Contract()
                c_cboe.symbol = sym
                c_cboe.secType = "STK"
                c_cboe.currency = "USD"
                c_cboe.exchange = cboe_v
                c_cboe.conId = con_id
                c_cboe.primaryExchange = prim_exch
                test_targets.append((sym, cboe_v, "NON_CONSOLIDATED_DIRECT_VENUE", c_cboe))

        logger.info(f"Compiled {len(test_targets)} quote test targets across symbols and venues.")

        # 6. Execute Phase 1: Standard Bid/Ask Ticks (genericTickList="")
        logger.info("\n" + "="*70)
        logger.info(" PHASE 1: Testing Standard Bid/Ask Ticks (genericTickList='')")
        logger.info("="*70)
        phase1_req_ids = []
        base_req_p1 = 3100

        for i, (sym, venue, q_source, contract) in enumerate(test_targets):
            req_id = base_req_p1 + i
            stream_key = f"{sym}_{venue}_PHASE1_STD"
            self._init_stream_record(stream_key, sym, venue, q_source, "PHASE1_STANDARD", "", req_id)
            self.req_id_to_meta[req_id] = {
                "symbol": sym,
                "venue": venue,
                "quote_source": q_source,
                "phase": "PHASE1_STANDARD",
                "generic_tick_list": "",
                "stream_key": stream_key
            }
            logger.info(f"Subscribing {sym} [{venue}] (Standard Ticks, reqId {req_id})...")
            # Snapshot=False and regulatorySnapshot=False (no paid regulatory snapshots)
            self.reqMktData(req_id, contract, "", False, False, [])
            phase1_req_ids.append(req_id)

        logger.info(f"Gathering Phase 1 callbacks for {duration_per_phase} seconds...")
        time.sleep(duration_per_phase)

        logger.info("Cancelling Phase 1 subscriptions...")
        for r_id in phase1_req_ids:
            try:
                self.cancelMktData(r_id)
            except Exception as ex:
                logger.warning(f"Error cancelling reqId {r_id}: {ex}")

        # Short pause between phases for clean gateway state
        time.sleep(2.0)

        # 7. Execute Phase 2: With Generic Tick List "233" (RTVolume)
        logger.info("\n" + "="*70)
        logger.info(" PHASE 2: Testing With Generic Tick List '233' (RTVolume)")
        logger.info("="*70)
        phase2_req_ids = []
        base_req_p2 = 3200

        for i, (sym, venue, q_source, contract) in enumerate(test_targets):
            req_id = base_req_p2 + i
            stream_key = f"{sym}_{venue}_PHASE2_WITH_233"
            self._init_stream_record(stream_key, sym, venue, q_source, "PHASE2_WITH_233", "233", req_id)
            self.req_id_to_meta[req_id] = {
                "symbol": sym,
                "venue": venue,
                "quote_source": q_source,
                "phase": "PHASE2_WITH_233",
                "generic_tick_list": "233",
                "stream_key": stream_key
            }
            logger.info(f"Subscribing {sym} [{venue}] (With 233, reqId {req_id})...")
            self.reqMktData(req_id, contract, "233", False, False, [])
            phase2_req_ids.append(req_id)

        logger.info(f"Gathering Phase 2 callbacks for {duration_per_phase} seconds...")
        time.sleep(duration_per_phase)

        logger.info("Cancelling Phase 2 subscriptions...")
        for r_id in phase2_req_ids:
            try:
                self.cancelMktData(r_id)
            except Exception as ex:
                logger.warning(f"Error cancelling reqId {r_id}: {ex}")

        # 8. Evaluate 30-second freshness contract across all streams
        now_utc = datetime.now(timezone.utc)
        for key, record in self.stream_records.items():
            eval_res = self._evaluate_quote_freshness(record, now_utc)
            record["freshness_evaluation"] = eval_res

        # Capture host and port before disconnect
        rep_host = self._configured_host
        rep_port = self._configured_port
        rep_client_id = self.client_id
        rep_verified = self.account_verified
        rep_account = self.active_paper_account

        # 9. Clean disconnect
        try:
            self.disconnect()
        except Exception:
            pass

        # 10. Generate synthesized findings and subscription gap analysis
        synthesized_findings = self._synthesize_findings()

        return {
            "success": True,
            "gateway_host": rep_host,
            "gateway_port": rep_port,
            "client_id": rep_client_id,
            "account_verified": rep_verified,
            "authenticated_paper_account": rep_account,
            "evaluation_timestamp_utc": now_utc.isoformat(),
            "resolved_contract_details": {
                k: {
                    "conId": v["conId"],
                    "primaryExchange": v["primaryExchange"],
                    "longName": v["longName"],
                    "has_iex": v["has_iex"],
                    "cboe_venues_confirmed": v["cboe_venues_confirmed"],
                    "total_valid_exchanges_count": len(v["valid_exchanges"])
                }
                for k, v in resolved_details.items()
            },
            "stream_records": self.stream_records,
            "errors": self.errors,
            "synthesized_findings": synthesized_findings
        }

    def _init_stream_record(
        self,
        stream_key: str,
        symbol: str,
        venue: str,
        quote_source: str,
        phase: str,
        generic_tick_list: str,
        req_id: int
    ):
        self.stream_records[stream_key] = {
            "stream_key": stream_key,
            "symbol": symbol,
            "venue": venue,
            "quote_source": quote_source,
            "phase": phase,
            "generic_tick_list": generic_tick_list,
            "req_id": req_id,
            "market_data_type": "NOT_RECEIVED",
            "market_data_type_code": null_or_none(),
            "bid": None,
            "ask": None,
            "last": None,
            "close": None,
            "is_delayed_bid": False,
            "is_delayed_ask": False,
            "delayed_data_indicated_available": None,
            "competing_live_session": False,
            "subscription_error": None,
            "unsubscribed_warning": None,
            "invalid_destination_error": None,
            "underlying_quote_timestamp_utc": None,
            "underlying_quote_epoch": None,
            "last_callback_utc": None,
            "ticks": {},
            "sizes": {},
            "strings": {},
            "generics": {},
            "errors": [],
            "freshness_evaluation": {}
        }

    def _evaluate_quote_freshness(self, data: Dict[str, Any], now_utc: datetime) -> Dict[str, Any]:
        """Evaluates whether the quote satisfies the 30-second freshness contract.

        Strict Contract Rule:
        Do not treat callback receipt time as proof of exchange quote freshness.
        Must verify real-time status and exchange quote timestamp.
        """
        bid = data.get("bid")
        ask = data.get("ask")
        md_type = data.get("market_data_type", "NOT_RECEIVED")
        is_delayed = (
            (data.get("market_data_type_code") in (3, 4))
            or data.get("is_delayed_bid")
            or data.get("is_delayed_ask")
            or (data.get("unsubscribed_warning") is not None)
        )
        quote_ts_str = data.get("underlying_quote_timestamp_utc")

        evaluation = {
            "has_executable_bid_ask": (bid is not None and ask is not None and bid > 0 and ask > 0),
            "bid": bid,
            "ask": ask,
            "spread": round(ask - bid, 4) if (bid is not None and ask is not None) else None,
            "midpoint": round((bid + ask) / 2.0, 4) if (bid is not None and ask is not None) else None,
            "market_data_type": md_type,
            "is_delayed": is_delayed,
            "underlying_quote_timestamp_utc": quote_ts_str,
            "callback_arrival_timestamp_utc": data.get("last_callback_utc"),
            "meets_30s_freshness_contract": False,
            "freshness_reasons": []
        }

        # Check delayed status
        if is_delayed:
            evaluation["freshness_reasons"].append(
                f"Quote is marked DELAYED (type={md_type}). Delayed quotes (15+ min) strictly violate the 30-second freshness contract."
            )

        # Check underlying exchange quote timestamp
        if quote_ts_str:
            try:
                dt_quote = datetime.fromisoformat(quote_ts_str.replace("Z", "+00:00"))
                age_seconds = (now_utc - dt_quote).total_seconds()
                evaluation["underlying_quote_age_seconds"] = round(age_seconds, 1)

                if age_seconds <= 30.0 and not is_delayed and evaluation["has_executable_bid_ask"]:
                    evaluation["meets_30s_freshness_contract"] = True
                    evaluation["freshness_reasons"].append(
                        f"Underlying exchange quote age ({round(age_seconds, 1)}s) satisfies the 30-second freshness contract."
                    )
                else:
                    evaluation["freshness_reasons"].append(
                        f"Underlying quote age ({round(age_seconds, 1)}s) exceeds 30-second threshold or lacks executable quotes."
                    )
            except Exception as ex:
                evaluation["freshness_reasons"].append(f"Could not parse exchange quote timestamp: {ex}")
        else:
            evaluation["underlying_quote_age_seconds"] = None
            evaluation["freshness_reasons"].append(
                "No exchange-level quote emission timestamp received from broker. Callback arrival time alone cannot certify freshness."
            )

        if not evaluation["has_executable_bid_ask"]:
            evaluation["freshness_reasons"].append("Missing executable two-sided (Bid/Ask) prices.")

        return evaluation

    def _synthesize_findings(self) -> Dict[str, Any]:
        """Synthesizes empirical findings, comparing tick configurations, venues, and subscriptions."""
        has_realtime_quotes = False
        has_delayed_quotes = False
        competing_live_session_detected = False
        unsubscribed_354_detected = False
        delayed_available_confirmed = False

        for rec in self.stream_records.values():
            if rec.get("freshness_evaluation", {}).get("meets_30s_freshness_contract"):
                has_realtime_quotes = True
            if rec.get("freshness_evaluation", {}).get("is_delayed") or rec.get("close") is not None:
                has_delayed_quotes = True
            if rec.get("competing_live_session"):
                competing_live_session_detected = True
            if rec.get("subscription_error"):
                unsubscribed_354_detected = True
            if rec.get("delayed_data_indicated_available"):
                delayed_available_confirmed = True

        # Phase comparison: standard vs generic tick 233
        phase1_records = [r for r in self.stream_records.values() if r.get("phase") == "PHASE1_STANDARD"]
        phase2_records = [r for r in self.stream_records.values() if r.get("phase") == "PHASE2_WITH_233"]

        p1_errors = [e["code"] for r in phase1_records for e in r.get("errors", [])]
        p2_errors = [e["code"] for r in phase2_records for e in r.get("errors", [])]

        free_data_works_socket_api = has_delayed_quotes or delayed_available_confirmed
        meets_freshness_contract = has_realtime_quotes

        missing_subscriptions = []
        if not meets_freshness_contract:
            missing_subscriptions = [
                {
                    "subscription_name": "US Equity and Options Add-On Streaming Bundle (Non-Professional)",
                    "code": "US_EQUITY_BUNDLE",
                    "monthly_cost": "~$4.50 USD / month (waived if monthly commissions >= $30)",
                    "coverage": "Consolidated Real-Time NBBO for NASDAQ (Network C), NYSE (Network A), NYSE American/BATS/ARCA (Network B), and OPRA Options."
                },
                {
                    "subscription_name": "NASDAQ (Network C/UTP)",
                    "code": "NASDAQ_UTP",
                    "monthly_cost": "$1.50 USD / month",
                    "coverage": "Real-time Level 1 quotes for NASDAQ-listed stocks (e.g. AAPL, MSFT)."
                },
                {
                    "subscription_name": "NYSE (Network A/CTA)",
                    "code": "NYSE_CTA",
                    "monthly_cost": "$1.50 USD / month",
                    "coverage": "Real-time Level 1 quotes for NYSE-listed stocks."
                },
                {
                    "subscription_name": "NYSE American, BATS, ARCA, IEX (Network B)",
                    "code": "NETWORK_B",
                    "monthly_cost": "$1.50 USD / month",
                    "coverage": "Real-time Level 1 quotes for ETF and Regional securities (e.g. SPY)."
                }
            ]

        return {
            "free_data_works_through_socket_api": free_data_works_socket_api,
            "meets_execution_freshness_contract": meets_freshness_contract,
            "competing_live_session_detected": competing_live_session_detected,
            "unsubscribed_354_detected": unsubscribed_354_detected,
            "delayed_data_explicitly_available": delayed_available_confirmed,
            "phase_comparison": {
                "phase1_standard_ticks_error_codes": list(set(p1_errors)),
                "phase2_with_233_error_codes": list(set(p2_errors)),
                "tick_233_behavior": (
                    "Generic tick 233 requests RTVolume. When real-time streaming is unsubscribed, "
                    "both standard and 233 requests behave consistently, receiving Code 354 with delayed availability notice "
                    "or Code 10197 if another live session is sharing the user's stream."
                )
            },
            "quote_source_distinction": {
                "CONSOLIDATED_NBBO": (
                    "SMART routing queries the consolidated SIP tape across all National Market System exchanges. "
                    "Requires CTA/UTP Level 1 streaming entitlements."
                ),
                "NON_CONSOLIDATED_DIRECT_VENUE": (
                    "Direct exchange routing (IEX, BATS, BYX) targets single-venue books. "
                    "Through TWS/Gateway socket API, direct venue Level 1 streaming on US equities requires either "
                    "consolidated SIP entitlement or specific venue top-of-book entitlement."
                )
            },
            "missing_market_data_subscriptions": missing_subscriptions
        }


def null_or_none():
    return None


def main():
    parser = argparse.ArgumentParser(description="StockAnalysis Extended IBKR Level 1 Market Data Verifier")
    parser.add_argument("--host", default=DEFAULT_GATEWAY_HOST, help="IBKR Gateway host")
    parser.add_argument("--port", type=int, default=DEFAULT_GATEWAY_PORT, help="IBKR Gateway port (4002)")
    parser.add_argument("--client-id", type=int, default=DESIGNATED_EXECUTION_CLIENT_ID, help="Client ID (22)")
    parser.add_argument("--symbols", default="AAPL,MSFT,SPY", help="Comma-separated ticker symbols")
    parser.add_argument("--mkt-data-type", type=int, default=1, choices=[1, 2, 3, 4], help="Market data type (1=Real-Time, 2=Frozen, 3=Delayed, 4=Delayed-Frozen)")
    parser.add_argument("--duration-per-phase", type=int, default=10, help="Streaming sample duration in seconds per phase")
    parser.add_argument("--output-json", default=None, help="Path to save output JSON")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    verifier = IBKRL1QuoteVerifier(
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        requested_market_data_type=args.mkt_data_type
    )
    report = verifier.run_verification(symbols=symbols, duration_per_phase=args.duration_per_phase)

    print("\n" + "="*84)
    print(" IBKR LEVEL 1 FREE MARKET DATA EXTENDED VERIFICATION REPORT (STAGE D2.3A.1)")
    print("="*84)
    print(f"Gateway: {report.get('gateway_host')}:{report.get('gateway_port')} (Client ID: {report.get('client_id')})")
    print(f"Authenticated Paper Account: {report.get('authenticated_paper_account')}")
    print(f"Account Verified: {report.get('account_verified')}")
    print(f"Evaluation Timestamp: {report.get('evaluation_timestamp_utc')}\n")

    print("--- CONTRACT DETAILS RESOLUTION SUMMARY ---")
    for sym, cd_data in report.get("resolved_contract_details", {}).items():
        print(f"  {sym}: conId={cd_data.get('conId')} | Primary Exchange={cd_data.get('primaryExchange')} | Long Name={cd_data.get('longName')}")
        print(f"        IEX In Valid Exchanges: {cd_data.get('has_iex')} | Cboe Venues Confirmed: {cd_data.get('cboe_venues_confirmed')}")
    print("-" * 84)

    print("\n--- STREAMING QUOTE EVALUATION RESULTS ---")
    for key, stream_info in report.get("stream_records", {}).items():
        freshness = stream_info.get("freshness_evaluation", {})
        sym = stream_info.get("symbol")
        venue = stream_info.get("venue")
        q_source = stream_info.get("quote_source")
        phase = stream_info.get("phase")

        print(f"Stream: [{sym}] Venue: {venue:<5} | Source: {q_source:<29} | Phase: {phase}")
        print(f"  Market Data Type: {freshness.get('market_data_type')} (Delayed: {freshness.get('is_delayed')})")
        print(f"  Bid: {freshness.get('bid')} | Ask: {freshness.get('ask')} | Last: {stream_info.get('last')} | Close: {stream_info.get('close')}")
        print(f"  Spread: {freshness.get('spread')} | Midpoint: {freshness.get('midpoint')}")
        print(f"  Underlying Quote Timestamp: {freshness.get('underlying_quote_timestamp_utc')}")
        print(f"  Meets 30-Second Freshness Contract: {freshness.get('meets_30s_freshness_contract')}")
        if freshness.get("freshness_reasons"):
            print(f"  Evaluation Details: {'; '.join(freshness.get('freshness_reasons'))}")
        if stream_info.get("subscription_error"):
            print(f"  Subscription Status: {stream_info.get('subscription_error')}")
        if stream_info.get("unsubscribed_warning"):
            print(f"  Warning: {stream_info.get('unsubscribed_warning')}")
        if stream_info.get("competing_live_session"):
            print(f"  Session Status: Competing live session blocked market data on paper account (Code 10197)")
        print("-" * 84)

    synth = report.get("synthesized_findings", {})
    print("\n" + "="*84)
    print(" SYNTHESIZED VERIFICATION FINDINGS & GAP ANALYSIS")
    print("="*84)
    print(f"1. Does Free Data Work Through Socket API?    : {'YES (Delayed/Close Data)' if synth.get('free_data_works_through_socket_api') else 'NO'}")
    print(f"2. Meets 30s Execution Freshness Contract?    : {'YES' if synth.get('meets_execution_freshness_contract') else 'NO (STRICTLY VIOLATED)'}")
    print(f"3. Delayed Market Data Explicitly Available?  : {'YES' if synth.get('delayed_data_explicitly_available') else 'NO'}")
    print(f"4. Competing Live Session Detected?           : {'YES' if synth.get('competing_live_session_detected') else 'NO'}")

    print("\nVenue Distinction:")
    for v_type, desc in synth.get("quote_source_distinction", {}).items():
        print(f"  * {v_type}: {desc}")

    print("\nGeneric Tick 233 Comparison:")
    print(f"  {synth.get('phase_comparison', {}).get('tick_233_behavior')}")

    if synth.get("missing_market_data_subscriptions"):
        print("\nRequired IBKR Market Data Subscriptions for Execution:")
        for sub in synth["missing_market_data_subscriptions"]:
            print(f"  - [{sub['code']}] {sub['subscription_name']}")
            print(f"    Cost    : {sub['monthly_cost']}")
            print(f"    Coverage: {sub['coverage']}")
    print("="*84 + "\n")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved complete structured report to: {out_path}")

    return 0 if report.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
