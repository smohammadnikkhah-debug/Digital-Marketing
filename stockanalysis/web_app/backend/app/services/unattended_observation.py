"""Unattended D2.4L observation runner (config + local helpers).

Does NOT register Windows Task Scheduler tasks.
Does NOT enable broker execution or change emergency-stop flags.
Missed slots earn no soak credit (no backfill / no fabrication).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import (
    ALPACA_EXECUTION_ENABLED,
    DATA_CACHE_DIR,
    IBKR_EMERGENCY_STOP,
    TRADING_EXECUTION_ENABLED,
)
from app.services.multi_session_soak import (
    DEFAULT_SLOT_WINDOW_MINUTES,
    MultiSessionSoak,
    NEXT_SESSION_SLOT_ID,
    POST_CLOSE_SLOT_ID,
    build_timing_audit,
    load_soak_ledger,
    soak_status,
)
from app.services.observation_safety import assert_observation_safety
from app.services.observation_schedule import (
    NY_TZ,
    ensure_schedule_config,
    should_run_slot,
)
from app.services.order_proposal_engine import STAGE_APPROVAL_ENABLED, STAGE_SUBMISSION_ENABLED

UNATTENDED_ROOT = DATA_CACHE_DIR / "observation" / "unattended"
LOCK_PATH = UNATTENDED_ROOT / "unattended.lock"
RUN_LOG_DIR = UNATTENDED_ROOT / "logs"
STATE_PATH = UNATTENDED_ROOT / "unattended_state.json"
TASK_ARTIFACTS_DIR = UNATTENDED_ROOT / "task_scheduler"
ACTIVATION_FLAG_PATH = UNATTENDED_ROOT / "ACTIVATION_APPROVED.flag"

# Poller cadence guidance (Melbourne-host DST-safe)
POLLER_INTERVAL_MINUTES = 5
# Bounded in-window retries after failure/interrupt (survives via state file)
MAX_ATTEMPTS_PER_SLOT_SESSION = 2


def ensure_unattended_dirs() -> None:
    UNATTENDED_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    TASK_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> Dict[str, Any]:
    ensure_unattended_dirs()
    if not STATE_PATH.exists():
        return {"version": "D2.4L", "slot_attempts": {}, "last_status": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "D2.4L", "slot_attempts": {}, "last_status": None}


def save_state(state: Dict[str, Any]) -> None:
    ensure_unattended_dirs()
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def safety_snapshot() -> Dict[str, Any]:
    s = assert_observation_safety(phase="unattended_preflight")
    return {
        "passed": bool(s.get("passed")),
        "ibkr_emergency_stop": IBKR_EMERGENCY_STOP,
        "trading_execution_enabled": TRADING_EXECUTION_ENABLED,
        "alpaca_execution_enabled": ALPACA_EXECUTION_ENABLED,
        "stage_approval_enabled": STAGE_APPROVAL_ENABLED,
        "stage_submission_enabled": STAGE_SUBMISSION_ENABLED,
        "detail": s,
    }


def windows_tasks_activated() -> bool:
    """True only when an explicit local approval flag file exists AND schedule says enabled."""
    cfg = ensure_schedule_config()
    act = (cfg.get("activation") or {})
    return bool(
        ACTIVATION_FLAG_PATH.exists()
        and act.get("windows_task_enabled")
        and act.get("unattended_enabled")
    )


class OverlapLock:
    """Simple exclusive lock to prevent overlapping unattended runs."""

    def __init__(self, path: Optional[Path] = None, *, stale_seconds: int = 4 * 3600):
        self.path = Path(path) if path else LOCK_PATH
        self.stale_seconds = stale_seconds
        self.held = False

    def acquire(self, *, mode: str) -> Dict[str, Any]:
        ensure_unattended_dirs()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        if self.path.exists():
            try:
                meta = json.loads(self.path.read_text(encoding="utf-8"))
                started = datetime.fromisoformat(str(meta.get("started_at_utc")))
                age = (now - started).total_seconds()
                if age < self.stale_seconds:
                    return {
                        "acquired": False,
                        "reason_code": "OVERLAP_LOCK_HELD",
                        "existing": meta,
                    }
            except Exception:
                pass
            # Stale lock — remove
            try:
                self.path.unlink()
            except OSError:
                return {"acquired": False, "reason_code": "LOCK_STALE_UNREMOVABLE"}

        payload = {
            "pid": os.getpid(),
            "mode": mode,
            "started_at_utc": now.isoformat(),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.held = True
        return {"acquired": True, "lock": payload}

    def release(self) -> None:
        if not self.held:
            return
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
        self.held = False


def next_session_day_from_pair_id(pair_id: Optional[str]) -> Optional[str]:
    """Extract next_session_day from `{post_close}->{next_session}` pair ids."""
    if not pair_id or "->" not in str(pair_id):
        return None
    suffix = str(pair_id).split("->", 1)[1].strip()
    return suffix or None


def resolve_prior_post_close_bundle(
    *,
    ledger: Optional[Dict[str, Any]] = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Pick the pending post-close whose next_session_day is today's NY session.

    Missed / past-due pending pairs stay listed for humans but are not selected
    for validation (no backfill, no fabricated soak credit). Future pendings wait
    until their next_session_day.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today_ny = now.astimezone(NY_TZ).date().isoformat()

    led = ledger or load_soak_ledger()
    status = soak_status(led)
    pending = list(status.get("pending_post_close_pair_ids") or [])
    if not pending:
        return {
            "found": False,
            "reason_code": "NO_PENDING_POST_CLOSE",
            "bundle_path": None,
            "pair_id": None,
            "today_ny": today_ny,
            "stale_pending_pair_ids": [],
            "future_pending_pair_ids": [],
        }

    pending_sorted = sorted(pending)
    due_today: list[str] = []
    stale: list[str] = []
    future: list[str] = []
    for pid in pending_sorted:
        ns_day = next_session_day_from_pair_id(pid)
        if not ns_day:
            stale.append(pid)
            continue
        if ns_day == today_ny:
            due_today.append(pid)
        elif ns_day < today_ny:
            stale.append(pid)
        else:
            future.append(pid)

    if not due_today:
        return {
            "found": False,
            "reason_code": "NO_PENDING_FOR_TODAY",
            "bundle_path": None,
            "pair_id": None,
            "today_ny": today_ny,
            "stale_pending_pair_ids": stale,
            "future_pending_pair_ids": future,
            "note": (
                "Missed historical pending pairs are retained without soak credit; "
                "no backfill. Waiting for a pending pair whose next_session_day "
                "matches today's NY session."
            ),
        }

    # Exactly one actionable pair for today when schedule is healthy; if several
    # somehow share the same next_session_day, take chronological first.
    pair_id = due_today[0]
    sessions = led.get("sessions") or []
    matches = [
        s
        for s in sessions
        if s.get("mode") == "post_close"
        and s.get("pair_id") == pair_id
        and s.get("eligible") is True
        and s.get("freshness_status") == "FRESH"
    ]
    if not matches:
        return {
            "found": False,
            "reason_code": "PENDING_PAIR_MISSING_ELIGIBLE_BUNDLE",
            "bundle_path": None,
            "pair_id": pair_id,
            "today_ny": today_ny,
            "stale_pending_pair_ids": stale,
            "future_pending_pair_ids": future,
        }

    # Latest eligible post-close for that pair
    matches.sort(key=lambda s: str(s.get("recorded_at_utc") or ""), reverse=True)
    chosen = matches[0]
    path = Path(str(chosen.get("bundle_path") or ""))
    if not path.exists():
        return {
            "found": False,
            "reason_code": "BUNDLE_PATH_MISSING",
            "bundle_path": str(path),
            "pair_id": pair_id,
            "run_id": chosen.get("run_id"),
            "today_ny": today_ny,
            "stale_pending_pair_ids": stale,
            "future_pending_pair_ids": future,
        }

    # Do not use if an eligible next-session already completed the pair
    if pair_id in (status.get("completed_pair_ids") or []):
        return {
            "found": False,
            "reason_code": "PAIR_ALREADY_COMPLETE",
            "bundle_path": str(path),
            "pair_id": pair_id,
            "today_ny": today_ny,
            "stale_pending_pair_ids": stale,
            "future_pending_pair_ids": future,
        }

    return {
        "found": True,
        "reason_code": "OK",
        "bundle_path": str(path),
        "pair_id": pair_id,
        "run_id": chosen.get("run_id"),
        "trading_day": chosen.get("trading_day"),
        "evidence_dir": chosen.get("evidence_dir"),
        "today_ny": today_ny,
        "expected_next_session_day": today_ny,
        "stale_pending_pair_ids": stale,
        "future_pending_pair_ids": future,
    }


def _attempt_key(slot_id: str, ny_date: str) -> str:
    return f"{slot_id}|{ny_date}"


def ledger_has_eligible_leg(
    *,
    mode: str,
    trading_day: Optional[str] = None,
    pair_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Persistable once-per-session guard via soak ledger (survives restarts)."""
    for s in load_soak_ledger().get("sessions") or []:
        if s.get("mode") != mode or not s.get("eligible"):
            continue
        if pair_id and s.get("pair_id") == pair_id:
            return s
        if trading_day and s.get("trading_day") == trading_day:
            return s
    return None


