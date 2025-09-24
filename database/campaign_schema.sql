-- Campaign Management Database Schema
-- This schema supports social media campaign management with automated posting
-- NOTE: This extends the existing supabase-schema.sql

-- Social Media Accounts Table
CREATE TABLE IF NOT EXISTS social_accounts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL, -- 'twitter', 'facebook', 'instagram', 'tiktok'
    account_name VARCHAR(255) NOT NULL,
    account_id VARCHAR(255) NOT NULL, -- Platform-specific account ID
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, platform, account_id)
);

-- Campaigns Table
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    domain VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'scheduled', 'active', 'paused', 'completed'
    start_date DATE NOT NULL,
    end_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Campaign Posts Table
CREATE TABLE IF NOT EXISTS campaign_posts (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    social_account_id UUID REFERENCES social_accounts(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    media_urls TEXT[], -- Array of media URLs
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'scheduled', 'published', 'failed'
    published_at TIMESTAMP WITH TIME ZONE,
    engagement_stats JSONB, -- Likes, shares, comments, etc.
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Campaign Templates Table
CREATE TABLE IF NOT EXISTS campaign_templates (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    template_data JSONB NOT NULL, -- Platform-specific template structure
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Campaign Analytics Table
CREATE TABLE IF NOT EXISTS campaign_analytics (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
    post_id UUID REFERENCES campaign_posts(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL, -- 'likes', 'shares', 'comments', 'clicks', 'impressions'
    metric_value INTEGER NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Campaign Scheduling Rules Table
CREATE TABLE IF NOT EXISTS campaign_scheduling_rules (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    day_of_week INTEGER NOT NULL, -- 0 = Sunday, 1 = Monday, etc.
    time_slot TIME NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_social_accounts_user_platform ON social_accounts(user_id, platform);
CREATE INDEX IF NOT EXISTS idx_campaigns_user_domain ON campaigns(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_campaigns_website_id ON campaigns(website_id);
CREATE INDEX IF NOT EXISTS idx_campaign_posts_scheduled_time ON campaign_posts(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_campaign_posts_status ON campaign_posts(status);
CREATE INDEX IF NOT EXISTS idx_campaign_analytics_campaign_post ON campaign_analytics(campaign_id, post_id);

-- Update triggers for updated_at timestamps
CREATE TRIGGER update_social_accounts_updated_at BEFORE UPDATE ON social_accounts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_campaigns_updated_at BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_campaign_posts_updated_at BEFORE UPDATE ON campaign_posts FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_campaign_templates_updated_at BEFORE UPDATE ON campaign_templates FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_campaign_scheduling_rules_updated_at BEFORE UPDATE ON campaign_scheduling_rules FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS on campaign tables
ALTER TABLE social_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_scheduling_rules ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role full access" ON social_accounts FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaigns FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaign_posts FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaign_templates FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaign_analytics FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaign_scheduling_rules FOR ALL USING (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users read access" ON social_accounts FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaigns FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaign_posts FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaign_templates FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaign_analytics FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaign_scheduling_rules FOR SELECT USING (auth.role() = 'authenticated');

-- Create a sample user for testing (optional)
INSERT INTO users (id, domain, business_description) VALUES
('mozarex-user', 'mozarex.com', 'Mozarex Digital Marketing - Professional SEO and digital marketing services')
ON CONFLICT (id) DO NOTHING;

-- Enhanced content management tables
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_content_calendar_user_domain ON content_calendar_entries(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_content_calendar_date ON content_calendar_entries(target_date);
CREATE INDEX IF NOT EXISTS idx_content_calendar_status ON content_calendar_entries(status);
CREATE INDEX IF NOT EXISTS idx_company_services_user_domain ON company_services(user_id, domain);
CREATE INDEX IF NOT EXISTS idx_content_generation_logs_user_domain ON content_generation_logs(user_id, domain);

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_content_calendar_entries_updated_at BEFORE UPDATE ON content_calendar_entries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_company_services_updated_at BEFORE UPDATE ON company_services FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS Policies
ALTER TABLE content_calendar_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_generation_logs ENABLE ROW LEVEL SECURITY;

-- Service role policies
CREATE POLICY "Service role can manage content_calendar_entries" ON content_calendar_entries FOR ALL USING (true);
CREATE POLICY "Service role can manage company_services" ON company_services FOR ALL USING (true);
CREATE POLICY "Service role can manage content_generation_logs" ON content_generation_logs FOR ALL USING (true);

-- Sample data for testing (optional)
INSERT INTO campaign_templates (user_id, name, description, template_data, is_default) VALUES
('mozarex-user', 'SEO Tips Template', 'Template for SEO-related social media posts', 
'{"twitter": {"content": "SEO Tip: {tip}", "hashtags": ["#SEO", "#DigitalMarketing"], "time": "10:00 AM"}, "facebook": {"content": "Learn about SEO: {tip}", "time": "2:00 PM"}, "instagram": {"content": "📈 SEO Tip: {tip}", "time": "7:00 PM"}, "tiktok": {"content": "Quick SEO tip: {tip}", "time": "6:00 PM"}}', true)
ON CONFLICT DO NOTHING;

-- Sample company services for Mozarex
INSERT INTO company_services (user_id, domain, service_name, service_description, target_keywords, content_themes) VALUES
('mozarex-user', 'mozarex.com', 'SEO Optimization', 'Professional SEO services to improve website rankings and organic traffic', 
 ARRAY['SEO', 'search engine optimization', 'organic traffic', 'keyword research'], 
 ARRAY['SEO tips', 'ranking improvements', 'organic growth', 'search visibility']),
('mozarex-user', 'mozarex.com', 'Digital Marketing', 'Comprehensive digital marketing strategies for business growth', 
 ARRAY['digital marketing', 'online advertising', 'social media marketing', 'PPC'], 
 ARRAY['marketing strategies', 'advertising tips', 'social media', 'campaign optimization']),
('mozarex-user', 'mozarex.com', 'Website Development', 'Custom website development and optimization services', 
 ARRAY['website development', 'web design', 'responsive design', 'user experience'], 
 ARRAY['web development', 'design trends', 'user experience', 'website optimization']),
('mozarex-user', 'mozarex.com', 'Content Marketing', 'Strategic content creation and marketing to engage audiences', 
 ARRAY['content marketing', 'content strategy', 'blog writing', 'content creation'], 
 ARRAY['content strategy', 'writing tips', 'content planning', 'audience engagement'])
ON CONFLICT DO NOTHING;

-- Sample scheduling rules
INSERT INTO campaign_scheduling_rules (user_id, platform, day_of_week, time_slot) VALUES
('mozarex-user', 'twitter', 1, '10:00:00'), -- Monday 10 AM
('mozarex-user', 'twitter', 3, '10:00:00'), -- Wednesday 10 AM
('mozarex-user', 'twitter', 5, '10:00:00'), -- Friday 10 AM
('mozarex-user', 'facebook', 1, '14:00:00'), -- Monday 2 PM
('mozarex-user', 'facebook', 3, '14:00:00'), -- Wednesday 2 PM
('mozarex-user', 'facebook', 5, '14:00:00'), -- Friday 2 PM
('mozarex-user', 'instagram', 1, '19:00:00'), -- Monday 7 PM
('mozarex-user', 'instagram', 3, '19:00:00'), -- Wednesday 7 PM
('mozarex-user', 'instagram', 5, '19:00:00'), -- Friday 7 PM
('mozarex-user', 'tiktok', 1, '18:00:00'), -- Monday 6 PM
('mozarex-user', 'tiktok', 3, '18:00:00'), -- Wednesday 6 PM
('mozarex-user', 'tiktok', 5, '18:00:00') -- Friday 6 PM
ON CONFLICT DO NOTHING;

-- Grant necessary permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;

-- Success message
SELECT 'Campaign management schema created successfully!' as message;
