"""Security Master & Autocomplete Search Service for Adaptive Trading V4.0.

Provides fast, fuzzy, typo-tolerant search across tickers, company names,
common aliases, and global equities beyond the baseline 28-stock universe.
"""
from typing import List, Dict, Any, Optional
import difflib
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models import WatchlistStock

# Cache file for remote search queries to ensure instant responses & offline resilience
SEARCH_CACHE_FILE = BACKEND_DIR / "data_cache" / "search_queries_cache.json"
SEARCH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

# In-memory query cache: {query: (timestamp, results)}
_SEARCH_MEMORY_CACHE: Dict[str, tuple] = {}
CACHE_TTL_SECONDS = 3600 * 24  # 24 hours

# Curated Master List of major equities, baseline universe, and aliases
CURATED_SECURITIES = [
    {
        "symbol": "ADBE",
        "name": "Adobe Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["adobe", "photoshop", "acrobat", "creative cloud", "illustrator", "premiere"],
    },
    {
        "symbol": "CRM",
        "name": "Salesforce, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["salesforce", "crm", "benioff", "slack", "tableaux", "cloud crm"],
    },
    {
        "symbol": "GOOGL",
        "name": "Alphabet Inc. (Class A)",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["google", "alphabet", "googl", "class a", "search", "youtube", "android"],
    },
    {
        "symbol": "GOOG",
        "name": "Alphabet Inc. (Class C)",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["google", "alphabet", "goog", "class c", "search", "youtube", "android"],
    },
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["apple", "iphone", "ipad", "mac", "tim cook"],
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["microsoft", "windows", "azure", "office", "xbox", "openai"],
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["nvidia", "geforce", "ai chips", "gpu", "jensen huang"],
    },
    {
        "symbol": "AMZN",
        "name": "Amazon.com, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Cyclical",
        "aliases": ["amazon", "aws", "prime", "ecommerce", "jeff bezos"],
    },
    {
        "symbol": "META",
        "name": "Meta Platforms, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["meta", "facebook", "fb", "instagram", "whatsapp", "zuckerberg"],
    },
    {
        "symbol": "TSLA",
        "name": "Tesla, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Cyclical",
        "aliases": ["tesla", "elon musk", "ev", "electric vehicles", "cybertruck"],
    },
    {
        "symbol": "BRK-B",
        "name": "Berkshire Hathaway Inc. (Class B)",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Financial Services",
        "aliases": ["berkshire", "berkshire hathaway", "warren buffett", "buffett", "charlie munger", "brk.b", "brkb"],
    },
    {
        "symbol": "DIS",
        "name": "The Walt Disney Company",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["disney", "walt disney", "marvel", "pixar", "espn", "star wars"],
    },
    {
        "symbol": "AVGO",
        "name": "Broadcom Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["broadcom", "avgo", "semiconductors"],
    },
    {
        "symbol": "AMD",
        "name": "Advanced Micro Devices, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["amd", "radeon", "ryzen", "lisa su"],
    },
    {
        "symbol": "INTC",
        "name": "Intel Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["intel", "chip", "pat gelsinger"],
    },
    {
        "symbol": "ORCL",
        "name": "Oracle Corporation",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["oracle", "database", "larry ellison", "cloud"],
    },
    {
        "symbol": "QCOM",
        "name": "QUALCOMM Incorporated",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["qualcomm", "snapdragon", "5g"],
    },
    {
        "symbol": "CRWD",
        "name": "CrowdStrike Holdings, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["crowdstrike", "falcon", "cybersecurity"],
    },
    {
        "symbol": "ANET",
        "name": "Arista Networks, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["arista", "networking", "ethernet"],
    },
    {
        "symbol": "MA",
        "name": "Mastercard Incorporated",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Financial Services",
        "aliases": ["mastercard", "payments", "credit card"],
    },
    {
        "symbol": "V",
        "name": "Visa Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Financial Services",
        "aliases": ["visa", "payments", "credit card"],
    },
    {
        "symbol": "NFLX",
        "name": "Netflix, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["netflix", "streaming", "movies"],
    },
    {
        "symbol": "COST",
        "name": "Costco Wholesale Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Defensive",
        "aliases": ["costco", "wholesale", "retail"],
    },
    {
        "symbol": "WMT",
        "name": "Walmart Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Defensive",
        "aliases": ["walmart", "retail"],
    },
    {
        "symbol": "JPM",
        "name": "JPMorgan Chase & Co.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Financial Services",
        "aliases": ["jpmorgan", "chase", "jamie dimon", "bank"],
    },
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "exchange": "NYSE Arca",
        "currency": "USD",
        "quote_type": "ETF",
        "sector": "Index Benchmark",
        "aliases": ["s&p 500", "spy", "benchmark", "sp500"],
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust Series 1",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "ETF",
        "sector": "Index Benchmark",
        "aliases": ["nasdaq 100", "qqq", "tech etf", "nasdaq"],
    },
    {
        "symbol": "UBER",
        "name": "Uber Technologies, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["uber", "rideshare", "delivery"],
    },
    {
        "symbol": "NOW",
        "name": "ServiceNow, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["servicenow", "it enterprise"],
    },
    {
        "symbol": "FICO",
        "name": "Fair Isaac Corporation",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["fico", "credit score", "fair isaac"],
    },
    {
        "symbol": "COHR",
        "name": "Coherent Corp.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["coherent", "lasers", "optics"],
    },
    {
        "symbol": "CELH",
        "name": "Celsius Holdings, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Defensive",
        "aliases": ["celsius", "energy drink"],
    },
    {
        "symbol": "ELF",
        "name": "e.l.f. Beauty, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Defensive",
        "aliases": ["elf", "elf beauty", "cosmetics"],
    },
    {
        "symbol": "RDDT",
        "name": "Reddit, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["reddit", "social media", "subreddits"],
    },
    {
        "symbol": "IONQ",
        "name": "IonQ, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["ionq", "quantum computing"],
    },
    {
        "symbol": "ASTS",
        "name": "AST SpaceMobile, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["ast spacemobile", "space satellite cellular"],
    },
    {
        "symbol": "MRVL",
        "name": "Marvell Technology, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["marvell", "semiconductors"],
    },
    {
        "symbol": "APP",
        "name": "AppLovin Corporation",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["applovin", "mobile ads"],
    },
    {
        "symbol": "GRAB",
        "name": "Grab Holdings Limited",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Technology",
        "aliases": ["grab", "ride hailing", "southeast asia"],
    },
    {
        "symbol": "NKE",
        "name": "NIKE, Inc.",
        "exchange": "NYSE",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Cyclical",
        "aliases": ["nike", "sneakers", "athletic"],
    },
    {
        "symbol": "ULTA",
        "name": "Ulta Beauty, Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Consumer Cyclical",
        "aliases": ["ulta", "ulta beauty", "cosmetics"],
    },
    {
        "symbol": "TWTR",
        "name": "Twitter, Inc. (Delisted / Private)",
        "exchange": "NYSE (Delisted)",
        "currency": "USD",
        "quote_type": "EQUITY",
        "sector": "Communication Services",
        "aliases": ["twitter", "tweet", "x corp"],
        "is_delisted": True,
        "delisted_reason": "Acquired by X Holdings Corp (Elon Musk) in October 2022 and taken private."
    },
]


