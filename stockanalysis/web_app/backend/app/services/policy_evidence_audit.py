"""Audit USER_POLICY classifications against the four exclusion rules (D2.4J).

Four exclusion categories (material involvement):
  1. Conventional banks / interest-based lending / related financial businesses
  2. Airlines
  3. Guns, weapons, defence, military-related activities
  4. Tobacco products

Confirms CRM/SOXX ALLOWED, PLTR/SPY/XLP EXCLUDED follow those rules with
documented evidence — does not invent Shariah certifications.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.d2_4i_review_resolution import (
    CRM_PLTR_OVERLAYS,
    ETF_FUND_UPDATES,
    apply_local_review_resolutions,
)
from app.services.universe_manager import universe_manager
from app.services.user_policy_eligibility import (
    CAT_AIRLINES,
    CAT_BANKING,
    CAT_TOBACCO,
    CAT_WEAPONS,
    POLICY_ALLOWED,
    POLICY_EXCLUDED,
    classify_user_policy,
)

FOUR_EXCLUSION_RULES = [
    {
        "id": 1,
        "category": CAT_BANKING,
        "label": "Conventional banks / interest-based lending / related financial businesses",
    },
    {
        "id": 2,
        "category": CAT_AIRLINES,
        "label": "Airlines",
    },
    {
        "id": 3,
        "category": CAT_WEAPONS,
        "label": "Guns, weapons, defence, military-related activities",
    },
    {
        "id": 4,
        "category": CAT_TOBACCO,
        "label": "Tobacco products",
    },
]

# Expected pilot classifications under review (Stage D2.4I evidence overlays).
PILOT_POLICY_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "CRM": {
        "expected_status": POLICY_ALLOWED,
        "entity": "Salesforce, Inc.",
        "rule_mapping": (
            "Primary business is enterprise CRM SaaS. Does not match any of the "
            "four exclusion categories (not a bank/lender, airline, weapons "
            "manufacturer, or tobacco producer)."
        ),
        "evidence_basis": "CRM_PLTR_OVERLAYS + universe_registry.name",
    },
    "PLTR": {
        "expected_status": POLICY_EXCLUDED,
        "entity": "Palantir Technologies Inc.",
        "rule_mapping": (
            "Material military, defence, and intelligence-related business "
            "activities map to exclusion rule 3 (guns/weapons/defence/military). "
            "Explicit USER_POLICY code MILITARY_DEFENCE_EXPOSURE."
        ),
        "evidence_basis": "EXPLICIT_ACTIVITY_EVIDENCE['PLTR'] + CRM_PLTR_OVERLAYS",
    },
    "SOXX": {
        "expected_status": POLICY_ALLOWED,
        "entity": "iShares Semiconductor ETF",
        "rule_mapping": (
            "Fund tracks semiconductor industry index. Fund-level screen documents "
            "no material banking, airline, weapons-manufacturing, or tobacco "
            "mandate — ALLOWED under all four exclusion rules at fund level."
        ),
        "evidence_basis": "ETF_FUND_UPDATES['SOXX'] methodology note",
    },
    "SPY": {
        "expected_status": POLICY_EXCLUDED,
        "entity": "SPDR S&P 500 ETF Trust",
        "rule_mapping": (
            "Tracks S&P 500 with material constituents in conventional banking "
            "(rule 1), tobacco (rule 4), aerospace & defence (rule 3), and airlines "
            "(rule 2). Fund-level exposure → EXCLUDED."
        ),
        "evidence_basis": "ETF_FUND_UPDATES['SPY'] + index methodology",
    },
    "XLP": {
        "expected_status": POLICY_EXCLUDED,
        "entity": "Consumer Staples Select Sector SPDR Fund",
        "rule_mapping": (
            "GICS Consumer Staples sector fund with material tobacco manufacturer "
            "holdings (rule 4). Fund-level tobacco exposure → EXCLUDED."
        ),
        "evidence_basis": "ETF_FUND_UPDATES['XLP'] + GICS staples mandate",
    },
}


def audit_pilot_policy_classifications(
    *,
    ensure_overlays: bool = True,
) -> Dict[str, Any]:
    """Re-classify CRM/PLTR/SOXX/SPY/XLP and map each to the four exclusion rules."""
    overlay_write = None
    if ensure_overlays:
        overlay_write = apply_local_review_resolutions()

    rows: List[Dict[str, Any]] = []
    for ticker, expect in PILOT_POLICY_EXPECTATIONS.items():
        stock = universe_manager.get_stock(ticker) or {}
        name = stock.get("name") or expect["entity"]
        sector = stock.get("sector") or (
            "ETFs" if ticker in ("SPY", "XLP", "SOXX") else "Technology"
        )
        industry = stock.get("industry") or (
            "Large Blend ETF"
            if ticker == "SPY"
            else "Sector Staples ETF"
            if ticker == "XLP"
            else "Semiconductor ETF"
            if ticker == "SOXX"
            else "Software - Application"
            if ticker == "CRM"
            else "Software - Infrastructure"
        )
        classified = classify_user_policy(
            ticker, name=name, sector=sector, industry=industry
        )
        status = classified.get("user_policy_status")
        matches = status == expect["expected_status"]
        overlay = CRM_PLTR_OVERLAYS.get(ticker) or ETF_FUND_UPDATES.get(ticker) or {}
        rows.append(
            {
                "ticker": ticker,
                "entity": expect["entity"],
                "expected_status": expect["expected_status"],
                "actual_status": status,
                "matches_expectation": matches,
                "reason_codes": classified.get("reason_codes"),
                "evidence_source": classified.get("evidence_source")
                or overlay.get("evidence_source"),
                "evidence_note": classified.get("evidence_note")
                or overlay.get("evidence_note"),
                "four_exclusion_rules_mapping": expect["rule_mapping"],
                "evidence_basis": expect["evidence_basis"],
                "registry": {
                    "name": name,
                    "sector": sector,
                    "industry": industry,
                },
            }
        )

    return {
        "four_exclusion_rules": FOUR_EXCLUSION_RULES,
        "overlay_write": overlay_write,
        "classifications": rows,
        "all_match_expectations": all(r["matches_expectation"] for r in rows),
        "summary": {
            "allowed": [r["ticker"] for r in rows if r["actual_status"] == POLICY_ALLOWED],
            "excluded": [
                r["ticker"] for r in rows if r["actual_status"] == POLICY_EXCLUDED
            ],
        },
    }
