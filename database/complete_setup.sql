-- Complete Database Setup Script for Mozarex SEO Dashboard
-- Run this script in Supabase SQL Editor to set up the complete database

-- Step 1: Run the base schema first
-- Copy and paste the contents of supabase-schema.sql here
-- (This creates users, websites, seo_analyses, keywords, content_calendar, chat_history tables)

-- Step 2: Run the campaign schema
-- Copy and paste the contents of database/campaign_schema.sql here
-- (This creates campaign management tables and sample data)

-- Step 3: Verify the setup
SELECT 
    'Database Setup Complete!' as status,
    (SELECT COUNT(*) FROM users) as users_count,
    (SELECT COUNT(*) FROM websites) as websites_count,
    (SELECT COUNT(*) FROM campaigns) as campaigns_count,
    (SELECT COUNT(*) FROM social_accounts) as social_accounts_count,
    (SELECT COUNT(*) FROM campaign_templates) as templates_count;

-- Step 4: Test the campaign system
SELECT 
    'Campaign System Ready!' as status,
    ct.name as template_name,
    ct.template_data->'twitter'->>'content' as sample_twitter_content
FROM campaign_templates ct 
WHERE ct.is_default = true;

-- Success message
SELECT '🎉 Mozarex SEO Dashboard with Campaign Management is ready!' as message;






