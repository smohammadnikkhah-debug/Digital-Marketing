-- Migration Script: From Old Schema to New Proper Schema
-- This script helps migrate existing data to the new structure

-- Step 1: Backup existing data (if any)
-- Note: This is just for reference - actual backup should be done before running this migration

-- Step 2: Create the new schema
-- Run the proper-database-schema.sql first

-- Step 3: Migrate existing data from old structure to new structure
-- This assumes you have existing data in the old 'users' table

-- Migrate customers from old users table
INSERT INTO customers (company_name, contact_email, business_description, industry)
SELECT 
    COALESCE(business_description, 'Unknown Company') as company_name,
    CONCAT('user@', domain) as contact_email, -- Generate email from domain
    business_description,
    'Unknown' as industry
FROM users
WHERE domain IS NOT NULL
ON CONFLICT (contact_email) DO NOTHING;

-- Migrate websites from old users table
INSERT INTO websites (customer_id, domain, website_name, website_description)
SELECT 
    c.id as customer_id,
    u.domain,
    COALESCE(u.business_description, u.domain) as website_name,
    u.business_description as website_description
FROM users u
JOIN customers c ON c.contact_email = CONCAT('user@', u.domain)
WHERE u.domain IS NOT NULL
ON CONFLICT (domain) DO NOTHING;

-- Step 4: Update any existing content_calendar data to use website_id
-- This assumes you have existing content_calendar data with domain field

UPDATE content_calendar 
SET website_id = w.id
FROM websites w
WHERE content_calendar.domain = w.domain
AND content_calendar.website_id IS NULL;

-- Step 5: Clean up old tables (optional - uncomment if you want to remove old tables)
-- DROP TABLE IF EXISTS users CASCADE;

-- Step 6: Verify the migration
SELECT 
    'Migration completed!' as status,
    COUNT(*) as total_customers
FROM customers;

SELECT 
    'Websites migrated:' as status,
    COUNT(*) as total_websites
FROM websites;

SELECT 
    'Content calendar entries updated:' as status,
    COUNT(*) as total_content_items
FROM content_calendar
WHERE website_id IS NOT NULL;

-- Success message
SELECT 'Migration to new schema completed successfully!' as message;
