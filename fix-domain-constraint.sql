-- Fix domain constraint to allow NULL values
-- Copy and paste this into your Supabase SQL Editor

-- Remove NOT NULL constraint from domain column
ALTER TABLE users ALTER COLUMN domain DROP NOT NULL;

-- Success message
SELECT 'Domain constraint fixed - users can now sign up without a domain!' as result;
