# Stage D2.3B.4 — Workspace Synchronization Plan

**Deployment source of truth:** `Digital Marketing` Git repository  
**Secondary workspace:** `StockAnalysis` (no git; research + frontend source)  
**Policy:** No blind directory copies. No activation of secondary `.do` cron.

## Hash comparison method

```powershell
Get-FileHash -Algorithm SHA256 <path>
# or
fc /b <dm-path> <sa-path>
```

## Selective sync matrix (DM → SA unless noted)

| Path | Action | Rationale |
|------|--------|-----------|
| `alpaca_adapter/alpaca_verification.py` | Sync DM → SA | D2.3B.4 verifier contract |
| `alpaca_adapter/alpaca_paper_adapter.py` | Sync DM → SA | Receipt timestamps / skew fields |
| `alpaca_adapter/alpaca_execution_agent.py` | Sync DM → SA | DM path portability |
| `alpaca_adapter/run_iex_validation.bat` | Sync DM → SA (optional; update paths) | Overnight runner |
| `stockanalysis/web_app/backend/app/services/market_data_service.py` → SA `web_app/backend/...` | Sync DM → SA | Shared contract |
| `stockanalysis/web_app/backend/app/models.py` → SA | Sync DM → SA | Account constraint alignment |
| `stockanalysis/web_app/backend/migrations/d2_2_*.sql` → SA | Sync DM → SA | DM has Alpaca regex (newer) |
| `stockanalysis/web_app/backend/tests/test_market_data_contract_d2_3b4.py` | Sync DM → SA | New regressions |
| `stockanalysis/web_app/backend/tests/conftest.py`, `pytest.ini` | Sync DM → SA | Test taxonomy |
| `stockanalysis/web_app/backend/tests/test_alpaca_*.py`, `test_d2_3a1_final_verification.py`, `test_isolated_postgres_*` | Sync DM → SA | Stabilization |
| `stockanalysis/web_app/frontend/src/**` | **Do not overwrite from DM** | Frontend source preserved in SA only |
| `stockanalysis/dist/**` | Rebuild from SA frontend when UI changes approved | Deploy artifact lives in DM |
| `StockAnalysis/web_app/.do/app.yaml` | **Do not sync / do not deploy** | Cron enabled; not Mozarex SoT |
| `adaptive_trading_v40/**` baseline Excel/cache | **Do not modify** | Frozen V4.0 baseline |
| `adaptive_trading_v50/**` | Remain SA-only research | Out of D2.3B.4 scope |

## Explicit non-goals

- No DigitalOcean deploy from secondary workspace
- No enabling `scheduled-market-*` jobs in primary `.do/app.yaml`
- No git commit/push in this stage
