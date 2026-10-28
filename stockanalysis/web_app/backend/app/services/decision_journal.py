"""Local decision journal for autonomous BUY dry runs (Stage D2.4D).

Persists JSONL under data_cache for isolated/local testing.
Idempotent: same signal_id + evaluation session key does not duplicate proposals.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.config import DATA_CACHE_DIR

JOURNAL_DIR = DATA_CACHE_DIR / "decision_journal"
_lock = threading.Lock()


class DecisionJournal:
    def __init__(self, journal_dir: Optional[Path] = None):
        self.journal_dir = Path(journal_dir) if journal_dir else JOURNAL_DIR
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self._proposal_keys: Set[str] = set()
        self._load_existing_keys()

    def _run_path(self, run_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)[:80]
        return self.journal_dir / f"{safe}.jsonl"

    def _load_existing_keys(self) -> None:
        for path in self.journal_dir.glob("*.jsonl"):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        row = json.loads(line)
                        key = row.get("idempotency_key")
                        if key and row.get("simulated_proposal"):
                            self._proposal_keys.add(key)
            except Exception:
                continue

    def append(self, run_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append one journal row. Dedupes simulated proposals by idempotency_key."""
        with _lock:
            idem = None
            proposal = entry.get("simulated_proposal")
            if isinstance(proposal, dict):
                idem = proposal.get("idempotency_key") or proposal.get("client_idempotency_key")
            if idem and idem in self._proposal_keys:
                entry = dict(entry)
                entry["simulated_proposal"] = None
                entry["proposal_deduplicated"] = True
                entry["dedupe_idempotency_key"] = idem
            elif idem:
                self._proposal_keys.add(idem)
                entry = dict(entry)
                entry["proposal_deduplicated"] = False

            entry.setdefault("journaled_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            path = self._run_path(run_id)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
            return entry

    def read_run(self, run_id: str) -> List[Dict[str, Any]]:
        path = self._run_path(run_id)
        if not path.exists():
            return []
        rows = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def summary(self, run_id: str) -> Dict[str, Any]:
        rows = self.read_run(run_id)
        counts = {"BUY_READY": 0, "WAIT": 0, "BLOCKED": 0, "NO_ACTION": 0}
        proposals = 0
        shariah_blocks = 0
        for r in rows:
            inv = (r.get("investment_decision") or {}).get("classification")
            if inv in counts:
                counts[inv] += 1
            if r.get("simulated_proposal"):
                proposals += 1
            if r.get("blocked_by_shariah"):
                shariah_blocks += 1
        return {
            "run_id": run_id,
            "entries": len(rows),
            "investment_counts": counts,
            "simulated_proposals": proposals,
            "shariah_blocked_opportunities": shariah_blocks,
            "path": str(self._run_path(run_id)),
        }


decision_journal = DecisionJournal()
