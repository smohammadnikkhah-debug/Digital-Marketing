"""Multi-session observation soak orchestrator (Stage D2.4L).

Coordinates:
  - post_close full-universe refreshed scans
  - persistence of exact signal bundles
  - next_session validation against prior signals + Alpaca RO quotes
  - soak ledger (distinct observed sessions)

Does NOT activate unattended schedules.
Does NOT submit broker orders.
Does NOT claim soak complete until three distinct real sessions are recorded.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.config import DATA_CACHE_DIR, V40_SIGNAL_SOURCE, V40_STRATEGY_VERSION
from app.services.alpaca_readonly import try_load_readonly_client
from app.services.observation_freshness import assess_scan_freshness
from app.services.observation_performance import attach_performance_to_proposals
from app.services.observation_runner import ObservationRunner, OBSERVATION_ROOT
from app.services.observation_safety import assert_observation_safety, require_observation_safety
from app.services.observation_schedule import (
    NY_TZ,
    ensure_schedule_config,
    is_observation_trading_day,
    pair_post_close_to_next_session,
    plan_soak_pairs,
    should_run_slot,
)
from app.services.order_execution_service import (
    DEFAULT_MAX_DAILY_NOTIONAL_USD,
    DEFAULT_MAX_DAILY_ORDERS,
    DEFAULT_MAX_OPEN_ORDERS,
    DEFAULT_MAX_ORDER_NOTIONAL_USD,
)
from app.services.us_session_freshness import last_completed_us_equity_session

SOAK_TARGET_PAIRS = 3
# Back-compat alias used by older prep scripts/tests
SOAK_TARGET_SESSIONS = SOAK_TARGET_PAIRS
LEDGER_PATH = OBSERVATION_ROOT / "soak_ledger.json"
SESSIONS_DIR = OBSERVATION_ROOT / "sessions"
DEFAULT_SLOT_WINDOW_MINUTES = 45
POST_CLOSE_SLOT_ID = "post_close_research"
NEXT_SESSION_SLOT_ID = "next_session_validate"


def _ny_now(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(NY_TZ)


def build_timing_audit(
    *,
    mode: str,
    now_utc: datetime,
    slot_id: str,
    expected_session_day: Optional[str] = None,
    window_minutes: int = DEFAULT_SLOT_WINDOW_MINUTES,
) -> Dict[str, Any]:
    """Fail-closed session-day + slot-window gate (injectable clock via now_utc)."""
    now_ny = _ny_now(now_utc)
    actual_day = now_ny.date().isoformat()
    slot_gate = should_run_slot(
        slot_id, now_utc=now_utc, window_minutes=window_minutes
    )
    day_ok = True
    reason = "IN_WINDOW" if slot_gate.get("should_run") else "OUTSIDE_WINDOW"
    if expected_session_day is not None:
        day_ok = actual_day == str(expected_session_day)
        if not day_ok:
            reason = "WRONG_SESSION_DAY"
        elif not slot_gate.get("should_run"):
            reason = str(slot_gate.get("reason_code") or "OUTSIDE_WINDOW")
    elif not slot_gate.get("should_run"):
        reason = str(slot_gate.get("reason_code") or "OUTSIDE_WINDOW")

    timing_ok = bool(day_ok and slot_gate.get("should_run"))
    return {
        "timing_ok": timing_ok,
        "eligibility_reason_code": "OK" if timing_ok else reason,
        "expected_session_day": expected_session_day,
        "actual_ny_date": actual_day,
        "actual_ny_datetime": now_ny.isoformat(),
        "slot_id": slot_id,
        "slot_name": slot_id,
        "configured_slot_window_minutes": window_minutes,
        "slot_check": slot_gate,
        "slot_check_passed": bool(slot_gate.get("should_run")),
        "day_match": day_ok,
        "mode": mode,
    }


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_soak_ledger() -> Dict[str, Any]:
    OBSERVATION_ROOT.mkdir(parents=True, exist_ok=True)
    data = _load_json(LEDGER_PATH)
    if not data:
        data = {
            "version": "D2.4L",
            "target_completed_pairs": SOAK_TARGET_PAIRS,
            "target_distinct_sessions": SOAK_TARGET_PAIRS,  # legacy field
            "sessions": [],
            "soak_complete": False,
            "unattended_activated": False,
        }
    return data


def save_soak_ledger(ledger: Dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str), encoding="utf-8")


def _pair_id_from_pair(pair: Optional[Dict[str, Any]], post_close_day: Optional[str] = None) -> Optional[str]:
    if pair and pair.get("post_close_day") and pair.get("next_session_day"):
        return f"{pair['post_close_day']}->{pair['next_session_day']}"
    if post_close_day:
        return str(post_close_day)
    return None


def completed_pair_ids(sessions: Sequence[Dict[str, Any]]) -> List[str]:
    """A pair counts only when both eligible legs exist for the same pair_id."""
    by_pair: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for s in sessions or []:
        pid = s.get("pair_id")
        mode = s.get("mode")
        if not pid or mode not in ("post_close", "next_session"):
            continue
        by_pair.setdefault(str(pid), {})[mode] = s

    done: List[str] = []
    for pid, legs in by_pair.items():
        pc = legs.get("post_close") or {}
        ns = legs.get("next_session") or {}
        if not pc or not ns:
            continue
        if not pc.get("eligible") or not ns.get("eligible"):
            continue
        if pc.get("freshness_status") != "FRESH":
            continue
        done.append(pid)
    return sorted(set(done))


def soak_status(ledger: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    led = ledger or load_soak_ledger()
    sessions = led.get("sessions") or []
    pairs = completed_pair_ids(sessions)
    complete = len(pairs) >= SOAK_TARGET_PAIRS
    pending_post = sorted(
        {
            str(s.get("pair_id"))
            for s in sessions
            if s.get("mode") == "post_close"
            and s.get("eligible")
            and s.get("freshness_status") == "FRESH"
            and str(s.get("pair_id")) not in pairs
        }
    )
    return {
        "target_completed_pairs": SOAK_TARGET_PAIRS,
        "target_distinct_sessions": SOAK_TARGET_PAIRS,  # legacy alias (= pairs)
        "observed_completed_pairs": len(pairs),
        "observed_distinct_sessions": len(pairs),  # legacy alias
        "completed_pair_ids": pairs,
        "pending_post_close_pair_ids": pending_post,
        "session_records": len(sessions),
        "soak_complete": complete,
        "claim_allowed": complete,
        "unattended_activated": bool(led.get("unattended_activated")),
        "recommendation": (
            "GO_FOR_CONTROLLED_PAPER_PILOT_REVIEW"
            if complete
            else "NO_GO_SOAK_INCOMPLETE"
        ),
        "note": (
            "Three distinct real post-close→next-session pairs observed."
            if complete
            else (
                "Do not claim three-session soak complete until three real "
                "session pairs have succeeded (post-close FRESH + paired next-session)."
            )
        ),
    }


def _session_key(mode: str, trading_day: str) -> str:
    return f"{trading_day}|{mode}"


def _summarize_buy_by_policy(buy_candidates: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {"ALLOWED": [], "EXCLUDED": [], "REVIEW REQUIRED": []}
    for c in buy_candidates or []:
        pol = str(c.get("policy") or "REVIEW REQUIRED")
        out.setdefault(pol, [])
        out[pol].append(str(c.get("ticker")))
    return out


class MultiSessionSoak:
    """Prepare and execute observation soak sessions (local evidence)."""

    def __init__(self, evidence_root: Optional[Path] = None):
        self.evidence_root = Path(evidence_root) if evidence_root else (
            DATA_CACHE_DIR / "evidence"
        )
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        ensure_schedule_config()

    def preflight(self, *, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
        now = now_utc or datetime.now(timezone.utc)
        safety = assert_observation_safety(phase="preflight")
        schedule = ensure_schedule_config()
        from zoneinfo import ZoneInfo

        ny_day = now.astimezone(ZoneInfo("America/New_York")).date()
        pairs = plan_soak_pairs(from_day=ny_day, pairs=3)
        today_pair = pair_post_close_to_next_session(ny_day)
        status = soak_status()
        universe_probe = ObservationRunner(refresh_prices=False)
        tickers = universe_probe.resolve_universe(include_benchmarks=True)
        return {
            "preflight_at_utc": now.isoformat(),
            "safety": safety,
            "schedule_activation": schedule.get("activation"),
            "today_et": ny_day.isoformat(),
            "today_pair": today_pair,
            "planned_soak_pairs": pairs,
            "soak_status": status,
            "full_universe_count": len(tickers),
            "unattended_schedules_activated": False,
            "passed": bool(safety.get("passed")),
        }

    def _persist_session_bundle(
        self,
        *,
        mode: str,
        trading_day: str,
        run_id: str,
        evidence_dir: Path,
        scan: Dict[str, Any],
        decisions: Dict[str, Any],
        freshness: Dict[str, Any],
        safety_pre: Dict[str, Any],
        safety_post: Dict[str, Any],
        pair: Optional[Dict[str, Any]] = None,
        prior_session_ref: Optional[str] = None,
    ) -> Path:
        bundle = {
            "stage": "D2.4L",
            "mode": mode,
            "trading_day": trading_day,
            "session_key": _session_key(mode, trading_day),
            "run_id": run_id,
            "evidence_dir": str(evidence_dir),
            "strategy_version": V40_STRATEGY_VERSION,
            "signal_source": V40_SIGNAL_SOURCE,
            "pair": pair,
            "prior_session_ref": prior_session_ref,
            "freshness": freshness,
            "safety_pre": safety_pre,
            "safety_post": safety_post,
            "scan_summary": {
                "universe_count": len(scan.get("tickers_requested") or []),
                "successfully_scanned": len(scan.get("tickers_scanned") or []),
                "signal_distribution": scan.get("signal_distribution"),
                "scanner_runtime_seconds": scan.get("scanner_runtime_seconds"),
                "data_quality_failures": len(scan.get("data_quality_failures") or []),
                "partial_universe": scan.get("partial_universe"),
            },
            "policy_eligibility_breakdown": decisions.get("policy_eligibility_breakdown"),
            "buy_candidates": decisions.get("buy_candidates"),
            "buy_candidates_by_policy": _summarize_buy_by_policy(
                decisions.get("buy_candidates") or []
            ),
            "simulated_proposals": [
                {
                    "ticker": r.get("ticker"),
                    "pilot_rank": r.get("pilot_rank"),
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
            "portfolio_exposure": decisions.get("portfolio_exposure"),
            "performance": decisions.get("performance"),
            # Exact prior signals for next_session reload
            "signals": [
                ObservationRunner(refresh_prices=False)._signal_from_scan(r)
                for r in (scan.get("scan_rows") or [])
            ],
            "scan_rows_path": str(evidence_dir / "scan_rows.json"),
            "broker_orders": False,
            "submissions_attempted": 0,
        }
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = SESSIONS_DIR / f"{run_id}_{mode}.json"
        path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")
        (evidence_dir / "session_bundle.json").write_text(
            json.dumps(bundle, indent=2, default=str), encoding="utf-8"
        )
        return path

    def _record_ledger_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append/replace a soak leg. Dedupes by pair_id+mode (no double-count).

        Protection: an ineligible entry never overwrites an existing eligible leg.
        A later eligible (or ineligible) attempt may replace a prior ineligible leg.
        Historical evidence dirs/run_ids on the discarded ineligible row are not deleted.
        """
        led = load_soak_ledger()
        sessions = list(led.get("sessions") or [])
        pair_id = entry.get("pair_id")
        mode = entry.get("mode")
        replaced = False
        preserved_eligible = False
        prior_run_id = None

        if pair_id and mode:
            existing = next(
                (
                    s
                    for s in sessions
                    if s.get("pair_id") == pair_id and s.get("mode") == mode
                ),
                None,
            )
            if existing and existing.get("eligible") and not entry.get("eligible"):
                # Keep eligible leg; attach audit note only via status return
                preserved_eligible = True
                prior_run_id = existing.get("run_id")
                status = soak_status(led)
                status["ledger_write"] = "PRESERVED_ELIGIBLE_LEG"
                status["rejected_overwrite_run_id"] = entry.get("run_id")
                status["preserved_run_id"] = prior_run_id
                return status
            sessions = [
                s
                for s in sessions
                if not (s.get("pair_id") == pair_id and s.get("mode") == mode)
            ]
            if existing:
                replaced = True
                prior_run_id = existing.get("run_id")
        else:
            sessions = [
                s
                for s in sessions
                if not (
                    s.get("session_key") == entry.get("session_key")
                    and s.get("run_id") == entry.get("run_id")
                )
            ]

        entry = dict(entry)
        entry["replaced_prior_run_id"] = prior_run_id if replaced else None
        sessions.append(entry)
        led["sessions"] = sessions
        status = soak_status(led)
        led["soak_complete"] = status["soak_complete"]
        led["completed_pair_ids"] = status.get("completed_pair_ids")
        led["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        save_soak_ledger(led)
        status["ledger_write"] = "REPLACED" if replaced else "APPENDED"
        status["preserved_eligible"] = preserved_eligible
        return status

    def run_post_close_session(
        self,
        *,
        now_utc: Optional[datetime] = None,
        tickers: Optional[Sequence[str]] = None,
        refresh_prices: bool = True,
        force_run: bool = False,
        resume: bool = True,
        count_toward_soak: bool = True,
        window_minutes: int = DEFAULT_SLOT_WINDOW_MINUTES,
    ) -> Dict[str, Any]:
        """Full-universe (or provided) post-close observation with refresh.

        Timing: post_close_research slot must be IN_WINDOW for soak credit.
        force_run=True allows a diagnostic scan outside the window but marks
        results INELIGIBLE and never counts toward soak completion.
        """
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        safety_pre = require_observation_safety(phase="pre_post_close")

        ny_now = _ny_now(now)
        ny_day = ny_now.date()
        trading, reason = is_observation_trading_day(ny_day)
        pair = pair_post_close_to_next_session(ny_day)
        timing = build_timing_audit(
            mode="post_close",
            now_utc=now,
            slot_id=POST_CLOSE_SLOT_ID,
            expected_session_day=ny_day.isoformat(),
            window_minutes=window_minutes,
        )
        # Post-close expected day is the NY trading day being observed
        if not trading and timing["eligibility_reason_code"] == "OK":
            timing["timing_ok"] = False
            timing["eligibility_reason_code"] = "MARKET_CLOSED"

        run_id = now.strftime("d2_4l_%Y%m%dT%H%M%SZ")
        evidence_dir = self.evidence_root / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        diagnostic = bool(force_run) and not timing.get("timing_ok")
        if not timing.get("timing_ok") and not force_run:
            return self._finalize_gated_rejection(
                mode="post_close",
                run_id=run_id,
                evidence_dir=evidence_dir,
                trading_day=ny_day.isoformat(),
                pair=pair,
                timing=timing,
                safety_pre=safety_pre,
                count_toward_soak=count_toward_soak,
                force_run=False,
                diagnostic=False,
            )

        scope = f"post_close_{ny_day.isoformat()}_{V40_STRATEGY_VERSION[:40]}"
        runner = ObservationRunner(
            refresh_prices=refresh_prices,
            checkpoint_scope=scope,
            use_optimize_cache=True,
        )
        runner.run_id = run_id
        runner.evidence_dir = evidence_dir
        runner.journal.journal_dir = evidence_dir / "journal"
        runner.journal.journal_dir.mkdir(parents=True, exist_ok=True)

        universe = runner.resolve_universe(tickers, include_benchmarks=True)
        scan = runner.scan_universe(universe, resume=resume)
        (runner.evidence_dir / "scan_rows.json").write_text(
            json.dumps(scan.get("scan_rows") or [], indent=2, default=str),
            encoding="utf-8",
        )

        freshness = assess_scan_freshness(
            scan.get("scan_rows") or [],
            now_utc=now,
            expected_session=last_completed_us_equity_session(now),
        )

        client, client_status = try_load_readonly_client()
        account = None
        quotes: Dict[str, Dict[str, Any]] = {}
        alpaca_meta: Dict[str, Any] = {"connected": False, "status": client_status}
        if client is not None and freshness.get("status") != "DATA_PENDING":
            try:
                alpaca_meta = client.validate_readonly()
                account = client.get_account_snapshot()
                buyish = [
                    str(r.get("ticker")).upper()
                    for r in (scan.get("scan_rows") or [])
                    if str(r.get("signal") or "").upper()
                    in ("BUY CANDIDATE", "BUY", "WATCH")
                ]
                quotes = client.get_quotes(buyish[:80]) if buyish else {}
            except Exception as exc:
                alpaca_meta["error"] = f"{type(exc).__name__}: {exc}"

        if freshness.get("status") == "DATA_PENDING":
            decisions = {
                "policy_eligibility_breakdown": {},
                "results": [],
                "buy_candidates": [],
                "simulated_proposals": [],
                "rejected_or_deferred": [
                    {
                        "reason": "DATA_PENDING",
                        "detail": freshness.get("reason_code"),
                        "note": freshness.get("note"),
                    }
                ],
                "performance": [],
                "portfolio_exposure": None,
                "ranking_method": None,
            }
        else:
            decisions = runner.evaluate_decisions(
                scan, now_utc=now, account=account, quotes=quotes
            )

        safety_post = require_observation_safety(
            phase="post_post_close",
            submissions_attempted=runner.submissions_attempted,
        )

        bundle_path = self._persist_session_bundle(
            mode="post_close",
            trading_day=ny_day.isoformat(),
            run_id=runner.run_id,
            evidence_dir=runner.evidence_dir,
            scan=scan,
            decisions=decisions,
            freshness=freshness,
            safety_pre=safety_pre,
            safety_post=safety_post,
            pair=pair,
        )

        pair_id = _pair_id_from_pair(pair, ny_day.isoformat())
        scanned_n = len(scan.get("tickers_scanned") or [])
        universe_n = len(universe)
        timing_ok = bool(timing.get("timing_ok"))
        eligible = bool(
            count_toward_soak
            and (not diagnostic)
            and timing_ok
            and trading
            and freshness.get("status") == "FRESH"
            and safety_pre.get("passed")
            and safety_post.get("passed")
            and scanned_n >= universe_n
            and universe_n > 0
            and tickers is None  # full universe only counts toward soak
            and (runner.evidence_dir / "session_bundle.json").exists()
        )
        reason_code = (
            "OK"
            if eligible
            else (
                "DIAGNOSTIC_FORCE_RUN_INELIGIBLE"
                if diagnostic
                else (
                    timing.get("eligibility_reason_code")
                    if not timing_ok
                    else "SOAK_INELIGIBLE"
                )
            )
        )
        status = soak_status()
        ledger_entry = {
            "session_key": _session_key("post_close", ny_day.isoformat()),
            "pair_id": pair_id,
            "mode": "post_close",
            "trading_day": ny_day.isoformat(),
            "run_id": runner.run_id,
            "evidence_dir": str(runner.evidence_dir),
            "bundle_path": str(bundle_path),
            "freshness_status": freshness.get("status"),
            "is_trading_day": trading,
            "holiday_reason": None if trading else reason,
            "universe_count": universe_n,
            "successfully_scanned": scanned_n,
            "simulated_proposals": len(decisions.get("simulated_proposals") or []),
            "eligible": eligible,
            "counts_toward_pair": False,  # pair completes only after next_session
            "eligibility_reason_code": reason_code,
            "timing": timing,
            "diagnostic_force_run": diagnostic,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "real_session": True,
        }
        if count_toward_soak or diagnostic:
            status = self._record_ledger_entry(ledger_entry)

        payload = {
            "stage": "D2.4L",
            "mode": "post_close",
            "run_id": runner.run_id,
            "trading_day_et": ny_day.isoformat(),
            "is_trading_day": trading,
            "pair": pair,
            "freshness": freshness,
            "safety_pre": safety_pre,
            "safety_post": safety_post,
            "timing": timing,
            "eligibility_reason_code": reason_code,
            "eligible": eligible,
            "counts_toward_pair": False,
            "diagnostic_force_run": diagnostic,
            "universe_count": len(universe),
            "successfully_scanned": len(scan.get("tickers_scanned") or []),
            "signal_distribution": scan.get("signal_distribution"),
            "scanner_runtime_seconds": scan.get("scanner_runtime_seconds"),
            "data_quality_failures": scan.get("data_quality_failures"),
            "policy_eligibility_breakdown": decisions.get("policy_eligibility_breakdown"),
            "buy_candidates": decisions.get("buy_candidates"),
            "buy_candidates_by_policy": _summarize_buy_by_policy(
                decisions.get("buy_candidates") or []
            ),
            "simulated_proposals": [
                {
                    "ticker": r.get("ticker"),
                    "pilot_rank": r.get("pilot_rank"),
                    "proposed_limit": (r.get("simulated_proposal") or {}).get(
                        "proposed_limit_price"
                    ),
                    "proposed_qty": (r.get("simulated_proposal") or {}).get(
                        "proposed_quantity"
                    ),
                    "proposed_notional": (r.get("simulated_proposal") or {}).get(
                        "proposed_notional"
                    ),
                }
                for r in (decisions.get("simulated_proposals") or [])
            ],
            "rejected_or_deferred_count": len(decisions.get("rejected_or_deferred") or []),
            "portfolio_exposure": decisions.get("portfolio_exposure"),
            "performance": decisions.get("performance"),
            "alpaca_readonly": {
                "connected": alpaca_meta.get("connected"),
                "status": client_status,
                "error": alpaca_meta.get("error"),
            },
            "bundle_path": str(bundle_path),
            "evidence_dir": str(runner.evidence_dir),
            "soak_status": status,
            "broker_orders": False,
            "submissions_attempted": 0,
            "risk_limits": {
                "max_order_notional_usd": DEFAULT_MAX_ORDER_NOTIONAL_USD,
                "max_daily_orders": DEFAULT_MAX_DAILY_ORDERS,
                "max_daily_notional_usd": DEFAULT_MAX_DAILY_NOTIONAL_USD,
                "max_open_orders": DEFAULT_MAX_OPEN_ORDERS,
            },
        }
        (runner.evidence_dir / "d2_4l_post_close.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload

    def _finalize_gated_rejection(
        self,
        *,
        mode: str,
        run_id: str,
        evidence_dir: Path,
        trading_day: str,
        pair: Optional[Dict[str, Any]],
        timing: Dict[str, Any],
        safety_pre: Dict[str, Any],
        count_toward_soak: bool,
        force_run: bool,
        diagnostic: bool,
        prior_bundle_path: Optional[Path] = None,
        prior: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Stop before market-data / proposals; record audit + ineligible ledger leg."""
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "journal").mkdir(parents=True, exist_ok=True)
        reason = str(timing.get("eligibility_reason_code") or "OUTSIDE_WINDOW")
        empty_scan = {
            "tickers_requested": [],
            "tickers_scanned": [],
            "scan_rows": [],
            "signal_distribution": {},
            "data_quality_failures": [],
            "scanner_runtime_seconds": 0.0,
            "partial_universe": False,
            "resumed_from_checkpoint": False,
        }
        empty_decisions = {
            "policy_eligibility_breakdown": {},
            "results": [],
            "buy_candidates": [],
            "simulated_proposals": [],
            "rejected_or_deferred": [
                {
                    "reason": reason,
                    "detail": "Timing gate failed before market-data / proposals",
                    "timing": timing,
                }
            ],
            "performance": [],
            "portfolio_exposure": None,
            "ranking_method": None,
        }
        freshness = {
            "status": "GATED",
            "reason_code": reason,
            "fabricated_freshness": False,
        }
        safety_post = {
            "passed": True,
            "phase": f"gated_{mode}",
            "note": "No broker interaction; gated before quotes/proposals",
        }
        bundle_path = self._persist_session_bundle(
            mode=mode,
            trading_day=trading_day,
            run_id=run_id,
            evidence_dir=evidence_dir,
            scan=empty_scan,
            decisions=empty_decisions,
            freshness=freshness,
            safety_pre=safety_pre,
            safety_post=safety_post,
            pair=pair,
            prior_session_ref=str(prior_bundle_path) if prior_bundle_path else None,
        )
        pair_id = _pair_id_from_pair(pair, (prior or {}).get("trading_day") or trading_day)
        prior_fresh = ((prior or {}).get("freshness") or {}).get("status")
        ledger_entry = {
            "session_key": _session_key(mode, trading_day),
            "pair_id": pair_id,
            "mode": mode,
            "trading_day": trading_day,
            "run_id": run_id,
            "evidence_dir": str(evidence_dir),
            "bundle_path": str(bundle_path),
            "prior_bundle": str(prior_bundle_path) if prior_bundle_path else None,
            "expected_next_session_day": timing.get("expected_session_day"),
            "eligible": False,
            "counts_toward_pair": False,
            "eligibility_reason_code": reason,
            "timing": timing,
            "diagnostic_force_run": diagnostic,
            "prior_freshness_status": prior_fresh,
            "freshness_status": freshness.get("status"),
            "universe_count": 0,
            "successfully_scanned": 0,
            "simulated_proposals": 0,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "real_session": True,
            "gated_before_proposals": True,
        }
        # Always record gated attempts so operators see the rejection reason
        status = self._record_ledger_entry(ledger_entry)

        payload = {
            "stage": "D2.4L",
            "mode": mode,
            "run_id": run_id,
            "trading_day_et": trading_day,
            "prior_bundle_path": str(prior_bundle_path) if prior_bundle_path else None,
            "prior_trading_day": (prior or {}).get("trading_day"),
            "expected_next_session_day": timing.get("expected_session_day"),
            "pair": pair,
            "loaded_exact_prior_signals": False,
            "gated_before_proposals": True,
            "timing": timing,
            "eligibility_reason_code": reason,
            "eligible": False,
            "counts_toward_pair": False,
            "diagnostic_force_run": bool(force_run and diagnostic),
            "freshness": freshness,
            "safety_pre": safety_pre,
            "safety_post": safety_post,
            "universe_count": 0,
            "successfully_scanned": 0,
            "signal_distribution": {},
            "policy_eligibility_breakdown": {},
            "buy_candidates": [],
            "simulated_proposals": [],
            "rejected_or_deferred_count": 1,
            "portfolio_exposure": None,
            "performance": [],
            "alpaca_readonly": {"connected": False, "quotes_retrieved": 0},
            "bundle_path": str(bundle_path),
            "evidence_dir": str(evidence_dir),
            "soak_status": status,
            "broker_orders": False,
            "submissions_attempted": 0,
            "note": (
                f"Fail-closed timing gate: {reason}. "
                "No market-data requests or simulated proposals were generated."
            ),
        }
        out_name = (
            "d2_4l_next_session.json" if mode == "next_session" else "d2_4l_post_close.json"
        )
        (evidence_dir / out_name).write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload

    def run_next_session_validation(
        self,
        *,
        prior_bundle_path: Path,
        now_utc: Optional[datetime] = None,
        force_run: bool = False,
        window_minutes: int = DEFAULT_SLOT_WINDOW_MINUTES,
    ) -> Dict[str, Any]:
        """Load exact prior-session signals; evaluate quotes/proposals (no rescan invent).

        Fail-closed: NY date must match expected_next_session_day AND
        next_session_validate slot must be in window before any quotes/proposals.
        force_run does not bypass the gate for proposals or soak credit.
        """
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        safety_pre = require_observation_safety(phase="pre_next_session")
        prior = _load_json(Path(prior_bundle_path))
        if not prior or not prior.get("signals"):
            raise FileNotFoundError(f"Prior session bundle missing signals: {prior_bundle_path}")

        ny_now = _ny_now(now)
        ny_day = ny_now.date()
        expected_next = (prior.get("pair") or {}).get("next_session_day")
        timing = build_timing_audit(
            mode="next_session",
            now_utc=now,
            slot_id=NEXT_SESSION_SLOT_ID,
            expected_session_day=str(expected_next) if expected_next else None,
            window_minutes=window_minutes,
        )

        run_id = now.strftime("d2_4l_%Y%m%dT%H%M%SZ")
        evidence_dir = self.evidence_root / run_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # force_run cannot generate proposals or earn soak credit outside the gate
        if not timing.get("timing_ok"):
            return self._finalize_gated_rejection(
                mode="next_session",
                run_id=run_id,
                evidence_dir=evidence_dir,
                trading_day=ny_day.isoformat(),
                pair=prior.get("pair"),
                timing=timing,
                safety_pre=safety_pre,
                count_toward_soak=True,
                force_run=force_run,
                diagnostic=bool(force_run),
                prior_bundle_path=Path(prior_bundle_path),
                prior=prior,
            )

        runner = ObservationRunner(refresh_prices=False)
        runner.run_id = run_id
        runner.evidence_dir = evidence_dir
        runner.journal.journal_dir = evidence_dir / "journal"
        runner.journal.journal_dir.mkdir(parents=True, exist_ok=True)

        # Rebuild scan_rows from exact prior signals (no silent new snapshot)
        scan_rows = []
        for sig in prior.get("signals") or []:
            scan_rows.append(
                {
                    **sig,
                    "as_of": sig.get("market_as_of_date") or sig.get("as_of"),
                    "refresh_status": "LOADED_FROM_PRIOR_SESSION",
                }
            )
        scan = {
            "tickers_requested": [s.get("ticker") for s in scan_rows],
            "tickers_scanned": [s.get("ticker") for s in scan_rows],
            "scan_rows": scan_rows,
            "signal_distribution": {},
            "data_quality_failures": [],
            "scanner_runtime_seconds": 0.0,
            "partial_universe": False,
            "resumed_from_checkpoint": False,
        }
        for row in scan_rows:
            sig = str(row.get("signal") or "UNKNOWN")
            scan["signal_distribution"][sig] = scan["signal_distribution"].get(sig, 0) + 1

        # Freshness of *prior* signal as_of vs last completed at next-session time
        freshness = assess_scan_freshness(scan_rows, now_utc=now)

        client, client_status = try_load_readonly_client()
        account = None
        quotes: Dict[str, Dict[str, Any]] = {}
        alpaca_meta: Dict[str, Any] = {"connected": False, "status": client_status}
        if client is not None:
            try:
                alpaca_meta = client.validate_readonly()
                account = client.get_account_snapshot()
                syms = [
                    str(s.get("ticker")).upper()
                    for s in (prior.get("buy_candidates") or [])
                    if s.get("policy") == "ALLOWED"
                ]
                if not syms:
                    syms = [str(s.get("ticker")).upper() for s in scan_rows[:40]]
                quotes = client.get_quotes(syms) if syms else {}
            except Exception as exc:
                alpaca_meta["error"] = f"{type(exc).__name__}: {exc}"

        decisions = runner.evaluate_decisions(
            scan, now_utc=now, account=account, quotes=quotes
        )
        # Attach performance vs prior signal date when subsequent bars exist
        decisions["performance"] = attach_performance_to_proposals(
            decisions.get("results") or []
        )

        safety_post = require_observation_safety(
            phase="post_next_session",
            submissions_attempted=runner.submissions_attempted,
        )

        bundle_path = self._persist_session_bundle(
            mode="next_session",
            trading_day=ny_day.isoformat(),
            run_id=runner.run_id,
            evidence_dir=runner.evidence_dir,
            scan=scan,
            decisions=decisions,
            freshness=freshness,
            safety_pre=safety_pre,
            safety_post=safety_post,
            pair=prior.get("pair"),
            prior_session_ref=str(prior_bundle_path),
        )

        prior_pair = prior.get("pair") or {}
        pair_id = _pair_id_from_pair(prior_pair, prior.get("trading_day"))
        prior_fresh = (prior.get("freshness") or {}).get("status")
        eligible = bool(
            prior_fresh == "FRESH"
            and safety_pre.get("passed")
            and safety_post.get("passed")
            and timing.get("timing_ok")
            and len(scan_rows) > 0
            and (runner.evidence_dir / "session_bundle.json").exists()
        )
        reason_code = "OK" if eligible else "SOAK_INELIGIBLE"
        status = self._record_ledger_entry(
            {
                "session_key": _session_key("next_session", ny_day.isoformat()),
                "pair_id": pair_id,
                "mode": "next_session",
                "trading_day": ny_day.isoformat(),
                "run_id": runner.run_id,
                "evidence_dir": str(runner.evidence_dir),
                "bundle_path": str(bundle_path),
                "prior_bundle": str(prior_bundle_path),
                "expected_next_session_day": expected_next,
                "eligible": eligible,
                "counts_toward_pair": eligible,
                "eligibility_reason_code": reason_code,
                "timing": timing,
                "prior_freshness_status": prior_fresh,
                "freshness_status": freshness.get("status"),
                "universe_count": len(scan_rows),
                "successfully_scanned": len(scan_rows),
                "simulated_proposals": len(decisions.get("simulated_proposals") or []),
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "real_session": True,
                "gated_before_proposals": False,
            }
        )

        payload = {
            "stage": "D2.4L",
            "mode": "next_session",
            "run_id": runner.run_id,
            "trading_day_et": ny_day.isoformat(),
            "prior_bundle_path": str(prior_bundle_path),
            "prior_trading_day": prior.get("trading_day"),
            "expected_next_session_day": expected_next,
            "loaded_exact_prior_signals": True,
            "freshness": freshness,
            "safety_pre": safety_pre,
            "safety_post": safety_post,
            "timing": timing,
            "eligibility_reason_code": reason_code,
            "eligible": eligible,
            "counts_toward_pair": eligible,
            "universe_count": len(scan_rows),
            "signal_distribution": scan.get("signal_distribution"),
            "policy_eligibility_breakdown": decisions.get("policy_eligibility_breakdown"),
            "buy_candidates": decisions.get("buy_candidates"),
            "simulated_proposals": [
                {
                    "ticker": r.get("ticker"),
                    "pilot_rank": r.get("pilot_rank"),
                    "proposed_limit": (r.get("simulated_proposal") or {}).get(
                        "proposed_limit_price"
                    ),
                    "proposed_qty": (r.get("simulated_proposal") or {}).get(
                        "proposed_quantity"
                    ),
                    "proposed_notional": (r.get("simulated_proposal") or {}).get(
                        "proposed_notional"
                    ),
                    "investment": (r.get("investment_decision") or {}).get("classification"),
                    "execution_readiness": (r.get("execution_readiness") or {}).get(
                        "execution_readiness"
                    ),
                }
                for r in (decisions.get("simulated_proposals") or [])
            ],
            "rejected_or_deferred_count": len(decisions.get("rejected_or_deferred") or []),
            "portfolio_exposure": decisions.get("portfolio_exposure"),
            "performance": decisions.get("performance"),
            "alpaca_readonly": {
                "connected": alpaca_meta.get("connected"),
                "account": {
                    "cash": getattr(account, "cash", None) if account else None,
                    "equity": getattr(account, "equity", None) if account else None,
                },
                "quotes_retrieved": len(quotes),
                "status": client_status,
                "error": alpaca_meta.get("error"),
            },
            "bundle_path": str(bundle_path),
            "evidence_dir": str(runner.evidence_dir),
            "soak_status": status,
            "broker_orders": False,
            "submissions_attempted": 0,
        }
        (runner.evidence_dir / "d2_4l_next_session.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload

    def write_final_soak_report(self, *, out_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Generate local three-session soak report from the ledger (claim only if complete)."""
        status = soak_status()
        led = load_soak_ledger()
        out = Path(out_dir) if out_dir else (
            self.evidence_root / datetime.now(timezone.utc).strftime("d2_4l_soak_report_%Y%m%dT%H%M%SZ")
        )
        out.mkdir(parents=True, exist_ok=True)
        sessions = led.get("sessions") or []
        by_pair: Dict[str, Dict[str, Any]] = {}
        for s in sessions:
            pid = s.get("pair_id")
            if not pid:
                continue
            by_pair.setdefault(str(pid), {})[s.get("mode")] = s

        lines = [
            "# D2.4L — Three-Session Observation Soak Report",
            "",
            f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
            f"- Completed pairs: **{status.get('observed_completed_pairs')}/{SOAK_TARGET_PAIRS}**",
            f"- Soak complete: **{status.get('soak_complete')}**",
            f"- Claim allowed: **{status.get('claim_allowed')}**",
            f"- Go/No-Go: **{status.get('recommendation')}**",
            f"- Broker orders: **False** (observation only)",
            f"- Unattended schedules activated: **False**",
            "",
            "## Completed pairs",
            "",
        ]
        for pid in status.get("completed_pair_ids") or []:
            legs = by_pair.get(pid) or {}
            pc = legs.get("post_close") or {}
            ns = legs.get("next_session") or {}
            lines += [
                f"### `{pid}`",
                "",
                f"- Post-close evidence: `{pc.get('evidence_dir')}` fresh=`{pc.get('freshness_status')}` "
                f"universe=`{pc.get('universe_count')}` scanned=`{pc.get('successfully_scanned')}`",
                f"- Next-session evidence: `{ns.get('evidence_dir')}` sims=`{ns.get('simulated_proposals')}`",
                "",
            ]
        if not status.get("completed_pair_ids"):
            lines.append("_No completed pairs yet._")
            lines.append("")

        lines += [
            "## Pending post-close legs (awaiting next-session)",
            "",
        ]
        for pid in status.get("pending_post_close_pair_ids") or []:
            lines.append(f"- `{pid}`")
        if not status.get("pending_post_close_pair_ids"):
            lines.append("_None._")

        lines += [
            "",
            "## Explicit limitation",
            "",
            status.get("note") or "",
            "",
            "Simulated fills are research approximations only — not broker fills.",
            "",
        ]
        report_path = out / "D2_4L_THREE_SESSION_SOAK_REPORT.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        payload = {
            "soak_status": status,
            "ledger": led,
            "report_path": str(report_path),
            "three_session_soak_claimed_complete": bool(status.get("soak_complete")),
        }
        (out / "d2_4l_soak_report.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        return payload

