-- Content Calendar Schema for Supabase
-- This table stores AI-generated social media content for each domain

CREATE TABLE IF NOT EXISTS content_calendar (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    target_date DATE NOT NULL,
    platform VARCHAR(50) NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    description TEXT,
    hashtags TEXT[],
    seo_keywords TEXT[],
    call_to_action TEXT,
    engagement_tip TEXT,
    scheduled_time TIME,
    status VARCHAR(50) DEFAULT 'planned',
    media_type VARCHAR(50) DEFAULT 'text',
    media_url TEXT,
    is_editable BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure unique content per domain per date per platform
    UNIQUE(domain, target_date, platform)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_content_calendar_domain ON content_calendar(domain);
CREATE INDEX IF NOT EXISTS idx_content_calendar_date ON content_calendar(target_date);
CREATE INDEX IF NOT EXISTS idx_content_calendar_domain_date ON content_calendar(domain, target_date);
CREATE INDEX IF NOT EXISTS idx_content_calendar_status ON content_calendar(status);

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

-- Add comments for documentation
COMMENT ON TABLE content_calendar IS 'Stores AI-generated social media content for content calendar';
COMMENT ON COLUMN content_calendar.domain IS 'Domain name for which content is generated';
COMMENT ON COLUMN content_calendar.target_date IS 'Date for which content is scheduled';
COMMENT ON COLUMN content_calendar.platform IS 'Social media platform (twitter, instagram, tiktok)';
COMMENT ON COLUMN content_calendar.content IS 'Main content text';
COMMENT ON COLUMN content_calendar.hashtags IS 'Array of hashtags for the content';
COMMENT ON COLUMN content_calendar.seo_keywords IS 'Array of SEO keywords used in content';
COMMENT ON COLUMN content_calendar.status IS 'Content status: planned, scheduled, published, cancelled';
COMMENT ON COLUMN content_calendar.is_editable IS 'Whether the content can be edited by user';