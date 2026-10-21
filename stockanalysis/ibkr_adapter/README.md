# StockAnalysis IBKR Paper Trading Windows Adapter

**Adaptive Trading V4.0 — Stage D1B: Read-Only Paper Account Integration**

This adapter runs on your Windows workstation alongside Interactive Brokers (IBKR) Gateway and securely publishes paper account balance, buying power, cash, and positions to the StockAnalysis platform.

---

## Security & Architecture Highlights

1. **Strictly Read-Only:** All order placement and cancellation methods (`placeOrder`, `cancelOrder`, `reqGlobalCancel`) are disabled and raise exceptions if invoked.
2. **Outbound-Only Communication:** Port 4002 remains strictly on `127.0.0.1` and is **never** exposed to the internet. The adapter initiates outbound HTTPS POST requests to the cloud platform.
3. **No IBKR Credentials Stored:** You log into IB Gateway normally on Windows using your paper trading credentials. The adapter connects locally to the unauthenticated local socket API.
4. **Segregation:** Paper account data is isolated from real user portfolios and the audited V4.0 quantitative baseline backtest.
5. **Staleness Protection:** If the adapter stops running, the StockAnalysis dashboard automatically displays a stale-data warning after 5 minutes.

---

## Prerequisites

- Windows 10/11
- IBKR Gateway for Windows (Paper Trading mode enabled, Socket Port 4002, Client ID 21)
- Python 3.10+ with `ibapi` and `requests` installed

---

## Configuration

You can pass CLI arguments or create a `.env` file:

```bash
# Gateway settings
IBKR_GATEWAY_HOST=127.0.0.1
IBKR_GATEWAY_PORT=4002
IBKR_CLIENT_ID=21

# StockAnalysis Destination
STOCKANALYSIS_BACKEND_URL=http://127.0.0.1:8000
IBKR_INGESTION_KEY=ibkr-ingest-key-dev-local-2026

# Polling Interval (seconds)
SYNC_INTERVAL_SECONDS=60
```

---

## How to Run

### 1. Test Gateway Connectivity (Dry-Run)
Prints the snapshot directly to your console without sending it to the backend:
```powershell
python ibkr_adapter.py --dry-run
```

### 2. Single Sync Pass
Publishes one snapshot to the StockAnalysis platform and exits:
```powershell
python ibkr_adapter.py --once
```

### 3. Continuous Background Sync
Pushes an update every 60 seconds with automated reconnection:
```powershell
python ibkr_adapter.py --interval 60
```

### 4. Mock / Offline Demo Mode
Useful for testing the dashboard when IB Gateway is not running:
```powershell
python ibkr_adapter.py --mock --once
```
