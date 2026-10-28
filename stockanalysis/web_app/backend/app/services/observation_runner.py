"""Autonomous observation-only pilot runner (Stage D2.4K).

Reuses:
  - scanner_service (V4.0 evaluate)
  - BuyPipelineDryRun + DecisionJournal
  - USER_POLICY classify_user_policy / DecisionContext.eligibility_mode
  - alpaca_readonly (quotes + account)
  - candidate_ranking
  - observation_schedule / observation_performance

Never submits, approves, or cancels broker orders.
Never writes production snapshot publishes.
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import (
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
    V40_SIGNAL_SOURCE,
    V40_STRATEGY_VERSION,
)
from app.services.alpaca_readonly import try_load_readonly_client
from app.services.buy_decision_engine import AccountSnapshot, DecisionContext
from app.services.buy_pipeline_dry_run import BuyPipelineDryRun
from app.services.candidate_ranking import describe_ranking_methodology, rank_candidates
from app.services.decision_journal import DecisionJournal
from app.services.observation_performance import attach_performance_to_proposals
from app.services.observation_schedule import (
    ensure_schedule_config,
    is_observation_trading_day,
    plan_upcoming_slots,
    should_run_slot,
)
from app.services.order_execution_service import (
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED
from app.services.scanner_service import scanner_service
from app.services.universe_manager import universe_manager
from app.services.user_policy_eligibility import MODE_USER_POLICY, classify_user_policy
from app.services.us_session_freshness import (
    evaluate_signal_session_freshness,
    last_completed_us_equity_session,
)

OBSERVATION_ROOT = DATA_CACHE_DIR / "observation"
CHECKPOINT_NAME = "checkpoint.json"
CHECKPOINTS_DIR = OBSERVATION_ROOT / "checkpoints"


def _progress(msg: str) -> None:
    """Write progress lines that flush immediately (PowerShell-friendly)."""
    print(msg, flush=True)


class ObservationRunner:
    """Session-scoped observation orchestrator (local evidence only)."""

    def __init__(
        self,
        *,
        evidence_dir: Optional[Path] = None,
        journal: Optional[DecisionJournal] = None,
        pipeline: Optional[BuyPipelineDryRun] = None,
        refresh_prices: bool = False,
        checkpoint_scope: Optional[str] = None,
        use_optimize_cache: bool = True,
    ):
        self.started = datetime.now(timezone.utc)
        self.run_id = self.started.strftime("d2_4k_%Y%m%dT%H%M%SZ")
        self.evidence_dir = Path(evidence_dir) if evidence_dir else (
            DATA_CACHE_DIR / "evidence" / self.run_id
        )
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.journal = journal or DecisionJournal(journal_dir=self.evidence_dir / "journal")
        self.pipeline = pipeline or BuyPipelineDryRun(journal=self.journal)
        self.refresh_prices = bool(refresh_prices)
        self.use_optimize_cache = bool(use_optimize_cache)
        self.checkpoint_scope = checkpoint_scope or "default"
        CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
        OBSERVATION_ROOT.mkdir(parents=True, exist_ok=True)
        safe_scope = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in self.checkpoint_scope
        )[:80]
        self.checkpoint_path = CHECKPOINTS_DIR / safe_scope / CHECKPOINT_NAME
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.submissions_attempted = 0

    def _load_checkpoint(self) -> Dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {
                "completed_tickers": [],
                "scan_rows_by_ticker": {},
                "last_run_id": None,
                "strategy_version": V40_STRATEGY_VERSION,
                "checkpoint_scope": self.checkpoint_scope,
            }
        try:
            data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            data.setdefault("scan_rows_by_ticker", {})
            data.setdefault("completed_tickers", [])
            return data
        except (OSError, json.JSONDecodeError):
            return {
                "completed_tickers": [],
                "scan_rows_by_ticker": {},
                "last_run_id": None,
                "corrupt": True,
                "checkpoint_scope": self.checkpoint_scope,
            }

    def _save_checkpoint(self, payload: Dict[str, Any]) -> None:
        payload = dict(payload)
        payload["checkpoint_scope"] = self.checkpoint_scope
        payload["strategy_version"] = V40_STRATEGY_VERSION
        payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        # Atomic-ish replace for KeyboardInterrupt safety
        tmp = self.checkpoint_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.checkpoint_path)

    def clear_checkpoint(self) -> None:
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def resolve_universe(
        self,
        tickers: Optional[Sequence[str]] = None,
        *,
        max_tickers: Optional[int] = None,
        include_benchmarks: bool = False,
    ) -> List[str]:
        from app.services.ticker_integrity import resolve_canonical_ticker

        if tickers:
            raw = [str(t).strip().upper() for t in tickers if str(t).strip()]
            # Map legacy listing aliases → canonical; dedupe (no OHLCV rewrite)
            seen = set()
            out: List[str] = []
            for t in raw:
                canon = str(resolve_canonical_ticker(t).get("canonical") or t).upper()
                if canon in seen:
                    continue
                seen.add(canon)
                out.append(canon)
        else:
            stocks = universe_manager.get_all(include_inactive=False) or []
            out = []
            for s in stocks:
                t = str(s.get("ticker") or "").upper()
                if not t:
                    continue
                if s.get("is_benchmark") and not include_benchmarks:
                    continue
                out.append(t)
            # Prefer tickers with local price cache for offline-safe observation
            cached = []
            uncached = []
            for t in out:
                p = DATA_CACHE_DIR / "price_cache" / f"{t}.csv"
                (cached if p.exists() else uncached).append(t)
            out = cached + uncached
        if max_tickers is not None:
            out = out[: int(max_tickers)]
        return out

    def scan_universe(
        self,
        tickers: Sequence[str],
        *,
        resume: bool = True,
    ) -> Dict[str, Any]:
        """Fresh V4.0 scanner evaluation over tickers (local caches; optional Yahoo).

        Checkpoint persists completed ticker *results* (not just names) so --resume
        continues without restarting the universe after KeyboardInterrupt.
        """
        from app.services.ticker_integrity import resolve_canonical_ticker

        t0 = time.perf_counter()
        seen = set()
        universe: List[str] = []
        for t in tickers:
            raw = str(t).strip().upper()
            if not raw:
                continue
            canon = str(resolve_canonical_ticker(raw).get("canonical") or raw).upper()
            if canon in seen:
                continue
            seen.add(canon)
            universe.append(canon)
        n_total = len(universe)

        if resume:
            ckpt = self._load_checkpoint()
            # Reject checkpoint if strategy version or universe scope diverges
            if ckpt.get("strategy_version") not in (None, V40_STRATEGY_VERSION):
                _progress(
                    f"[SCAN] checkpoint strategy mismatch "
                    f"({ckpt.get('strategy_version')} != {V40_STRATEGY_VERSION}); starting fresh"
                )
                ckpt = {
                    "completed_tickers": [],
                    "scan_rows_by_ticker": {},
                    "last_run_id": None,
                }
            prev_univ = ckpt.get("universe_tickers")
            if prev_univ and list(prev_univ) != list(universe):
                # Allow resume when checkpoint is a prefix/subset of current universe
                prev_set = set(prev_univ)
                if not prev_set.issubset(set(universe)):
                    _progress("[SCAN] checkpoint universe mismatch; starting fresh")
                    ckpt = {
                        "completed_tickers": [],
                        "scan_rows_by_ticker": {},
                        "last_run_id": None,
                    }
        else:
            ckpt = {
                "completed_tickers": [],
                "scan_rows_by_ticker": {},
                "last_run_id": None,
            }
            self.clear_checkpoint()

        rows_by: Dict[str, Any] = dict(ckpt.get("scan_rows_by_ticker") or {})
        already = set(ckpt.get("completed_tickers") or []) if resume else set()
        # Keep only tickers still in this universe
        already = {t for t in already if t in set(universe) and t in rows_by}

        scan_rows: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        signal_dist: Dict[str, int] = {}
        completed: List[str] = []
        timings: List[Dict[str, Any]] = list(ckpt.get("timings") or [])

        # Restore prior rows in universe order
        for t in universe:
            if t in already and t in rows_by:
                row = rows_by[t]
                scan_rows.append(row)
                completed.append(t)
                sig = str(row.get("signal") or "UNKNOWN")
                signal_dist[sig] = signal_dist.get(sig, 0) + 1

        if already:
            _progress(
                f"[SCAN] resume scope={self.checkpoint_scope} "
                f"restored={len(already)}/{n_total} from {self.checkpoint_path}"
            )
        else:
            _progress(
                f"[SCAN] start scope={self.checkpoint_scope} universe={n_total} "
                f"refresh_prices={self.refresh_prices} optimize_cache={self.use_optimize_cache}"
            )

        for idx, t in enumerate(universe, start=1):
            if t in already:
                continue
            tick_t0 = time.perf_counter()
            t_price = 0.0
            t_eval = 0.0
            try:
                df = None
                refresh_status = "CACHE_ONLY"
                p0 = time.perf_counter()
                if self.refresh_prices:
                    df, stale = scanner_service.fetch_or_update_stock(t, force_full=False)
                    refresh_status = "STALE_PRESERVED" if stale else "REFRESHED_OR_CACHED"
                else:
                    df = scanner_service.get_price_df(t)
                    if df is None or getattr(df, "empty", True):
                        refresh_status = "NO_CACHE"
                t_price = time.perf_counter() - p0

                if df is None or getattr(df, "empty", True):
                    failures.append(
                        {
                            "ticker": t,
                            "error": "MISSING_PRICE_DATA",
                            "refresh_status": refresh_status,
                        }
                    )
                    row = {
                        "ticker": t,
                        "signal": "INSUFFICIENT DATA",
                        "validation_status": "MISSING_PRICE_DATA",
                        "signal_source": V40_SIGNAL_SOURCE,
                        "strategy_version": V40_STRATEGY_VERSION,
                    }
                    t_eval = 0.0
                else:
                    e0 = time.perf_counter()
                    row = scanner_service.evaluate_stock_signal(
                        t, df, use_optimize_cache=self.use_optimize_cache
                    )
                    t_eval = time.perf_counter() - e0
                    row["refresh_status"] = refresh_status

                sig = str(row.get("signal") or "UNKNOWN")
                signal_dist[sig] = signal_dist.get(sig, 0) + 1
                scan_rows.append(row)
                completed.append(t)
                rows_by[t] = row
                already.add(t)

                tick_total = time.perf_counter() - tick_t0
                timings.append(
                    {
                        "ticker": t,
                        "prices_s": round(t_price, 3),
                        "evaluate_s": round(t_eval, 3),
                        "total_s": round(tick_total, 3),
                    }
                )

                # Persist after each ticker so KeyboardInterrupt keeps prior work
                ckpt = {
                    "completed_tickers": [x for x in universe if x in already],
                    "scan_rows_by_ticker": rows_by,
                    "universe_tickers": list(universe),
                    "last_run_id": self.run_id,
                    "strategy_version": V40_STRATEGY_VERSION,
                    "checkpoint_scope": self.checkpoint_scope,
                    "timings": timings[-500:],
                }
                self._save_checkpoint(ckpt)

                done_n = len(completed)
                elapsed = time.perf_counter() - t0
                avg = (
                    sum(x["total_s"] for x in timings) / len(timings) if timings else tick_total
                )
                remaining = max(0, n_total - done_n)
                eta_s = avg * remaining
                _progress(
                    f"[SCAN] {done_n}/{n_total} {t} | prices={t_price:.1f}s | "
                    f"optimize+signal={t_eval:.1f}s | total={tick_total:.1f}s | "
                    f"elapsed={elapsed / 60:.1f}m | ETA~{eta_s / 60:.1f}m | sig={sig}"
                )
            except KeyboardInterrupt:
                _progress(
                    f"[SCAN] INTERRUPTED at {t} after {len(completed)}/{n_total} "
                    f"— checkpoint saved; re-run with --resume"
                )
                raise
            except Exception as exc:
                failures.append(
                    {
                        "ticker": t,
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc()[-500:],
                    }
                )
                signal_dist["SCAN_ERROR"] = signal_dist.get("SCAN_ERROR", 0) + 1
                _progress(f"[SCAN] {idx}/{n_total} {t} ERROR {type(exc).__name__}: {exc}")

        runtime_s = round(time.perf_counter() - t0, 3)
        avg_total = (
            round(sum(x["total_s"] for x in timings) / len(timings), 3) if timings else None
        )
        return {
            "tickers_requested": list(universe),
            "tickers_scanned": completed,
            "partial_universe": len(completed) < len(universe) or bool(failures),
            "resumed_from_checkpoint": bool(ckpt.get("completed_tickers")) and resume,
            "checkpoint_path": str(self.checkpoint_path),
            "checkpoint_scope": self.checkpoint_scope,
            "scan_rows": scan_rows,
            "signal_distribution": signal_dist,
            "data_quality_failures": failures,
            "scanner_runtime_seconds": runtime_s,
            "timing_summary": {
                "tickers_timed": len(timings),
                "avg_total_s": avg_total,
                "estimated_full_universe_minutes": (
                    round((avg_total or 0) * n_total / 60.0, 1) if avg_total else None
                ),
            },
        }

    def _signal_from_scan(self, row: Dict[str, Any]) -> Dict[str, Any]:
        t = str(row.get("ticker") or "").upper()
        stock = universe_manager.get_stock(t) or {}
        as_of = row.get("market_as_of_date") or row.get("as_of")
        return {
            "ticker": t,
            "name": row.get("name") or stock.get("name") or t,
            "company_name": row.get("name") or stock.get("name") or t,
            "sector": stock.get("sector") or row.get("sector") or "",
            "industry": stock.get("industry") or row.get("industry") or "",
            "signal": row.get("signal") or "AVOID",
            "signal_source": V40_SIGNAL_SOURCE,
            "strategy_version": row.get("strategy_version") or V40_STRATEGY_VERSION,
            "entry_rule": row.get("entry_rule") or "CROSS",
            "exit_rule": row.get("exit_rule") or "MA250_3CLOSE",
            "is_fresh_analysis": True,
            "provenance_mode": "LIVE_SCAN",
            "market_as_of_date": as_of,
            "as_of": as_of,
            "validation_status": row.get("validation_status") or "OK",
            "data_freshness": row.get("data_freshness") or "FRESH",
            "ma250": row.get("ma250"),
            "ma50": row.get("ma50"),
            "ma30": row.get("ma30"),
            "close": row.get("close"),
            "roc20_pct": row.get("roc20_pct"),
            "atr14": row.get("atr14"),
            "shariah_status": "NOT VERIFIED",
            "signal_id": f"obs_{t}_{as_of}",
        }

    def evaluate_decisions(
        self,
        scan: Dict[str, Any],
        *,
        now_utc: Optional[datetime] = None,
        account: Optional[AccountSnapshot] = None,
        quotes: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        now = now_utc or datetime.now(timezone.utc)
        quotes = quotes or {}
        rows = scan.get("scan_rows") or []

        policy_counts = {"ALLOWED": 0, "EXCLUDED": 0, "REVIEW REQUIRED": 0}
        results: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for row in rows:
            sig = self._signal_from_scan(row)
            t = sig["ticker"]
            policy = classify_user_policy(
                t,
                name=sig.get("name"),
                sector=sig.get("sector"),
                industry=sig.get("industry"),
            )
            st = policy.get("user_policy_status") or "REVIEW REQUIRED"
            policy_counts[st] = policy_counts.get(st, 0) + 1

            fresh_ok, fresh_code, *_ = evaluate_signal_session_freshness(
                sig.get("market_as_of_date"), now_utc=now
            )
            quote = quotes.get(t)
            quote_ok = bool(
                quote
                and float(quote.get("bid") or 0) > 0
                and float(quote.get("ask") or 0) > 0
                and float(quote.get("ask") or 0) >= float(quote.get("bid") or 0)
                and not quote.get("is_synthetic")
            )

            ctx = DecisionContext(
                account=account,
                broker_quote=quote if quote_ok else None,
                emergency_stop=True,
                execution_enabled=False,
                trading_execution_enabled=False,
                max_order_notional_usd=DEFAULT_MAX_ORDER_NOTIONAL_USD,
                max_daily_orders=DEFAULT_MAX_DAILY_ORDERS,
                max_daily_notional_usd=DEFAULT_MAX_DAILY_NOTIONAL_USD,
                max_open_orders=DEFAULT_MAX_OPEN_ORDERS,
                now_utc=now,
                eligibility_mode=MODE_USER_POLICY,
                allow_off_session_sizing=True,
            )
            entry = self.pipeline.evaluate_signal(
                sig, ctx, run_id=self.run_id, persist_journal=True
            )
            inv = (entry.get("investment_decision") or {}).get("classification")
            prop = entry.get("simulated_proposal")
            if not fresh_ok:
                prop = None

            record = {
                "ticker": t,
                "v40_signal": sig.get("signal"),
                "entry_rule": sig.get("entry_rule"),
                "strategy_version": sig.get("strategy_version"),
                "market_as_of_date": sig.get("market_as_of_date"),
                "signal_price": sig.get("close"),
                "freshness": {"is_fresh": fresh_ok, "reason_code": fresh_code},
                "user_policy_status": st,
                "policy_reason_codes": policy.get("reason_codes"),
                "quote_available": quote is not None,
                "quote_valid": quote_ok,
                "quote": {
                    "bid": (quote or {}).get("bid"),
                    "ask": (quote or {}).get("ask"),
                    "source": (quote or {}).get("source"),
                }
                if quote
                else None,
                "investment_decision": entry.get("investment_decision"),
                "execution_readiness": entry.get("execution_readiness"),
                "simulated_proposal": prop if prop and prop.get("status") == "SIMULATED" else None,
                "sizing_block": entry.get("sizing_block"),
                "submission_attempted": False,
            }
            results.append(record)
            if not (prop and prop.get("status") == "SIMULATED"):
                rejected.append(
                    {
                        "ticker": t,
                        "v40_signal": sig.get("signal"),
                        "investment": inv,
                        "policy": st,
                        "fresh": fresh_ok,
                        "reasons": (
                            (entry.get("sizing_block") or {}).get("reason_codes")
                            or (entry.get("investment_decision") or {}).get("reason_codes")
                            or (entry.get("execution_readiness") or {}).get("reason_codes")
                            or []
                        ),
                        "sizing_block": entry.get("sizing_block"),
                    }
                )

        buy_candidates = [
            r
            for r in results
            if (r.get("v40_signal") or "").upper() in ("BUY CANDIDATE", "BUY")
        ]
        simulated = [
            r for r in results if (r.get("simulated_proposal") or {}).get("status") == "SIMULATED"
        ]
        ranked = rank_candidates(
            simulated,
            buy_ready_details=[{"ticker": r["ticker"]} for r in buy_candidates],
        )
        performance = attach_performance_to_proposals(results)

        # Portfolio exposure from account snapshot (cash-only observation)
        exposure = None
        if account is not None:
            invested = max(0.0, float(account.equity) - float(account.cash))
            exposure = {
                "cash": round(float(account.cash), 2),
                "equity": round(float(account.equity), 2),
                "invested": round(invested, 2),
                "exposure_pct": round(
                    (invested / float(account.equity) * 100.0) if account.equity else 0.0, 2
                ),
                "open_orders": len(account.open_orders or []),
                "positions": len(account.positions or []),
            }

        return {
            "policy_eligibility_breakdown": policy_counts,
            "results": results,
            "buy_candidates": [
                {
                    "ticker": r["ticker"],
                    "entry_rule": r.get("entry_rule"),
                    "signal_price": r.get("signal_price"),
                    "policy": r.get("user_policy_status"),
                    "investment": (r.get("investment_decision") or {}).get("classification"),
                }
                for r in buy_candidates
            ],
            "simulated_proposals": ranked,
            "rejected_or_deferred": rejected,
            "performance": performance,
            "portfolio_exposure": exposure,
            "ranking_method": describe_ranking_methodology(),
        }

    def run_observation_session(
        self,
        *,
        mode: str = "post_close",
        tickers: Optional[Sequence[str]] = None,
        max_tickers: Optional[int] = None,
        resume: bool = True,
        force_run: bool = True,
        slot_id: Optional[str] = None,
        now_utc: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Full observation path. force_run=True bypasses schedule window (manual/validation)."""
        now = now_utc or datetime.now(timezone.utc)
        schedule_cfg = ensure_schedule_config()
        gate = None
        if slot_id:
            gate = should_run_slot(slot_id, now_utc=now, config=schedule_cfg)
            if not force_run and not gate.get("should_run"):
                return {
                    "run_id": self.run_id,
                    "skipped": True,
                    "skip_reason": gate,
                    "broker_orders": False,
                    "submissions_attempted": 0,
                }

        today_ny = now.astimezone(
            __import__("zoneinfo").ZoneInfo("America/New_York")
        ).date()
        trading, holiday_reason = is_observation_trading_day(today_ny)

        universe = self.resolve_universe(tickers, max_tickers=max_tickers)
        scan = self.scan_universe(universe, resume=resume)

        client, client_status = try_load_readonly_client()
        account = None
        quotes: Dict[str, Dict[str, Any]] = {}
        alpaca_meta: Dict[str, Any] = {"connected": False, "status": client_status}
        if client is not None:
            try:
                alpaca_meta = client.validate_readonly()
                account = client.get_account_snapshot()
                buyish = [
                    str(r.get("ticker")).upper()
                    for r in (scan.get("scan_rows") or [])
                    if str(r.get("signal") or "").upper() in ("BUY CANDIDATE", "BUY", "WATCH")
                ]
                # Cap quote batch for observation
                quote_syms = buyish[:40] or universe[:20]
                quotes = client.get_quotes(quote_syms) if quote_syms else {}
            except Exception as exc:
                alpaca_meta["error"] = f"{type(exc).__name__}: {exc}"

        decisions = self.evaluate_decisions(
            scan, now_utc=now, account=account, quotes=quotes
        )

        # Clear completed_tickers for this universe after successful full pass
        ckpt = self._load_checkpoint()
        sessions = list(ckpt.get("sessions") or [])
        sessions.append(
            {
                "run_id": self.run_id,
                "mode": mode,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "tickers": len(universe),
                "buy_candidates": len(decisions.get("buy_candidates") or []),
                "simulated": len(decisions.get("simulated_proposals") or []),
            }
        )
        if not scan.get("partial_universe"):
            ckpt["completed_tickers"] = []
        ckpt["sessions"] = sessions[-50:]
        ckpt["last_run_id"] = self.run_id
        self._save_checkpoint(ckpt)

        payload = {
            "stage": "D2.4K",
            "run_id": self.run_id,
            "mode": mode,
            "started_at_utc": self.started.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "force_run": force_run,
            "schedule_gate": gate,
            "schedule_config_path": str(
                DATA_CACHE_DIR / "observation" / "schedule_config.json"
            ),
            "trading_day_et": today_ny.isoformat(),
            "is_trading_day": trading,
            "holiday_or_weekend_reason": None if trading else holiday_reason,
            "expected_last_completed_session": last_completed_us_equity_session(now).isoformat(),
            "production_db_writes": False,
            "broker_orders": False,
            "submissions_attempted": 0,
            "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
            "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
            "trading_execution_enabled": bool(TRADING_EXECUTION_ENABLED),
            "ibkr_emergency_stop": bool(IBKR_EMERGENCY_STOP),
            "risk_limits": {
                "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
                "max_daily_orders": DEFAULT_MAX_DAILY_ORDERS,
                "max_daily_notional_usd": DEFAULT_MAX_DAILY_NOTIONAL_USD,
                "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
                "fractional_shares": False,
            },
            "alpaca_readonly": {
                "connected": alpaca_meta.get("connected"),
                "status": client_status,
                "order_submission_blocked": alpaca_meta.get("order_submission_blocked"),
                "account_cash": (alpaca_meta.get("account") or {}).get("cash"),
                "error": alpaca_meta.get("error"),
            },
            "scanned_universe_size": len(universe),
            "signal_distribution": scan.get("signal_distribution"),
            "scanner_runtime_seconds": scan.get("scanner_runtime_seconds"),
            "data_quality_failures": scan.get("data_quality_failures"),
            "partial_universe": scan.get("partial_universe"),
            "resumed_from_checkpoint": scan.get("resumed_from_checkpoint"),
            "policy_eligibility_breakdown": decisions.get("policy_eligibility_breakdown"),
            "buy_candidates": decisions.get("buy_candidates"),
            "simulated_proposals": [
                {
                    "pilot_rank": r.get("pilot_rank"),
                    "ticker": r.get("ticker"),
                    "entry_rule": r.get("entry_rule"),
                    "ask": (r.get("quote") or {}).get("ask"),
                    "proposed_limit": (r.get("simulated_proposal") or {}).get(
                        "proposed_limit_price"
                    ),
                    "proposed_qty": (r.get("simulated_proposal") or {}).get(
                        "proposed_quantity"
                    ),
                    "proposed_notional": (r.get("simulated_proposal") or {}).get(
                        "proposed_notional"
                    ),
                    "idempotency_key": (r.get("simulated_proposal") or {}).get(
                        "idempotency_key"
                    ),
                }
                for r in (decisions.get("simulated_proposals") or [])
            ],
            "rejected_or_deferred_count": len(decisions.get("rejected_or_deferred") or []),
            "rejected_or_deferred_sample": (decisions.get("rejected_or_deferred") or [])[:25],
            "portfolio_exposure": decisions.get("portfolio_exposure"),
            "ranking_method": decisions.get("ranking_method"),
            "performance": decisions.get("performance"),
            "upcoming_schedule_plan": plan_upcoming_slots(from_utc=now, trading_days=3),
            "journal_summary": self.journal.summary(self.run_id),
            "stop_for_review": True,
        }

        results_path = self.evidence_dir / "d2_4k_results.json"
        # Keep scan rows out of huge payload but persist separately
        (self.evidence_dir / "scan_rows.json").write_text(
            json.dumps(scan.get("scan_rows") or [], indent=2, default=str),
            encoding="utf-8",
        )
        (self.evidence_dir / "decision_results.json").write_text(
            json.dumps(decisions.get("results") or [], indent=2, default=str),
            encoding="utf-8",
        )
        results_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        payload["_paths"] = {
            "results": str(results_path),
            "scan_rows": str(self.evidence_dir / "scan_rows.json"),
            "decisions": str(self.evidence_dir / "decision_results.json"),
            "evidence_dir": str(self.evidence_dir),
        }
        return payload
