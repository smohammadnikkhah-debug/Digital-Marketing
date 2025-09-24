-- Create simple content_calendar table with basic columns only
-- Run this in Supabase SQL Editor

-- Drop table if exists to start fresh
DROP TABLE IF EXISTS content_calendar CASCADE;

-- Create the table with basic columns
CREATE TABLE content_calendar (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    target_date DATE NOT NULL,
    platform VARCHAR(50) NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    description TEXT,
    hashtags TEXT[],
    seo_keywords TEXT[],
    status VARCHAR(50) DEFAULT 'planned',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure unique content per domain per date per platform
    UNIQUE(domain, target_date, platform)
);

-- Create indexes for better performance
CREATE INDEX idx_content_calendar_domain ON content_calendar(domain);
CREATE INDEX idx_content_calendar_date ON content_calendar(target_date);
CREATE INDEX idx_content_calendar_domain_date ON content_calendar(domain, target_date);
CREATE INDEX idx_content_calendar_status ON content_calendar(status);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_content_calendar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
CREATE TRIGGER trigger_update_content_calendar_updated_at
    BEFORE UPDATE ON content_calendar
    FOR EACH ROW
    EXECUTE FUNCTION update_content_calendar_updated_at();

-- Test the table with sample data
INSERT INTO content_calendar (domain, target_date, platform, content, title, description, hashtags, seo_keywords, status)
VALUES (
    'test.com',
    '2025-09-18',
    'twitter',
    'This is a test post for content calendar',
    'Test Post',
    'Test description',
    ARRAY['#test', '#content'],
    ARRAY['test', 'content'],
    'planned'
);

-- Verify the table was created
SELECT * FROM content_calendar WHERE domain = 'test.com';

-- Clean up test data
DELETE FROM content_calendar WHERE domain = 'test.com';

-- Show table structure
\d content_calendar;
