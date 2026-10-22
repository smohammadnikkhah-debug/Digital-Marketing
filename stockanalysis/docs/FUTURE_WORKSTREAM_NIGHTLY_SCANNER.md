# Future Workstream — Nightly Stock Scanner (Non-Operational)

**Status:** Documented backlog only. **Not activated in Stage D2.3B.4.**

## Current state (verified)

`NightlyScanScheduler` in `web_app/backend/app/jobs.py`:

- Starts a daemon thread from FastAPI startup
- Loop only waits 60 seconds (heartbeat); **does not evaluate the universe**
- `last_run_time` / `next_run_time` are hardcoded placeholder strings
- DigitalOcean scheduled jobs remain **commented out** in primary `.do/app.yaml`

## Boundaries for a future stage

1. Do **not** modify the frozen Adaptive Trading V4.0 quantitative baseline or its Excel artifacts.
2. Do **not** enable DO cron until a separate approval covering Mozarex health checks and 231-stock scan gates.
3. Prefer durable job records (`refresh_jobs` / screener snapshots) over in-process stub status strings.
4. Keep scanner market data (Yahoo delayed) **segregated** from Alpaca/IBKR execution market-data contracts.

## Suggested future acceptance criteria

- Deterministic schedule in America/New_York with holiday/early-close awareness
- Idempotent daily run with audit trail in `stockanalysis` schema
- Explicit feature flag defaulting to disabled
- No coupling to paper-order execution agents
