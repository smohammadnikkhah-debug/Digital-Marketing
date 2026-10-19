# StockAnalysis — Controlled Production Deployment Plan (Option A)

**Target Application:** `digital-marketing-seo-analyzer` (DigitalOcean App Platform)  
**Database:** Supabase Free PostgreSQL (Project: `nrunrjfmqczeowakjnjh`, isolated schema `stockanalysis`)  
**Storage Destination:** Supabase Storage Private Bucket (`stockanalysis-backups`)  
**Strategy Baseline:** Frozen Adaptive Trading V4.0 Research Baseline  
**Brokerage Connectivity:** IBKR DISCONNECTED (Zero live trading connection)

---

## 1. Safety Boundaries & Core Architecture Guarantees

1. **Non-Destructive Guarantee (Data Preservation by Default):**
   - Rollback instructions **NEVER execute `DROP SCHEMA stockanalysis CASCADE`**.
   - Rollback is non-destructive: reverting container deployments in DigitalOcean preserves all StockAnalysis database records (`daily_bars`, `screener_snapshots`, `portfolios`, `monitored_stocks`, etc.) intact in Supabase PostgreSQL.
   - The existing `public` schema (Mozarex & AivekAI), `auth`, `storage`, and `vault` are completely untouched.
2. **Hardened Least-Privilege Role Architecture:**
   - Security is enforced at the database kernel level (table-level permissions), **not relying on `search_path` alone**.
   - Pseudo-role `PUBLIC` inherited privileges on schema `stockanalysis` are explicitly revoked.
   - Separation of **Runtime (DML only)** from **Migration (DDL)** privileges. The runtime application role `stockanalysis_app` possesses zero DDL privileges (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` are blocked).
   - Zero access permissions to `public.*`, `auth.*`, `storage.*`, `vault.*`.
3. **Endpoint Protection & Excessive Submission Prevention:**
   - The manual refresh endpoint (`/api/scanner/refresh`) is restricted to authenticated administrators and authorized API credentials.
   - Protected against excessive job submissions via dedicated rate limiting (max 5 requests per 15 minutes) and concurrency guards (HTTP 409 Conflict if a job is already in flight).
4. **Independent Approval Checkpoints:**
   - `deploy_on_push: false` is configured across all services in `.do/app.yaml`.
   - **Git Commit**, **Git Push**, and **DigitalOcean Deployment** are decoupled into independently approved steps. Pushing to `master` will not trigger an automatic deployment.
5. **Deferred Scheduled Jobs:**
   - Scheduled market-open and market-close cron jobs remain disabled during initial deployment. They are activated only after the full 231-stock live scan and Mozarex service checks pass.

---

## 2. Completed Step 1: Pre-Deployment Durable Backup

A verified durable backup of the existing StockAnalysis data was created and uploaded to private Supabase Storage:

- **Backup Identifier:** `pre_deploy_backup_v40_20261018_233052`
- **Timestamp:** `2026-10-18 23:30:52 UTC`
- **Storage Destination:** Private Supabase Storage bucket `stockanalysis-backups` (Project: `nrunrjfmqczeowakjnjh`)
- **Storage Key:** `stockanalysis-backups/pre_deploy_backup_v40_20261018_233052.json.gz`
- **Archive Size:** 36,575 bytes (Uncompressed: 467,019 bytes, **12.77x compression ratio**)
- **SHA-256 Checksum:** `362daa3f89d8303efa4ba7bed3380e8f5582e141e36cd9f152a46b28b5a0ab3c`
- **Integrity Verification:** Downloaded from Supabase Storage and decompressed; payload checksum match: **`True`**
- **Covered Tables (11/11):**
  - `monitored_stocks`: 231 records
  - `portfolios`: 1 record
  - `portfolio_transactions`: 1 record
  - `portfolio_lots`: 0 records
  - `screener_snapshots`: 3 records
  - `refresh_jobs`: 2 records
  - `daily_bars`: 1 record
  - `watchlist_stocks`: 0 records
  - `backtest_runs`: 0 records
  - `system_settings`: 0 records
  - `users`: 0 records
  - **Total Records:** 239 records

---

## 3. Database Least-Privilege Provisioning & Security Script

Before deploying the runtime application, execute [`setup_stockanalysis_least_privilege.sql`](file:///C:/Users/zeiva/OneDrive/Desktop/Project/StockAnalysis/web_app/backend/setup_stockanalysis_least_privilege.sql) in the Supabase SQL Editor:

```sql
-- 1. Ensure isolated application schema exists
CREATE SCHEMA IF NOT EXISTS stockanalysis;

-- 2. Neutralize PUBLIC pseudo-role inherited permissions on schema
REVOKE USAGE, CREATE ON SCHEMA stockanalysis FROM PUBLIC;

-- 3. Create dedicated runtime role 'stockanalysis_app' (DML Only, No Inheritance)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'stockanalysis_app') THEN
        CREATE ROLE stockanalysis_app WITH 
            LOGIN 
            NOSUPERUSER 
            NOCREATEDB 
            NOCREATEROLE 
            NOINHERIT 
            NOBYPASSRLS 
            PASSWORD '<STRONG_PRODUCTION_PASSWORD>';
    ELSE
        ALTER ROLE stockanalysis_app WITH 
            NOSUPERUSER 
            NOCREATEDB 
            NOCREATEROLE 
            NOINHERIT 
            NOBYPASSRLS;
    END IF;
