"""Proposed universe / market-data remediation (Stage D2.4L) — APPROVAL REQUIRED.

Read-only proposal artifacts. Does NOT mutate production universe, registry JSON,
DB rows, or historical observation sessions unless an explicit apply path is
approved later.

Evidence date context: post-close scan d2_4l_20261026T233205Z (STALE_MIXED).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from app.config import DATA_CACHE_DIR
from app.services.ticker_integrity import CANONICAL_TICKER_ALIASES, PROPOSED_TICKER_ALIASES

PROPOSAL_PATH = DATA_CACHE_DIR / "observation" / "universe_remediation_proposal.json"

# ---------------------------------------------------------------------------
# Evidence-backed recommendations (do not apply without approval)
# ---------------------------------------------------------------------------

REMEDIATION_ITEMS: List[Dict[str, Any]] = [
    {
        "ticker": "EA",
        "recommendation": "RETIRE_NO_SUCCESSOR",
        "reason_code": "DELISTED_CASH_TAKE_PRIVATE",
        "canonical_active": None,
        "preserve_historical_ticker": "EA",
        "evidence": [
            {
                "source": "EA issuer press release",
                "url": "https://www.ea.com/news/ea-announces-completion-of-acquisition",
                "summary": (
                    "2026-08-04: Acquisition by PIF/Silver Lake/Affinity closed; "
                    "common stock ceased trading and will be delisted from Nasdaq; "
                    "$210 cash per share."
                ),
            },
            {
                "source": "SEC Form 8-K (Item 3.01 delisting notice)",
                "url": "https://www.sec.gov/Archives/edgar/data/712515/000114036126031157/ef20079099_8k.htm",
                "summary": (
                    "Closing Date 2026-08-04; Nasdaq asked to suspend trading before "
                    "open 2026-08-05 and file Form 25 for removal from listing."
                ),
            },
            {
                "source": "Local scan/cache",
                "summary": (
                    "d2_4l_20261026T233205Z: as_of=2026-08-04, INSUFFICIENT_DATA, "
                    "price_cache 1 bar ending 2026-08-04; Yahoo 5d empty/delisted."
                ),
            },
        ],
        "action_if_approved": [
            "Mark EA inactive / exclude from active observation universe",
            "Do not rewrite historical EA observation rows",
            "Do not add a successor equity ticker (cash deal, no public survivor)",
        ],
    },
    {
        "ticker": "WBD",
        "recommendation": "RETIRE_NO_EQUITY_SUCCESSOR",
        "reason_code": "DELISTED_CASH_MERGER",
        "canonical_active": None,
        "optional_new_listing_note": (
            "Acquirer lists as SKYD (NYSE) after Paramount/Skydance combination; "
            "WBD consideration was cash — SKYD is not an automatic share-for-share "
            "successor for WBD monitoring. Optional separate curated add of SKYD later."
        ),
        "preserve_historical_ticker": "WBD",
        "evidence": [
            {
                "source": "Nasdaq Trader Corporate Actions Alert ECA2026-710",
                "url": "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-710",
                "summary": (
                    "Merger closed prior to open 2026-10-06; last trading date "
                    "2026-10-05; suspension effective 2026-10-07; cash "
                    "$31.01666668/share."
                ),
            },
            {
                "source": "Skydance / Paramount completion release",
                "url": "https://ir.skydance.com/news-releases/news-release-details/paramount-completes-acquisition-warner-bros-discovery-creating",
                "summary": "WBD shares ceased trading on Nasdaq; Skydance trades NYSE:SKYD.",
            },
            {
                "source": "Local scan/cache",
                "summary": (
                    "d2_4l_20261026T233205Z: as_of=2026-10-05, INSUFFICIENT_DATA, "
                    "price_cache 1 bar ending 2026-10-05; Yahoo 5d empty/delisted."
                ),
            },
        ],
        "action_if_approved": [
            "Mark WBD inactive / exclude from active observation universe",
            "Do not rewrite historical WBD rows",
            "Optionally propose SKYD as a new universe candidate (separate approval)",
        ],
    },
    {
        "ticker": "SQ",
        "recommendation": "REPLACE_WITH_SUCCESSOR",
        "reason_code": "TICKER_SYMBOL_CHANGE",
        "canonical_active": "XYZ",
        "preserve_historical_ticker": "SQ",
        "evidence": [
            {
                "source": "Block, Inc. / Business Wire / Nasdaq press",
                "url": "https://www.nasdaq.com/press-release/block-announces-ticker-symbol-change-xyz-report-fourth-quarter-results-2025-01-09",
                "summary": (
                    "NYSE Class A ticker SQ→XYZ effective 2025-01-21; same issuer "
                    "(Block, Inc.); CUSIP unchanged."
                ),
            },
            {
                "source": "Local scan/cache",
                "summary": (
                    "SQ: MISSING_PRICE_DATA, no cache. XYZ: not in universe; Yahoo "
                    "history available through 2026-10-26."
                ),
            },
        ],
        "action_if_approved": [
            "Deactivate SQ in active universe (retain historical identity)",
            "Add/activate XYZ as canonical Block, Inc. listing",
            "Scanner alias SQ→XYZ for market-data fetch only (already proposed)",
        ],
    },
    {
        "ticker": "MMC",
        "recommendation": "REPLACE_WITH_SUCCESSOR",
        "reason_code": "TICKER_SYMBOL_CHANGE",
        "canonical_active": "MRSH",
        "preserve_historical_ticker": "MMC",
        "evidence": [
            {
                "source": "Marsh McLennan issuer announcement",
                "url": "https://www.marsh.com/en/corp/about/news/marsh-mclennan-to-change-nyse-symbol-to-mrsh.html",
                "summary": (
                    "NYSE ticker MMC→MRSH effective 2026-01-14; legal name/CUSIP "
                    "unchanged; still listed NYSE."
                ),
            },
            {
                "source": "SEC Form 8-K 2026-01-14",
                "url": "https://www.sec.gov/Archives/edgar/data/62709/000006270926000008/a8-kamendedbylaws11426.htm",
                "summary": "Securities table lists Common Stock trading symbol MRSH on NYSE.",
            },
            {
                "source": "Local scan/cache",
                "summary": "MMC: MISSING_PRICE_DATA / no Yahoo cache under MMC.",
            },
        ],
        "action_if_approved": [
            "Deactivate MMC in active universe (retain historical identity)",
            "Add/activate MRSH as canonical Marsh listing",
            "Add scanner alias MMC→MRSH for market-data fetch",
        ],
    },
    {
        "ticker": "QUALCOMM",
        "recommendation": "RETIRE_DUPLICATE",
        "reason_code": "INVALID_TICKER_DUPLICATE",
        "canonical_active": "QCOM",
        "preserve_historical_ticker": "QUALCOMM",
        "evidence": [
            {
                "source": "Universe registry + Nasdaq listing practice",
                "summary": (
                    "QCOM is the Nasdaq symbol for QUALCOMM Incorporated. "
                    "QUALCOMM is a company-name string, not a listing ticker."
                ),
            },
            {
                "source": "Local scan",
                "summary": (
                    "QUALCOMM: MISSING_PRICE_DATA. QCOM: FRESH as_of 2026-10-26 "
                    "WATCH in same scan."
                ),
            },
        ],
        "action_if_approved": [
            "Deactivate QUALCOMM; keep QCOM canonical",
            "Do not fetch Yahoo under QUALCOMM",
        ],
    },
]


def build_proposal_document() -> Dict[str, Any]:
    aliases = dict(CANONICAL_TICKER_ALIASES)
    return {
        "stage": "D2.4L",
        "status": "PROPOSED_AWAITING_APPROVAL",
        "production_mutated": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_scan": "d2_4l_20261026T233205Z",
        "strict_freshness_preserved": True,
        "historical_sessions_immutable": True,
        "items": REMEDIATION_ITEMS,
        "proposed_aliases_if_approved": aliases,
        "proposed_retire_from_active": ["EA", "WBD", "SQ", "MMC", "QUALCOMM"],
        "proposed_add_or_activate": ["XYZ", "MRSH"],
        "optional_curated_adds": ["SKYD"],
        "apply_requires": [
            "Explicit user approval",
            "Non-destructive: deactivate rather than delete rows",
            "No rewrite of historical observation evidence",
        ],
        "note": (
            "This file is a proposal only. Applying changes requires a separate "
            "approved apply step that is not implemented for automatic execution."
        ),
    }


def write_proposal(path: Optional[Path] = None) -> Path:
    dest = Path(path) if path else PROPOSAL_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = build_proposal_document()
    dest.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return dest


def proposed_inactive_tickers() -> Set[str]:
    return {str(x["ticker"]).upper() for x in REMEDIATION_ITEMS}


def proposed_successor_map() -> Dict[str, str]:
    return dict(CANONICAL_TICKER_ALIASES)


def filter_active_universe_for_proposal(
    tickers: Sequence[str],
    *,
    apply_proposed_exclusions: bool = True,
    include_proposed_successors: bool = True,
) -> Dict[str, Any]:
    """Dry-run canonical list for tests — does not touch production stores."""
    inactive = proposed_inactive_tickers() if apply_proposed_exclusions else set()
    successors = proposed_successor_map()
    base = [str(t).strip().upper() for t in tickers if str(t).strip()]
    kept = [t for t in base if t not in inactive]
    added: List[str] = []
    if include_proposed_successors:
        for src, dst in successors.items():
            if src in base or src in inactive:
                if dst not in kept:
                    kept.append(dst)
                    added.append(dst)
    return {
        "input_count": len(base),
        "excluded": sorted(set(base) & inactive),
        "added_successors": added,
        "active_count": len(kept),
        "active_tickers": kept,
        "production_mutated": False,
    }
