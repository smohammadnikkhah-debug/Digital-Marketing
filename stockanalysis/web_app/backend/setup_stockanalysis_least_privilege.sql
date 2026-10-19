-- ==============================================================================
-- StockAnalysis — Hardened Least-Privilege Role Setup for Supabase PostgreSQL
-- Project: nrunrjfmqczeowakjnjh
--
-- Security Objectives:
-- 1. Create a dedicated application runtime role: 'stockanalysis_app'.
-- 2. Explicitly enforce NOINHERIT, NOBYPASSRLS, NOSUPERUSER, NOCREATEDB, NOCREATEROLE.
-- 3. Verify zero membership in privileged roles and zero ownership of production objects.
-- 4. Strictly separate Runtime (DML only) from Migration/Admin (DDL) privileges.
-- 5. Neutralize inherited permissions from the pseudo-role 'PUBLIC' on 'stockanalysis'.
-- 6. Preserve ALL existing Mozarex/AivekAI roles, PUBLIC schema grants, and permissions.
-- 7. Explicitly block all access to 'public' (Mozarex/AivekAI), 'auth', 'storage', 'vault'.
-- 8. Verify effective privileges non-destructively using has_schema_privilege() and has_table_privilege().
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Step 1: Ensure Isolated Schema Exists
-- ------------------------------------------------------------------------------
-- Creates the isolated namespace for StockAnalysis tables and sequences.
-- Does not touch, alter, or recreate 'public' or any existing schema.
CREATE SCHEMA IF NOT EXISTS stockanalysis;

-- ------------------------------------------------------------------------------
-- Step 2: Neutralize PUBLIC Pseudo-Role Inherited Permissions on 'stockanalysis'
-- ------------------------------------------------------------------------------
-- In PostgreSQL, newly created schemas may inherit default USAGE or CREATE for PUBLIC.
-- This revokes all permissions on schema 'stockanalysis' from the pseudo-role PUBLIC.
-- CRITICAL CONFIRMATION: This targets ONLY schema 'stockanalysis'.
-- It does NOT modify permissions on schema 'public' or affect Mozarex/AivekAI.
REVOKE USAGE, CREATE ON SCHEMA stockanalysis FROM PUBLIC;

-- ------------------------------------------------------------------------------
-- Step 3: Create Runtime Role 'stockanalysis_app' (DML Only, No Inheritance)
-- ------------------------------------------------------------------------------
-- Role Attributes:
-- - LOGIN: Allows database authentication.
-- - NOSUPERUSER: Zero administrative powers.
-- - NOCREATEDB: Cannot create or drop databases.
-- - NOCREATEROLE: Cannot create, alter, or drop other database roles.
-- - NOINHERIT: Cannot automatically inherit privileges from any group roles.
-- - NOBYPASSRLS: Cannot bypass Row Level Security on any table in the database.
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
            PASSWORD 'REPLACE_WITH_SECURE_STRONG_PASSWORD';
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

-- ------------------------------------------------------------------------------
-- Step 4: Ensure NO Membership in Privileged Roles and Zero Object Ownership
-- ------------------------------------------------------------------------------
-- 4a. Explicitly revoke any potential membership in privileged or Supabase default roles
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

-- ------------------------------------------------------------------------------
-- Step 5: Strict Revocations on Mozarex / AivekAI Production Tables (Schema 'public')
-- ------------------------------------------------------------------------------
-- Explicitly revokes all schema, table, sequence, and routine privileges from 'stockanalysis_app'.
-- CRITICAL CONFIRMATION:
-- - This revokes privileges FROM 'stockanalysis_app' ONLY.
-- - It does NOT revoke anything from 'PUBLIC', 'postgres', 'anon', 'authenticated', or 'service_role'.
-- - Existing Mozarex and AivekAI production roles, permissions, and grants remain 100% UNTOUCHED.
REVOKE ALL ON SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM stockanalysis_app;
REVOKE ALL ON ALL ROUTINES IN SCHEMA public FROM stockanalysis_app;

-- Ensure future tables created by any role in 'public' grant nothing to 'stockanalysis_app'
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM stockanalysis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM stockanalysis_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON ROUTINES FROM stockanalysis_app;

-- ------------------------------------------------------------------------------
-- Step 6: Strict Revocations on Supabase System & Protected Schemas
-- ------------------------------------------------------------------------------
-- Ensures 'stockanalysis_app' cannot read or write auth.users, storage.objects, vault secrets, etc.
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