END
$$;

-- 4. Ensure NO membership in privileged roles and zero object ownership
DO $$
DECLARE
    priv_role text;
BEGIN
    FOR priv_role IN 
        SELECT rolname FROM pg_roles WHERE rolname IN (
            'postgres', 'service_role', 'supabase_admin', 
            'anon', 'authenticated', 'authenticator', 'dashboard_user'
        )
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_auth_members m
            JOIN pg_roles r ON r.oid = m.roleid
            JOIN pg_roles member ON member.oid = m.member
            WHERE r.rolname = priv_role AND member.rolname = 'stockanalysis_app'
        ) THEN
            EXECUTE format('REVOKE %I FROM stockanalysis_app;', priv_role);
        END IF;
    END LOOP;
END
$$;

-- 4b. Read-Only Ownership Audit: Verify stockanalysis_app does not own any database objects.
-- If unexpected ownership is detected, fail immediately and report it without modifying ownership.
DO $$
DECLARE
    owned_count integer;
BEGIN
    SELECT count(*) INTO owned_count
    FROM pg_class c
    JOIN pg_roles r ON r.oid = c.relowner
    WHERE r.rolname = 'stockanalysis_app';

    IF owned_count > 0 THEN
        RAISE EXCEPTION 'SECURITY AUDIT HALTED: stockanalysis_app owns % database object(s). Unexpected ownership detected. Halting without modifying ownership.', owned_count;
    END IF;
END
$$;

-- 5. Explicitly revoke ALL privileges on public schema (Mozarex & AivekAI)
REVOKE ALL ON SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM stockanalysis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM stockanalysis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM stockanalysis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON ROUTINES FROM stockanalysis_app;

-- 6. Revoke ALL privileges on sensitive Supabase internal schemas
DO $$
DECLARE
    sys_schema text;
BEGIN
    FOR sys_schema IN SELECT nspname FROM pg_namespace WHERE nspname IN ('auth', 'storage', 'vault', 'supabase_migrations', 'graphql', 'realtime') LOOP
        EXECUTE format('REVOKE ALL ON SCHEMA %I FROM stockanalysis_app', sys_schema);
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM stockanalysis_app', sys_schema);
        EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM stockanalysis_app', sys_schema);
        EXECUTE format('REVOKE ALL ON ALL ROUTINES IN SCHEMA %I FROM stockanalysis_app', sys_schema);
    END LOOP;
END
$$;

-- 7. Grant RUNTIME DML privileges ONLY in 'stockanalysis' schema (NO DDL)
GRANT USAGE ON SCHEMA stockanalysis TO stockanalysis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stockanalysis TO stockanalysis_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA stockanalysis TO stockanalysis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA stockanalysis
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stockanalysis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA stockanalysis
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO stockanalysis_app;

-- 8. Set default search_path as convenience
ALTER ROLE stockanalysis_app SET search_path TO stockanalysis;
```

### Safe, Non-Destructive Privilege Introspection Queries
Run these verification queries in the Supabase SQL editor to evaluate effective permissions without mutating any Mozarex or AivekAI tables:

```sql
-- Test 1: Verify NO membership in privileged Supabase roles
SELECT r.rolname AS privileged_role, 
       pg_has_role('stockanalysis_app', r.rolname, 'member') AS is_member
FROM pg_roles r
WHERE r.rolname IN ('postgres', 'service_role', 'supabase_admin', 'anon', 'authenticated', 'authenticator', 'dashboard_user');
-- Expected: ALL rows return is_member = FALSE

