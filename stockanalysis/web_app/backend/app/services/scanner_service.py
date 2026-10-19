"""Market Scanner & V4.0 Signal Generation Service for Adaptive Trading.

Implements Phase 4A requirements:
1. Strict separation of data layers (Frozen baseline vs rolling price cache).
2. Incremental daily OHLCV bar updates with retry and stale preservation.
3. V4.0 indicator calculation (SMA30, SMA50, SMA250, ROC20, ATR14).
4. Per-stock walk-forward optimization without lookahead.
5. Signal classifications: BUY CANDIDATE, WATCH, HOLD, EXIT, AVOID, INSUFFICIENT DATA.
6. Research-only short-side classification (no unsupported short recommendations).
7. Thread-safe manual screener refresh with live progress tracking and resumption.
"""
from typing import Dict, List, Any, Optional, Tuple
import os
import sys
import time
import uuid
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

from app.config import (
    ACTIVE_ENGINE_DIR,
    PRICE_CACHE_DIR,
    ROLLING_PRICE_CACHE_DIR,
    BASELINE_EXCEL_PATH,
    SIGNAL_PALETTE,
    DATA_PROVENANCE,
    DEFAULT_FEE_BPS,
    DEFAULT_TRAIN_YEARS,
    DEFAULT_MIN_BUYS,
    WORKER_MODE,
)
from app.services.universe_manager import universe_manager


# Ensure engine directory is in sys.path
if str(ACTIVE_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ACTIVE_ENGINE_DIR))

import strategy_core_v38 as v41_core
from defensive_exits import exit_trigger


# Known simulated holdings from the audited V4.0 baseline portfolio
SIMULATED_HOLDINGS = {"QQQ", "NVDA", "MA"}