def slot_attempt_record(
    *,
    slot_id: str,
    ny_date: str,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    st = state or load_state()
    prev = (st.get("slot_attempts") or {}).get(_attempt_key(slot_id, ny_date)) or {}
    return dict(prev)


def should_skip_slot_attempt(
    *,
    slot_id: str,
    ny_date: str,
    mode: str,
    pair_id: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """At-most-once eligible + bounded retry for failures.

    Terminal (skip):
      - ledger already has eligible leg for this session/pair
      - state shows eligible success
      - state attempts >= MAX_ATTEMPTS_PER_SLOT_SESSION

    Retry allowed:
      - prior in-window attempt failed/ineligible and attempts < max
      - crash before state write (no record) → treated as fresh attempt
    """
    led = ledger_has_eligible_leg(
        mode=mode, trading_day=ny_date, pair_id=pair_id
    )
    if led:
        return {
            "skip": True,
            "reason_code": "LEDGER_ELIGIBLE_EXISTS",
            "detail": led,
        }
    prev = slot_attempt_record(slot_id=slot_id, ny_date=ny_date, state=state)
    if not prev:
        return {"skip": False, "reason_code": "NO_PRIOR_ATTEMPT", "detail": None}
    if prev.get("eligible"):
        return {
            "skip": True,
            "reason_code": "STATE_ELIGIBLE_EXISTS",
            "detail": prev,
        }
    attempts = int(prev.get("attempts") or 0)
    if attempts >= MAX_ATTEMPTS_PER_SLOT_SESSION:
        return {
            "skip": True,
            "reason_code": "MAX_ATTEMPTS_EXHAUSTED",
            "detail": prev,
        }
    # Prior failed/ineligible but retries remain
    return {
        "skip": False,
        "reason_code": "RETRY_ALLOWED",
        "detail": prev,
        "attempts_so_far": attempts,
    }


def already_completed_in_window(
    *,
    slot_id: str,
    ny_date: str,
    state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Back-compat helper: terminal skip detail if slot must not re-run."""
    decision = should_skip_slot_attempt(
        slot_id=slot_id,
        ny_date=ny_date,
        mode=(
            "post_close"
            if slot_id == POST_CLOSE_SLOT_ID
            else "next_session"
        ),
        state=state,
    )
    if decision.get("skip"):
        return decision.get("detail") or {"reason_code": decision.get("reason_code")}
    return None


def record_slot_attempt(
    *,
    slot_id: str,
    ny_date: str,
    run_id: Optional[str],
    eligible: bool,
    timing_ok: bool,
    outcome: str,
    pair_id: Optional[str] = None,
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist attempt counter to disk (survives app/PC restart)."""
    st = state or load_state()
    key = _attempt_key(slot_id, ny_date)
    prev = dict((st.get("slot_attempts") or {}).get(key) or {})
    attempts = int(prev.get("attempts") or 0) + 1
    rec = {
        "run_id": run_id,
        "timing_ok": bool(timing_ok),
        "eligible": bool(eligible),
        "attempts": attempts,
        "max_attempts": MAX_ATTEMPTS_PER_SLOT_SESSION,
        "outcome": outcome,
        "pair_id": pair_id,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "terminal": bool(eligible or attempts >= MAX_ATTEMPTS_PER_SLOT_SESSION),
    }
    st.setdefault("slot_attempts", {})[key] = rec
    save_state(st)
    return rec


def _write_run_log(payload: Dict[str, Any]) -> Path:
    ensure_unattended_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = str(payload.get("mode") or "run")
    path = RUN_LOG_DIR / f"{ts}_{mode}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    # Also append a one-line index
    idx = RUN_LOG_DIR / "index.jsonl"
    with idx.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": ts,
                    "mode": mode,
                    "eligibility_reason_code": payload.get("eligibility_reason_code"),
                    "log": str(path),
                    "evidence_dir": payload.get("evidence_dir"),
                },
                default=str,
            )
            + "\n"
        )
    return path


