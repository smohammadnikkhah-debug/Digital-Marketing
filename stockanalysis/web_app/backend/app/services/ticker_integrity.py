"""Universe ticker integrity helpers (Stage D2.4F / D2.4L).

Canonical alias map is applied for membership / eligibility / reporting
normalization after D2.4L approval. Does not rewrite historical OHLCV files
or substitute successor bars into legacy ticker strategy history.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


# Canonical listing aliases (approved D2.4L). Used for identity normalization.
# Market-data caches remain keyed by the symbol actually fetched (successors
# under XYZ/MRSH/QCOM); legacy SQ/MMC/QUALCOMM OHLCV files are left untouched.
CANONICAL_TICKER_ALIASES: Dict[str, str] = {
    "SQ": "XYZ",  # Block, Inc. NYSE ticker change effective 2025-01-21
    "MMC": "MRSH",  # Marsh McLennan NYSE ticker change effective 2026-01-14
    "QUALCOMM": "QCOM",  # company name mistakenly used as ticker
}

# Backward-compatible name
PROPOSED_TICKER_ALIASES: Dict[str, str] = CANONICAL_TICKER_ALIASES

# Proposed retirements from the *active* evaluable universe (history preserved).
PROPOSED_RETIRE_FROM_ACTIVE: Dict[str, str] = {
    "EA": (
        "Cash take-private closed 2026-08-04 (PIF/Silver Lake/Affinity); "
        "Nasdaq delisting Form 25; no public equity successor."
    ),
    "WBD": (
        "Cash merger into Skydance/Paramount closed 2026-10-06; last trade "
        "2026-10-05; Nasdaq suspension 2026-10-07. Cash consideration — SKYD "
        "is not an automatic share-for-share successor for WBD monitoring."
    ),
    "SQ": "Ticker changed to XYZ (same issuer); deactivate SQ after XYZ activated.",
    "MMC": "Ticker changed to MRSH (same issuer); deactivate MMC after MRSH activated.",
    "QUALCOMM": "Invalid listing symbol; duplicate of QCOM.",
}


def resolve_canonical_ticker(ticker: str) -> Dict[str, Any]:
    """Resolve listing alias to canonical symbol (identity only; no OHLCV rewrite)."""
    raw = str(ticker or "").strip().upper()
    canonical = CANONICAL_TICKER_ALIASES.get(raw, raw)
    return {
        "input": raw,
        "canonical": canonical,
        "proposed_canonical": canonical,
        "alias_applied": canonical != raw,
        "ohlcv_rewritten": False,
        "mutate_production": False,
    }


def resolve_proposed_alias(ticker: str) -> Dict[str, Any]:
    """Compat wrapper → resolve_canonical_ticker."""
    return resolve_canonical_ticker(ticker)


def investigate_problem_tickers(
    *,
    universe_tickers: Sequence[str],
    registry_records: Optional[Dict[str, Dict[str, Any]]] = None,
    yahoo_bars: Optional[Dict[str, int]] = None,
    alpaca_quote_ok: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Investigate EA / WBD / SQ / MMC / QUALCOMM integrity against current universe."""
    registry_records = registry_records or {}
    yahoo_bars = yahoo_bars or {}
    alpaca_quote_ok = alpaca_quote_ok or {}
    universe_set = {str(t).strip().upper() for t in universe_tickers}

    findings: List[Dict[str, Any]] = []

    findings.append(
        {
            "ticker": "EA",
            "name_in_registry": (registry_records.get("EA") or {}).get("name"),
            "present_in_universe": "EA" in universe_set,
            "duplicate_of": None,
            "proposed_action": "RETIRE_NO_SUCCESSOR",
            "proposed_canonical": None,
            "historical_alias": None,
            "yahoo_bars": yahoo_bars.get("EA"),
            "alpaca_quote_ok": alpaca_quote_ok.get("EA"),
            "notes": PROPOSED_RETIRE_FROM_ACTIVE["EA"],
            "mutate_production": False,
        }
    )

    findings.append(
        {
            "ticker": "WBD",
            "name_in_registry": (registry_records.get("WBD") or {}).get("name"),
            "present_in_universe": "WBD" in universe_set,
            "duplicate_of": None,
            "proposed_action": "RETIRE_NO_EQUITY_SUCCESSOR",
            "proposed_canonical": None,
            "optional_new_listing": "SKYD",
            "yahoo_bars": yahoo_bars.get("WBD"),
            "alpaca_quote_ok": alpaca_quote_ok.get("WBD"),
            "notes": PROPOSED_RETIRE_FROM_ACTIVE["WBD"],
            "mutate_production": False,
        }
    )

    findings.append(
        {
            "ticker": "SQ",
            "name_in_registry": (registry_records.get("SQ") or {}).get("name"),
            "present_in_universe": "SQ" in universe_set,
            "duplicate_of": None,
            "proposed_action": "ALIAS_TO_XYZ",
            "proposed_canonical": "XYZ",
            "historical_alias": "SQ → XYZ (Block, Inc.)",
            "xyz_also_present": "XYZ" in universe_set,
            "yahoo_bars": yahoo_bars.get("SQ"),
            "yahoo_bars_canonical": yahoo_bars.get("XYZ"),
            "alpaca_quote_ok": alpaca_quote_ok.get("SQ"),
            "alpaca_quote_ok_canonical": alpaca_quote_ok.get("XYZ"),
            "notes": (
                "Block, Inc. NYSE ticker SQ→XYZ effective 2025-01-21. "
                "Do not rewrite historical SQ scan rows; propose deactivate SQ "
                "and activate XYZ."
            ),
            "mutate_production": False,
        }
    )

    findings.append(
        {
            "ticker": "MMC",
            "name_in_registry": (registry_records.get("MMC") or {}).get("name"),
            "present_in_universe": "MMC" in universe_set,
            "duplicate_of": None,
            "proposed_action": "ALIAS_TO_MRSH",
            "proposed_canonical": "MRSH",
            "historical_alias": "MMC → MRSH (Marsh McLennan / Marsh)",
            "mrsh_also_present": "MRSH" in universe_set,
            "yahoo_bars": yahoo_bars.get("MMC"),
            "yahoo_bars_canonical": yahoo_bars.get("MRSH"),
            "alpaca_quote_ok": alpaca_quote_ok.get("MMC"),
            "alpaca_quote_ok_canonical": alpaca_quote_ok.get("MRSH"),
            "notes": (
                "Marsh McLennan NYSE ticker MMC→MRSH effective 2026-01-14 "
                "(issuer + SEC 8-K). Not a delisting; replace symbol."
            ),
            "mutate_production": False,
        }
    )

    findings.append(
        {
            "ticker": "QUALCOMM",
            "name_in_registry": (registry_records.get("QUALCOMM") or {}).get("name"),
            "present_in_universe": "QUALCOMM" in universe_set,
            "duplicate_of": "QCOM",
            "proposed_action": "RETIRE_DUPLICATE_KEEP_QCOM",
            "proposed_canonical": "QCOM",
            "historical_alias": "QUALCOMM is not a valid listing symbol",
            "qcom_also_present": "QCOM" in universe_set,
            "yahoo_bars": yahoo_bars.get("QUALCOMM"),
            "yahoo_bars_canonical": yahoo_bars.get("QCOM"),
            "alpaca_quote_ok": alpaca_quote_ok.get("QUALCOMM"),
            "alpaca_quote_ok_canonical": alpaca_quote_ok.get("QCOM"),
            "notes": (
                "QUALCOMM entry duplicates QCOM (QUALCOMM Incorporated). "
                "Propose deactivate QUALCOMM; retain QCOM."
            ),
            "mutate_production": False,
        }
    )

    qcom = registry_records.get("QCOM") or {}
    correction_plan = [
        {
            "id": "EA_RETIRE",
            "action": "Deactivate EA from active universe; preserve historical rows; no successor ticker.",
            "risk": "low",
            "applies_without_approval": False,
        },
        {
            "id": "WBD_RETIRE",
            "action": "Deactivate WBD from active universe; preserve historical rows; optional later curated add of SKYD.",
            "risk": "low",
            "applies_without_approval": False,
        },
        {
            "id": "SQ_TO_XYZ",
            "action": "Add scanner alias SQ→XYZ; activate XYZ; deactivate SQ; keep SQ historical rows immutable.",
            "risk": "low",
            "applies_without_approval": False,
        },
        {
            "id": "MMC_TO_MRSH",
            "action": "Add scanner alias MMC→MRSH; activate MRSH; deactivate MMC; keep MMC historical rows immutable.",
            "risk": "low",
            "applies_without_approval": False,
        },
        {
            "id": "QUALCOMM_RETIRE",
            "action": "Mark QUALCOMM inactive; retain QCOM as canonical.",
            "risk": "low",
            "applies_without_approval": False,
        },
    ]

    return {
        "read_only": True,
        "production_mutated": False,
        "proposed_aliases": dict(PROPOSED_TICKER_ALIASES),
        "proposed_retire_from_active": dict(PROPOSED_RETIRE_FROM_ACTIVE),
        "qcom_name": qcom.get("name"),
        "findings": findings,
        "correction_plan": correction_plan,
    }