class ScannerService:
    def __init__(self):
        self._refresh_lock = threading.Lock()
        self._cancel_flag = False
        self._refresh_thread: Optional[threading.Thread] = None

        self.refresh_state: Dict[str, Any] = {
            "is_running": False,
            "total": 0,
            "completed": 0,
            "remaining": 0,
            "failed": 0,
            "stale": 0,
            "current_ticker": "",
            "start_time": None,
            "finish_time": None,
            "errors": [],
            "message": "Idle",
        }

        # Initialize any baseline signals from the frozen Excel sheet if registry is unpopulated
        self._seed_baseline_signals_if_needed()

    def _seed_baseline_signals_if_needed(self):
        """Seed initial signals from audited Excel for baseline stocks so first load is instant."""
        if not BASELINE_EXCEL_PATH.exists():
            return

        try:
            xl = pd.ExcelFile(BASELINE_EXCEL_PATH)
            if "TodayTrade" in xl.sheet_names:
                df = xl.parse("TodayTrade")
                for _, r in df.iterrows():
                    ticker = str(r["Ticker"]).strip().upper()
                    existing = universe_manager.get_stock(ticker)
                    if existing and existing.get("latest_signal") is None:
                        sig = str(r["Signal"]).strip()
                        entry_rule = str(r["Entry rule"]) if pd.notna(r["Entry rule"]) else ""
                        exit_rule = str(r["Exit rule"]) if pd.notna(r["Exit rule"]) else ""
                        close_val = round(float(r["Close"]), 2) if pd.notna(r["Close"]) else None
                        palette = SIGNAL_PALETTE.get(sig, {"bg": "#E2E8F0", "text": "#1E293B", "border": "#CBD5E1"})

                        is_delayed = entry_rule in ("DELAYED_MA50", "DELAYED_STACK")
                        entry_type = "DELAYED" if is_delayed else "IMMEDIATE" if entry_rule else "NONE"
                        delayed_stage = ""
                        if is_delayed:
                            delayed_stage = "Waiting for 3 consecutive closes above MA250" if sig == "WATCH" else ""

                        sig_dict = {
                            "ticker": ticker,
                            "name": existing.get("name", ticker),
                            "as_of": str(r["As of"])[:10],
                            "close": close_val,
                            "ma30": round(float(r["MA30"]), 2) if pd.notna(r["MA30"]) else None,
                            "ma50": round(float(r["MA50"]), 2) if pd.notna(r["MA50"]) else None,
                            "ma250": round(float(r["MA250"]), 2) if pd.notna(r["MA250"]) else None,
                            "roc20_pct": None,
                            "atr14": None,
                            "entry_rule": entry_rule,
                            "exit_rule": exit_rule,
                            "entry_type": entry_type,
                            "delayed_stage": delayed_stage,
                            "order_notice": "RESEARCH SIGNAL — NOT AN EXECUTABLE ORDER" if sig in ("BUY", "BUY CANDIDATE") else "Simulated portfolio holding" if sig in ("HOLD", "EXIT") else "Research observation",
                            "signal": sig,
                            "shariah_status": "COMPLIANT" if ticker in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AMD") else "NOT VERIFIED",
                            "explanation": str(r["Explanation"]) if pd.notna(r["Explanation"]) else "",
                            "is_simulated_position": ticker in SIMULATED_HOLDINGS,
                            "data_freshness": "FROZEN_BASELINE",
                            "color_bg": palette["bg"],
                            "color_text": palette["text"],
                        }

                        universe_manager.update_stock(ticker, {
                            "latest_price_date": str(r["As of"])[:10],
                            "data_status": "READY",
                            "latest_signal": sig_dict,
                            "optimal_rule": {"entry": entry_rule, "exit": exit_rule},
                        }, sync_db=False)
        except Exception as e:
            print(f"[ScannerService] Error loading baseline TodayTrade: {e}")

    def get_price_df(self, ticker: str) -> Optional[pd.DataFrame]:
        """Loads price data, prioritizing the rolling research cache, then database DailyBar table, then frozen baseline."""
        ticker = ticker.strip().upper()
        # 1. Check Rolling Research Cache (Local L1 File Cache)
        rolling_file = ROLLING_PRICE_CACHE_DIR / f"{ticker}.csv"
        if rolling_file.exists():
            try:
                df = pd.read_csv(rolling_file, index_col="Date", parse_dates=True).sort_index()
                df = df[~df.index.duplicated(keep="last")]
                if not df.empty and len(df) >= 1:
                    return df
            except Exception:
                pass

        # 2. Check Database DailyBar Table (Durable Supabase L2 Storage - Survives container restarts)
        try:
            from app.database import SessionLocal
            from app.models import DailyBar
            db = SessionLocal()
            try:
                bars = db.query(DailyBar).filter(DailyBar.ticker == ticker).order_by(DailyBar.bar_date.asc()).all()
                if bars and len(bars) >= 20:
                    records = [{
                        "Date": b.bar_date,
                        "Open": b.open,
                        "High": b.high,
                        "Low": b.low,
                        "Close": b.close,
                        "Volume": b.volume,
                    } for b in bars]
                    df = pd.DataFrame(records).set_index("Date")
                    df.index = pd.to_datetime(df.index)
                    # Cache to disk for instant next access in this container
                    rolling_file.parent.mkdir(parents=True, exist_ok=True)
                    df.to_csv(rolling_file, index_label="Date")
                    return df
            finally:
                db.close()
        except Exception:
            pass

        # 3. Check Frozen Baseline Cache
        baseline_file = PRICE_CACHE_DIR / f"{ticker.replace('^', 'IDX_')}.csv"
        if baseline_file.exists():
            try:
                df = pd.read_csv(baseline_file, index_col="Date", parse_dates=True).sort_index()
                df = df[~df.index.duplicated(keep="last")]
                if not df.empty and len(df) >= 1:
                    return df
            except Exception:
                pass

        return None

    def _persist_bars_to_db(self, ticker: str, df: pd.DataFrame, full: bool = False):
        """Persists daily OHLCV bars into durable Supabase DailyBar table with atomic upserts."""
        if df is None or df.empty:
            return
        from app.database import SessionLocal
        from app.models import DailyBar
        db = SessionLocal()
        try:
            target_slice = df.tail(2520) if full else df.tail(30)
            for idx, row in target_slice.iterrows():
                date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                bar = DailyBar(
                    ticker=ticker,
                    bar_date=date_str,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0)) if pd.notna(row.get("Volume", 0.0)) else 0.0,
                )
                db.merge(bar)
            db.commit()
        except Exception as ex:
            db.rollback()
            print(f"[ScannerService] Error persisting daily bars to DB for {ticker}: {ex}")
        finally:
            db.close()

    def fetch_or_update_stock(self, ticker: str, force_full: bool = False) -> Tuple[Optional[pd.DataFrame], bool]:
        """Fetches or incrementally updates stock OHLCV data using Yahoo Finance.
        Returns: (DataFrame or None, is_stale_boolean)
        """
        ticker = ticker.strip().upper()
        existing_df = self.get_price_df(ticker)

        import yfinance as yf

        is_stale = False
        try:
            if existing_df is not None and not force_full and len(existing_df) >= 250:
                last_dt = existing_df.index[-1]
                # If last bar is already recent (within last calendar day / weekend), reuse existing
                days_old = (datetime.now().date() - last_dt.date()).days
                if days_old <= 0:
                    return existing_df, False

                # Incremental fetch: from 7 days before last_dt to ensure splits/adjustments overlap
                start_fetch = (last_dt - timedelta(days=7)).strftime("%Y-%m-%d")
                new_bars = yf.download(
                    ticker,
                    start=start_fetch,
                    auto_adjust=True,
                    progress=False,
                    multi_level_index=False,
                    timeout=10,
                )

                if new_bars is not None and not new_bars.empty:
                    # Clean and align columns
                    new_bars = new_bars[["Open", "High", "Low", "Close"]].dropna()
                    combined = pd.concat([existing_df[["Open", "High", "Low", "Close"]], new_bars])
                    combined = combined[~combined.index.duplicated(keep="last")].sort_index()

                    # Save to rolling cache (Never mutate frozen baseline!)
                    target_file = ROLLING_PRICE_CACHE_DIR / f"{ticker}.csv"
                    combined.to_csv(target_file, index_label="Date")
                    self._persist_bars_to_db(ticker, combined, full=False)
                    return combined, False
                else:
                    # Failed to get new bars; preserve existing data and flag as stale
                    return existing_df, True
            else:
                # Full backfill for new or small stock: 5-10 years of data
                bars = yf.download(
                    ticker,
                    period="5y",
                    auto_adjust=True,
                    progress=False,
                    multi_level_index=False,
                    timeout=12,
                )

                if bars is not None and not bars.empty:
                    bars = bars[["Open", "High", "Low", "Close"]].dropna().sort_index()
                    bars = bars[~bars.index.duplicated(keep="last")]
                    target_file = ROLLING_PRICE_CACHE_DIR / f"{ticker}.csv"
                    bars.to_csv(target_file, index_label="Date")
                    self._persist_bars_to_db(ticker, bars, full=True)
                    return bars, False
                else:
                    if existing_df is not None:
                        return existing_df, True
                    return None, False


        except Exception as e:
            print(f"[ScannerService] Error fetching {ticker}: {e}")
            if existing_df is not None:
                return existing_df, True
            return None, False

    def optimize_v40_rule(self, d: pd.DataFrame, asof: pd.Timestamp) -> Optional[Dict[str, Any]]:
        """Per-stock walk-forward parameter optimization without lookahead using V4.0 engine."""
        import engine as v41_engine
        try:
            # 5-year lookback or whatever is eligible (minimum 1 year / 250 bars)
            win, _ = v41_engine.train(
                d,
                asof=asof,
                years=DEFAULT_TRAIN_YEARS,
                fee=DEFAULT_FEE_BPS,
                min_buys=DEFAULT_MIN_BUYS,
                exit_mode="baseline",
            )
            if win is None:
                # Try with min_buys=1 for stocks with fewer crossover cycles
                win, _ = v41_engine.train(
                    d,
                    asof=asof,
                    years=DEFAULT_TRAIN_YEARS,
                    fee=DEFAULT_FEE_BPS,
                    min_buys=1,
                    exit_mode="baseline",
                )
            return win
        except Exception:
            return None

    def evaluate_stock_signal(self, ticker: str, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """Calculates indicators and evaluates V4.0 trading signal for a stock."""
        ticker = ticker.strip().upper()
        stock_info = universe_manager.get_stock(ticker) or {"ticker": ticker, "name": ticker}

        if df is None:
            df = self.get_price_df(ticker)

        if df is None or len(df) < 30:
            return {
                "ticker": ticker,
                "name": stock_info.get("name", ticker),
                "as_of": str(df.index[-1].date()) if df is not None and len(df) > 0 else datetime.now().strftime("%Y-%m-%d"),
                "close": round(float(df["Close"].iloc[-1]), 2) if df is not None and len(df) > 0 else None,
                "ma30": None,
                "ma50": None,
                "ma250": None,
                "roc20_pct": None,
                "atr14": None,
                "entry_rule": "N/A",
                "exit_rule": "N/A",
                "entry_type": "NONE",
                "delayed_stage": "",
                "order_notice": "INSUFFICIENT DATA",
                "signal": "INSUFFICIENT DATA",
                "shariah_status": "NOT VERIFIED",
                "explanation": f"Insufficient historical price history ({len(df) if df is not None else 0} bars available, minimum 250 bars required for MA250).",
                "is_simulated_position": False,
                "data_freshness": "INSUFFICIENT_DATA",
                "color_bg": "#F1F5F9",
                "color_text": "#64748B",
            }

        # Calculate V4.0 core indicators
        d = v41_core.prep(df)
        if d.empty or len(d) < 30:
            return {
                "ticker": ticker,
                "name": stock_info.get("name", ticker),
                "as_of": str(df.index[-1].date()),
                "close": round(float(df["Close"].iloc[-1]), 2),
                "ma30": None,
                "ma50": None,
                "ma250": None,
                "roc20_pct": None,
                "atr14": None,
                "entry_rule": "N/A",
                "exit_rule": "N/A",
                "entry_type": "NONE",
                "delayed_stage": "",
                "order_notice": "INSUFFICIENT DATA",
                "signal": "INSUFFICIENT DATA",
                "shariah_status": "NOT VERIFIED",
                "explanation": "Calculation error during indicator preparation.",
                "is_simulated_position": False,
                "data_freshness": "INSUFFICIENT_DATA",
                "color_bg": "#F1F5F9",
                "color_text": "#64748B",
            }

        r = d.iloc[-1]
        as_of = str(d.index[-1].date())
        close = round(float(r.Close), 2)
        ma30 = round(float(r.MA30), 2) if pd.notna(r.MA30) else None
        ma50 = round(float(r.MA50), 2) if pd.notna(r.MA50) else None
        ma250 = round(float(r.MA250), 2) if pd.notna(r.MA250) else None
        roc20_val = round(float(r.ROC20) * 100, 2) if pd.notna(r.ROC20) else None
        atr14_val = round(float(r.ATR14), 2) if pd.notna(r.ATR14) else None

        if len(d) < 250 or ma250 is None:
            return {
                "ticker": ticker,
                "name": stock_info.get("name", ticker),
                "as_of": as_of,
                "close": close,
                "ma30": ma30,
                "ma50": ma50,
                "ma250": None,
                "roc20_pct": roc20_val,
                "atr14": atr14_val,
                "entry_rule": "N/A",
                "exit_rule": "N/A",
                "entry_type": "NONE",
                "delayed_stage": "",
                "order_notice": "INSUFFICIENT DATA",
                "signal": "INSUFFICIENT DATA",
                "shariah_status": "NOT VERIFIED",
                "explanation": f"Fewer than 250 bars ({len(d)} bars). MA250 requires 250 sessions.",
                "is_simulated_position": False,
                "data_freshness": "INSUFFICIENT_DATA",
                "color_bg": "#F1F5F9",
                "color_text": "#64748B",
            }

        # Derive historically eligible optimal V4.0 parameters for this stock
        win = self.optimize_v40_rule(d, d.index[-1])
        entry_rule = win["entry"] if win else "CROSS"
        exit_rule = win["exit"] if win else "MA250_3CLOSE"

        is_delayed_rule = entry_rule in ("DELAYED_MA50", "DELAYED_STACK")
        entry_type = "DELAYED" if is_delayed_rule else "IMMEDIATE" if entry_rule else "NONE"

        # Signal Classification
        sig = "AVOID"
        explanation = ""
        delayed_stage = ""

        is_simulated = ticker in SIMULATED_HOLDINGS

        if is_simulated:
            # Check exit rule for open position
            if exit_trigger(r, exit_rule):
                sig = "EXIT"
                explanation = f"Simulated holding triggered exit rule ({exit_rule}) on latest close."
            else:
                sig = "HOLD"
                explanation = f"Simulated holding active; exit condition ({exit_rule}) not met."
        elif close < ma250:
            sig = "AVOID"
            explanation = "Price below MA250; unfavorable long technical setup."
        else:
            # Close >= MA250
            if bool(r.cross):
                # Fresh crossover on the latest bar
                if entry_rule == "CROSS":
                    sig = "BUY CANDIDATE"
                    explanation = "Fresh MA250 crossover with immediate entry rule."
                elif entry_rule == "MA50_AT_CROSS":
                    if bool(r.bull50):
                        sig = "BUY CANDIDATE"
                        explanation = "Fresh MA250 crossover with MA50 > MA250 golden alignment."
                    else:
                        sig = "WATCH"
                        explanation = "Fresh MA250 cross occurred, but MA50 <= MA250; awaiting golden alignment."
                elif entry_rule == "ROC20_AT_CROSS":
                    if pd.notna(r.ROC20) and r.ROC20 > 0:
                        sig = "BUY CANDIDATE"
                        explanation = "Fresh MA250 crossover with positive 20-day momentum."
                    else:
                        sig = "WATCH"
                        explanation = "Fresh MA250 cross occurred, but ROC20 is negative; awaiting momentum confirmation."
                elif is_delayed_rule:
                    sig = "WATCH"
                    delayed_stage = "Fresh cross occurred; awaiting 3 consecutive closes above MA250."
                    explanation = "Awaiting 3-day close persistence and moving average alignment."
            else:
                # Not a fresh crossover on this exact bar, but Close > MA250
                if is_delayed_rule:
                    # Check recent cross persistence
                    recent_bars = d.iloc[-25:]
                    has_recent_cross = bool(recent_bars["cross"].any())
                    stayed_above = bool((recent_bars["Close"] > recent_bars["MA250"]).all())

                    if entry_rule == "DELAYED_MA50":
                        is_above3 = bool(r.above3)
                        is_aligned = bool(r.bull50)
                        if is_above3 and is_aligned:
                            sig = "BUY CANDIDATE"
                            delayed_stage = "Conditions aligned: 3 Closes Met & MA50 > MA250"
                            explanation = "Delayed MA50 condition fulfilled; valid long setup."
                        elif not is_above3:
                            sig = "WATCH"
                            delayed_stage = "Waiting for 3 consecutive closes above MA250"
                            explanation = "Trading above MA250; waiting for 3 consecutive closes."
                        else:
                            sig = "WATCH"
                            delayed_stage = "3 Closes Met; awaiting MA50 > MA250 alignment"
                            explanation = "3 closes met; waiting for MA50 to cross above MA250."
                    elif entry_rule == "DELAYED_STACK":
                        is_above3 = bool(r.above3)
                        is_aligned = bool(r.stack)
                        if is_above3 and is_aligned:
                            sig = "BUY CANDIDATE"
                            delayed_stage = "Conditions aligned: 3 Closes Met & MA30 > MA50 > MA250 Stack"
                            explanation = "Delayed Stack condition fulfilled; valid long setup."
                        elif not is_above3:
                            sig = "WATCH"
                            delayed_stage = "Waiting for 3 consecutive closes above MA250"
                            explanation = "Trading above MA250; waiting for 3 consecutive closes."
                        else:
                            sig = "WATCH"
                            delayed_stage = "3 Closes Met; awaiting MA30 > MA50 > MA250 Stack alignment"
                            explanation = "3 closes met; waiting for full MA30 > MA50 > MA250 stack."
                else:
                    # Immediate crossover rule, but crossover date has already passed
                    sig = "WATCH"
                    explanation = "Above MA250; awaiting next qualifying setup or crossover cycle."

        palette = SIGNAL_PALETTE.get(sig, {"bg": "#E2E8F0", "text": "#1E293B", "border": "#CBD5E1"})
        order_notice = (
            "RESEARCH SIGNAL — NOT AN EXECUTABLE ORDER"
            if sig == "BUY CANDIDATE"
            else "Simulated portfolio holding"
            if sig in ("HOLD", "EXIT")
            else "Research watchlist observation"
        )

        return {
            "ticker": ticker,
            "name": stock_info.get("name", ticker),
            "as_of": as_of,
            "close": close,
            "ma30": ma30,
            "ma50": ma50,
            "ma250": ma250,
            "roc20_pct": roc20_val,
            "atr14": atr14_val,
            "entry_rule": entry_rule,
            "exit_rule": exit_rule,
            "entry_type": entry_type,
            "delayed_stage": delayed_stage,
            "order_notice": order_notice,
            "signal": sig,
            "shariah_status": stock_info.get("shariah_status", "NOT VERIFIED"),
            "explanation": explanation,
            "is_simulated_position": is_simulated,
            "data_freshness": "FRESH",
            "color_bg": palette["bg"],
            "color_text": palette["text"],
        }

    def add_stock_to_screener(self, ticker: str, name: Optional[str] = None, exchange: Optional[str] = None, sector: Optional[str] = None) -> Dict[str, Any]:
        """Dynamically ingests, optimizes, analyzes, and persists a stock into the screener universe and active snapshot."""
        ticker = ticker.strip().upper()

        with self._refresh_lock:
            # 1. Fetch historical data into rolling cache
            df, is_stale = self.fetch_or_update_stock(ticker, force_full=True)

            data_status = "READY"
            if df is None or len(df) < 250:
                data_status = "INSUFFICIENT_DATA"
            elif is_stale:
                data_status = "STALE"

            # 2. Evaluate V4.0 signal & indicators
            signal_data = self.evaluate_stock_signal(ticker, df)
            if is_stale:
                signal_data["data_freshness"] = "STALE"

            optimal_rule = {
                "entry": signal_data.get("entry_rule"),
                "exit": signal_data.get("exit_rule"),
            }

            # 3. Persist in universe registry & MonitoredStock table
            record = universe_manager.add_stock(
                ticker=ticker,
                name=name or ticker,
                exchange=exchange or "NASDAQ",
                sector=sector or "Technology",
                data_status=data_status,
                optimal_rule=optimal_rule,
                latest_signal=signal_data,
                latest_price_date=signal_data.get("as_of"),
                v40_eligible=len(df) >= 250 if df is not None else False,
            )

            # 4. Safely update active snapshot if one exists so stock appears immediately
            try:
                from app.services.snapshot_service import snapshot_service
                from app.database import SessionLocal
                from app.models import ScreenerSnapshot
                db = SessionLocal()
                try:
                    active_snap = db.query(ScreenerSnapshot).filter(
                        ScreenerSnapshot.is_active == True,
                        ScreenerSnapshot.status == "COMPLETED"
                    ).first()
                    if active_snap:
                        signals = json.loads(active_snap.signals_json) if active_snap.signals_json else []
                        # Replace if ticker exists, otherwise append
                        filtered_signals = [s for s in signals if s.get("ticker") != ticker]
                        filtered_signals.append(signal_data)
                        active_snap.signals_json = json.dumps(filtered_signals)
                        active_snap.total_stocks = len(filtered_signals)
                        db.commit()
                finally:
                    db.close()
            except Exception as e:
                print(f"[ScannerService] Active snapshot append notice: {e}")

            return {
                "stock": record,
                "signal": signal_data,
                "bars_count": len(df) if df is not None else 0,
                "status": "SUCCESS" if data_status == "READY" else data_status,
            }

    def start_refresh_async(self, force_all: bool = False, job_type: str = "MANUAL_REFRESH") -> Dict[str, Any]:
        """Initiates a durable screener refresh as a background job."""
        from app.database import SessionLocal
        from app.models import RefreshJob

        with self._refresh_lock:
            db = SessionLocal()
            try:
                # Check for active existing job
                existing_job = db.query(RefreshJob).filter(
                    RefreshJob.status.in_(["QUEUED", "RUNNING"])
                ).order_by(RefreshJob.created_at.desc()).first()

                if existing_job:
                    return {
                        "status": "ALREADY_RUNNING",
                        "job_id": existing_job.id,
                        "message": "A screener refresh is already in progress.",
                        "progress": self._format_job_dict(existing_job),
                    }

                stocks = universe_manager.get_all(include_inactive=False)
                job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                self._cancel_flag = False

                new_job = RefreshJob(
                    id=job_id,
                    job_type=job_type,
                    status="QUEUED",
                    force_all=force_all,
                    total_stocks=len(stocks),
                    completed_stocks=0,
                    remaining_stocks=len(stocks),
                    failed_stocks=0,
                    stale_stocks=0,
                    current_ticker="",
                    start_time=datetime.utcnow(),
                    message=f"Refresh queued for {len(stocks)} symbols...",
                    errors_json="[]",
                )
                db.add(new_job)
                db.commit()
                db.refresh(new_job)

                job_info = self._format_job_dict(new_job)

                # Check worker mode: in 'standalone' mode (e.g. production worker container),
                # the web service queues the job and lets the external worker daemon process it.
                # In 'embedded' mode (local dev / single-container), run in-process thread.
                if WORKER_MODE == "standalone":
                    return {
                        "status": "QUEUED",
                        "job_id": job_id,
                        "message": f"Refresh job {job_id} queued for standalone worker across {len(stocks)} symbols.",
                        "progress": job_info,
                    }

                # Embedded worker thread
                self._refresh_thread = threading.Thread(
                    target=self._run_refresh_worker,
                    args=(job_id, stocks, force_all),
                    daemon=True,
                    name=f"RefreshWorker-{job_id}",
                )
                self._refresh_thread.start()

                return {
                    "status": "STARTED",
                    "job_id": job_id,
                    "message": f"Refresh job {job_id} initiated for {len(stocks)} symbols.",
                    "progress": job_info,
                }
            finally:
                db.close()


    def _format_job_dict(self, job) -> Dict[str, Any]:
        """Format a RefreshJob SQLAlchemy model into a clean API dictionary."""
        summary = universe_manager.get_summary_counts()
        return {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "is_running": job.status in ("QUEUED", "RUNNING"),
            "total": job.total_stocks,
            "completed": job.completed_stocks,
            "remaining": job.remaining_stocks,
            "failed": job.failed_stocks,
            "stale": job.stale_stocks,
            "current_ticker": job.current_ticker or "",
            "start_time": job.start_time.strftime("%Y-%m-%d %H:%M:%S UTC") if job.start_time else None,
            "finish_time": job.finish_time.strftime("%Y-%m-%d %H:%M:%S UTC") if job.finish_time else None,
            "message": job.message or "",
            "error_message": job.error_message or "",
            "snapshot_id": job.snapshot_id,
            "summary": summary,
        }

    def _run_refresh_worker(self, job_id: str, stocks: List[Dict[str, Any]], force_all: bool):
        """Worker executing incremental daily updates and publishing an atomic screener snapshot."""
        from app.database import SessionLocal
        from app.models import RefreshJob
        from app.services.snapshot_service import snapshot_service

        db = SessionLocal()
        staged_signals: List[Dict[str, Any]] = []
        errors = []

        try:
            job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
            if not job:
                return
            job.status = "RUNNING"
            job.start_time = datetime.utcnow()
            job.message = f"Starting analysis across {len(stocks)} securities..."
            db.commit()

            for i, stock in enumerate(stocks):
                if self._cancel_flag:
                    job.status = "CANCELLED"
                    job.finish_time = datetime.utcnow()
                    job.message = "Refresh cancelled by user."
                    db.commit()
                    return

                ticker = stock["ticker"]
                job.current_ticker = ticker
                job.message = f"Refreshing {ticker} ({i+1}/{len(stocks)})..."
                db.commit()

                try:
                    df, is_stale = self.fetch_or_update_stock(ticker, force_full=force_all)
                    if df is not None and len(df) >= 250:
                        sig_data = self.evaluate_stock_signal(ticker, df)
                        if is_stale:
                            sig_data["data_freshness"] = "STALE"
                            job.stale_stocks += 1
                        staged_signals.append(sig_data)
                    elif df is not None and len(df) < 250:
                        sig_data = self.evaluate_stock_signal(ticker, df)
                        sig_data["data_freshness"] = "INSUFFICIENT_DATA"
                        job.failed_stocks += 1
                        staged_signals.append(sig_data)
                    else:
                        job.failed_stocks += 1
                        # If existing signal exists in universe, attach as stale
                        existing_sig = stock.get("latest_signal") or self.evaluate_stock_signal(ticker, None)
                        existing_sig["data_freshness"] = "STALE"
                        staged_signals.append(existing_sig)
                except Exception as ex:
                    job.failed_stocks += 1
                    errors.append({"ticker": ticker, "error": str(ex)})
                    existing_sig = stock.get("latest_signal") or self.evaluate_stock_signal(ticker, None)
                    existing_sig["data_freshness"] = "STALE"
                    staged_signals.append(existing_sig)

                job.completed_stocks = i + 1
                job.remaining_stocks = len(stocks) - (i + 1)
                db.commit()
                time.sleep(0.04)

            # Determine dominant market date
            valid_dates = [s["as_of"] for s in staged_signals if s.get("as_of")]
            market_as_of = max(valid_dates) if valid_dates else datetime.now().strftime("%Y-%m-%d")

            # ATOMIC SNAPSHOT PUBLICATION
            new_snap = snapshot_service.publish_new_snapshot(
                staged_signals=staged_signals,
                market_as_of_date=market_as_of,
                refresh_job_id=job_id,
                db=db,
            )

            job.status = "COMPLETED"
            job.finish_time = datetime.utcnow()
            job.snapshot_id = new_snap["snapshot_id"]
            job.message = f"Refresh completed successfully ({len(staged_signals)} securities analyzed)."
            job.current_ticker = ""
            job.errors_json = json.dumps(errors)
            db.commit()

        except Exception as ex:
            print(f"[ScannerService] Error during refresh worker execution: {ex}")
            try:
                job = db.query(RefreshJob).filter(RefreshJob.id == job_id).first()
                if job:
                    job.status = "FAILED"
                    job.finish_time = datetime.utcnow()
                    job.error_message = str(ex)
                    job.message = f"Refresh failed: {str(ex)[:100]}"
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    def cancel_refresh(self) -> Dict[str, Any]:
        """Cancels an ongoing refresh operation."""
        from app.database import SessionLocal
        from app.models import RefreshJob

        with self._refresh_lock:
            self._cancel_flag = True
            db = SessionLocal()
            try:
                active_job = db.query(RefreshJob).filter(
                    RefreshJob.status.in_(["QUEUED", "RUNNING"])
                ).first()
                if active_job:
                    active_job.status = "CANCELLED"
                    active_job.finish_time = datetime.utcnow()
                    active_job.message = "Cancelled by user."
                    db.commit()
                    return {"status": "CANCELLED", "message": f"Job {active_job.id} cancelled."}
                return {"status": "NOT_RUNNING", "message": "No active refresh job is currently running."}
            finally:
                db.close()

    def get_refresh_status(self) -> Dict[str, Any]:
        """Returns the current state and progress of the active or latest refresh job."""
        from app.database import SessionLocal
        from app.models import RefreshJob

        db = SessionLocal()
        try:
            # First check for currently running / queued job
            job = db.query(RefreshJob).filter(
                RefreshJob.status.in_(["QUEUED", "RUNNING"])
            ).order_by(RefreshJob.created_at.desc()).first()

            if not job:
                # Return most recently completed / failed job
                job = db.query(RefreshJob).order_by(RefreshJob.created_at.desc()).first()

            if job:
                return self._format_job_dict(job)

            # Fallback if no jobs exist yet
            summary = universe_manager.get_summary_counts()
            return {
                "job_id": None,
                "job_type": "MANUAL_REFRESH",
                "status": "IDLE",
                "is_running": False,
                "total": summary.get("total_universe", 0),
                "completed": summary.get("analysed_count", 0),
                "remaining": 0,
                "failed": 0,
                "stale": summary.get("stale_count", 0),
                "current_ticker": "",
                "start_time": None,
                "finish_time": None,
                "message": "Idle",
                "error_message": "",
                "snapshot_id": None,
                "summary": summary,
            }
        finally:
            db.close()

    def get_active_job(self) -> Optional[Dict[str, Any]]:
        """Retrieve currently running job if one exists, else None."""
        from app.database import SessionLocal
        from app.models import RefreshJob

        db = SessionLocal()
        try:
            job = db.query(RefreshJob).filter(
                RefreshJob.status.in_(["QUEUED", "RUNNING"])
            ).order_by(RefreshJob.created_at.desc()).first()
            if job:
                return self._format_job_dict(job)
            return None
        finally:
            db.close()


# Singleton instance
scanner_service = ScannerService()

