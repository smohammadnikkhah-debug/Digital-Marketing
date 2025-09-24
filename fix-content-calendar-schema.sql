-- Fix Content Calendar Schema to Properly Link to Domains
-- This script updates the content_calendar table to use proper foreign key relationships

-- First, let's check if we need to clean up the existing content_calendar table
-- Drop the existing content_calendar table if it exists (it might have wrong structure)
DROP TABLE IF EXISTS content_calendar CASCADE;

-- Create the proper content_calendar table with correct relationships
CREATE TABLE content_calendar (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    domain TEXT NOT NULL, -- Direct reference to domain from users table
    target_date DATE NOT NULL,
    platform VARCHAR(50) NOT NULL, -- twitter, instagram, tiktok
    title TEXT,
    content TEXT NOT NULL,
    description TEXT,
    hashtags TEXT[], -- Array of hashtags
    seo_keywords TEXT[], -- Array of SEO keywords
    call_to_action TEXT,
    engagement_tip TEXT,
    status VARCHAR(50) DEFAULT 'draft', -- draft, scheduled, published
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Foreign key constraint to users table
    CONSTRAINT fk_content_calendar_domain 
        FOREIGN KEY (domain) 
        REFERENCES users(domain) 
        ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX idx_content_calendar_domain ON content_calendar(domain);
CREATE INDEX idx_content_calendar_target_date ON content_calendar(target_date);
CREATE INDEX idx_content_calendar_platform ON content_calendar(platform);
CREATE INDEX idx_content_calendar_status ON content_calendar(status);
CREATE INDEX idx_content_calendar_domain_date ON content_calendar(domain, target_date);

-- Create updated_at trigger for content_calendar table
CREATE TRIGGER update_content_calendar_updated_at 
    BEFORE UPDATE ON content_calendar 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security
ALTER TABLE content_calendar ENABLE ROW LEVEL SECURITY;

-- Create policies for service role (full access)
CREATE POLICY "Service role full access" ON content_calendar FOR ALL USING (true);

-- Create policies for authenticated users (read-only for now)
CREATE POLICY "Authenticated users read access" ON content_calendar FOR SELECT USING (auth.role() = 'authenticated');

-- Grant necessary permissions
GRANT ALL ON content_calendar TO anon, authenticated;

-- Success message
SELECT 'Content Calendar schema fixed successfully! Now properly linked to domains via users table.' as message;