-- ------------------------------------------------------------------------------
-- Step 7: Grant RUNTIME DML Privileges in 'stockanalysis' Schema (Zero DDL)
-- ------------------------------------------------------------------------------
-- Runtime vs. Migration Privilege Separation:
-- - Migration Role (postgres): Possesses DDL (CREATE, ALTER, DROP, TRUNCATE). Runs schema migrations.
-- - Runtime Role (stockanalysis_app): Possesses DML ONLY (SELECT, INSERT, UPDATE, DELETE).
--   Notice: NO CREATE privilege is granted on schema 'stockanalysis'.
--   Runtime application CANNOT create tables, drop tables, alter columns, or modify schema.

-- Allow connection and schema namespace resolution (no CREATE)
GRANT USAGE ON SCHEMA stockanalysis TO stockanalysis_app;

-- Allow DML operations on all existing StockAnalysis tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stockanalysis TO stockanalysis_app;

-- Allow sequence usage for auto-incrementing surrogate keys
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA stockanalysis TO stockanalysis_app;

-- Ensure future tables created by the migration role (postgres) automatically grant DML to runtime role
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA stockanalysis
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stockanalysis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA stockanalysis
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO stockanalysis_app;

-- Set default search path as a convenience (Security is strictly enforced by table-level grants)
ALTER ROLE stockanalysis_app SET search_path TO stockanalysis;

-- ------------------------------------------------------------------------------
-- Step 8: Safe, Non-Destructive Privilege Introspection Queries
-- ------------------------------------------------------------------------------
-- These verification queries inspect PostgreSQL catalog metadata directly using
-- has_schema_privilege() and has_table_privilege(). They evaluate effective permissions
-- (including PUBLIC and inherited grants) WITHOUT inserting, updating, or modifying
-- any data in AivekAI or Mozarex tables.
/*
-- 1. Verify NO membership in privileged Supabase roles:
SELECT r.rolname AS privileged_role, 
       pg_has_role('stockanalysis_app', r.rolname, 'member') AS is_member
FROM pg_roles r
WHERE r.rolname IN ('postgres', 'service_role', 'supabase_admin', 'anon', 'authenticated', 'authenticator', 'dashboard_user');
-- Expected: ALL rows return is_member = FALSE

-- 2. Verify role does NOT own any database objects:
SELECT count(*) AS owned_objects_count
FROM pg_class c
JOIN pg_roles r ON r.oid = c.relowner
WHERE r.rolname = 'stockanalysis_app';
-- Expected: owned_objects_count = 0

-- 3. Verify effective privileges on Mozarex / AivekAI tables (public schema):
SELECT 
    has_schema_privilege('stockanalysis_app', 'public', 'CREATE') AS can_create_in_public,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'SELECT') AS can_read_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'INSERT') AS can_write_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'UPDATE') AS can_update_mozarex,
    has_table_privilege('stockanalysis_app', 'public.website_audits', 'DELETE') AS can_delete_mozarex;
-- Expected: can_create_in_public = FALSE, can_read_mozarex = FALSE, can_write_mozarex = FALSE, can_update_mozarex = FALSE, can_delete_mozarex = FALSE

-- 4. Verify effective privileges on Supabase internal schemas (auth, storage, vault):
SELECT 
    has_schema_privilege('stockanalysis_app', 'auth', 'USAGE') AS can_use_auth,
    has_table_privilege('stockanalysis_app', 'auth.users', 'SELECT') AS can_read_auth_users,
    has_schema_privilege('stockanalysis_app', 'storage', 'USAGE') AS can_use_storage,
    has_schema_privilege('stockanalysis_app', 'vault', 'USAGE') AS can_use_vault;
-- Expected: ALL return FALSE

-- 5. Verify DDL is blocked while DML is permitted on StockAnalysis schema:
SELECT 
    has_schema_privilege('stockanalysis_app', 'stockanalysis', 'USAGE') AS can_use_schema,
    has_schema_privilege('stockanalysis_app', 'stockanalysis', 'CREATE') AS can_create_tables_ddl,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'SELECT') AS can_read_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'INSERT') AS can_insert_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'UPDATE') AS can_update_monitored_stocks,
    has_table_privilege('stockanalysis_app', 'stockanalysis.monitored_stocks', 'DELETE') AS can_delete_monitored_stocks;
-- Expected: can_use_schema = TRUE, can_create_tables_ddl = FALSE (DDL blocked!), all DML operations = TRUE
*/
