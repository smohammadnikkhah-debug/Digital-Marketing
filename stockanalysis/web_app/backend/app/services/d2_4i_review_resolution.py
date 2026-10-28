"""D2.4I review-candidate resolution helpers (local evidence only).

Uses company legal names and fund methodology evidence — not ticker/sector inference.
Does not write production databases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.user_policy_eligibility import (
    BUSINESS_EVIDENCE_PATH,
    CAT_BANKING,
    CAT_TOBACCO,
    CAT_WEAPONS,
    ETF_EVIDENCE_PATH,
    POLICY_ALLOWED,
    POLICY_EXCLUDED,
    POLICY_REVIEW,
    ensure_user_policy_templates,
)


# Reliable activity notes grounded in legal entity names / public fund mandates.
CRM_PLTR_OVERLAYS: Dict[str, Dict[str, Any]] = {
    "CRM": {
        "ticker": "CRM",
        "status": POLICY_ALLOWED,
        "business_type": "enterprise_application_software",
        "category_tags": [],
        "evidence_source": "universe_registry.name=Salesforce, Inc. + primary product line (CRM SaaS)",
        "evidence_note": (
            "Salesforce, Inc. primary business is enterprise cloud application software "
            "(Customer Relationship Management SaaS). No material classification as a "
            "conventional bank, airline, weapons/defence manufacturer, or tobacco producer."
        ),
        "reason_codes": ["POLICY_SOFTWARE_ACTIVITY_ALLOWED"],
    },
    "PLTR": {
        "ticker": "PLTR",
        "status": POLICY_EXCLUDED,
        "business_type": "military_defence_intelligence_software",
        "category_tags": [CAT_WEAPONS],
        "evidence_source": "user_policy.explicit_exclusion=MILITARY_DEFENCE_EXPOSURE",
        "evidence_note": (
            "Palantir Technologies Inc. has material military, defence, and "
            "intelligence-related business activities. EXCLUDED under USER_POLICY "
            "(MILITARY_DEFENCE_EXPOSURE). Research-visible only — not proposal/order eligible."
        ),
        "reason_codes": ["MILITARY_DEFENCE_EXPOSURE", "POLICY_EXCLUDED_WEAPONS_DEFENCE"],
    },
}

ETF_FUND_UPDATES: Dict[str, Dict[str, Any]] = {
    "SPY": {
        "status": POLICY_EXCLUDED,
        "fund_name": "SPDR S&P 500 ETF Trust",
        "evidence_source": "S&P 500 index methodology — broad large-cap US equities",
        "evidence_note": (
            "SPY tracks the S&P 500, which includes material conventional banks "
            "(e.g. JPM/BAC), tobacco (MO/PM), aerospace & defence (LMT/RTX/BA), "
            "and airlines among constituents. Fund-level exposure to USER_POLICY "
            "excluded categories → EXCLUDED (not auto-approved)."
        ),
        "excluded_categories_screened": [],
        "reason_codes": ["POLICY_ETF_EXCLUDED_EXPOSURES"],
    },
    "XLP": {
        "status": POLICY_EXCLUDED,
        "fund_name": "Consumer Staples Select Sector SPDR Fund",
        "evidence_source": "GICS Consumer Staples sector fund mandate",
        "evidence_note": (
            "XLP holds GICS Consumer Staples constituents, which materially include "
            "tobacco manufacturers (historically MO/PM among top holdings). "
            "Fund-level tobacco exposure → EXCLUDED under USER_POLICY."
        ),
        "excluded_categories_screened": [],
        "reason_codes": ["POLICY_ETF_EXCLUDED_TOBACCO_EXPOSURE"],
    },
    "SOXX": {
        "status": POLICY_ALLOWED,
        "fund_name": "iShares Semiconductor ETF",
        "evidence_source": "iShares SOXX methodology — PHLX Semiconductor Sector Index",
        "evidence_note": (
            "SOXX tracks a semiconductor industry index (chip designers/manufacturers/"
            "equipment). Constituents are semiconductor businesses outside USER_POLICY "
            "banking, airline, weapons-manufacturing, and tobacco exclusions. "
            "Fund-level industry screen → ALLOWED."
        ),
        "excluded_categories_screened": [CAT_BANKING, CAT_WEAPONS, CAT_TOBACCO, "airlines"],
        "reason_codes": ["POLICY_ETF_FUND_SCREEN_ALLOWED"],
    },
}


def apply_local_review_resolutions() -> Dict[str, Any]:
    """Write local evidence overlays for D2.4I review resolution. No production writes."""
    ensure_user_policy_templates()

    # Business overlays for CRM / PLTR
    try:
        biz = json.loads(BUSINESS_EVIDENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        biz = {"version": "D2.4H", "records": []}
    existing = {
        str(r.get("ticker", "")).upper(): i
        for i, r in enumerate(biz.get("records") or [])
        if isinstance(r, dict)
    }
    for ticker, rec in CRM_PLTR_OVERLAYS.items():
        if ticker in existing:
            biz["records"][existing[ticker]] = rec
        else:
            biz.setdefault("records", []).append(rec)
    biz["version"] = "D2.4I"
    BUSINESS_EVIDENCE_PATH.write_text(json.dumps(biz, indent=2), encoding="utf-8")

    # ETF fund evidence
    try:
        etf = json.loads(ETF_EVIDENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        etf = {"version": "D2.4H", "funds": {}}
    funds = etf.setdefault("funds", {})
    for ticker, rec in ETF_FUND_UPDATES.items():
        funds[ticker] = rec
    etf["version"] = "D2.4I"
    ETF_EVIDENCE_PATH.write_text(json.dumps(etf, indent=2), encoding="utf-8")

    return {
        "business_overlays_written": list(CRM_PLTR_OVERLAYS.keys()),
        "etf_overlays_written": list(ETF_FUND_UPDATES.keys()),
        "paths": {
            "business": str(BUSINESS_EVIDENCE_PATH),
            "etf": str(ETF_EVIDENCE_PATH),
        },
        "production_mutated": False,
    }


def review_resolution_summary() -> List[Dict[str, Any]]:
    rows = []
    for t, rec in {**CRM_PLTR_OVERLAYS, **{k: v for k, v in ETF_FUND_UPDATES.items()}}.items():
        rows.append(
            {
                "ticker": t,
                "resolved_status": rec.get("status"),
                "reason_codes": rec.get("reason_codes"),
                "evidence_source": rec.get("evidence_source"),
                "evidence_note": rec.get("evidence_note"),
            }
        )
    return rows