def _fetch_yahoo_search(query: str) -> List[Dict[str, Any]]:
    """Query live Yahoo Finance Autocomplete API for global symbol lookup."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(query)}&quotesCount=10&newsCount=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            quotes = data.get("quotes", [])
            results = []
            for q in quotes:
                sym = q.get("symbol", "").strip().upper()
                if not sym or "^" in sym:  # filter out cryptic index symbols like ^GSPC
                    continue
                name = q.get("shortname") or q.get("longname") or sym
                exchange = q.get("exchDisp") or q.get("exchange", "UNKNOWN")
                quote_type = q.get("quoteType", "EQUITY")
                sector = q.get("sector") or q.get("sectorDisp") or "Equity"
                results.append({
                    "symbol": sym,
                    "name": name,
                    "exchange": exchange,
                    "currency": "USD",  # Default USD for major global search
                    "quote_type": quote_type,
                    "sector": sector,
                    "aliases": [sym.lower(), name.lower()],
                })
            return results
    except Exception as e:
        # Graceful fallback if network is offline or throttled
        return []


def search_symbols(query: str, db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Search for symbols by ticker, company name, partial text, or common aliases.
    
    Supports fuzzy matching, typo tolerance, global equity expansion,
    and returns watchlist enrollment status.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    query_lower = clean_query.lower()
    query_upper = clean_query.upper()

    # 1. Fetch user's current watchlist symbols and active screener universe
    watchlist_set = set()
    if db:
        try:
            stocks = db.query(WatchlistStock.ticker).all()
            watchlist_set = {s[0].upper() for s in stocks}
        except Exception:
            pass

    from app.services.universe_manager import universe_manager
    screener_stocks = universe_manager.get_all(include_inactive=False)
    screener_set = {s["ticker"] for s in screener_stocks}

    # 2. Check in-memory query cache
    now = time.time()
    if query_lower in _SEARCH_MEMORY_CACHE:
        cached_time, cached_results = _SEARCH_MEMORY_CACHE[query_lower]
        if now - cached_time < CACHE_TTL_SECONDS:
            # Re-apply watchlist and screener flags and return
            for r in cached_results:
                r["in_watchlist"] = r["symbol"] in watchlist_set
                r["in_screener"] = r["symbol"] in screener_set
                r["can_add_to_screener"] = not r["in_screener"]
            return cached_results

    # 3. Match against Curated Securities and Universe with scored relevance
    scored_candidates: Dict[str, Dict[str, Any]] = {}

    # Check active screener universe stocks
    for u in screener_stocks:
        sym = u["ticker"]
        sym_lower = sym.lower()
        name_lower = u.get("name", "").lower()
        score = 0
        match_reason = ""
        if query_upper == sym:
            score = 100
            match_reason = "Exact symbol match"
        elif sym_lower.startswith(query_lower):
            score = 92
            match_reason = "Symbol prefix match"
        elif name_lower.startswith(query_lower):
            score = 86
            match_reason = "Company name prefix match"
        elif query_lower in name_lower:
            score = 82
            match_reason = "Company name match"

        if score > 0:
            scored_candidates[sym] = {
                "symbol": sym,
                "name": u.get("name", sym),
                "exchange": u.get("exchange", "NASDAQ"),
                "currency": "USD",
                "quote_type": "EQUITY",
                "sector": u.get("sector", "Equity"),
                "is_delisted": False,
                "delisted_reason": None,
                "match_reason": match_reason,
                "score": score,
            }

    for item in CURATED_SECURITIES:
        sym = item["symbol"]
        sym_lower = sym.lower()
        name_lower = item["name"].lower()
        aliases = [a.lower() for a in item.get("aliases", [])]

        score = 0
        match_reason = ""

        # Exact ticker match
        if query_upper == sym:
            score = 100
            match_reason = "Exact symbol match"
        # Exact alias match (e.g. "Google" -> GOOGL/GOOG, "Facebook" -> META)
        elif query_lower in aliases:
            score = 95
            match_reason = f"Common alias match ('{query_lower}')"
        # Symbol prefix match (e.g. "Goo" -> GOOG, "Nvd" -> NVDA)
        elif sym_lower.startswith(query_lower):
            score = 90
            match_reason = "Symbol prefix match"
        # Name prefix match (e.g. "Alp" -> Alphabet)
        elif name_lower.startswith(query_lower):
            score = 85
            match_reason = "Company name prefix match"
        # Name contains query (e.g. "Disney" in The Walt Disney Company)
        elif query_lower in name_lower:
            score = 80
            match_reason = "Company name match"
        # Alias prefix match (e.g. "Goo" in "google")
        elif any(a.startswith(query_lower) for a in aliases):
            score = 78
            matched_alias = next(a for a in aliases if a.startswith(query_lower))
            match_reason = f"Alias prefix match ('{matched_alias}')"
        # Fuzzy match / typo tolerance (e.g. "Alpabet" -> Alphabet, "Microsft" -> Microsoft)
        else:
            all_tokens = [sym_lower, name_lower] + aliases
            close = difflib.get_close_matches(query_lower, all_tokens, n=1, cutoff=0.7)
            if close:
                score = 65
                match_reason = f"Fuzzy match with '{close[0]}'"

        if score > 0:
            scored_candidates[sym] = {
                "symbol": sym,
                "name": item["name"],
                "exchange": item["exchange"],
                "currency": item.get("currency", "USD"),
                "quote_type": item.get("quote_type", "EQUITY"),
                "sector": item.get("sector", "Equity"),
                "is_delisted": item.get("is_delisted", False),
                "delisted_reason": item.get("delisted_reason"),
                "match_reason": match_reason,
                "score": score,
            }

    # 4. If query length >= 2 and we need broader global coverage, query Yahoo search
    if len(clean_query) >= 2:
        try:
            remote_quotes = _fetch_yahoo_search(clean_query)
            for r in remote_quotes:
                sym = r["symbol"]
                if sym not in scored_candidates:
                    score = 60
                    sym_lower = sym.lower()
                    name_lower = r["name"].lower()
                    if query_upper == sym:
                        score = 98
                    elif sym_lower.startswith(query_lower):
                        score = 88
                    elif query_lower in name_lower:
                        score = 75

                    scored_candidates[sym] = {
                        "symbol": sym,
                        "name": r["name"],
                        "exchange": r["exchange"],
                        "currency": r["currency"],
                        "quote_type": r["quote_type"],
                        "sector": r["sector"],
                        "is_delisted": False,
                        "delisted_reason": None,
                        "match_reason": "Global market search match",
                        "score": score,
                    }
        except Exception:
            pass

    # 5. Sort by score descending, then symbol ascending
    ranked = sorted(scored_candidates.values(), key=lambda x: (-x["score"], x["symbol"]))

    # 6. Attach watchlist and screener boolean flags
    results = []
    for item in ranked[:20]:
        item_copy = dict(item)
        item_copy["in_watchlist"] = item_copy["symbol"] in watchlist_set
        item_copy["in_screener"] = item_copy["symbol"] in screener_set
        item_copy["can_add_to_screener"] = not item_copy["in_screener"]
        results.append(item_copy)

    # 7. Store in memory cache
    _SEARCH_MEMORY_CACHE[query_lower] = (now, results)

    return results
