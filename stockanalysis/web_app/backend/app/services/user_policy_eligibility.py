"""User-defined investment eligibility policy (Stage D2.4H).

USER_POLICY exclusions (material involvement):
  1. Conventional banks / interest-based lending / related financial businesses
  2. Airlines
  3. Guns, weapons, defence, military-related activities
  4. Tobacco products

This is NOT independent Shariah certification. Formal Shariah remains optional
(SHARIAH_STRICT mode). Classifications require evidence (registry industry,
explicit activity map, or fund-level ETF screen) — unknowns stay REVIEW REQUIRED.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.config import DATA_CACHE_DIR
from app.services.ticker_integrity import resolve_proposed_alias

MODE_USER_POLICY = "USER_POLICY"
MODE_SHARIAH_STRICT = "SHARIAH_STRICT"
MODE_LEGACY = "LEGACY"

POLICY_ALLOWED = "ALLOWED"
POLICY_EXCLUDED = "EXCLUDED"
POLICY_REVIEW = "REVIEW REQUIRED"

CAT_BANKING = "conventional_banking_lending"
CAT_AIRLINES = "airlines"
CAT_WEAPONS = "weapons_defence"
CAT_TOBACCO = "tobacco"

POLICY_DIR = DATA_CACHE_DIR / "user_policy"
BUSINESS_EVIDENCE_PATH = POLICY_DIR / "business_activity_evidence.json"
ETF_EVIDENCE_PATH = POLICY_DIR / "etf_fund_evidence.json"
PROPOSED_UNIVERSE_PATH = POLICY_DIR / "proposed_universe_additions.json"

# Explicit activity overrides with documented evidence notes (not sector-only guesses).
# Used when industry alone is insufficient or when payment networks must be distinguished.
EXPLICIT_ACTIVITY_EVIDENCE: Dict[str, Dict[str, Any]] = {
    "V": {
        "status": POLICY_ALLOWED,
        "business_type": "payment_network",
        "category_tags": [],
        "evidence_source": "universe_registry+user_policy",
        "evidence_note": (
            "Visa Inc. is classified as a payment-network / credit-services brand "
            "facilitating card transactions; not a conventional deposit-taking bank "
            "under the user's current policy."
        ),
        "reason_codes": ["POLICY_PAYMENT_NETWORK_ALLOWED"],
    },
    "MA": {
        "status": POLICY_ALLOWED,
        "business_type": "payment_network",
        "category_tags": [],
        "evidence_source": "universe_registry+user_policy",
        "evidence_note": (
            "Mastercard Incorporated operates a payment network; distinguished from "
            "conventional banks/lenders under USER_POLICY."
        ),
        "reason_codes": ["POLICY_PAYMENT_NETWORK_ALLOWED"],
    },
    "PYPL": {
        "status": POLICY_ALLOWED,
        "business_type": "payment_network",
        "category_tags": [],
        "evidence_source": "universe_registry+user_policy",
        "evidence_note": (
            "PayPal Holdings provides digital payments services; treated as payment "
            "network (not a conventional bank) under USER_POLICY."
        ),
        "reason_codes": ["POLICY_PAYMENT_NETWORK_ALLOWED"],
    },
    "COF": {
        "status": POLICY_EXCLUDED,
        "business_type": "consumer_lender",
        "category_tags": [CAT_BANKING],
        "evidence_source": "universe_registry+user_policy",
        "evidence_note": (
            "Capital One Financial is a major interest-based consumer lender / "
            "bank-like credit issuer — excluded under conventional banking/lending."
        ),
        "reason_codes": ["POLICY_EXCLUDED_BANKING_LENDING"],
    },
    "AXP": {
        "status": POLICY_EXCLUDED,
        "business_type": "card_issuer_lender",
        "category_tags": [CAT_BANKING],
        "evidence_source": "universe_registry+user_policy",
        "evidence_note": (
            "American Express issues cards and earns material interest/lending-related "
            "finance charges — excluded as related interest-based financial business."
        ),
        "reason_codes": ["POLICY_EXCLUDED_BANKING_LENDING"],
    },
    "MO": {
        "status": POLICY_EXCLUDED,
        "business_type": "tobacco",
        "category_tags": [CAT_TOBACCO],
        "evidence_source": "universe_registry.industry=Tobacco",
        "evidence_note": "Altria Group — tobacco products manufacturer.",
        "reason_codes": ["POLICY_EXCLUDED_TOBACCO"],
    },
    "PM": {
        "status": POLICY_EXCLUDED,
        "business_type": "tobacco",
        "category_tags": [CAT_TOBACCO],
        "evidence_source": "universe_registry.industry=Tobacco",
        "evidence_note": "Philip Morris International — tobacco products.",
        "reason_codes": ["POLICY_EXCLUDED_TOBACCO"],
    },
    "PLTR": {
        "status": POLICY_EXCLUDED,
        "business_type": "military_defence_intelligence_software",
        "category_tags": [CAT_WEAPONS],
        "evidence_source": "user_policy.explicit_exclusion=MILITARY_DEFENCE_EXPOSURE",
        "evidence_note": (
            "Palantir Technologies Inc. has material military, defence, and "
            "intelligence-related business activities. EXCLUDED under USER_POLICY "
            "weapons/defence/military rule. Remains research-visible in the scan "
            "universe as POLICY_EXCLUDED — not eligible for proposals or orders."
        ),
        "reason_codes": ["MILITARY_DEFENCE_EXPOSURE", "POLICY_EXCLUDED_WEAPONS_DEFENCE"],
    },
}

# Industry strings (exact, case-insensitive) → exclusion when supported by registry evidence.
INDUSTRY_EXCLUSION_RULES: List[Tuple[str, str, str]] = [
    # (industry_substring_or_exact, category, reason_code)
    ("tobacco", CAT_TOBACCO, "POLICY_EXCLUDED_TOBACCO"),
    ("banks - diversified", CAT_BANKING, "POLICY_EXCLUDED_BANKING_LENDING"),
    ("banks - regional", CAT_BANKING, "POLICY_EXCLUDED_BANKING_LENDING"),
    ("capital markets", CAT_BANKING, "POLICY_EXCLUDED_BANKING_LENDING"),
    ("aerospace & defense", CAT_WEAPONS, "POLICY_EXCLUDED_WEAPONS_DEFENCE"),
    ("aerospace and defense", CAT_WEAPONS, "POLICY_EXCLUDED_WEAPONS_DEFENCE"),
    ("airlines", CAT_AIRLINES, "POLICY_EXCLUDED_AIRLINES"),
    ("airline", CAT_AIRLINES, "POLICY_EXCLUDED_AIRLINES"),
]

# Industries that are clearly out of exclusion scope when no conflicting evidence.
INDUSTRY_CLEAR_ALLOWED_PREFIXES = (
    "semiconductor",
    "software",
    "internet",
    "biotechnology",
    "drug manufacturers",
    "medical",
    "diagnostics",
    "oil & gas",
    "utilities",
    "specialty chemicals",
    "steel",
    "gold",
    "copper",
    "railroads",
    "restaurants",
    "apparel",
    "auto manufacturers",
    "auto parts",
    "footwear",
    "home improvement",
    "discount stores",
    "household & personal",
    "beverages - non-alcoholic",
    "packaged foods",
    "grocery",
    "telecom",
    "entertainment",
    "electronic gaming",
    "communication equipment",
    "computer hardware",
    "consumer electronics",
    "information technology",
    "scientific & technical",
    "semiconductor equipment",
    "building products",
    "farm & heavy",
    "specialty industrial",
    "waste management",
    "integrated freight",
    "reit",
    "insurance - property",
    "insurance brokers",
    "financial data & stock exchanges",
    "healthcare plans",
    "lodging",
    "residential construction",
    "farm products",
    "confectioners",
    "agricultural inputs",
    "chemicals",
)


def _canonical(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    return str(resolve_proposed_alias(raw).get("proposed_canonical") or raw).upper()


def ensure_user_policy_templates() -> Dict[str, str]:
    """Create empty local evidence templates (no fabricated VERIFIED/ALLOWED rows)."""
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    created = {}
    if not BUSINESS_EVIDENCE_PATH.exists():
        BUSINESS_EVIDENCE_PATH.write_text(
            json.dumps(
                {
                    "version": "D2.4H",
                    "mode": MODE_USER_POLICY,
                    "description": (
                        "Optional per-ticker business activity evidence overlays. "
                        "Unknown tickers without registry/explicit evidence remain REVIEW REQUIRED."
                    ),
                    "records": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        created["business_activity"] = str(BUSINESS_EVIDENCE_PATH)
    if not ETF_EVIDENCE_PATH.exists():
        ETF_EVIDENCE_PATH.write_text(
            json.dumps(
                {
                    "version": "D2.4H",
                    "description": (
                        "Fund-level ETF screening evidence. Broad ETFs (SPY, XLP, …) "
                        "remain REVIEW REQUIRED until holdings/fund screen is documented."
                    ),
                    "funds": {
                        "SPUS": {
                            "status": POLICY_ALLOWED,
                            "fund_name": "SP Funds S&P 500 Sharia Industry Exclusions ETF",
                            "evidence_source": "fund_methodology_name+user_policy",
                            "evidence_note": (
                                "SPUS is an S&P 500 industry-exclusions ETF marketed with "
                                "Sharia industry screens. Treated as fund-level USER_POLICY "
                                "eligible pending ongoing holdings review; not a certification "
                                "of independent AAOIFI Shariah VERIFIED status."
                            ),
                            "excluded_categories_screened": [
                                CAT_BANKING,
                                CAT_WEAPONS,
                                CAT_TOBACCO,
                                CAT_AIRLINES,
                            ],
                            "reason_codes": ["POLICY_ETF_FUND_SCREEN_ALLOWED"],
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        created["etf_fund"] = str(ETF_EVIDENCE_PATH)
    if not PROPOSED_UNIVERSE_PATH.exists():
        PROPOSED_UNIVERSE_PATH.write_text(
            json.dumps(
                {
                    "version": "D2.4H",
                    "production_mutated": False,
                    "proposed_additions": [
                        {
                            "ticker": "SPUS",
                            "name": "SP Funds S&P 500 Sharia Industry Exclusions ETF",
                            "exchange": "NYSE",
                            "sector": "ETFs",
                            "industry": "Large Blend ETF",
                            "source": "user_policy_d2_4h",
                            "duplicate_of": None,
                            "data_checks": {
                                "in_current_universe": False,
                                "notes": (
                                    "Propose add after Yahoo/Alpaca symbol validation; "
                                    "do not write production registry in D2.4H."
                                ),
                            },
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        created["proposed_universe"] = str(PROPOSED_UNIVERSE_PATH)
    return created


def load_etf_fund_evidence(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    ensure_user_policy_templates()
    p = path or ETF_EVIDENCE_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    funds = raw.get("funds") if isinstance(raw, dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in (funds or {}).items():
        if isinstance(v, dict):
            out[_canonical(k)] = dict(v)
    return out


def load_business_overlays(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    ensure_user_policy_templates()
    p = path or BUSINESS_EVIDENCE_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = raw.get("records") if isinstance(raw, dict) else []
    out: Dict[str, Dict[str, Any]] = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        t = _canonical(rec.get("ticker") or "")
        if t:
            out[t] = dict(rec)
    return out


def load_proposed_universe_additions() -> Dict[str, Any]:
    ensure_user_policy_templates()
    try:
        return json.loads(PROPOSED_UNIVERSE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"proposed_additions": [], "production_mutated": False}


def _is_etf(sector: str, industry: str, name: str) -> bool:
    blob = f"{sector} {industry} {name}".upper()
    return "ETF" in blob or sector.strip().upper() in ("ETFS", "ETF")


def _match_industry_exclusion(industry: str) -> Optional[Tuple[str, str]]:
    ind = (industry or "").strip().lower()
    if not ind:
        return None
    for needle, cat, code in INDUSTRY_EXCLUSION_RULES:
        if needle in ind or ind == needle:
            return cat, code
    return None


def _industry_clearly_allowed(industry: str) -> bool:
    ind = (industry or "").strip().lower()
    if not ind:
        return False
    return any(ind.startswith(p) or p in ind for p in INDUSTRY_CLEAR_ALLOWED_PREFIXES)


def classify_user_policy(
    ticker: str,
    *,
    name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    etf_evidence: Optional[Dict[str, Dict[str, Any]]] = None,
    business_overlays: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify a ticker under USER_POLICY. Never fabricates ALLOWED for unknowns."""
    t = _canonical(ticker)
    name = (name or "").strip()
    sector = (sector or "").strip()
    industry = (industry or "").strip()
    etf_evidence = etf_evidence if etf_evidence is not None else load_etf_fund_evidence()
    business_overlays = (
        business_overlays if business_overlays is not None else load_business_overlays()
    )

    # 1) Explicit curated activity evidence
    if t in EXPLICIT_ACTIVITY_EVIDENCE:
        exp = EXPLICIT_ACTIVITY_EVIDENCE[t]
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": exp["status"],
            "business_type": exp.get("business_type"),
            "category_tags": list(exp.get("category_tags") or []),
            "reason_codes": list(exp.get("reason_codes") or []),
            "evidence_source": exp.get("evidence_source"),
            "evidence_note": exp.get("evidence_note"),
            "sector": sector or None,
            "industry": industry or None,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": exp["status"] == POLICY_ALLOWED,
            "research_visible": True,
        }

    # 2) File overlays (manual reviews)
    if t in business_overlays:
        ov = business_overlays[t]
        status = str(ov.get("status") or POLICY_REVIEW).strip().upper()
        if status in ("EXCLUDE", "EXCLUDED"):
            status = POLICY_EXCLUDED
        elif status in ("ALLOW", "ALLOWED"):
            status = POLICY_ALLOWED
        else:
            status = POLICY_REVIEW
        note = str(ov.get("evidence_note") or ov.get("rationale") or "").strip()
        if status != POLICY_REVIEW and not note:
            status = POLICY_REVIEW
            note = "Overlay missing evidence_note — fail-closed to REVIEW REQUIRED"
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": status,
            "business_type": ov.get("business_type") or "overlay",
            "category_tags": list(ov.get("category_tags") or []),
            "reason_codes": list(ov.get("reason_codes") or ["POLICY_OVERLAY"]),
            "evidence_source": ov.get("evidence_source") or "business_activity_evidence.json",
            "evidence_note": note,
            "sector": sector or None,
            "industry": industry or None,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": status == POLICY_ALLOWED,
            "research_visible": True,
        }

    # 3) ETFs — require fund-level evidence; never auto-approve broad ETFs
    if _is_etf(sector, industry, name):
        fund = etf_evidence.get(t)
        if fund:
            status = str(fund.get("status") or POLICY_REVIEW).strip().upper()
            if status in ("ALLOW", "ALLOWED"):
                status = POLICY_ALLOWED
            elif status in ("EXCLUDE", "EXCLUDED"):
                status = POLICY_EXCLUDED
            else:
                status = POLICY_REVIEW
            note = str(fund.get("evidence_note") or "").strip()
            if status == POLICY_ALLOWED and not note:
                status = POLICY_REVIEW
                note = "ETF fund evidence missing evidence_note"
            return {
                "ticker": t,
                "eligibility_mode": MODE_USER_POLICY,
                "user_policy_status": status,
                "business_type": "etf",
                "category_tags": list(fund.get("excluded_categories_screened") or []),
                "reason_codes": list(
                    fund.get("reason_codes")
                    or (
                        ["POLICY_ETF_FUND_SCREEN_ALLOWED"]
                        if status == POLICY_ALLOWED
                        else ["POLICY_ETF_REVIEW_REQUIRED"]
                    )
                ),
                "evidence_source": fund.get("evidence_source") or "etf_fund_evidence.json",
                "evidence_note": note or fund.get("fund_name") or "",
                "sector": sector or None,
                "industry": industry or None,
                "name": name or None,
                "sector_used_as_sole_basis": False,
                "proposal_permitted": status == POLICY_ALLOWED,
                "research_visible": True,
            }
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": POLICY_REVIEW,
            "business_type": "etf",
            "category_tags": [],
            "reason_codes": ["POLICY_ETF_HOLDINGS_UNSCREENED"],
            "evidence_source": "universe_registry.sector=ETFs",
            "evidence_note": (
                f"ETF '{t}' has no fund-level / holdings screen on file. "
                "Broad ETFs (e.g. SPY, XLP) are not auto-approved under USER_POLICY."
            ),
            "sector": sector or None,
            "industry": industry or None,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": False,
            "research_visible": True,
        }

    # 4) Industry-backed exclusions (evidence = registry industry string)
    if industry:
        matched = _match_industry_exclusion(industry)
        if matched:
            cat, code = matched
            return {
                "ticker": t,
                "eligibility_mode": MODE_USER_POLICY,
                "user_policy_status": POLICY_EXCLUDED,
                "business_type": industry,
                "category_tags": [cat],
                "reason_codes": [code],
                "evidence_source": f"universe_registry.industry={industry}",
                "evidence_note": f"Registry industry '{industry}' maps to USER_POLICY exclusion '{cat}'.",
                "sector": sector or None,
                "industry": industry,
                "name": name or None,
                "sector_used_as_sole_basis": False,
                "proposal_permitted": False,
                "research_visible": True,
            }

    # 5) Credit Services without explicit override → REVIEW (do not assume bank vs network)
    if industry.lower() == "credit services":
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": POLICY_REVIEW,
            "business_type": "credit_services_unclassified",
            "category_tags": [],
            "reason_codes": ["POLICY_CREDIT_SERVICES_REVIEW"],
            "evidence_source": f"universe_registry.industry={industry}",
            "evidence_note": (
                "Credit Services industry requires explicit payment-network vs lender "
                "classification; not auto-allowed or auto-excluded."
            ),
            "sector": sector or None,
            "industry": industry,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": False,
            "research_visible": True,
        }

    # 6) Insurance - Diversified / Asset Management / ambiguous Financial → REVIEW
    if industry.lower() in (
        "insurance - diversified",
        "asset management",
        "conglomerates",
    ) or industry.lower() == "equity":
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": POLICY_REVIEW,
            "business_type": industry or "ambiguous",
            "category_tags": [],
            "reason_codes": ["POLICY_AMBIGUOUS_BUSINESS_REVIEW"],
            "evidence_source": f"universe_registry.industry={industry}" if industry else "missing_industry",
            "evidence_note": (
                f"Business classification '{industry or 'unknown'}' is ambiguous under "
                "USER_POLICY — manual review required; not auto-eligible."
            ),
            "sector": sector or None,
            "industry": industry or None,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": False,
            "research_visible": True,
        }

    # 7) Clear allowed industries (evidence = specific industry, not bare sector)
    if industry and _industry_clearly_allowed(industry):
        return {
            "ticker": t,
            "eligibility_mode": MODE_USER_POLICY,
            "user_policy_status": POLICY_ALLOWED,
            "business_type": industry,
            "category_tags": [],
            "reason_codes": ["POLICY_INDUSTRY_OUTSIDE_EXCLUSIONS"],
            "evidence_source": f"universe_registry.industry={industry}",
            "evidence_note": (
                f"Industry '{industry}' has no material match to banking/lending, "
                "airlines, weapons/defence, or tobacco exclusions."
            ),
            "sector": sector or None,
            "industry": industry,
            "name": name or None,
            "sector_used_as_sole_basis": False,
            "proposal_permitted": True,
            "research_visible": True,
        }

    # 8) Fail closed — unknown / missing industry
    return {
        "ticker": t,
        "eligibility_mode": MODE_USER_POLICY,
        "user_policy_status": POLICY_REVIEW,
        "business_type": industry or "unknown",
        "category_tags": [],
        "reason_codes": ["POLICY_UNKNOWN_CLASSIFICATION"],
        "evidence_source": "insufficient",
        "evidence_note": (
            "Insufficient business-activity evidence to confirm USER_POLICY eligibility; "
            "REVIEW REQUIRED (not auto-approved)."
        ),
        "sector": sector or None,
        "industry": industry or None,
        "name": name or None,
        "sector_used_as_sole_basis": bool(sector and not industry),
        "proposal_permitted": False,
        "research_visible": True,
    }


