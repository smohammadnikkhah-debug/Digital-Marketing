-- Remove domain UNIQUE constraint to allow multiple users per domain
-- Copy and paste this into your Supabase SQL Editor

-- Remove UNIQUE constraint from domain column
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_domain_key;

-- Success message
SELECT 'Domain UNIQUE constraint removed - multiple users can now use the same domain!' as result;
