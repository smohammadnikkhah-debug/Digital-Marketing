-- Cleanup and Create Single Content Calendar Table
-- Run this in Supabase SQL Editor to clean up all existing tables and create one proper table

-- Step 1: Drop ALL existing content calendar related tables
DROP TABLE IF EXISTS content_calendar CASCADE;
DROP TABLE IF EXISTS content_calendar_entries CASCADE;
DROP TABLE IF EXISTS content_calendar_entry CASCADE;
DROP TABLE IF EXISTS content_calendar_items CASCADE;
DROP TABLE IF EXISTS content_calendar_posts CASCADE;

-- Step 2: Drop any related functions and triggers
DROP FUNCTION IF EXISTS update_content_calendar_updated_at() CASCADE;

-- Step 3: Create the single, clean content_calendar table
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

-- Step 4: Create indexes for better performance
CREATE INDEX idx_content_calendar_domain ON content_calendar(domain);
CREATE INDEX idx_content_calendar_date ON content_calendar(target_date);
CREATE INDEX idx_content_calendar_domain_date ON content_calendar(domain, target_date);
CREATE INDEX idx_content_calendar_status ON content_calendar(status);
CREATE INDEX idx_content_calendar_platform ON content_calendar(platform);

-- Step 5: Create function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_content_calendar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 6: Create trigger to automatically update updated_at
CREATE TRIGGER trigger_update_content_calendar_updated_at
    BEFORE UPDATE ON content_calendar
    FOR EACH ROW
    EXECUTE FUNCTION update_content_calendar_updated_at();

-- Step 7: Test the table with sample data
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

-- Step 8: Verify the table was created and test data inserted
SELECT 'Table created successfully!' as status;
SELECT * FROM content_calendar WHERE domain = 'test.com';

-- Step 9: Clean up test data
DELETE FROM content_calendar WHERE domain = 'test.com';

-- Step 10: Show final table structure
SELECT 
    'Final Table Structure:' as info,
    column_name, 
    data_type, 
    is_nullable, 
    column_default
FROM information_schema.columns 
WHERE table_name = 'content_calendar' 
ORDER BY ordinal_position;

-- Step 11: Show all tables to confirm cleanup
SELECT 
    'All Tables in Database:' as info,
    table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE '%content%'
ORDER BY table_name;
