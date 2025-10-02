-- Add plan column to existing users table
-- Run this SQL in your Supabase SQL Editor

-- Add plan column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'basic';

-- Update existing users to have basic plan if they don't have one
UPDATE users SET plan = 'basic' WHERE plan IS NULL;

-- Add constraint to ensure plan is one of the valid values
ALTER TABLE users ADD CONSTRAINT check_plan 
CHECK (plan IN ('basic', 'pro', 'business'));

-- Add comment to the column
COMMENT ON COLUMN users.plan IS 'User subscription plan: basic, pro, or business';
