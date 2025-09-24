-- Quick update script to add the missing users table to existing Supabase database
-- Run this in your Supabase SQL Editor

-- Users table - stores user onboarding data
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  domain TEXT NOT NULL UNIQUE,
  business_description TEXT,
  integrations JSONB DEFAULT '{}',
  analysis_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_domain ON users(domain);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at);

-- Enable Row Level Security (RLS)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role full access" ON users FOR ALL USING (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users read access" ON users FOR SELECT USING (auth.role() = 'authenticated');

-- Create trigger for users table
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Success message
SELECT 'Users table added successfully!' as message;