def classify_universe_user_policy(
    stocks: Sequence[Dict[str, Any]],
    *,
    etf_evidence: Optional[Dict[str, Dict[str, Any]]] = None,
    business_overlays: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify a stock list; returns rows + counts. Does not mutate production."""
    etf_evidence = etf_evidence if etf_evidence is not None else load_etf_fund_evidence()
    business_overlays = (
        business_overlays if business_overlays is not None else load_business_overlays()
    )
    rows = []
    counts = {
        POLICY_ALLOWED: 0,
        POLICY_EXCLUDED: 0,
        POLICY_REVIEW: 0,
    }
    for s in stocks:
        if not s:
            continue
        t = str(s.get("ticker") or "").strip().upper()
        if not t:
            continue
        row = classify_user_policy(
            t,
            name=s.get("name"),
            sector=s.get("sector"),
            industry=s.get("industry"),
            etf_evidence=etf_evidence,
            business_overlays=business_overlays,
        )
        row["v40_signal"] = s.get("v40_signal") or s.get("signal") or ""
        rows.append(row)
        counts[row["user_policy_status"]] = counts.get(row["user_policy_status"], 0) + 1

    return {
        "mode": MODE_USER_POLICY,
        "total": len(rows),
        "counts": counts,
        "rows": rows,
        "production_mutated": False,
        "shariah_certification": False,
    }


def assert_user_policy_order_permitted(
    ticker: str,
    *,
    name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> Dict[str, Any]:
    """Fail-closed gate for proposals and broker submission under USER_POLICY.

    EXCLUDED / REVIEW REQUIRED tickers (e.g. PLTR / MILITARY_DEFENCE_EXPOSURE)
    must not generate proposals or reach broker submit.
    Research visibility is unchanged (research_visible remains True on classify).
    """
    policy = classify_user_policy(
        ticker, name=name, sector=sector, industry=industry
    )
    status = str(policy.get("user_policy_status") or POLICY_REVIEW)
    permitted = status == POLICY_ALLOWED and bool(policy.get("proposal_permitted"))
    return {
        "ticker": policy.get("ticker") or _canonical(ticker),
        "permitted": permitted,
        "user_policy_status": status,
        "reason_codes": list(policy.get("reason_codes") or []),
        "evidence_note": policy.get("evidence_note"),
        "research_visible": bool(policy.get("research_visible", True)),
        "blocking_reason": (
            None
            if permitted
            else (
                f"USER_POLICY {status}: "
                f"{', '.join(policy.get('reason_codes') or []) or status}"
            )
        ),
        "policy": policy,
    }


def propose_spus_addition(
    *,
    current_tickers: Sequence[str],
) -> Dict[str, Any]:
    """Propose SPUS for monitored universe without writing production registry."""
    ensure_user_policy_templates()
    present = {_canonical(t) for t in current_tickers}
    duplicate = "SPUS" in present
    proposal = {
        "ticker": "SPUS",
        "action": "NO_OP_ALREADY_PRESENT" if duplicate else "PROPOSE_ADD",
        "duplicate": duplicate,
        "production_mutated": False,
        "name": "SP Funds S&P 500 Sharia Industry Exclusions ETF",
        "data_checks": {
            "in_universe": duplicate,
            "etf_fund_evidence_present": "SPUS" in load_etf_fund_evidence(),
            "requires_yahoo_alpaca_symbol_validation": not duplicate,
        },
        "notes": (
            "SPUS already in universe — no add required."
            if duplicate
            else "Proposed local addition only; registry/DB not written in D2.4H."
        ),
    }
    # Persist proposal file (local cache only)
    payload = load_proposed_universe_additions()
    payload["last_check"] = proposal
    payload["production_mutated"] = False
    PROPOSED_UNIVERSE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return proposal
