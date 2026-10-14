"""SEC EDGAR Primary-Source Verification Adapter for US-Listed Equities.

Provides direct regulatory verification of SEC 10-K and 10-Q filings:
- Resolves Ticker -> CIK mapping
- Fetches official XBRL company facts from SEC EDGAR API
- Extracts filing dates, fiscal period end dates, and SEC accession numbers
- Provides point-in-time filing availability to eliminate look-ahead bias
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.config import BACKEND_DIR

SEC_CACHE_DIR = BACKEND_DIR / "data_cache" / "sec_edgar"
SEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)

CIK_CACHE_FILE = SEC_CACHE_DIR / "company_tickers.json"
CACHE_TTL_DAYS = 7  # CIK mapping changes infrequently
FACTS_TTL_HOURS = 24

SEC_USER_AGENT = "AdaptiveTradingResearch/4.0 (compliance@adaptivetrading.local)"


class SecEdgarAdapter:
    """Primary-source regulatory verification adapter connecting to SEC EDGAR."""

    def __init__(self):
        self._ticker_to_cik: Dict[str, str] = {}
        self._load_cik_mapping()

    def _load_cik_mapping(self):
        """Load or download SEC Ticker -> CIK mapping."""
        # Try local cache first
        if CIK_CACHE_FILE.exists():
            try:
                mtime = CIK_CACHE_FILE.stat().st_mtime
                if time.time() - mtime < CACHE_TTL_DAYS * 86400:
                    with open(CIK_CACHE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._parse_cik_data(data)
                        return
            except Exception:
                pass

        # Fetch from SEC EDGAR
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                with open(CIK_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                self._parse_cik_data(data)
        except Exception as e:
            # Fallback hardcoded for common tickers
            self._ticker_to_cik = {
                "GOOGL": "0001652044",
                "GOOG": "0001652044",
                "AAPL": "0000320193",
                "MSFT": "0000789019",
                "NVDA": "0001045810",
                "AMZN": "0001018724",
                "META": "0001326801",
                "TSLA": "0001318605",
                "DIS": "0001744489",
                "NFLX": "0001065280",
                "COST": "0000909832",
                "AMD": "0000002488",
                "INTC": "0000050863",
                "ORCL": "0001341439",
                "QCOM": "0000804328",
                "CRWD": "0001535527",
                "ANET": "0001596532",
                "MA": "0001141391",
                "V": "0001403161",
                "UBER": "0001543151",
            }

    def _parse_cik_data(self, data: Dict[str, Any]):
        mapping = {}
        for entry in data.values():
            sym = str(entry.get("ticker", "")).strip().upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            if sym and cik:
                mapping[sym] = cik
        self._ticker_to_cik = mapping

    def get_cik(self, ticker: str) -> Optional[str]:
        """Resolve US ticker to 10-digit zero-padded SEC CIK."""
        return self._ticker_to_cik.get(ticker.strip().upper())

    def get_company_facts(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch official US-GAAP XBRL company facts from SEC EDGAR API with disk caching."""
        ticker = ticker.strip().upper()
        cik = self.get_cik(ticker)
        if not cik:
            return None

        cache_path = SEC_CACHE_DIR / f"facts_{ticker}.json"
        if cache_path.exists():
            try:
                mtime = cache_path.stat().st_mtime
                if time.time() - mtime < FACTS_TTL_HOURS * 3600:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return json.load(f)
            except Exception:
                pass

        # Query SEC EDGAR API
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                return data
        except Exception:
            return None

    def get_all_filings(self, ticker: str) -> List[Dict[str, Any]]:
        """Extract all verified chronologically ordered 10-K and 10-Q regulatory filing submissions."""
        ticker = ticker.strip().upper()
        facts_data = self.get_company_facts(ticker)
        if not facts_data:
            return []

        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
        filings_by_accn: Dict[str, Dict[str, Any]] = {}

        for concept, c_dict in us_gaap.items():
            for unit_name, units in c_dict.get("units", {}).items():
                for u in units:
                    form = u.get("form")
                    if form in ("10-Q", "10-K"):
                        accn = u.get("accn")
                        if not accn:
                            continue
                        if accn not in filings_by_accn:
                            filings_by_accn[accn] = {
                                "form": form,
                                "fiscal_year": u.get("fy"),
                                "fiscal_period": u.get("fp"),
                                "filing_date": u.get("filed"),
                                "accession_number": accn,
                                "period_ends": set(),
                            }
                        if u.get("end"):
                            filings_by_accn[accn]["period_ends"].add(u.get("end"))

        for accn, f_dict in filings_by_accn.items():
            ends = f_dict.pop("period_ends", set())
            f_dict["fiscal_period_end"] = max(ends) if ends else None

        filings_list = list(filings_by_accn.values())
        filings_list.sort(key=lambda r: (r.get("filing_date") or "", r.get("fiscal_period_end") or ""))
        return filings_list

    def get_filing_records(self, ticker: str, fact_concepts: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Extract verified chronologically ordered 10-K and 10-Q filing records.
        
        Merges across all candidate concepts (e.g. Revenues and RevenueFromContractWithCustomerExcludingAssessedTax)
        to prevent concept dropoff when ASC 606 was adopted.
        """
        if not fact_concepts:
            return self.get_all_filings(ticker)

        facts_data = self.get_company_facts(ticker)
        if not facts_data:
            return []

        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
        seen_keys = set()
        records = []

        for concept in fact_concepts:
            if concept in us_gaap:
                units_dict = us_gaap[concept].get("units", {})
                for unit_name, units in units_dict.items():
                    for u in units:
                        form = u.get("form")
                        if form in ("10-Q", "10-K"):
                            accn = u.get("accn")
                            key = (accn, u.get("end"), u.get("val"))
                            if key not in seen_keys:
                                seen_keys.add(key)
                                records.append({
                                    "form": form,
                                    "fiscal_year": u.get("fy"),
                                    "fiscal_period": u.get("fp"),
                                    "fiscal_period_end": u.get("end"),
                                    "filing_date": u.get("filed"),
                                    "accession_number": accn,
                                    "concept": concept,
                                    "value": u.get("val"),
                                    "frame": u.get("frame"),
                                })

        records.sort(key=lambda r: (r.get("filing_date") or "", r.get("fiscal_period_end") or ""))
        return records

    def get_filing_dates_map(self, ticker: str) -> Dict[str, str]:
        """Build dictionary mapping fiscal_period_end -> SEC filed date from official 10-K/10-Q records."""
        mapping = {}
        filings = self.get_all_filings(ticker)
        for f in filings:
            end_d = f.get("fiscal_period_end")
            filed_d = f.get("filing_date")
            if end_d and filed_d:
                mapping[end_d] = filed_d
        return mapping

    def get_latest_filing_verification(self, ticker: str) -> Dict[str, Any]:
        """Retrieve verification metadata for the latest filed 10-Q or 10-K report."""
        ticker = ticker.strip().upper()
        cik = self.get_cik(ticker)
        if not cik:
            return {
                "is_sec_verified": False,
                "cik": None,
                "reason": "Not a registered US reporting issuer or ADR",
            }

        filings = self.get_all_filings(ticker)
        if not filings:
            return {
                "is_sec_verified": False,
                "cik": cik,
                "reason": "SEC EDGAR filing facts currently unavailable or rate-limited",
            }

        latest = filings[-1]
        return {
            "is_sec_verified": True,
            "cik": cik,
            "sec_form": latest.get("form"),
            "fiscal_period": latest.get("fiscal_period"),
            "fiscal_year": latest.get("fiscal_year"),
            "fiscal_period_end": latest.get("fiscal_period_end"),
            "filing_date": latest.get("filing_date"),
            "accession_number": latest.get("accession_number"),
            "source_citation": f"SEC Form {latest.get('form')} (Filed: {latest.get('filing_date')}, Accn: {latest.get('accession_number')}) via SEC EDGAR",
        }

    def find_fact_by_period(
        self,
        ticker: str,
        concepts: List[str],
        target_period_end: str,
        preferred_units: Optional[List[str]] = None,
        max_day_offset: int = 7,
        is_quarterly_flow: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Find official SEC XBRL fact matching a target period end date with retail calendar tolerance."""
        facts_data = self.get_company_facts(ticker)
        if not facts_data:
            return None

        us_gaap = facts_data.get("facts", {}).get("us-gaap", {})
        if not preferred_units:
            preferred_units = ["USD", "shares", "USD/shares"]

        from datetime import datetime
        try:
            target_dt = datetime.strptime(target_period_end, "%Y-%m-%d")
        except Exception:
            return None

        matches = []
        for concept in concepts:
            if concept not in us_gaap:
                continue
            u_dict = us_gaap[concept].get("units", {})
            for u_key in preferred_units:
                if u_key not in u_dict:
                    continue
                for entry in u_dict[u_key]:
                    if entry.get("form") not in ("10-Q", "10-K"):
                        continue
                    end_str = entry.get("end")
                    if not end_str:
                        continue
                    try:
                        e_dt = datetime.strptime(end_str, "%Y-%m-%d")
                    except Exception:
                        continue
                    day_diff = abs((e_dt - target_dt).days)
                    if day_diff > max_day_offset:
                        continue

                    # If quarterly flow is requested, verify ~90 day duration
                    duration_score = 0
                    if is_quarterly_flow and entry.get("start"):
                        try:
                            s_dt = datetime.strptime(entry["start"], "%Y-%m-%d")
                            dur = (e_dt - s_dt).days
                            if 70 <= dur <= 105:
                                duration_score = 2
                            else:
                                duration_score = -1  # Skip YTD or full year if looking for quarterly flow
                        except Exception:
                            pass
                    elif not is_quarterly_flow:
                        duration_score = 1

                    if duration_score >= 0:
                        matches.append({
                            "concept": concept,
                            "value": entry.get("val"),
                            "fiscal_year": entry.get("fy"),
                            "fiscal_period": entry.get("fp"),
                            "fiscal_period_end": end_str,
                            "filing_date": entry.get("filed"),
                            "accession_number": entry.get("accn"),
                            "form": entry.get("form"),
                            "day_diff": day_diff,
                            "duration_score": duration_score,
                        })

        if not matches:
            return None

        # Prioritize closest date diff, highest duration score, most recent filing date
        matches.sort(key=lambda m: (m["day_diff"], -m["duration_score"], m.get("filing_date") or ""), reverse=False)
        return matches[0]


# Global singleton instance
sec_edgar_adapter = SecEdgarAdapter()
