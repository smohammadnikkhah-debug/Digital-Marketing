-- ==============================================================================
-- StockAnalysis Stage D2.2 / D2.3A.1: Non-Destructive Rollback Migration Script
-- Namespace: schema 'stockanalysis'
-- 
-- PRE-MIGRATION BACKUP & RECOVERY INSTRUCTIONS:
-- 1. Backup using pg_dump:
--    pg_dump -h aws-0-ap-southeast-1.pooler.supabase.com -p 5432 -U postgres -d postgres -n stockanalysis -f stockanalysis_pre_migration_backup.sql
-- 2. Verify System Settings snapshot:
--    SELECT key, value, updated_at FROM stockanalysis.system_settings WHERE key IN ('ibkr_bound_paper_account', 'ibkr_paper_snapshot', 'ibkr_paper_orders');
-- 3. Recovery:
--    psql -h aws-0-ap-southeast-1.pooler.supabase.com -p 5432 -U postgres -d postgres -f stockanalysis_pre_migration_backup.sql
-- 
-- NON-DESTRUCTIVE ROLLBACK GUARANTEE:
-- If transactional records exist in paper_orders, this script archives them to
-- stockanalysis.paper_orders_archive_<timestamp> (using LIKE ... INCLUDING ALL)
-- preserving column types, defaults, and constraints before dropping active tables.
--
-- ARCHIVE RESTORATION PROCEDURE (Rebuilding Constraints, Triggers, & Permissions):
-- To restore from an archived snapshot (replace <suffix> with timestamp):
-- 1. Re-run migrations/d2_2_paper_orders_transactional.sql to recreate active schema,
--    constraints, triggers, indexes, and grant scoped permissions to stockanalysis_app.
-- 2. Populate data from archive:
--    INSERT INTO stockanalysis.paper_orders SELECT * FROM stockanalysis.paper_orders_archive_<suffix>;
--    INSERT INTO stockanalysis.paper_order_events SELECT * FROM stockanalysis.paper_order_events_archive_<suffix>;
--    INSERT INTO stockanalysis.paper_execution_claims SELECT * FROM stockanalysis.paper_execution_claims_archive_<suffix>;
-- 3. Reset serial sequence for audit events:
--    SELECT setval(pg_get_serial_sequence('stockanalysis.paper_order_events', 'event_id'), COALESCE(MAX(event_id), 1)) FROM stockanalysis.paper_order_events;
-- ==============================================================================

BEGIN;

DO $$
DECLARE
    order_count INTEGER := 0;
    archive_suffix TEXT := to_char(NOW(), 'YYYYMMDD_HH24MISS');
BEGIN
    -- Check if paper_orders table exists and contains records
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'stockanalysis' AND table_name = 'paper_orders'
    ) THEN
        EXECUTE 'SELECT COUNT(*) FROM stockanalysis.paper_orders' INTO order_count;
        
        IF order_count > 0 THEN
            RAISE NOTICE 'Rollback safety: Found % transactional orders. Archiving to paper_*_archive_%...', order_count, archive_suffix;
            
            -- Archive preserving all column definitions, constraints, defaults, and indexes
            EXECUTE format('CREATE TABLE stockanalysis.paper_orders_archive_%s (LIKE stockanalysis.paper_orders INCLUDING ALL)', archive_suffix);
            EXECUTE format('INSERT INTO stockanalysis.paper_orders_archive_%s SELECT * FROM stockanalysis.paper_orders', archive_suffix);

            EXECUTE format('CREATE TABLE stockanalysis.paper_order_events_archive_%s (LIKE stockanalysis.paper_order_events INCLUDING ALL)', archive_suffix);
            EXECUTE format('INSERT INTO stockanalysis.paper_order_events_archive_%s SELECT * FROM stockanalysis.paper_order_events', archive_suffix);

            EXECUTE format('CREATE TABLE stockanalysis.paper_execution_claims_archive_%s (LIKE stockanalysis.paper_execution_claims INCLUDING ALL)', archive_suffix);
            EXECUTE format('INSERT INTO stockanalysis.paper_execution_claims_archive_%s SELECT * FROM stockanalysis.paper_execution_claims', archive_suffix);
            
            RAISE NOTICE 'Preserved % orders in archive tables with suffix % (including constraints, indexes, and defaults)', order_count, archive_suffix;
        ELSE
            RAISE NOTICE 'Rollback safety: paper_orders is empty (0 records). Proceeding with clean drop.';
        END IF;
    END IF;
END
$$;

-- Safely drop active triggers, functions, and active tables
DROP TRIGGER IF EXISTS trg_prevent_audit_event_mutation ON stockanalysis.paper_order_events;
DROP FUNCTION IF EXISTS stockanalysis.prevent_audit_event_mutation();
DROP TABLE IF EXISTS stockanalysis.paper_execution_claims CASCADE;
DROP TABLE IF EXISTS stockanalysis.paper_order_events CASCADE;
DROP TABLE IF EXISTS stockanalysis.paper_orders CASCADE;

COMMIT;
