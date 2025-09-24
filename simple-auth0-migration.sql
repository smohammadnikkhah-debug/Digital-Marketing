-- Simple migration to add Auth0 fields
-- Copy and paste this into your Supabase SQL Editor

-- Add Auth0 fields to users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS auth0_id TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS email TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS name TEXT,
ADD COLUMN IF NOT EXISTS picture TEXT;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_users_auth0_id ON users(auth0_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Success message
SELECT 'Auth0 fields added successfully!' as result;
