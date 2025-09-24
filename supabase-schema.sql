-- Supabase Database Schema for Mozarex SEO Dashboard
-- Run this SQL in your Supabase SQL Editor to create the required tables

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table - stores user onboarding data and Auth0 integration
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  auth0_id TEXT UNIQUE, -- Auth0 user ID
  email TEXT UNIQUE,
  name TEXT,
  picture TEXT,
  domain TEXT UNIQUE,
  business_description TEXT,
  integrations JSONB DEFAULT '{}',
  analysis_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Websites table - stores basic website information
CREATE TABLE IF NOT EXISTS websites (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  domain VARCHAR(255) UNIQUE NOT NULL,
  company_name VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- SEO Analysis table - stores comprehensive SEO analysis data
CREATE TABLE IF NOT EXISTS seo_analyses (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
  analysis_data JSONB NOT NULL,
  analysis_type VARCHAR(50) DEFAULT 'comprehensive',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '14 days')
);

-- Keywords table - stores keyword analysis data
CREATE TABLE IF NOT EXISTS keywords (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
  keyword VARCHAR(255) NOT NULL,
  search_volume INTEGER DEFAULT 0,
  difficulty INTEGER DEFAULT 0,
  current_rank INTEGER,
  optimization_notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Content Calendar table - stores AI-generated content calendar
CREATE TABLE IF NOT EXISTS content_calendar (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
  keyword_id UUID REFERENCES keywords(id) ON DELETE SET NULL,
  content_type VARCHAR(50) NOT NULL, -- twitter, facebook, tiktok, instagram
  target_date DATE NOT NULL,
  content_ideas TEXT NOT NULL,
  status VARCHAR(50) DEFAULT 'planned', -- planned, scheduled, published
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chat History table - stores Mozarex AI chat conversations
CREATE TABLE IF NOT EXISTS chat_history (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
  user_message TEXT NOT NULL,
  ai_response TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_domain ON users(domain);
CREATE INDEX IF NOT EXISTS idx_users_auth0_id ON users(auth0_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at);
CREATE INDEX IF NOT EXISTS idx_websites_domain ON websites(domain);
CREATE INDEX IF NOT EXISTS idx_seo_analyses_website_id ON seo_analyses(website_id);
CREATE INDEX IF NOT EXISTS idx_seo_analyses_expires_at ON seo_analyses(expires_at);
CREATE INDEX IF NOT EXISTS idx_keywords_website_id ON keywords(website_id);
CREATE INDEX IF NOT EXISTS idx_keywords_search_volume ON keywords(search_volume DESC);
CREATE INDEX IF NOT EXISTS idx_content_calendar_website_id ON content_calendar(website_id);
CREATE INDEX IF NOT EXISTS idx_content_calendar_target_date ON content_calendar(target_date);
CREATE INDEX IF NOT EXISTS idx_chat_history_website_id ON chat_history(website_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at DESC);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for websites table
CREATE TRIGGER update_websites_updated_at 
    BEFORE UPDATE ON websites 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create trigger for users table
CREATE TRIGGER update_users_updated_at 
    BEFORE UPDATE ON users 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (RLS) policies
-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE websites ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_calendar ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role full access" ON users FOR ALL USING (true);
CREATE POLICY "Service role full access" ON websites FOR ALL USING (true);
CREATE POLICY "Service role full access" ON seo_analyses FOR ALL USING (true);
CREATE POLICY "Service role full access" ON keywords FOR ALL USING (true);
CREATE POLICY "Service role full access" ON content_calendar FOR ALL USING (true);
CREATE POLICY "Service role full access" ON chat_history FOR ALL USING (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users read access" ON users FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON websites FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON seo_analyses FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON keywords FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON content_calendar FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON chat_history FOR SELECT USING (auth.role() = 'authenticated');

-- Insert sample data for testing (optional)
INSERT INTO websites (domain, company_name) VALUES 
('mozarex.com', 'Mozarex Digital Marketing'),
('example.com', 'Example Company')
ON CONFLICT (domain) DO NOTHING;

-- Create a function to clean up expired analyses
CREATE OR REPLACE FUNCTION cleanup_expired_analyses()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM seo_analyses WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create a function to get website statistics
CREATE OR REPLACE FUNCTION get_website_stats(website_domain TEXT)
RETURNS TABLE (
    total_analyses BIGINT,
    total_keywords BIGINT,
    total_calendar_entries BIGINT,
    total_chat_messages BIGINT,
    last_analysis_date TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT sa.id) as total_analyses,
        COUNT(DISTINCT k.id) as total_keywords,
        COUNT(DISTINCT cc.id) as total_calendar_entries,
        COUNT(DISTINCT ch.id) as total_chat_messages,
        MAX(sa.created_at) as last_analysis_date
    FROM websites w
    LEFT JOIN seo_analyses sa ON w.id = sa.website_id
    LEFT JOIN keywords k ON w.id = k.website_id
    LEFT JOIN content_calendar cc ON w.id = cc.website_id
    LEFT JOIN chat_history ch ON w.id = ch.website_id
    WHERE w.domain = website_domain;
END;
$$ LANGUAGE plpgsql;

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;

-- Success message
SELECT 'Mozarex SEO Dashboard database schema created successfully!' as message;
