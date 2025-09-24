-- Run these SQL statements in your Supabase Dashboard SQL Editor
-- Go to: https://supabase.com/dashboard -> Your Project -> SQL Editor

-- 1. Create company_services table
CREATE TABLE IF NOT EXISTS company_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    service_name TEXT NOT NULL,
    service_description TEXT,
    target_keywords TEXT[],
    content_themes TEXT[],
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Create content_calendar_entries table
CREATE TABLE IF NOT EXISTS content_calendar_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    target_date DATE NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('twitter', 'facebook', 'instagram', 'tiktok')),
    content TEXT NOT NULL,
    engagement_tip TEXT,
    scheduled_time TIME,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'published', 'rejected')),
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, domain, target_date, platform)
);

-- 3. Create content_generation_logs table
CREATE TABLE IF NOT EXISTS content_generation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    generation_date DATE NOT NULL,
    days_generated INTEGER NOT NULL,
    services_used TEXT[],
    ai_model TEXT,
    tokens_used INTEGER,
    generation_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_content_calendar_user_domain ON content_calendar_entries(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_content_calendar_date ON content_calendar_entries(target_date);
CREATE INDEX IF NOT EXISTS idx_content_calendar_status ON content_calendar_entries(status);
CREATE INDEX IF NOT EXISTS idx_company_services_user_domain ON company_services(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_content_generation_logs_user_domain ON content_generation_logs(user_id, domain);

-- 5. Create triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_content_calendar_entries_updated_at BEFORE UPDATE ON content_calendar_entries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_company_services_updated_at BEFORE UPDATE ON company_services FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 6. Enable RLS (Row Level Security)
ALTER TABLE content_calendar_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_generation_logs ENABLE ROW LEVEL SECURITY;

-- 7. Create RLS policies (allow service role to manage all data)
CREATE POLICY "Service role can manage content_calendar_entries" ON content_calendar_entries FOR ALL USING (true);
CREATE POLICY "Service role can manage company_services" ON company_services FOR ALL USING (true);
CREATE POLICY "Service role can manage content_generation_logs" ON content_generation_logs FOR ALL USING (true);

-- 8. Insert sample company services for Mozarex (only if they don't exist)
INSERT INTO company_services (user_id, domain, service_name, service_description, target_keywords, content_themes) 
SELECT 'mozarex-user', 'mozarex.com', 'SEO Optimization', 'Professional SEO services to improve website rankings and organic traffic', 
 ARRAY['SEO', 'search engine optimization', 'organic traffic', 'keyword research'], 
 ARRAY['SEO tips', 'ranking improvements', 'organic growth', 'search visibility']
WHERE NOT EXISTS (SELECT 1 FROM company_services WHERE user_id = 'mozarex-user' AND domain = 'mozarex.com' AND service_name = 'SEO Optimization');

INSERT INTO company_services (user_id, domain, service_name, service_description, target_keywords, content_themes) 
SELECT 'mozarex-user', 'mozarex.com', 'Digital Marketing', 'Comprehensive digital marketing strategies for business growth', 
 ARRAY['digital marketing', 'online advertising', 'social media marketing', 'PPC'], 
 ARRAY['marketing strategies', 'advertising tips', 'social media', 'campaign optimization']
WHERE NOT EXISTS (SELECT 1 FROM company_services WHERE user_id = 'mozarex-user' AND domain = 'mozarex.com' AND service_name = 'Digital Marketing');

INSERT INTO company_services (user_id, domain, service_name, service_description, target_keywords, content_themes) 
SELECT 'mozarex-user', 'mozarex.com', 'Website Development', 'Custom website development and optimization services', 
 ARRAY['website development', 'web design', 'responsive design', 'user experience'], 
 ARRAY['web development', 'design trends', 'user experience', 'website optimization']
WHERE NOT EXISTS (SELECT 1 FROM company_services WHERE user_id = 'mozarex-user' AND domain = 'mozarex.com' AND service_name = 'Website Development');

INSERT INTO company_services (user_id, domain, service_name, service_description, target_keywords, content_themes) 
SELECT 'mozarex-user', 'mozarex.com', 'Content Marketing', 'Strategic content creation and marketing to engage audiences', 
 ARRAY['content marketing', 'content strategy', 'blog writing', 'content creation'], 
 ARRAY['content strategy', 'writing tips', 'content planning', 'audience engagement']
WHERE NOT EXISTS (SELECT 1 FROM company_services WHERE user_id = 'mozarex-user' AND domain = 'mozarex.com' AND service_name = 'Content Marketing');

-- 9. Verify tables were created
SELECT 'company_services' as table_name, count(*) as row_count FROM company_services
UNION ALL
SELECT 'content_calendar_entries' as table_name, count(*) as row_count FROM content_calendar_entries
UNION ALL
SELECT 'content_generation_logs' as table_name, count(*) as row_count FROM content_generation_logs;