-- Test 2: Verify role does NOT own any database objects
SELECT count(*) AS owned_objects_count
FROM pg_class c
JOIN pg_roles r ON r.oid = c.relowner
WHERE r.rolname = 'stockanalysis_app';
-- Expected: owned_objects_count = 0

-- Test 3: Verify effective privileges on Mozarex / AivekAI tables (public schema)
SELECT 
    has_schema_privilege('stockanalysis_app', 'public', 'CREATE') AS can_create_in_public,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'SELECT') AS can_read_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'INSERT') AS can_write_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'UPDATE') AS can_update_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'DELETE') AS can_delete_mozarex;
-- Expected: ALL return FALSE

-- Test 4: Verify effective privileges on Supabase internal schemas (auth, storage, vault)
SELECT 
    has_schema_privilege('stockanalysis_app', 'auth', 'USAGE') AS can_use_auth,
    has_table_privilege('stockanalysis_app', 'auth.users', 'SELECT') AS can_read_auth_users,
    has_schema_privilege('stockanalysis_app', 'storage', 'USAGE') AS can_use_storage,
    has_schema_privilege('stockanalysis_app', 'vault', 'USAGE') AS can_use_vault;
-- Expected: ALL return FALSE

-- Test 5: Verify DDL is blocked while DML is permitted on StockAnalysis schema
SELECT 
    has_schema_privilege('stockanalysis_app', 'stockanalysis', 'USAGE') AS can_use_schema,
    has_schema_privilege('stockanalysis_app', 'stockanalysis', 'CREATE') AS can_create_tables_ddl,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'SELECT') AS can_read_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'INSERT') AS can_insert_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'UPDATE') AS can_update_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'DELETE') AS can_delete_monitored_stocks;
-- Expected: can_use_schema = TRUE, can_create_tables_ddl = FALSE (DDL blocked!), all DML operations = TRUE
```

---

## 4. End-to-End Phased Deployment Workflow

```
[COMPLETED] Step 1: Pre-deployment durable database backup created & verified in Supabase Storage.
    ↓
[COMPLETED] Step 2: Dedicated stockanalysis_app least-privilege role provisioned & empirically verified.
    ↓
[AWAITING]  Step 3: DigitalOcean secrets & app spec assembled and verified (DATABASE_URL, STOCKANALYSIS_ADMIN_KEY). 
                    Awaiting user approval due to DO App Platform automatic deployment trigger gate.
    ↓
[PENDING]   Step 4: User approves Git Commit of local changes (deploy_on_push: false).
    ↓
[PENDING]   Step 5: User approves Git Push to branch master.
    ↓
[PENDING]   Step 6: User approves applying DO App Spec / triggering DigitalOcean Deployment.
    ↓
[PENDING]   Step 7: Production verification: Mozarex.com health, 231-stock scan, CPU/memory telemetry, browser disconnect check.
    ↓
[PENDING]   Step 8: User approves activating scheduled market-open and market-close jobs (Phase 2).
```

---

## 5. Non-Destructive Rollback Procedure (Preserving StockAnalysis Data)

If any anomaly or failure occurs during or after deployment:

1. **DigitalOcean Application Rollback (Zero Downtime):**
   - In DigitalOcean App Platform $\rightarrow$ App `digital-marketing-seo-analyzer` $\rightarrow$ **Deployments** $\rightarrow$ Click **Rollback** to the prior active deployment.
   - Alternatively: Revert commit on `master` and redeploy.
   - **Result:** Traffic routes back to the previous stable release. Mozarex website continues running without interruption.
2. **Database Data Preservation:**
   - **No tables or schemas are dropped.** All StockAnalysis data in `stockanalysis.*` is retained intact.
   - If historical signal rollback is needed, revert the active snapshot flag:
     ```sql
     UPDATE stockanalysis.screener_snapshots SET is_active = false WHERE is_active = true;
     UPDATE stockanalysis.screener_snapshots SET is_active = true WHERE id = 'snap_pre_deploy_baseline';
     ```
   - If full point-in-time database restoration is required, restore from the verified backup archive (`pre_deploy_backup_v40_20261018_233052.json.gz`) into `stockanalysis` using `python -m app.cli restore-db --from-cloud pre_deploy_backup_v40_20261018_233052.json.gz --allow-overwrite`.
   - **Zero impact on Mozarex (`public.*`) or AivekAI tables.**
