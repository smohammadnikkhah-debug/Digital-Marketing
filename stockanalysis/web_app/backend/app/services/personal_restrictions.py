"""Personal investment restriction layer (Stage D2.4G).

Independent from Shariah screening. Never infers exclusion from sector name alone.
Exclusions require an explicit ticker override or an evidence-backed category tag.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.services.ticker_integrity import resolve_proposed_alias

RESTRICT_ALLOWED = "ALLOWED"
RESTRICT_EXCLUDED = "EXCLUDED"
RESTRICT_REVIEW = "REVIEW REQUIRED"

# Configurable exclusion categories (user-specified). Matching requires an
# explicit category_tag on a ticker override — never sector-name auto-mapping.
DEFAULT_EXCLUSION_CATEGORIES = {
    "conventional_banking_lending": {
        "label": "Conventional banking / lending",
        "description": "Conventional banks, interest-based lending and related financial businesses (USER_POLICY).",
    },
    "airlines": {
        "label": "Airlines",
        "description": "Airlines and material airline operating businesses (USER_POLICY).",
    },
    "weapons_defence": {
        "label": "Weapons / defence",
        "description": "Guns, weapons, defence and military-related activities (USER_POLICY).",
    },
    "tobacco": {
        "label": "Tobacco",
        "description": "Tobacco products manufacturers and material tobacco businesses (USER_POLICY).",
    },
    "pork": {
        "label": "Pork",
        "description": "Optional legacy category — not part of D2.4H USER_POLICY core four.",
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "D2.4G",
    "exclusion_categories": DEFAULT_EXCLUSION_CATEGORIES,
    # ticker → {status, category_tags[], rationale, evidence_note, updated_at}
    "ticker_overrides": {},
    "notes": (
        "Personal restrictions are user-specific. Do not auto-classify from sector. "
        "category_tags must be set explicitly with supporting evidence_note."
    ),
}


def _canonical(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    return str(resolve_proposed_alias(raw).get("proposed_canonical") or raw).upper()


def default_personal_restrictions_config() -> Dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def load_personal_restrictions_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load local personal-restrictions JSON. Missing file → defaults (all ALLOWED)."""
    cfg = default_personal_restrictions_config()
    if path is None or not path.exists() or not path.is_file():
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    if isinstance(raw.get("exclusion_categories"), dict) and raw["exclusion_categories"]:
        cfg["exclusion_categories"] = raw["exclusion_categories"]
    overrides = raw.get("ticker_overrides") or {}
    if isinstance(overrides, dict):
        normalized: Dict[str, Any] = {}
        for k, v in overrides.items():
            if not isinstance(v, dict):
                continue
            normalized[_canonical(k)] = dict(v)
        cfg["ticker_overrides"] = normalized
    if raw.get("notes"):
        cfg["notes"] = str(raw["notes"])
    return cfg


def assess_personal_restriction(
    ticker: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    sector: Optional[str] = None,
) -> Dict[str, Any]:
    """Assess personal restriction status for a ticker.

    Sector is accepted for display only and never used as sole classification basis.
    """
    cfg = config or default_personal_restrictions_config()
    canonical = _canonical(ticker)
    overrides = cfg.get("ticker_overrides") or {}
    known_categories = set((cfg.get("exclusion_categories") or {}).keys())

    override = overrides.get(canonical)
    if not override:
        return {
            "ticker": canonical,
            "personal_restriction_status": RESTRICT_ALLOWED,
            "category_tags": [],
            "rationale": "",
            "evidence_note": "",
            "sector_observed": (sector or "").strip() or None,
            "sector_used_for_classification": False,
            "blocking": False,
            "blocking_reason": "",
        }

    status_raw = str(override.get("status") or RESTRICT_ALLOWED).strip().upper()
    if status_raw in ("EXCLUDE", "EXCLUDED", "BLOCKED"):
        status = RESTRICT_EXCLUDED
    elif status_raw in ("REVIEW", "REVIEW REQUIRED", "REVIEW_REQUIRED"):
        status = RESTRICT_REVIEW
    elif status_raw in ("ALLOW", "ALLOWED"):
        status = RESTRICT_ALLOWED
    else:
        # Unknown override → fail closed to REVIEW REQUIRED
        status = RESTRICT_REVIEW

    tags = [
        str(t).strip()
        for t in (override.get("category_tags") or override.get("categories") or [])
        if str(t).strip()
    ]
    # Reject sector-only inference: if tags empty and status EXCLUDED without evidence_note, REVIEW
    evidence_note = str(override.get("evidence_note") or override.get("evidence") or "").strip()
    rationale = str(override.get("rationale") or "").strip()

    if status == RESTRICT_EXCLUDED and not evidence_note and not tags:
        status = RESTRICT_REVIEW
        rationale = rationale or (
            "EXCLUDED override lacks category_tags and evidence_note — "
            "sector-only classification is not permitted"
        )

    # Unknown category tags do not auto-exclude; force review
    unknown_tags = [t for t in tags if t not in known_categories]
    if unknown_tags and status == RESTRICT_EXCLUDED:
        status = RESTRICT_REVIEW
        rationale = rationale or f"Unknown category_tags require review: {unknown_tags}"

    blocking = status in (RESTRICT_EXCLUDED, RESTRICT_REVIEW)
    if status == RESTRICT_EXCLUDED:
        reason = rationale or f"Personal exclusion ({', '.join(tags) or 'user override'})"
    elif status == RESTRICT_REVIEW:
        reason = rationale or "Personal restriction requires review"
    else:
        reason = ""

    return {
        "ticker": canonical,
        "personal_restriction_status": status,
        "category_tags": tags,
        "rationale": rationale,
        "evidence_note": evidence_note,
        "sector_observed": (sector or "").strip() or None,
        "sector_used_for_classification": False,
        "blocking": blocking,
        "blocking_reason": reason if blocking else "",
        "updated_at": override.get("updated_at"),
    }


def list_exclusion_categories(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config or default_personal_restrictions_config()
    return dict(cfg.get("exclusion_categories") or {})
