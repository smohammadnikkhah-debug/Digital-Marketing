-- Test Campaign Management System
-- Run this after setting up the database to verify everything works

-- Test 1: Check if all tables exist
SELECT 
    table_name,
    CASE 
        WHEN table_name IN ('users', 'websites', 'seo_analyses', 'keywords', 'content_calendar', 'chat_history') 
        THEN '✅ Base Tables'
        WHEN table_name IN ('social_accounts', 'campaigns', 'campaign_posts', 'campaign_templates', 'campaign_analytics', 'campaign_scheduling_rules')
        THEN '✅ Campaign Tables'
        ELSE '❓ Other Tables'
    END as category
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN (
    'users', 'websites', 'seo_analyses', 'keywords', 'content_calendar', 'chat_history',
    'social_accounts', 'campaigns', 'campaign_posts', 'campaign_templates', 'campaign_analytics', 'campaign_scheduling_rules'
)
ORDER BY category, table_name;

-- Test 2: Check sample data
SELECT 
    'Sample Data Check' as test,
    (SELECT COUNT(*) FROM users WHERE id = 'mozarex-user') as user_exists,
    (SELECT COUNT(*) FROM campaign_templates WHERE user_id = 'mozarex-user') as templates_count,
    (SELECT COUNT(*) FROM campaign_scheduling_rules WHERE user_id = 'mozarex-user') as rules_count;

-- Test 3: Test campaign template data
SELECT 
    'Template Test' as test,
    name,
    template_data->'twitter'->>'content' as twitter_sample,
    template_data->'facebook'->>'content' as facebook_sample,
    template_data->'instagram'->>'content' as instagram_sample,
    template_data->'tiktok'->>'content' as tiktok_sample
FROM campaign_templates 
WHERE user_id = 'mozarex-user' AND is_default = true;

-- Test 4: Test scheduling rules
SELECT 
    'Scheduling Rules Test' as test,
    platform,
    CASE day_of_week 
        WHEN 1 THEN 'Monday'
        WHEN 3 THEN 'Wednesday' 
        WHEN 5 THEN 'Friday'
        ELSE 'Other'
    END as day_name,
    time_slot
FROM campaign_scheduling_rules 
WHERE user_id = 'mozarex-user'
ORDER BY platform, day_of_week;

-- Test 5: Test API compatibility (simulate what the server.js will query)
SELECT 
    'API Compatibility Test' as test,
    ct.id as template_id,
    ct.name,
    ct.template_data,
    ct.is_default
FROM campaign_templates ct
WHERE ct.user_id = 'mozarex-user'
ORDER BY ct.is_default DESC, ct.created_at DESC;

-- Final success message
SELECT '🚀 Campaign Management System Test Complete!' as status;