def run_unattended_post_close(
    *,
    now_utc: Optional[datetime] = None,
    force_diagnostic: bool = False,
) -> Dict[str, Any]:
    """Execute post-close only when slot gate passes (unless diagnostic)."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    safety = safety_snapshot()
    if not safety["passed"]:
        out = {
            "mode": "post_close",
            "status": "ABORTED_SAFETY",
            "safety": safety,
            "eligibility_reason_code": "SAFETY_FAIL",
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    ny_date = now.astimezone(NY_TZ).date().isoformat()
    timing = build_timing_audit(
        mode="post_close",
        now_utc=now,
        slot_id=POST_CLOSE_SLOT_ID,
        expected_session_day=ny_date,
        window_minutes=DEFAULT_SLOT_WINDOW_MINUTES,
    )
    state = load_state()
    skip = should_skip_slot_attempt(
        slot_id=POST_CLOSE_SLOT_ID,
        ny_date=ny_date,
        mode="post_close",
        state=state,
    )
    if skip.get("skip") and not force_diagnostic:
        out = {
            "mode": "post_close",
            "status": "SKIPPED_DUPLICATE",
            "eligibility_reason_code": skip.get("reason_code") or "DUPLICATE_SLOT_ATTEMPT",
            "prior_attempt": skip.get("detail"),
            "timing": timing,
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    if not timing.get("timing_ok") and not force_diagnostic:
        out = {
            "mode": "post_close",
            "status": "SKIPPED_OUTSIDE_WINDOW",
            "eligibility_reason_code": timing.get("eligibility_reason_code"),
            "timing": timing,
            "note": "Missed/outside window — no soak credit fabricated",
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    lock = OverlapLock()
    acq = lock.acquire(mode="post_close")
    if not acq.get("acquired"):
        out = {
            "mode": "post_close",
            "status": "SKIPPED_OVERLAP",
            "eligibility_reason_code": acq.get("reason_code"),
            "lock": acq,
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    try:
        soak = MultiSessionSoak()
        result = soak.run_post_close_session(
            now_utc=now,
            refresh_prices=True,
            force_run=bool(force_diagnostic and not timing.get("timing_ok")),
            resume=True,
            count_toward_soak=True,
            tickers=None,
        )
        out = {
            "mode": "post_close",
            "status": "COMPLETED",
            "run_id": result.get("run_id"),
            "eligibility_reason_code": result.get("eligibility_reason_code"),
            "eligible": result.get("eligible"),
            "counts_toward_pair": result.get("counts_toward_pair"),
            "timing": result.get("timing") or timing,
            "freshness": (result.get("freshness") or {}).get("status"),
            "universe_count": result.get("universe_count"),
            "successfully_scanned": result.get("successfully_scanned"),
            "simulated_proposals": len(result.get("simulated_proposals") or []),
            "bundle_path": result.get("bundle_path"),
            "evidence_dir": result.get("evidence_dir"),
            "soak_status": result.get("soak_status"),
            "diagnostic_force_run": result.get("diagnostic_force_run"),
            "gated_before_proposals": result.get("gated_before_proposals"),
            "safety": safety,
            "broker_orders": False,
            "windows_tasks_activated": windows_tasks_activated(),
        }
        # Persist attempt (disk) — eligible or failed counts toward bounded retry
        if timing.get("timing_ok") or result.get("eligible"):
            attempt = record_slot_attempt(
                slot_id=POST_CLOSE_SLOT_ID,
                ny_date=ny_date,
                run_id=result.get("run_id"),
                eligible=bool(result.get("eligible")),
                timing_ok=bool(timing.get("timing_ok")),
                outcome=(
                    "ELIGIBLE"
                    if result.get("eligible")
                    else str(result.get("eligibility_reason_code") or "INELIGIBLE")
                ),
                state=state,
            )
            out["slot_attempt"] = attempt
            st2 = load_state()
            st2["last_status"] = out
            save_state(st2)
        out["log_path"] = str(_write_run_log(out))
        return out
    finally:
        lock.release()


def run_unattended_next_session(
    *,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute next-session using auto-resolved prior bundle; fail-closed on timing."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    safety = safety_snapshot()
    if not safety["passed"]:
        out = {
            "mode": "next_session",
            "status": "ABORTED_SAFETY",
            "safety": safety,
            "eligibility_reason_code": "SAFETY_FAIL",
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    prior = resolve_prior_post_close_bundle(now_utc=now)
    if not prior.get("found"):
        out = {
            "mode": "next_session",
            "status": "SKIPPED_NO_PRIOR",
            "eligibility_reason_code": prior.get("reason_code"),
            "prior_resolution": prior,
            "note": (
                "No eligible pending post-close for today's NY session — "
                "no soak credit fabricated (missed pairs not backfilled)"
            ),
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    expected = None
    try:
        bundle = json.loads(Path(prior["bundle_path"]).read_text(encoding="utf-8"))
        expected = (bundle.get("pair") or {}).get("next_session_day")
    except Exception:
        expected = None

    ny_date = now.astimezone(NY_TZ).date().isoformat()
    timing = build_timing_audit(
        mode="next_session",
        now_utc=now,
        slot_id=NEXT_SESSION_SLOT_ID,
        expected_session_day=str(expected) if expected else None,
        window_minutes=DEFAULT_SLOT_WINDOW_MINUTES,
    )

    state = load_state()
    skip = should_skip_slot_attempt(
        slot_id=NEXT_SESSION_SLOT_ID,
        ny_date=str(expected or ny_date),
        mode="next_session",
        pair_id=prior.get("pair_id"),
        state=state,
    )
    if skip.get("skip"):
        out = {
            "mode": "next_session",
            "status": "SKIPPED_DUPLICATE",
            "eligibility_reason_code": skip.get("reason_code")
            or "DUPLICATE_ELIGIBLE_NEXT_SESSION",
            "pair_id": prior.get("pair_id"),
            "prior_attempt": skip.get("detail"),
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    if not timing.get("timing_ok"):
        # Still invoke soak gate path so ledger gets WRONG_SESSION_DAY/OUTSIDE_WINDOW
        # only when calendar day matches expected OR we're in wrong day — actually
        # calling run_next_session_validation will gate before proposals. For pure
        # poller outside window with wrong day, skip without fabricating credit.
        # If day matches but outside window, also skip poller noise unless inside
        # a soft pre-window? Fail-closed: skip without calling when clearly outside,
        # except we want ledger audit when operator expects — for unattended poller,
        # SKIP without ledger spam when OUTSIDE_WINDOW; call soak only when day matches
        # and we're near window OR always call soak which records gate.
        #
        # Spec: missed sessions do not receive fabricated soak credit.
        # Recording OUTSIDE_WINDOW gated legs is OK (ineligible). Avoid flooding:
        # only invoke soak when day_match (expected == ny) so wrong-day polls are quiet.
        if not timing.get("day_match"):
            out = {
                "mode": "next_session",
                "status": "SKIPPED_WRONG_SESSION_DAY",
                "eligibility_reason_code": "WRONG_SESSION_DAY",
                "timing": timing,
                "prior_resolution": prior,
                "note": "Waiting for expected next-session NY date — no soak credit",
                "broker_orders": False,
            }
            out["log_path"] = str(_write_run_log(out))
            return out
        # Correct day but outside window: skip quietly (no fabricated credit)
        out = {
            "mode": "next_session",
            "status": "SKIPPED_OUTSIDE_WINDOW",
            "eligibility_reason_code": "OUTSIDE_WINDOW",
            "timing": timing,
            "prior_resolution": prior,
            "note": "Outside 09:45 ET ±45m — no soak credit fabricated",
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    lock = OverlapLock()
    acq = lock.acquire(mode="next_session")
    if not acq.get("acquired"):
        out = {
            "mode": "next_session",
            "status": "SKIPPED_OVERLAP",
            "eligibility_reason_code": acq.get("reason_code"),
            "lock": acq,
            "broker_orders": False,
        }
        out["log_path"] = str(_write_run_log(out))
        return out

    try:
        soak = MultiSessionSoak()
        result = soak.run_next_session_validation(
            prior_bundle_path=Path(prior["bundle_path"]),
            now_utc=now,
            force_run=False,
        )
        out = {
            "mode": "next_session",
            "status": "COMPLETED",
            "run_id": result.get("run_id"),
            "eligibility_reason_code": result.get("eligibility_reason_code"),
            "eligible": result.get("eligible"),
            "counts_toward_pair": result.get("counts_toward_pair"),
            "timing": result.get("timing") or timing,
            "prior_resolution": prior,
            "expected_next_session_day": result.get("expected_next_session_day"),
            "simulated_proposals": len(result.get("simulated_proposals") or []),
            "bundle_path": result.get("bundle_path"),
            "evidence_dir": result.get("evidence_dir"),
            "soak_status": result.get("soak_status"),
            "gated_before_proposals": result.get("gated_before_proposals"),
            "safety": safety,
            "broker_orders": False,
            "windows_tasks_activated": windows_tasks_activated(),
        }
        if expected and (result.get("eligible") or timing.get("timing_ok")):
            attempt = record_slot_attempt(
                slot_id=NEXT_SESSION_SLOT_ID,
                ny_date=str(expected),
                run_id=result.get("run_id"),
                eligible=bool(result.get("eligible")),
                timing_ok=bool(timing.get("timing_ok")),
                outcome=(
                    "ELIGIBLE"
                    if result.get("eligible")
                    else str(result.get("eligibility_reason_code") or "INELIGIBLE")
                ),
                pair_id=prior.get("pair_id"),
                state=state,
            )
            out["slot_attempt"] = attempt
            st2 = load_state()
            st2["last_status"] = out
            save_state(st2)
        out["log_path"] = str(_write_run_log(out))
        return out
    finally:
        lock.release()


def run_unattended_poll(
    *,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """DST-safe entrypoint: check both slots; run at most one action."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    pc_gate = should_run_slot(
        POST_CLOSE_SLOT_ID, now_utc=now, window_minutes=DEFAULT_SLOT_WINDOW_MINUTES
    )
    ns_gate = should_run_slot(
        NEXT_SESSION_SLOT_ID, now_utc=now, window_minutes=DEFAULT_SLOT_WINDOW_MINUTES
    )

    actions: list = []
    if pc_gate.get("should_run"):
        actions.append(("post_close", run_unattended_post_close(now_utc=now)))
    if ns_gate.get("should_run"):
        actions.append(("next_session", run_unattended_next_session(now_utc=now)))

    if not actions:
        out = {
            "mode": "poll",
            "status": "IDLE",
            "eligibility_reason_code": "NO_SLOT_IN_WINDOW",
            "post_close_gate": pc_gate,
            "next_session_gate": ns_gate,
            "now_et": now.astimezone(NY_TZ).isoformat(),
            "broker_orders": False,
            "windows_tasks_activated": windows_tasks_activated(),
            "note": "No action — outside both observation windows",
        }
        # Lightweight: don't spam index every 5 min — write only when VERBOSE
        return out

    # Prefer next_session if both somehow true (shouldn't happen)
    mode, result = actions[-1] if len(actions) == 1 else (
        "next_session",
        dict(actions[1][1]),
    )
    if len(actions) > 1:
        # Run post_close first if both — rare; sequential under lock
        result = {
            "mode": "poll",
            "status": "MULTI",
            "results": {a[0]: a[1] for a in actions},
            "broker_orders": False,
        }
        result["log_path"] = str(_write_run_log(result))
        return result
    return result


