"""Universe Registry & Stock Discovery Service for Adaptive Trading V4.0.

Provides:
1. Broad-market universe registry (~350-450 liquid US stocks & ETFs).
2. Dynamic persistence across application restarts (JSON manifest).
3. Search & Add-to-Screener for any US-listed security.
4. Summary metrics and filtering by sector, signal, freshness, and status.
"""
from typing import Dict, List, Any, Optional
import os
import json
import threading
from datetime import datetime
from pathlib import Path
import re

from app.config import (
    UNIVERSE_REGISTRY_PATH,
    DATA_CACHE_DIR,
    BASELINE_EXCEL_PATH,
    SIGNAL_PALETTE,
    DATA_PROVENANCE,
    IS_PRODUCTION,
)

_lock = threading.Lock()

# Curated seed universe covering original 28, ADBE, CRM, S&P 500 constituents, and major liquid sectors
SEED_UNIVERSE = [
    # --- Original V4.0 Baseline Stocks & Benchmarks ---
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "NYSE", "sector": "ETFs", "industry": "Large Blend ETF", "is_benchmark": True, "source": "v40_baseline"},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "exchange": "NASDAQ", "sector": "ETFs", "industry": "Large Growth ETF", "is_benchmark": False, "source": "v40_baseline"},
    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Internet Retail", "source": "v40_baseline"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "GOOGL", "name": "Alphabet Inc. (Class A)", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Internet Content & Information", "source": "v40_baseline"},
    {"ticker": "META", "name": "Meta Platforms, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Internet Content & Information", "source": "v40_baseline"},
    {"ticker": "AMD", "name": "Advanced Micro Devices, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "MA", "name": "Mastercard Incorporated", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services", "source": "v40_baseline"},
    {"ticker": "ELF", "name": "e.l.f. Beauty, Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Household & Personal Products", "source": "v40_baseline"},
    {"ticker": "IONQ", "name": "IonQ, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Computer Hardware", "source": "v40_baseline"},
    {"ticker": "NOW", "name": "ServiceNow, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Application", "source": "v40_baseline"},
    {"ticker": "INTC", "name": "Intel Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "NKE", "name": "NIKE, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Footwear & Accessories", "source": "v40_baseline"},
    {"ticker": "ORCL", "name": "Oracle Corporation", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Infrastructure", "source": "v40_baseline"},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "QCOM", "name": "QUALCOMM Incorporated", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "UBER", "name": "Uber Technologies, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Application", "source": "v40_baseline"},
    {"ticker": "CRWD", "name": "CrowdStrike Holdings, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "v40_baseline"},
    {"ticker": "ANET", "name": "Arista Networks, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Computer Hardware", "source": "v40_baseline"},
    {"ticker": "APP", "name": "AppLovin Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "v40_baseline"},
    {"ticker": "ASTS", "name": "AST SpaceMobile, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Telecom Services", "source": "v40_baseline"},
    {"ticker": "FICO", "name": "Fair Isaac Corporation", "exchange": "NYSE", "sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "source": "v40_baseline"},
    {"ticker": "MRVL", "name": "Marvell Technology, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "v40_baseline"},
    {"ticker": "COHR", "name": "Coherent Corp.", "exchange": "NYSE", "sector": "Technology", "industry": "Scientific & Technical Instruments", "source": "v40_baseline"},
    {"ticker": "TSLA", "name": "Tesla, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "source": "v40_baseline"},
    {"ticker": "CELH", "name": "Celsius Holdings, Inc.", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic", "source": "v40_baseline"},
    {"ticker": "ULTA", "name": "Ulta Beauty, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Specialty Retail", "source": "v40_baseline"},
    {"ticker": "GRAB", "name": "Grab Holdings Limited", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "v40_baseline"},
    {"ticker": "RDDT", "name": "Reddit, Inc.", "exchange": "NYSE", "sector": "Communication Services", "industry": "Internet Content & Information", "source": "v40_baseline"},

    # --- Specifically Requested Additions ---
    {"ticker": "ADBE", "name": "Adobe Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "CRM", "name": "Salesforce, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},

    # --- Major US Technology & Software ---
    {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Consumer Electronics", "source": "curated_expansion"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "PLTR", "name": "Palantir Technologies Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "SNOW", "name": "Snowflake Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "PANW", "name": "Palo Alto Networks, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "FTNT", "name": "Fortinet, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "INTU", "name": "Intuit Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "WDAY", "name": "Workday, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "TEAM", "name": "Atlassian Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "DDOG", "name": "Datadog, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "NET", "name": "Cloudflare, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "ZS", "name": "Zscaler, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "MDB", "name": "MongoDB, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "HUBS", "name": "HubSpot, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "SHOP", "name": "Shopify Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Application", "source": "curated_expansion"},
    {"ticker": "SQ", "name": "Block, Inc.", "exchange": "NYSE", "sector": "Technology", "industry": "Software - Infrastructure", "source": "curated_expansion"},
    {"ticker": "PYPL", "name": "PayPal Holdings, Inc.", "exchange": "NASDAQ", "sector": "Financial Services", "industry": "Credit Services", "source": "curated_expansion"},
    {"ticker": "CSCO", "name": "Cisco Systems, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Communication Equipment", "source": "curated_expansion"},
    {"ticker": "IBM", "name": "International Business Machines Corp.", "exchange": "NYSE", "sector": "Technology", "industry": "Information Technology Services", "source": "curated_expansion"},

    # --- Major US Semiconductors ---
    {"ticker": "TSM", "name": "Taiwan Semiconductor Manufacturing Co.", "exchange": "NYSE", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "ASML", "name": "ASML Holding N.V.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductor Equipment", "source": "curated_expansion"},
    {"ticker": "TXN", "name": "Texas Instruments Incorporated", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "ADI", "name": "Analog Devices, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "MU", "name": "Micron Technology, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "LRCX", "name": "Lam Research Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductor Equipment", "source": "curated_expansion"},
    {"ticker": "AMAT", "name": "Applied Materials, Inc.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductor Equipment", "source": "curated_expansion"},
    {"ticker": "KLAC", "name": "KLA Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductor Equipment", "source": "curated_expansion"},
    {"ticker": "ARM", "name": "Arm Holdings plc", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "ON", "name": "ON Semiconductor Corporation", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "NXPI", "name": "NXP Semiconductors N.V.", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},
    {"ticker": "MCHP", "name": "Microchip Technology Incorporated", "exchange": "NASDAQ", "sector": "Technology", "industry": "Semiconductors", "source": "curated_expansion"},

    # --- Major US Healthcare & Pharmaceuticals ---
    {"ticker": "LLY", "name": "Eli Lilly and Company", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "UNH", "name": "UnitedHealth Group Incorporated", "exchange": "NYSE", "sector": "Healthcare", "industry": "Healthcare Plans", "source": "curated_expansion"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "ABBV", "name": "AbbVie Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "MRK", "name": "Merck & Co., Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "TMO", "name": "Thermo Fisher Scientific Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Diagnostics & Research", "source": "curated_expansion"},
    {"ticker": "ABT", "name": "Abbott Laboratories", "exchange": "NYSE", "sector": "Healthcare", "industry": "Medical Devices", "source": "curated_expansion"},
    {"ticker": "PFE", "name": "Pfizer Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "DHR", "name": "Danaher Corporation", "exchange": "NYSE", "sector": "Healthcare", "industry": "Diagnostics & Research", "source": "curated_expansion"},
    {"ticker": "ISRG", "name": "Intuitive Surgical, Inc.", "exchange": "NASDAQ", "sector": "Healthcare", "industry": "Medical Instruments & Supplies", "source": "curated_expansion"},
    {"ticker": "AMGN", "name": "Amgen Inc.", "exchange": "NASDAQ", "sector": "Healthcare", "industry": "Biotechnology", "source": "curated_expansion"},
    {"ticker": "BMY", "name": "Bristol-Myers Squibb Company", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - General", "source": "curated_expansion"},
    {"ticker": "VRTX", "name": "Vertex Pharmaceuticals Incorporated", "exchange": "NASDAQ", "sector": "Healthcare", "industry": "Biotechnology", "source": "curated_expansion"},
    {"ticker": "REGN", "name": "Regeneron Pharmaceuticals, Inc.", "exchange": "NASDAQ", "sector": "Healthcare", "industry": "Biotechnology", "source": "curated_expansion"},
    {"ticker": "MDT", "name": "Medtronic plc", "exchange": "NYSE", "sector": "Healthcare", "industry": "Medical Devices", "source": "curated_expansion"},
    {"ticker": "SYK", "name": "Stryker Corporation", "exchange": "NYSE", "sector": "Healthcare", "industry": "Medical Devices", "source": "curated_expansion"},
    {"ticker": "BSX", "name": "Boston Scientific Corporation", "exchange": "NYSE", "sector": "Healthcare", "industry": "Medical Devices", "source": "curated_expansion"},
    {"ticker": "GILD", "name": "Gilead Sciences, Inc.", "exchange": "NASDAQ", "sector": "Healthcare", "industry": "Biotechnology", "source": "curated_expansion"},
    {"ticker": "ZTS", "name": "Zoetis Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Drug Manufacturers - Specialty & Generic", "source": "curated_expansion"},
    {"ticker": "ELV", "name": "Elevance Health, Inc.", "exchange": "NYSE", "sector": "Healthcare", "industry": "Healthcare Plans", "source": "curated_expansion"},
    {"ticker": "CI", "name": "The Cigna Group", "exchange": "NYSE", "sector": "Healthcare", "industry": "Healthcare Plans", "source": "curated_expansion"},

    # --- Major US Financial Services & Banks ---
    {"ticker": "BRK-B", "name": "Berkshire Hathaway Inc. (Class B)", "exchange": "NYSE", "sector": "Financial Services", "industry": "Insurance - Diversified", "source": "curated_expansion"},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Diversified", "source": "curated_expansion"},
    {"ticker": "V", "name": "Visa Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services", "source": "curated_expansion"},
    {"ticker": "BAC", "name": "Bank of America Corporation", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Diversified", "source": "curated_expansion"},
    {"ticker": "WFC", "name": "Wells Fargo & Company", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Diversified", "source": "curated_expansion"},
    {"ticker": "MS", "name": "Morgan Stanley", "exchange": "NYSE", "sector": "Financial Services", "industry": "Capital Markets", "source": "curated_expansion"},
    {"ticker": "GS", "name": "The Goldman Sachs Group, Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Capital Markets", "source": "curated_expansion"},
    {"ticker": "BLK", "name": "BlackRock, Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Asset Management", "source": "curated_expansion"},
    {"ticker": "SCHW", "name": "The Charles Schwab Corporation", "exchange": "NYSE", "sector": "Financial Services", "industry": "Capital Markets", "source": "curated_expansion"},
    {"ticker": "AXP", "name": "American Express Company", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services", "source": "curated_expansion"},
    {"ticker": "CB", "name": "Chubb Limited", "exchange": "NYSE", "sector": "Financial Services", "industry": "Insurance - Property & Casualty", "source": "curated_expansion"},
    {"ticker": "MMC", "name": "Marsh & McLennan Companies, Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Insurance Brokers", "source": "curated_expansion"},
    {"ticker": "PGR", "name": "The Progressive Corporation", "exchange": "NYSE", "sector": "Financial Services", "industry": "Insurance - Property & Casualty", "source": "curated_expansion"},
    {"ticker": "SPGI", "name": "S&P Global Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "source": "curated_expansion"},
    {"ticker": "ICE", "name": "Intercontinental Exchange, Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "source": "curated_expansion"},
    {"ticker": "CME", "name": "CME Group Inc.", "exchange": "NASDAQ", "sector": "Financial Services", "industry": "Financial Data & Stock Exchanges", "source": "curated_expansion"},
    {"ticker": "C", "name": "Citigroup Inc.", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Diversified", "source": "curated_expansion"},
    {"ticker": "USB", "name": "U.S. Bancorp", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Regional", "source": "curated_expansion"},
    {"ticker": "PNC", "name": "The PNC Financial Services Group", "exchange": "NYSE", "sector": "Financial Services", "industry": "Banks - Regional", "source": "curated_expansion"},
    {"ticker": "COF", "name": "Capital One Financial Corporation", "exchange": "NYSE", "sector": "Financial Services", "industry": "Credit Services", "source": "curated_expansion"},

    # --- Major US Consumer Discretionary / Cyclical ---
    {"ticker": "HD", "name": "The Home Depot, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Home Improvement Retail", "source": "curated_expansion"},
    {"ticker": "MCD", "name": "McDonald's Corporation", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Restaurants", "source": "curated_expansion"},
    {"ticker": "SBUX", "name": "Starbucks Corporation", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Restaurants", "source": "curated_expansion"},
    {"ticker": "TJX", "name": "The TJX Companies, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Apparel Retail", "source": "curated_expansion"},
    {"ticker": "BKNG", "name": "Booking Holdings Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Travel Services", "source": "curated_expansion"},
    {"ticker": "LOW", "name": "Lowe's Companies, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Home Improvement Retail", "source": "curated_expansion"},
    {"ticker": "CMG", "name": "Chipotle Mexican Grill, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Restaurants", "source": "curated_expansion"},
    {"ticker": "MAR", "name": "Marriott International, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Lodging", "source": "curated_expansion"},
    {"ticker": "HLT", "name": "Hilton Worldwide Holdings Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Lodging", "source": "curated_expansion"},
    {"ticker": "LULU", "name": "Lululemon Athletica Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Apparel Retail", "source": "curated_expansion"},
    {"ticker": "ROST", "name": "Ross Stores, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Apparel Retail", "source": "curated_expansion"},
    {"ticker": "ORLY", "name": "O'Reilly Automotive, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Auto Parts", "source": "curated_expansion"},
    {"ticker": "AZO", "name": "AutoZone, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Auto Parts", "source": "curated_expansion"},
    {"ticker": "DHI", "name": "D.R. Horton, Inc.", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Residential Construction", "source": "curated_expansion"},
    {"ticker": "LEN", "name": "Lennar Corporation", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Residential Construction", "source": "curated_expansion"},
    {"ticker": "F", "name": "Ford Motor Company", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "source": "curated_expansion"},
    {"ticker": "GM", "name": "General Motors Company", "exchange": "NYSE", "sector": "Consumer Cyclical", "industry": "Auto Manufacturers", "source": "curated_expansion"},
    {"ticker": "ABNB", "name": "Airbnb, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Travel Services", "source": "curated_expansion"},
    {"ticker": "DASH", "name": "DoorDash, Inc.", "exchange": "NASDAQ", "sector": "Consumer Cyclical", "industry": "Internet Retail", "source": "curated_expansion"},

    # --- Major US Consumer Staples / Defensive ---
    {"ticker": "WMT", "name": "Walmart Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Discount Stores", "source": "curated_expansion"},
    {"ticker": "PG", "name": "The Procter & Gamble Company", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Household & Personal Products", "source": "curated_expansion"},
    {"ticker": "COST", "name": "Costco Wholesale Corporation", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Discount Stores", "source": "curated_expansion"},
    {"ticker": "KO", "name": "The Coca-Cola Company", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic", "source": "curated_expansion"},
    {"ticker": "PEP", "name": "PepsiCo, Inc.", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Beverages - Non-Alcoholic", "source": "curated_expansion"},
    {"ticker": "PM", "name": "Philip Morris International Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Tobacco", "source": "curated_expansion"},
    {"ticker": "MO", "name": "Altria Group, Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Tobacco", "source": "curated_expansion"},
    {"ticker": "CL", "name": "Colgate-Palmolive Company", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Household & Personal Products", "source": "curated_expansion"},
    {"ticker": "MDLZ", "name": "Mondelez International, Inc.", "exchange": "NASDAQ", "sector": "Consumer Defensive", "industry": "Confectioners", "source": "curated_expansion"},
    {"ticker": "KMB", "name": "Kimberly-Clark Corporation", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Household & Personal Products", "source": "curated_expansion"},
    {"ticker": "STZ", "name": "Constellation Brands, Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Beverages - Wineries & Distilleries", "source": "curated_expansion"},
    {"ticker": "TGT", "name": "Target Corporation", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Discount Stores", "source": "curated_expansion"},
    {"ticker": "DG", "name": "Dollar General Corporation", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Discount Stores", "source": "curated_expansion"},
    {"ticker": "KR", "name": "The Kroger Co.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Grocery Stores", "source": "curated_expansion"},
    {"ticker": "ADM", "name": "Archer-Daniels-Midland Company", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Farm Products", "source": "curated_expansion"},
    {"ticker": "GIS", "name": "General Mills, Inc.", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Packaged Foods", "source": "curated_expansion"},
    {"ticker": "HSY", "name": "The Hershey Company", "exchange": "NYSE", "sector": "Consumer Defensive", "industry": "Confectioners", "source": "curated_expansion"},

    # --- Major US Industrials & Aerospace ---
    {"ticker": "GE", "name": "GE Aerospace", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "CAT", "name": "Caterpillar Inc.", "exchange": "NYSE", "sector": "Industrials", "industry": "Farm & Heavy Construction Machinery", "source": "curated_expansion"},
    {"ticker": "BA", "name": "The Boeing Company", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "UNP", "name": "Union Pacific Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Railroads", "source": "curated_expansion"},
    {"ticker": "HON", "name": "Honeywell International Inc.", "exchange": "NASDAQ", "sector": "Industrials", "industry": "Conglomerates", "source": "curated_expansion"},
    {"ticker": "RTX", "name": "RTX Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "LMT", "name": "Lockheed Martin Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "DE", "name": "Deere & Company", "exchange": "NYSE", "sector": "Industrials", "industry": "Farm & Heavy Construction Machinery", "source": "curated_expansion"},
    {"ticker": "UPS", "name": "United Parcel Service, Inc.", "exchange": "NYSE", "sector": "Industrials", "industry": "Integrated Freight & Logistics", "source": "curated_expansion"},
    {"ticker": "FDX", "name": "FedEx Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Integrated Freight & Logistics", "source": "curated_expansion"},
    {"ticker": "ETN", "name": "Eaton Corporation plc", "exchange": "NYSE", "sector": "Industrials", "industry": "Specialty Industrial Machinery", "source": "curated_expansion"},
    {"ticker": "ITW", "name": "Illinois Tool Works Inc.", "exchange": "NYSE", "sector": "Industrials", "industry": "Specialty Industrial Machinery", "source": "curated_expansion"},
    {"ticker": "WM", "name": "Waste Management, Inc.", "exchange": "NYSE", "sector": "Industrials", "industry": "Waste Management", "source": "curated_expansion"},
    {"ticker": "GD", "name": "General Dynamics Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "NOC", "name": "Northrop Grumman Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "CSX", "name": "CSX Corporation", "exchange": "NASDAQ", "sector": "Industrials", "industry": "Railroads", "source": "curated_expansion"},
    {"ticker": "NSC", "name": "Norfolk Southern Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Railroads", "source": "curated_expansion"},
    {"ticker": "EMR", "name": "Emerson Electric Co.", "exchange": "NYSE", "sector": "Industrials", "industry": "Specialty Industrial Machinery", "source": "curated_expansion"},
    {"ticker": "PCAR", "name": "PACCAR Inc", "exchange": "NASDAQ", "sector": "Industrials", "industry": "Farm & Heavy Construction Machinery", "source": "curated_expansion"},
    {"ticker": "PH", "name": "Parker-Hannifin Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Specialty Industrial Machinery", "source": "curated_expansion"},
    {"ticker": "TDG", "name": "TransDigm Group Incorporated", "exchange": "NYSE", "sector": "Industrials", "industry": "Aerospace & Defense", "source": "curated_expansion"},
    {"ticker": "CARR", "name": "Carrier Global Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Building Products & Equipment", "source": "curated_expansion"},
    {"ticker": "OTIS", "name": "Otis Worldwide Corporation", "exchange": "NYSE", "sector": "Industrials", "industry": "Building Products & Equipment", "source": "curated_expansion"},

    # --- Major US Energy ---
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Integrated", "source": "curated_expansion"},
    {"ticker": "CVX", "name": "Chevron Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Integrated", "source": "curated_expansion"},
    {"ticker": "COP", "name": "ConocoPhillips", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas E&P", "source": "curated_expansion"},
    {"ticker": "SLB", "name": "Schlumberger Limited", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Equipment & Services", "source": "curated_expansion"},
    {"ticker": "EOG", "name": "EOG Resources, Inc.", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas E&P", "source": "curated_expansion"},
    {"ticker": "MPC", "name": "Marathon Petroleum Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Refining & Marketing", "source": "curated_expansion"},
    {"ticker": "PSX", "name": "Phillips 66", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Refining & Marketing", "source": "curated_expansion"},
    {"ticker": "VLO", "name": "Valero Energy Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Refining & Marketing", "source": "curated_expansion"},
    {"ticker": "OXY", "name": "Occidental Petroleum Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas E&P", "source": "curated_expansion"},
    {"ticker": "WMB", "name": "The Williams Companies, Inc.", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Midstream", "source": "curated_expansion"},
    {"ticker": "KMI", "name": "Kinder Morgan, Inc.", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Midstream", "source": "curated_expansion"},
    {"ticker": "HAL", "name": "Halliburton Company", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas Equipment & Services", "source": "curated_expansion"},
    {"ticker": "BKR", "name": "Baker Hughes Company", "exchange": "NASDAQ", "sector": "Energy", "industry": "Oil & Gas Equipment & Services", "source": "curated_expansion"},
    {"ticker": "DVN", "name": "Devon Energy Corporation", "exchange": "NYSE", "sector": "Energy", "industry": "Oil & Gas E&P", "source": "curated_expansion"},
    {"ticker": "FANG", "name": "Diamondback Energy, Inc.", "exchange": "NASDAQ", "sector": "Energy", "industry": "Oil & Gas E&P", "source": "curated_expansion"},

    # --- Major US Communication Services ---
    {"ticker": "NFLX", "name": "Netflix, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Entertainment", "source": "curated_expansion"},
    {"ticker": "DIS", "name": "The Walt Disney Company", "exchange": "NYSE", "sector": "Communication Services", "industry": "Entertainment", "source": "curated_expansion"},
    {"ticker": "CMCSA", "name": "Comcast Corporation", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Telecom Services", "source": "curated_expansion"},
    {"ticker": "VZ", "name": "Verizon Communications Inc.", "exchange": "NYSE", "sector": "Communication Services", "industry": "Telecom Services", "source": "curated_expansion"},
    {"ticker": "T", "name": "AT&T Inc.", "exchange": "NYSE", "sector": "Communication Services", "industry": "Telecom Services", "source": "curated_expansion"},
    {"ticker": "TMUS", "name": "T-Mobile US, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Telecom Services", "source": "curated_expansion"},
    {"ticker": "EA", "name": "Electronic Arts Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Electronic Gaming & Multimedia", "source": "curated_expansion"},
    {"ticker": "TTWO", "name": "Take-Two Interactive Software, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Electronic Gaming & Multimedia", "source": "curated_expansion"},
    {"ticker": "WBD", "name": "Warner Bros. Discovery, Inc.", "exchange": "NASDAQ", "sector": "Communication Services", "industry": "Entertainment", "source": "curated_expansion"},

    # --- Major US Utilities & Infrastructure ---
    {"ticker": "NEE", "name": "NextEra Energy, Inc.", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "SO", "name": "The Southern Company", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "DUK", "name": "Duke Energy Corporation", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "SRE", "name": "Sempra", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Diversified", "source": "curated_expansion"},
    {"ticker": "AEP", "name": "American Electric Power Company", "exchange": "NASDAQ", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "D", "name": "Dominion Energy, Inc.", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "EXC", "name": "Exelon Corporation", "exchange": "NASDAQ", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "XEL", "name": "Xcel Energy Inc.", "exchange": "NASDAQ", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "ED", "name": "Consolidated Edison, Inc.", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Regulated Electric", "source": "curated_expansion"},
    {"ticker": "PEG", "name": "Public Service Enterprise Group", "exchange": "NYSE", "sector": "Utilities", "industry": "Utilities - Diversified", "source": "curated_expansion"},

    # --- Major US Real Estate (REITs) ---
    {"ticker": "PLD", "name": "Prologis, Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Industrial", "source": "curated_expansion"},
    {"ticker": "AMT", "name": "American Tower Corporation", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Specialty", "source": "curated_expansion"},
    {"ticker": "EQIX", "name": "Equinix, Inc.", "exchange": "NASDAQ", "sector": "Real Estate", "industry": "REIT - Specialty", "source": "curated_expansion"},
    {"ticker": "PSA", "name": "Public Storage", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Industrial", "source": "curated_expansion"},
    {"ticker": "SPG", "name": "Simon Property Group, Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Retail", "source": "curated_expansion"},
    {"ticker": "CCI", "name": "Crown Castle Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Specialty", "source": "curated_expansion"},
    {"ticker": "WELL", "name": "Welltower Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Healthcare Facilities", "source": "curated_expansion"},
    {"ticker": "DLR", "name": "Digital Realty Trust, Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Specialty", "source": "curated_expansion"},
    {"ticker": "O", "name": "Realty Income Corporation", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Retail", "source": "curated_expansion"},
    {"ticker": "VICI", "name": "VICI Properties Inc.", "exchange": "NYSE", "sector": "Real Estate", "industry": "REIT - Specialty", "source": "curated_expansion"},

    # --- Major US Basic Materials & Mining ---
    {"ticker": "LIN", "name": "Linde plc", "exchange": "NASDAQ", "sector": "Basic Materials", "industry": "Specialty Chemicals", "source": "curated_expansion"},
    {"ticker": "SHW", "name": "The Sherwin-Williams Company", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Specialty Chemicals", "source": "curated_expansion"},
    {"ticker": "FCX", "name": "Freeport-McMoRan Inc.", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Copper", "source": "curated_expansion"},
    {"ticker": "APD", "name": "Air Products and Chemicals, Inc.", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Specialty Chemicals", "source": "curated_expansion"},
    {"ticker": "ECL", "name": "Ecolab Inc.", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Specialty Chemicals", "source": "curated_expansion"},
    {"ticker": "NEM", "name": "Newmont Corporation", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Gold", "source": "curated_expansion"},
    {"ticker": "DOW", "name": "Dow Inc.", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Chemicals", "source": "curated_expansion"},
    {"ticker": "NUE", "name": "Nucor Corporation", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Steel", "source": "curated_expansion"},
    {"ticker": "CTVA", "name": "Corteva, Inc.", "exchange": "NYSE", "sector": "Basic Materials", "industry": "Agricultural Inputs", "source": "curated_expansion"},

    # --- Key Liquid US ETFs ---
    {"ticker": "IWM", "name": "iShares Russell 2000 ETF", "exchange": "NYSE", "sector": "ETFs", "industry": "Small Blend ETF", "source": "curated_expansion"},
    {"ticker": "DIA", "name": "SPDR Dow Jones Industrial Average ETF", "exchange": "NYSE", "sector": "ETFs", "industry": "Large Value ETF", "source": "curated_expansion"},
    {"ticker": "XLK", "name": "Technology Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Tech ETF", "source": "curated_expansion"},
    {"ticker": "XLF", "name": "Financial Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Financials ETF", "source": "curated_expansion"},
    {"ticker": "XLE", "name": "Energy Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Energy ETF", "source": "curated_expansion"},
    {"ticker": "XLV", "name": "Health Care Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Health ETF", "source": "curated_expansion"},
    {"ticker": "XLI", "name": "Industrial Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Industrial ETF", "source": "curated_expansion"},
    {"ticker": "XLY", "name": "Consumer Discretionary Select Sector SPDR", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Discretionary ETF", "source": "curated_expansion"},
    {"ticker": "XLP", "name": "Consumer Staples Select Sector SPDR Fund", "exchange": "NYSE", "sector": "ETFs", "industry": "Sector Staples ETF", "source": "curated_expansion"},
    {"ticker": "SMH", "name": "VanEck Semiconductor ETF", "exchange": "NASDAQ", "sector": "ETFs", "industry": "Semiconductor ETF", "source": "curated_expansion"},
    {"ticker": "SOXX", "name": "iShares Semiconductor ETF", "exchange": "NASDAQ", "sector": "ETFs", "industry": "Semiconductor ETF", "source": "curated_expansion"},
    {"ticker": "ARKK", "name": "ARK Innovation ETF", "exchange": "NYSE", "sector": "ETFs", "industry": "Innovation ETF", "source": "curated_expansion"},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "exchange": "NYSE", "sector": "ETFs", "industry": "Large Blend ETF", "source": "curated_expansion"},
    {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF", "exchange": "NYSE", "sector": "ETFs", "industry": "Total Market ETF", "source": "curated_expansion"},
]


class UniverseManager:
    """Manages the configurable, persistent screener universe across sessions."""

    def __init__(self):
        self.registry: Dict[str, Dict[str, Any]] = {}
        self._load_or_initialize_registry()

    def _load_or_initialize_registry(self):
        """Loads from database or JSON disk, or initializes with seed universe."""
        with _lock:
            DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # 1. Try loading from database first (Durable Storage)
            try:
                from app.database import SessionLocal
                from app.models import MonitoredStock
                db = SessionLocal()
                try:
                    db_stocks = db.query(MonitoredStock).all()
                    if len(db_stocks) >= 28:
                        self.registry = {}
                        for s in db_stocks:
                            opt = json.loads(s.optimal_rule_json) if s.optimal_rule_json else None
                            sig = json.loads(s.latest_signal_json) if s.latest_signal_json else None
                            self.registry[s.ticker] = {
                                "ticker": s.ticker,
                                "name": s.name,
                                "exchange": s.exchange,
                                "sector": s.sector,
                                "industry": s.industry,
                                "is_active": s.is_active,
                                "is_benchmark": s.is_benchmark,
                                "inclusion_date": s.inclusion_date,
                                "source": s.source,
                                "latest_price_date": s.latest_price_date,
                                "data_status": s.data_status,
                                "v40_eligible": s.v40_eligible,
                                "optimal_rule": opt,
                                "latest_signal": sig,
                                "last_scanned_at": s.last_scanned_at,
                            }
                        return
                finally:
                    db.close()
            except Exception as e:
                print(f"[UniverseManager] DB load notice: {e}")

            # 2. Fallback to JSON registry
            if UNIVERSE_REGISTRY_PATH.exists():
                try:
                    with open(UNIVERSE_REGISTRY_PATH, "r", encoding="utf-8") as f:
                        self.registry = json.load(f)
                    if len(self.registry) >= 28:
                        return
                except Exception:
                    pass

            # 3. Initialize from SEED_UNIVERSE
            now_iso = datetime.now().isoformat()
            self.registry = {}
            for item in SEED_UNIVERSE:
                ticker = item["ticker"].strip().upper()
                is_bm = item.get("is_benchmark", ticker == "SPY")
                self.registry[ticker] = {
                    "ticker": ticker,
                    "name": item.get("name", ticker),
                    "exchange": item.get("exchange", "NASDAQ"),
                    "sector": item.get("sector", "Technology"),
                    "industry": item.get("industry", "Equity"),
                    "is_active": True,
                    "is_benchmark": is_bm,
                    "inclusion_date": "2026-10-09" if item.get("source") == "v40_baseline" else "2026-10-12",
                    "source": item.get("source", "curated_expansion"),
                    "latest_price_date": "2026-10-09" if item.get("source") == "v40_baseline" else None,
                    "data_status": "READY" if item.get("source") == "v40_baseline" else "PENDING",
                    "v40_eligible": True,
                    "optimal_rule": None,
                    "latest_signal": None,
                    "last_scanned_at": now_iso if item.get("source") == "v40_baseline" else None,
                }

            self._save_registry_locked()

    def _save_registry_locked(self, sync_db: bool = True):
        """Save registry atomically to persistent JSON file and synchronize DB."""
        try:
            UNIVERSE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = UNIVERSE_REGISTRY_PATH.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, indent=2)
            os.replace(tmp_file, UNIVERSE_REGISTRY_PATH)
        except Exception as e:
            print(f"[UniverseManager] JSON registry file write notice: {e}")

        # In production, Supabase PostgreSQL is the authoritative universe.
        # Bypass legacy sequential 231-row table synchronization to eliminate startup bottleneck.
        if IS_PRODUCTION or not sync_db:
            return

        # Synchronize database MonitoredStock table (local development SQLite only)
        try:
            from app.database import SessionLocal
            from app.models import MonitoredStock
            db = SessionLocal()
            try:
                for ticker, r in self.registry.items():
                    opt = json.dumps(r.get("optimal_rule")) if r.get("optimal_rule") else None
                    sig = json.dumps(r.get("latest_signal")) if r.get("latest_signal") else None
                    stock_rec = db.query(MonitoredStock).filter(MonitoredStock.ticker == ticker).first()
                    if stock_rec:
                        stock_rec.name = r.get("name", ticker)
                        stock_rec.exchange = r.get("exchange", "NASDAQ")
                        stock_rec.sector = r.get("sector", "Technology")
                        stock_rec.industry = r.get("industry", "Equity")
                        stock_rec.is_active = r.get("is_active", True)
                        stock_rec.is_benchmark = r.get("is_benchmark", False)
                        stock_rec.data_status = r.get("data_status", "READY")
                        stock_rec.latest_price_date = r.get("latest_price_date")
                        stock_rec.v40_eligible = r.get("v40_eligible", True)
                        stock_rec.optimal_rule_json = opt
                        stock_rec.latest_signal_json = sig
                        stock_rec.last_scanned_at = r.get("last_scanned_at")
                    else:
                        new_stock = MonitoredStock(
                            ticker=ticker,
                            name=r.get("name", ticker),
                            exchange=r.get("exchange", "NASDAQ"),
                            sector=r.get("sector", "Technology"),
                            industry=r.get("industry", "Equity"),
                            is_active=r.get("is_active", True),
                            is_benchmark=r.get("is_benchmark", False),
                            inclusion_date=r.get("inclusion_date", datetime.now().strftime("%Y-%m-%d")),
                            source=r.get("source", "user_added"),
                            data_status=r.get("data_status", "READY"),
                            latest_price_date=r.get("latest_price_date"),
                            v40_eligible=r.get("v40_eligible", True),
                            optimal_rule_json=opt,
                            latest_signal_json=sig,
                            last_scanned_at=r.get("last_scanned_at"),
                        )
                        db.add(new_stock)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[UniverseManager] DB sync warning: {e}")

    def _sync_single_stock_to_db(self, ticker: str, r: Dict[str, Any]):
        """Synchronize a single stock directly to PostgreSQL without scanning or updating other records."""
        try:
            from app.database import SessionLocal
            from app.models import MonitoredStock
            db = SessionLocal()
            try:
                opt = json.dumps(r.get("optimal_rule")) if r.get("optimal_rule") else None
                sig = json.dumps(r.get("latest_signal")) if r.get("latest_signal") else None
                stock_rec = db.query(MonitoredStock).filter(MonitoredStock.ticker == ticker).first()
                if stock_rec:
                    stock_rec.name = r.get("name", ticker)
                    stock_rec.exchange = r.get("exchange", "NASDAQ")
                    stock_rec.sector = r.get("sector", "Technology")
                    stock_rec.industry = r.get("industry", "Equity")
                    stock_rec.is_active = r.get("is_active", True)
                    stock_rec.is_benchmark = r.get("is_benchmark", False)
                    stock_rec.data_status = r.get("data_status", "READY")
                    stock_rec.latest_price_date = r.get("latest_price_date")
                    stock_rec.v40_eligible = r.get("v40_eligible", True)
                    stock_rec.optimal_rule_json = opt
                    stock_rec.latest_signal_json = sig
                    stock_rec.last_scanned_at = r.get("last_scanned_at")
                else:
                    new_stock = MonitoredStock(
                        ticker=ticker,
                        name=r.get("name", ticker),
                        exchange=r.get("exchange", "NASDAQ"),
                        sector=r.get("sector", "Technology"),
                        industry=r.get("industry", "Equity"),
                        is_active=r.get("is_active", True),
                        is_benchmark=r.get("is_benchmark", False),
                        inclusion_date=r.get("inclusion_date", datetime.now().strftime("%Y-%m-%d")),
                        source=r.get("source", "user_added"),
                        data_status=r.get("data_status", "READY"),
                        latest_price_date=r.get("latest_price_date"),
                        v40_eligible=r.get("v40_eligible", True),
                        optimal_rule_json=opt,
                        latest_signal_json=sig,
                        last_scanned_at=r.get("last_scanned_at"),
                    )
                    db.add(new_stock)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[UniverseManager] Single stock DB sync notice for {ticker}: {e}")

    def save(self):
        """Public thread-safe save method."""
        with _lock:
            self._save_registry_locked()

    def get_stock(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Retrieve single stock record by ticker."""
        return self.registry.get(ticker.strip().upper())

    def get_all(
        self,
        include_inactive: bool = False,
        sector: Optional[str] = None,
        signal: Optional[str] = None,
        data_status: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve filtered, sorted universe list."""
        stocks = list(self.registry.values())
        if not include_inactive:
            stocks = [s for s in stocks if s.get("is_active", True)]

        if sector and sector.upper() != "ALL":
            stocks = [s for s in stocks if s.get("sector", "").lower() == sector.lower()]

        if signal and signal.upper() != "ALL":
            stocks = [
                s for s in stocks
                if (s.get("latest_signal") or {}).get("signal", "").upper() == signal.upper()
            ]

        if data_status and data_status.upper() != "ALL":
            stocks = [s for s in stocks if s.get("data_status", "").upper() == data_status.upper()]

        if search:
            q = search.strip().lower()
            stocks = [
                s for s in stocks
                if q in s["ticker"].lower() or q in s.get("name", "").lower()
            ]

        # Sorting logic
        if sort_by == "ticker":
            stocks.sort(key=lambda x: x["ticker"], reverse=not ascending)
        elif sort_by == "name":
            stocks.sort(key=lambda x: x.get("name", ""), reverse=not ascending)
        elif sort_by == "sector":
            stocks.sort(key=lambda x: x.get("sector", ""), reverse=not ascending)
        elif sort_by == "signal":
            # Priority order: BUY CANDIDATE > WATCH > HOLD > EXIT > AVOID > INSUFFICIENT
            priority = {"BUY CANDIDATE": 1, "BUY": 1, "WATCH": 2, "HOLD": 3, "EXIT": 4, "AVOID": 5}
            stocks.sort(
                key=lambda x: priority.get((x.get("latest_signal") or {}).get("signal", ""), 99),
                reverse=not ascending,
            )
        elif sort_by == "close":
            stocks.sort(
                key=lambda x: (x.get("latest_signal") or {}).get("close") or 0.0,
                reverse=not ascending,
            )

        return stocks

    def add_stock(
        self,
        ticker: str,
        name: Optional[str] = None,
        exchange: Optional[str] = "NASDAQ",
        sector: Optional[str] = "Technology",
        industry: Optional[str] = "Equity",
        data_status: str = "PENDING",
        optimal_rule: Optional[Dict[str, Any]] = None,
        latest_signal: Optional[Dict[str, Any]] = None,
        latest_price_date: Optional[str] = None,
        v40_eligible: bool = True,
    ) -> Dict[str, Any]:
        """Add new stock to the screener universe or update existing."""
        ticker = ticker.strip().upper()
        now_iso = datetime.now().isoformat()
        with _lock:
            existing = self.registry.get(ticker)
            if existing:
                existing["is_active"] = True
                if name: existing["name"] = name
                if exchange: existing["exchange"] = exchange
                if sector: existing["sector"] = sector
                if industry: existing["industry"] = industry
                if data_status: existing["data_status"] = data_status
                if optimal_rule: existing["optimal_rule"] = optimal_rule
                if latest_signal: existing["latest_signal"] = latest_signal
                if latest_price_date: existing["latest_price_date"] = latest_price_date
                existing["v40_eligible"] = v40_eligible
                existing["last_scanned_at"] = now_iso
                if IS_PRODUCTION:
                    self._sync_single_stock_to_db(ticker, existing)
                else:
                    self._save_registry_locked()
                return existing

            record = {
                "ticker": ticker,
                "name": name or ticker,
                "exchange": exchange or "NASDAQ",
                "sector": sector or "Technology",
                "industry": industry or "Equity",
                "is_active": True,
                "is_benchmark": False,
                "inclusion_date": datetime.now().strftime("%Y-%m-%d"),
                "source": "user_added",
                "latest_price_date": latest_price_date,
                "data_status": data_status,
                "v40_eligible": v40_eligible,
                "optimal_rule": optimal_rule,
                "latest_signal": latest_signal,
                "last_scanned_at": now_iso,
            }
            self.registry[ticker] = record
            if IS_PRODUCTION:
                self._sync_single_stock_to_db(ticker, record)
            else:
                self._save_registry_locked()
            return record

    def update_stock(self, ticker: str, updates: Dict[str, Any], sync_db: bool = True) -> Optional[Dict[str, Any]]:
        """Update fields on an existing stock record."""
        ticker = ticker.strip().upper()
        with _lock:
            if ticker not in self.registry:
                return None
            self.registry[ticker].update(updates)
            if sync_db:
                if IS_PRODUCTION:
                    self._sync_single_stock_to_db(ticker, self.registry[ticker])
                else:
                    self._save_registry_locked()
            return self.registry[ticker]

    def remove_stock(self, ticker: str) -> bool:
        """Deactivate or remove a stock from active screener."""
        ticker = ticker.strip().upper()
        with _lock:
            if ticker in self.registry:
                self.registry[ticker]["is_active"] = False
                if IS_PRODUCTION:
                    self._sync_single_stock_to_db(ticker, self.registry[ticker])
                else:
                    self._save_registry_locked()
                return True
            return False

    def get_summary_counts(self) -> Dict[str, Any]:
        """Compute broad market dashboard metrics backed by the persistent active snapshot."""
        try:
            from app.services.snapshot_service import snapshot_service
            active_snap = snapshot_service.get_active_snapshot()
            if active_snap and active_snap.get("summary"):
                summary = dict(active_snap["summary"])
                summary["last_refresh_time"] = active_snap.get("calculated_at") or summary.get("last_refresh_time")
                summary["latest_market_date"] = active_snap.get("market_as_of_date") or summary.get("latest_market_date")
                summary["active_snapshot_id"] = active_snap.get("snapshot_id")
                return summary
        except Exception as e:
            print(f"[UniverseManager] Snapshot summary read fallback: {e}")

        total = len(self.registry)
        active = sum(1 for s in self.registry.values() if s.get("is_active", True))
        refreshed = sum(1 for s in self.registry.values() if s.get("data_status") == "READY")
        stale = sum(1 for s in self.registry.values() if s.get("data_status") == "STALE")
        insufficient = sum(1 for s in self.registry.values() if s.get("data_status") == "INSUFFICIENT_DATA")

        signal_counts = {
            "BUY CANDIDATE": 0,
            "WATCH": 0,
            "HOLD": 0,
            "EXIT": 0,
            "AVOID": 0,
            "SHORT": 0,  # Explicitly 0: Research only
            "INSUFFICIENT_DATA": insufficient,
        }

        analysed = 0
        latest_market_date = "2026-10-09"
        latest_scan_time = None

        for s in self.registry.values():
            if not s.get("is_active", True):
                continue
            sig_obj = s.get("latest_signal")
            if sig_obj:
                analysed += 1
                sig_type = sig_obj.get("signal", "").upper()
                if sig_type in ("BUY", "BUY CANDIDATE"):
                    signal_counts["BUY CANDIDATE"] += 1
                elif sig_type == "WATCH":
                    signal_counts["WATCH"] += 1
                elif sig_type == "HOLD":
                    signal_counts["HOLD"] += 1
                elif sig_type == "EXIT":
                    signal_counts["EXIT"] += 1
                elif sig_type == "AVOID":
                    signal_counts["AVOID"] += 1
                as_of = sig_obj.get("as_of")
                if as_of and as_of > latest_market_date:
                    latest_market_date = as_of
            scan_at = s.get("last_scanned_at")
            if scan_at and (not latest_scan_time or scan_at > latest_scan_time):
                latest_scan_time = scan_at

        return {
            "total_universe": total,
            "active_monitored": active,
            "refreshed_count": refreshed,
            "analysed_count": analysed,
            "stale_count": stale,
            "insufficient_data_count": insufficient,
            "signals": signal_counts,
            "short_candidates_validated": 0,
            "short_status_notice": "RESEARCH ONLY — Audited V4.0 strategy is long-only. No short strategy validated.",
            "latest_market_date": latest_market_date,
            "last_refresh_time": latest_scan_time or "2026-10-14 16:30:00 UTC",
            "data_provenance": DATA_PROVENANCE,
        }


# Singleton instance
universe_manager = UniverseManager()
