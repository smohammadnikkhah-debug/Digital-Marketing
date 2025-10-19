-- Add password_hash column to users table
-- Run this SQL in your Supabase SQL Editor

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Verify the column was added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name = 'password_hash';