def _classify_log(entry: Dict[str, Any]) -> str:
    status = str(entry.get("status") or "")
    if entry.get("eligible") is True:
        return "completed"
    if status.startswith("SKIPPED") or status == "IDLE":
        return "skipped" if status != "IDLE" else "idle"
    if status == "ABORTED_SAFETY":
        return "failed"
    if status == "COMPLETED":
        return "completed" if entry.get("eligible") else "failed"
    if entry.get("error"):
        return "failed"
    return "other"


def morning_status(*, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """Human-friendly overnight summary for next-morning review."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ensure_unattended_dirs()
    st = soak_status()
    state = load_state()
    recent_logs = sorted(RUN_LOG_DIR.glob("*_*.json"), reverse=True)[:20]
    recent = []
    for p in recent_logs:
        try:
            recent.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            recent.append({"log_path": str(p), "error": "unreadable", "status": "FAILED_READ"})

    categorized = {"completed": [], "pending": [], "failed": [], "skipped": []}
    for r in recent:
        bucket = _classify_log(r)
        row = {
            "mode": r.get("mode"),
            "status": r.get("status"),
            "eligibility_reason_code": r.get("eligibility_reason_code"),
            "eligible": r.get("eligible"),
            "run_id": r.get("run_id"),
            "evidence_dir": r.get("evidence_dir"),
            "bundle_path": r.get("bundle_path"),
            "log_path": r.get("log_path"),
            "note": r.get("note"),
            "category": bucket,
        }
        if bucket in categorized:
            categorized[bucket].append(row)

    # Ledger-backed completed soak legs (authoritative across restarts)
    for s in load_soak_ledger().get("sessions") or []:
        if not s.get("eligible"):
            continue
        categorized["completed"].append(
            {
                "mode": s.get("mode"),
                "status": "LEDGER_ELIGIBLE",
                "eligible": True,
                "run_id": s.get("run_id"),
                "pair_id": s.get("pair_id"),
                "trading_day": s.get("trading_day"),
                "evidence_dir": s.get("evidence_dir"),
                "bundle_path": s.get("bundle_path"),
                "category": "completed",
                "source": "soak_ledger",
            }
        )

    prior = resolve_prior_post_close_bundle(now_utc=now)
    if prior.get("found"):
        categorized["pending"].append(
            {
                "mode": "post_close_awaiting_next_session",
                "pair_id": prior.get("pair_id"),
                "bundle_path": prior.get("bundle_path"),
                "run_id": prior.get("run_id"),
                "category": "pending",
            }
        )
    for pid in prior.get("stale_pending_pair_ids") or []:
        if not any(p.get("pair_id") == pid for p in categorized["pending"]):
            categorized["pending"].append(
                {
                    "mode": "stale_pending_pair",
                    "pair_id": pid,
                    "category": "pending",
                    "note": "Missed next-session day — retained without soak credit",
                }
            )
    for pid in prior.get("future_pending_pair_ids") or []:
        if not any(p.get("pair_id") == pid for p in categorized["pending"]):
            categorized["pending"].append(
                {
                    "mode": "future_pending_pair",
                    "pair_id": pid,
                    "category": "pending",
                    "note": "Waiting for next_session_day",
                }
            )
    for pid in st.get("pending_post_close_pair_ids") or []:
        if not any(p.get("pair_id") == pid for p in categorized["pending"]):
            categorized["pending"].append(
                {"mode": "pending_pair", "pair_id": pid, "category": "pending"}
            )

    cfg = ensure_schedule_config()
    return {
        "generated_at_utc": now.isoformat(),
        "generated_at_et": now.astimezone(NY_TZ).isoformat(),
        "soak_status": st,
        "session_categories": {
            "completed": categorized["completed"],
            "pending": categorized["pending"],
            "failed": categorized["failed"],
            "skipped": categorized["skipped"],
            "counts": {
                "completed": len(categorized["completed"]),
                "pending": len(categorized["pending"]),
                "failed": len(categorized["failed"]),
                "skipped": len(categorized["skipped"]),
            },
        },
        "pending_prior_bundle": prior,
        "slot_attempts_state": state.get("slot_attempts") or {},
        "last_unattended": state.get("last_status"),
        "recent_unattended_logs": [
            {
                "mode": r.get("mode"),
                "status": r.get("status"),
                "eligibility_reason_code": r.get("eligibility_reason_code"),
                "eligible": r.get("eligible"),
                "run_id": r.get("run_id"),
                "evidence_dir": r.get("evidence_dir"),
                "bundle_path": r.get("bundle_path"),
                "log_path": r.get("log_path"),
                "note": r.get("note"),
                "category": _classify_log(r),
            }
            for r in recent
        ],
        "safety": safety_snapshot(),
        "schedule_activation": cfg.get("activation"),
        "windows_tasks_activated": windows_tasks_activated(),
        "activation_flag_present": ACTIVATION_FLAG_PATH.exists(),
        "broker_orders": False,
        "execution_flags_mutable_by_scheduler": False,
        "max_attempts_per_slot_session": MAX_ATTEMPTS_PER_SLOT_SESSION,
        "intentional_windows_et": {
            "post_close_research": "16:30–17:15 America/New_York",
            "next_session_validate": "09:45–10:30 America/New_York",
            "window_minutes": DEFAULT_SLOT_WINDOW_MINUTES,
            "aligned_with_soak_gates": True,
        },
        "task_artifacts_dir": str(TASK_ARTIFACTS_DIR),
        "note": (
            "Windows tasks are NOT activated until ACTIVATION_APPROVED.flag exists "
            "and schedule_config activation flags are explicitly enabled."
        ),
    }


def generate_task_scheduler_artifacts(*, backend_dir: Path) -> Dict[str, Any]:
    """Write inactive XML + helper scripts. Does not call schtasks /Create."""
    ensure_unattended_dirs()
    backend = Path(backend_dir).resolve()
    python = Path(os.environ.get("D24L_PYTHON", "") or os.path.abspath(sys.executable))
    runner = backend / "scratch" / "run_d2_4l_unattended.py"
    # Escape for XML
    def _xml(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    py = _xml(str(python))
    script = _xml(str(runner))
    work = _xml(str(backend))
    # Wrapper sets PYTHONPATH so Task Scheduler launches the correct env
    wrapper = TASK_ARTIFACTS_DIR / "run_poll.cmd"
    wrapper.write_text(
        "\r\n".join(
            [
                "@echo off",
                f'set "PYTHONPATH={backend}"',
                f'set "D24L_UNATTENDED=1"',
                f'cd /d "{backend}"',
                f'"{python}" -u "{runner}" poll',
                "exit /b %ERRORLEVEL%",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrap_xml = _xml(str(wrapper))

    # DST-safe poller: every 5 minutes; Python decides ET window via zoneinfo
    # StartWhenAvailable=false → slept/off PC does NOT catch up missed windows
    poll_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>D2.4L unattended observation poller (DST-safe via America/New_York in Python). INACTIVE until approved.</Description>
    <URI>\\StockAnalysis\\D24L_Observation_Poll</URI>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT{POLLER_INTERVAL_MINUTES}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-10-27T00:00:00</StartBoundary>
      <Enabled>false</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowHardTerminate>true</AllowHardTerminate>
    <Enabled>false</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT3H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{wrap_xml}</Command>
      <WorkingDirectory>{work}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

    readme = f"""# D2.4L Unattended Task Scheduler Artifacts (INACTIVE)

## Intended ET wall-clock slots
- post_close_research: 16:30 America/New_York (±45m gate in Python)
- next_session_validate: 09:45 America/New_York (±45m gate in Python)

## DST / Melbourne
Host clock may be Australia/Melbourne. Do **not** hard-code Melbourne times.
The recommended task is the **5-minute poller** (`D24L_Observation_Poll.xml`):
Python uses `zoneinfo.ZoneInfo("America/New_York")` so EDT/EST transitions are correct.

## Safety
- Broker execution remains disabled; emergency stop unchanged.
- Timing guards, freshness, ledger protections unchanged.
- Missed windows → SKIPPED, no fabricated soak credit.
- Overlap: Windows `IgnoreNew` + Python file lock.

## Activation (requires explicit approval — NOT done automatically)
1. Review this folder and `schedule_config.json` activation block.
2. Create empty flag file: `{ACTIVATION_FLAG_PATH}`
3. Set in schedule_config.json:
   - activation.windows_task_enabled = true
   - activation.unattended_enabled = true
4. Register (example — run manually after approval):

```powershell
schtasks /Create /TN "StockAnalysis\\D24L_Observation_Poll" /XML "{TASK_ARTIFACTS_DIR / 'D24L_Observation_Poll.xml'}" /F
schtasks /Change /TN "StockAnalysis\\D24L_Observation_Poll" /ENABLE
```

5. Morning review:

```powershell
cd "{backend}"
$env:PYTHONPATH="{backend}"
python -u scratch/run_d2_4l_unattended.py status
```

## Deactivate

```powershell
schtasks /Change /TN "StockAnalysis\\D24L_Observation_Poll" /DISABLE
# or
schtasks /Delete /TN "StockAnalysis\\D24L_Observation_Poll" /F
```

Python: `{python}`
Script: `{runner}`
Backend: `{backend}`
"""

    poll_path = TASK_ARTIFACTS_DIR / "D24L_Observation_Poll.xml"
    # Write UTF-16 LE with BOM for Task Scheduler XML
    poll_path.write_bytes(("\ufeff" + poll_xml).encode("utf-16"))
    readme_path = TASK_ARTIFACTS_DIR / "README_ACTIVATION.md"
    readme_path.write_text(readme, encoding="utf-8")

    register_ps1 = TASK_ARTIFACTS_DIR / "register_tasks_AFTER_APPROVAL.ps1"
    register_ps1.write_text(
        f"""# REQUIRES EXPLICIT APPROVAL — does nothing unless -ConfirmActivation is passed
param(
  [switch]$ConfirmActivation
)
$ErrorActionPreference = "Stop"
$xml = "{poll_path}"
$tn = "StockAnalysis\\D24L_Observation_Poll"
$flag = "{ACTIVATION_FLAG_PATH}"
if (-not $ConfirmActivation) {{
  Write-Host "Refusing to register. Re-run with -ConfirmActivation after approval."
  Write-Host "Also create flag: $flag"
  exit 2
}}
if (-not (Test-Path $flag)) {{
  Write-Host "Missing activation flag: $flag"
  exit 3
}}
schtasks /Create /TN $tn /XML $xml /F
schtasks /Change /TN $tn /ENABLE
Write-Host "Registered and ENABLED: $tn"
""",
        encoding="utf-8",
    )

    # Keep schedule_config activation false
    cfg = ensure_schedule_config()
    cfg.setdefault("activation", {})
    cfg["activation"]["windows_task_enabled"] = False
    cfg["activation"]["unattended_enabled"] = False
    cfg["activation"]["digitalocean_cron_enabled"] = False
    cfg["activation"]["poller_interval_minutes"] = POLLER_INTERVAL_MINUTES
    cfg["activation"]["task_artifacts_dir"] = str(TASK_ARTIFACTS_DIR)
    cfg["activation"]["note"] = (
        "Artifacts generated under observation/unattended/task_scheduler. "
        "Tasks are NOT registered. Do not enable without explicit approval."
    )
    from app.services.observation_schedule import SCHEDULE_PATH

    SCHEDULE_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    return {
        "generated": True,
        "windows_tasks_registered": False,
        "windows_tasks_enabled": False,
        "poll_xml": str(poll_path),
        "readme": str(readme_path),
        "register_script": str(register_ps1),
        "python": str(python),
        "runner": str(runner),
        "backend": str(backend),
        "activation_flag_path": str(ACTIVATION_FLAG_PATH),
        "schedule_activation": cfg.get("activation"),
    }
