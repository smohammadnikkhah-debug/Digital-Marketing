"""Apply approved D2.4L universe remediation (non-destructive).

Soft-deactivates retired symbols, activates successors, writes an audit
artifact. Does not rewrite historical OHLCV, observation journals, or
strategy math. Does not place broker orders or change execution flags.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_CACHE_DIR
from app.services.ticker_integrity import CANONICAL_TICKER_ALIASES
from app.services.universe_manager import universe_manager
from app.services.universe_remediation_proposal import (
    PROPOSAL_PATH,
    build_proposal_document,
    write_proposal,
)

APPLY_AUDIT_PATH = DATA_CACHE_DIR / "observation" / "universe_remediation_apply_audit.json"

# Approved scope (no SKYD)
DEACTIVATE = ("EA", "WBD", "SQ", "MMC", "QUALCOMM")
ACTIVATE = (
    {
        "ticker": "XYZ",
        "name": "Block, Inc.",
        "exchange": "NYSE",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "replaces": "SQ",
    },
    {
        "ticker": "MRSH",
        "name": "Marsh & McLennan Companies, Inc.",
        "exchange": "NYSE",
        "sector": "Financial Services",
        "industry": "Insurance Brokers",
        "replaces": "MMC",
    },
)


def _stamp_remediation(record: Dict[str, Any], *, action: str, detail: str) -> None:
    record["remediation_stage"] = "D2.4L"
    record["remediation_action"] = action
    record["remediation_detail"] = detail
    record["remediation_applied_at_utc"] = datetime.now(timezone.utc).isoformat()


def apply_approved_remediation(*, force: bool = False) -> Dict[str, Any]:
    """Apply soft-deactivate + successor activation. Idempotent unless force=True."""
    before_active = [
        s["ticker"] for s in universe_manager.get_all(include_inactive=False, exclude_synthetic=True)
    ]
    audit: Dict[str, Any] = {
        "stage": "D2.4L",
        "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization": "user_approved_non_destructive_universe_remediation",
        "skyd_added": False,
        "historical_ohlcv_rewritten": False,
        "execution_flags_changed": False,
        "broker_orders": False,
        "before_active_count": len(before_active),
        "actions": [],
        "canonical_aliases": dict(CANONICAL_TICKER_ALIASES),
    }

    # Idempotency: if already applied and successors active / retirees inactive
    already = all(
        (universe_manager.get_stock(t) or {}).get("is_active") is False for t in DEACTIVATE
    ) and all(
        (universe_manager.get_stock(a["ticker"]) or {}).get("is_active") is True for a in ACTIVATE
    )
    if already and not force:
        after = [
            s["ticker"]
            for s in universe_manager.get_all(include_inactive=False, exclude_synthetic=True)
        ]
        audit["status"] = "ALREADY_APPLIED"
        audit["after_active_count"] = len(after)
        audit["actions"].append({"note": "No-op; remediation already reflected in universe"})
        _write_audit(audit)
        _mark_proposal_applied(audit)
        return audit

    for item in ACTIVATE:
        rec = universe_manager.add_stock(
            item["ticker"],
            name=item["name"],
            exchange=item["exchange"],
            sector=item["sector"],
            industry=item["industry"],
            data_status="PENDING",
        )
        _stamp_remediation(
            rec,
            action="ACTIVATE_SUCCESSOR",
            detail=f"Replaces {item['replaces']} after approved ticker change",
        )
        rec["source"] = "d2_4l_remediation"
        rec["replaces_ticker"] = item["replaces"]
        universe_manager.update_stock(item["ticker"], rec)
        audit["actions"].append(
            {
                "ticker": item["ticker"],
                "action": "ACTIVATE_SUCCESSOR",
                "replaces": item["replaces"],
            }
        )

    for t in DEACTIVATE:
        existing = universe_manager.get_stock(t)
        if not existing:
            audit["actions"].append({"ticker": t, "action": "SKIP_MISSING"})
            continue
        detail = {
            "EA": "Delisted cash take-private 2026-08-04; no public successor",
            "WBD": "Delisted cash merger 2026-10-06; no equity successor (SKYD not added)",
            "SQ": "Ticker changed to XYZ; historical SQ identity preserved inactive",
            "MMC": "Ticker changed to MRSH; historical MMC identity preserved inactive",
            "QUALCOMM": "Invalid duplicate of QCOM; QCOM retained",
        }.get(t, "Approved soft-deactivate")
        existing = dict(existing)
        existing["is_active"] = False
        _stamp_remediation(existing, action="SOFT_DEACTIVATE", detail=detail)
        if t in CANONICAL_TICKER_ALIASES:
            existing["canonical_successor"] = CANONICAL_TICKER_ALIASES[t]
        universe_manager.update_stock(t, existing)
        # ensure flag via remove_stock path as well
        universe_manager.remove_stock(t)
        # re-apply metadata after remove_stock (which only flips is_active)
        again = universe_manager.get_stock(t) or {}
        again.update(
            {
                "remediation_stage": existing.get("remediation_stage"),
                "remediation_action": existing.get("remediation_action"),
                "remediation_detail": existing.get("remediation_detail"),
                "remediation_applied_at_utc": existing.get("remediation_applied_at_utc"),
                "canonical_successor": existing.get("canonical_successor"),
            }
        )
        universe_manager.update_stock(t, again)
        audit["actions"].append({"ticker": t, "action": "SOFT_DEACTIVATE", "detail": detail})

    after_active = [
        s["ticker"] for s in universe_manager.get_all(include_inactive=False, exclude_synthetic=True)
    ]
    audit["after_active_count"] = len(after_active)
    audit["deactivated_present_inactive"] = {
        t: (universe_manager.get_stock(t) or {}).get("is_active") is False for t in DEACTIVATE
    }
    audit["successors_active"] = {
        a["ticker"]: (universe_manager.get_stock(a["ticker"]) or {}).get("is_active") is True
        for a in ACTIVATE
    }
    audit["qcom_active"] = (universe_manager.get_stock("QCOM") or {}).get("is_active") is True
    audit["duplicate_canonical_symbols"] = _find_duplicate_canonicals(after_active)
    audit["status"] = "APPLIED"
    audit["net_active_delta"] = len(after_active) - len(before_active)

    _write_audit(audit)
    _mark_proposal_applied(audit)
    return audit


def _find_duplicate_canonicals(active: List[str]) -> List[str]:
    """Flag if both legacy and successor appear active (should be empty after apply)."""
    active_set = {str(t).upper() for t in active}
    dups: List[str] = []
    for legacy, canon in CANONICAL_TICKER_ALIASES.items():
        if legacy in active_set and canon in active_set:
            dups.append(f"{legacy}+{canon}")
    if "QUALCOMM" in active_set and "QCOM" in active_set:
        dups.append("QUALCOMM+QCOM")
    return dups


def _write_audit(audit: Dict[str, Any]) -> Path:
    APPLY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    APPLY_AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return APPLY_AUDIT_PATH


def _mark_proposal_applied(audit: Dict[str, Any]) -> None:
    doc = build_proposal_document()
    if PROPOSAL_PATH.exists():
        try:
            doc = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    doc["status"] = "APPLIED"
    doc["production_mutated"] = True
    doc["production_mutation_scope"] = "universe_registry_soft_deactivate_and_successor_activate"
    doc["applied_at_utc"] = audit.get("applied_at_utc")
    doc["apply_audit_path"] = str(APPLY_AUDIT_PATH)
    doc["skyd_added"] = False
    write_proposal(PROPOSAL_PATH)
    # write_proposal rebuilds from REMEDIATION_ITEMS — overwrite status fields
    final = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    final.update(
        {
            "status": "APPLIED",
            "production_mutated": True,
            "production_mutation_scope": doc["production_mutation_scope"],
            "applied_at_utc": audit.get("applied_at_utc"),
            "apply_audit_path": str(APPLY_AUDIT_PATH),
            "skyd_added": False,
        }
    )
    PROPOSAL_PATH.write_text(json.dumps(final, indent=2), encoding="utf-8")


def verify_active_universe() -> Dict[str, Any]:
    active = [
        s["ticker"] for s in universe_manager.get_all(include_inactive=False, exclude_synthetic=True)
    ]
    active_set = set(active)
    return {
        "active_count": len(active),
        "has_XYZ": "XYZ" in active_set,
        "has_MRSH": "MRSH" in active_set,
        "has_QCOM": "QCOM" in active_set,
        "absent_retired": {
            t: t not in active_set for t in DEACTIVATE
        },
        "inactive_preserved": {
            t: universe_manager.get_stock(t) is not None
            and (universe_manager.get_stock(t) or {}).get("is_active") is False
            for t in DEACTIVATE
        },
        "duplicate_canonical_symbols": _find_duplicate_canonicals(active),
        "skyd_in_active": "SKYD" in active_set,
    }
