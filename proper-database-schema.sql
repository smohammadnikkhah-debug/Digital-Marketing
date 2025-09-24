-- Proper Database Schema for Mozarex SEO Dashboard
-- 1 Customer → Multiple Websites → Each Website has its own data

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables if they exist (in correct order due to foreign keys)
DROP TABLE IF EXISTS content_calendar CASCADE;
DROP TABLE IF EXISTS campaigns CASCADE;
DROP TABLE IF EXISTS company_services CASCADE;
DROP TABLE IF EXISTS social_contents CASCADE;
DROP TABLE IF EXISTS seo_analyses CASCADE;
DROP TABLE IF EXISTS keywords CASCADE;
DROP TABLE IF EXISTS websites CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- 1. CUSTOMERS TABLE - Main customer/company information
CREATE TABLE customers (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255) UNIQUE NOT NULL,
    contact_phone VARCHAR(50),
    business_description TEXT,
    industry VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. WEBSITES TABLE - Each customer can have multiple websites
CREATE TABLE websites (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    domain VARCHAR(255) UNIQUE NOT NULL,
    website_name VARCHAR(255),
    website_description TEXT,
    status VARCHAR(50) DEFAULT 'active', -- active, inactive, maintenance
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. KEYWORDS TABLE - Keywords for each website
CREATE TABLE keywords (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    keyword VARCHAR(255) NOT NULL,
    search_volume INTEGER DEFAULT 0,
    difficulty INTEGER DEFAULT 0,
    current_rank INTEGER,
    target_rank INTEGER,
    optimization_notes TEXT,
    status VARCHAR(50) DEFAULT 'tracking', -- tracking, targeting, achieved
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. SEO ANALYSES TABLE - SEO analysis data for each website
CREATE TABLE seo_analyses (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    analysis_data JSONB NOT NULL,
    analysis_type VARCHAR(50) DEFAULT 'comprehensive',
    score INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'completed', -- completed, in_progress, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '14 days')
);

-- 5. COMPANY SERVICES TABLE - Services offered by each website/company
CREATE TABLE company_services (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    service_name VARCHAR(255) NOT NULL,
    service_description TEXT,
    service_category VARCHAR(100),
    pricing_info TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. SOCIAL CONTENTS TABLE - Social media content for each website
CREATE TABLE social_contents (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL, -- twitter, instagram, facebook, linkedin, tiktok
    content_type VARCHAR(50) NOT NULL, -- post, story, reel, video
    content_text TEXT NOT NULL,
    hashtags TEXT[],
    media_urls TEXT[],
    engagement_metrics JSONB,
    status VARCHAR(50) DEFAULT 'draft', -- draft, scheduled, published
    scheduled_for TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. CAMPAIGNS TABLE - Marketing campaigns for each website
CREATE TABLE campaigns (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    campaign_name VARCHAR(255) NOT NULL,
    campaign_description TEXT,
    campaign_type VARCHAR(100), -- seo, social_media, content_marketing, ppc
    target_audience TEXT,
    budget DECIMAL(10,2),
    start_date DATE,
    end_date DATE,
    status VARCHAR(50) DEFAULT 'planning', -- planning, active, paused, completed
    performance_metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. CONTENT CALENDAR TABLE - Content calendar for each website
CREATE TABLE content_calendar (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    website_id UUID NOT NULL REFERENCES websites(id) ON DELETE CASCADE,
    target_date DATE NOT NULL,
    platform VARCHAR(50) NOT NULL, -- twitter, instagram, facebook, linkedin, tiktok
    title VARCHAR(255),
    content TEXT NOT NULL,
    description TEXT,
    hashtags TEXT[],
    seo_keywords TEXT[],
    call_to_action TEXT,
    engagement_tip TEXT,
    media_urls TEXT[],
    status VARCHAR(50) DEFAULT 'draft', -- draft, scheduled, published
    scheduled_for TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_customers_email ON customers(contact_email);
CREATE INDEX idx_websites_customer_id ON websites(customer_id);
CREATE INDEX idx_websites_domain ON websites(domain);
CREATE INDEX idx_keywords_website_id ON keywords(website_id);
CREATE INDEX idx_keywords_keyword ON keywords(keyword);
CREATE INDEX idx_seo_analyses_website_id ON seo_analyses(website_id);
CREATE INDEX idx_seo_analyses_expires_at ON seo_analyses(expires_at);
CREATE INDEX idx_company_services_website_id ON company_services(website_id);
CREATE INDEX idx_social_contents_website_id ON social_contents(website_id);
CREATE INDEX idx_social_contents_platform ON social_contents(platform);
CREATE INDEX idx_campaigns_website_id ON campaigns(website_id);
CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_content_calendar_website_id ON content_calendar(website_id);
CREATE INDEX idx_content_calendar_target_date ON content_calendar(target_date);
CREATE INDEX idx_content_calendar_platform ON content_calendar(platform);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_websites_updated_at BEFORE UPDATE ON websites FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_keywords_updated_at BEFORE UPDATE ON keywords FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_company_services_updated_at BEFORE UPDATE ON company_services FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_social_contents_updated_at BEFORE UPDATE ON social_contents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_campaigns_updated_at BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_content_calendar_updated_at BEFORE UPDATE ON content_calendar FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security (RLS)
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE websites ENABLE ROW LEVEL SECURITY;
ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_contents ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_calendar ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role full access" ON customers FOR ALL USING (true);
CREATE POLICY "Service role full access" ON websites FOR ALL USING (true);
CREATE POLICY "Service role full access" ON keywords FOR ALL USING (true);
CREATE POLICY "Service role full access" ON seo_analyses FOR ALL USING (true);
CREATE POLICY "Service role full access" ON company_services FOR ALL USING (true);
CREATE POLICY "Service role full access" ON social_contents FOR ALL USING (true);
CREATE POLICY "Service role full access" ON campaigns FOR ALL USING (true);
CREATE POLICY "Service role full access" ON content_calendar FOR ALL USING (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users read access" ON customers FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON websites FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON keywords FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON seo_analyses FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON company_services FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON social_contents FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON campaigns FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON content_calendar FOR SELECT USING (auth.role() = 'authenticated');

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;

-- Create helper functions
-- Drop existing function first if it exists
DROP FUNCTION IF EXISTS get_website_stats(TEXT);

CREATE OR REPLACE FUNCTION get_website_stats(website_domain TEXT)
RETURNS TABLE (
    total_keywords BIGINT,
    total_seo_analyses BIGINT,
    total_services BIGINT,
    total_social_contents BIGINT,
    total_campaigns BIGINT,
    total_calendar_entries BIGINT,
    last_analysis_date TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT k.id) as total_keywords,
        COUNT(DISTINCT sa.id) as total_seo_analyses,
        COUNT(DISTINCT cs.id) as total_services,
        COUNT(DISTINCT sc.id) as total_social_contents,
        COUNT(DISTINCT c.id) as total_campaigns,
        COUNT(DISTINCT cc.id) as total_calendar_entries,
        MAX(sa.created_at) as last_analysis_date
    FROM websites w
    LEFT JOIN keywords k ON w.id = k.website_id
    LEFT JOIN seo_analyses sa ON w.id = sa.website_id
    LEFT JOIN company_services cs ON w.id = cs.website_id
    LEFT JOIN social_contents sc ON w.id = sc.website_id
    LEFT JOIN campaigns c ON w.id = c.website_id
    LEFT JOIN content_calendar cc ON w.id = cc.website_id
    WHERE w.domain = website_domain;
END;
$$ LANGUAGE plpgsql;

-- Create a function to get customer with all websites
-- Drop existing function first if it exists
DROP FUNCTION IF EXISTS get_customer_with_websites(TEXT);

CREATE OR REPLACE FUNCTION get_customer_with_websites(customer_email TEXT)
RETURNS TABLE (
    customer_id UUID,
    company_name VARCHAR(255),
    contact_email VARCHAR(255),
    website_id UUID,
    domain VARCHAR(255),
    website_name VARCHAR(255)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id as customer_id,
        c.company_name,
        c.contact_email,
        w.id as website_id,
        w.domain,
        w.website_name
    FROM customers c
    LEFT JOIN websites w ON c.id = w.customer_id
    WHERE c.contact_email = customer_email;
END;
$$ LANGUAGE plpgsql;

-- Insert sample data for testing
INSERT INTO customers (company_name, contact_email, business_description, industry) VALUES 
('Mozarex Digital Marketing', 'contact@mozarex.com', 'Digital marketing agency specializing in SEO and social media', 'Marketing'),
('Example Corp', 'info@example.com', 'Example company for testing', 'Technology')
ON CONFLICT (contact_email) DO NOTHING;

-- Insert sample websites
INSERT INTO websites (customer_id, domain, website_name, website_description) 
SELECT 
    c.id,
    'mozarex.com',
    'Mozarex Main Site',
    'Main website for Mozarex Digital Marketing'
FROM customers c WHERE c.contact_email = 'contact@mozarex.com'
ON CONFLICT (domain) DO NOTHING;

INSERT INTO websites (customer_id, domain, website_name, website_description) 
SELECT 
    c.id,
    'example.com',
    'Example Corp Site',
    'Main website for Example Corp'
FROM customers c WHERE c.contact_email = 'info@example.com'
ON CONFLICT (domain) DO NOTHING;

-- Success message
SELECT 'Proper database schema created successfully! 1 Customer → Multiple Websites → Each Website has its own data.' as message;
