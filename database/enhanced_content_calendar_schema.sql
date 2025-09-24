-- Enhanced Content Calendar Schema for Mozarex SEO Dashboard
-- This extends the existing content_calendar table with additional fields

-- First, let's add new columns to the existing content_calendar table
ALTER TABLE content_calendar 
ADD COLUMN IF NOT EXISTS content_text TEXT,
ADD COLUMN IF NOT EXISTS media_url TEXT,
ADD COLUMN IF NOT EXISTS media_type VARCHAR(20) DEFAULT 'text', -- text, image, video
ADD COLUMN IF NOT EXISTS scheduled_time TIME,
ADD COLUMN IF NOT EXISTS engagement_tip TEXT,
ADD COLUMN IF NOT EXISTS hashtags TEXT[],
ADD COLUMN IF NOT EXISTS platform_specific_data JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS is_editable BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS last_modified TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS modified_by TEXT DEFAULT 'user';

-- Create a new table for media uploads
CREATE TABLE IF NOT EXISTS content_media (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  content_id UUID REFERENCES content_calendar(id) ON DELETE CASCADE,
  file_name VARCHAR(255) NOT NULL,
  file_url TEXT NOT NULL,
  file_type VARCHAR(50) NOT NULL, -- image, video, audio
  file_size BIGINT,
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  uploaded_by TEXT DEFAULT 'user'
);

-- Create a new table for content scheduling
CREATE TABLE IF NOT EXISTS content_schedules (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  content_id UUID REFERENCES content_calendar(id) ON DELETE CASCADE,
  scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
  platform VARCHAR(50) NOT NULL,
  status VARCHAR(50) DEFAULT 'scheduled', -- scheduled, published, failed
  published_at TIMESTAMP WITH TIME ZONE,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_content_calendar_target_date_status ON content_calendar(target_date, status);
CREATE INDEX IF NOT EXISTS idx_content_calendar_platform ON content_calendar(content_type);
CREATE INDEX IF NOT EXISTS idx_content_media_content_id ON content_media(content_id);
CREATE INDEX IF NOT EXISTS idx_content_schedules_scheduled_for ON content_schedules(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_content_schedules_status ON content_schedules(status);

-- Create a function to get content for a specific date
CREATE OR REPLACE FUNCTION get_content_for_date(website_domain TEXT, target_date DATE)
RETURNS TABLE (
    id UUID,
    content_type VARCHAR(50),
    content_text TEXT,
    media_url TEXT,
    media_type VARCHAR(20),
    scheduled_time TIME,
    status VARCHAR(50),
    engagement_tip TEXT,
    hashtags TEXT[],
    platform_specific_data JSONB,
    is_editable BOOLEAN,
    last_modified TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        cc.id,
        cc.content_type,
        cc.content_text,
        cc.media_url,
        cc.media_type,
        cc.scheduled_time,
        cc.status,
        cc.engagement_tip,
        cc.hashtags,
        cc.platform_specific_data,
        cc.is_editable,
        cc.last_modified
    FROM websites w
    JOIN content_calendar cc ON w.id = cc.website_id
    WHERE w.domain = website_domain 
    AND cc.target_date = target_date
    ORDER BY cc.scheduled_time ASC;
END;
$$ LANGUAGE plpgsql;

-- Create a function to update content
CREATE OR REPLACE FUNCTION update_content_item(
    content_id UUID,
    new_content_text TEXT DEFAULT NULL,
    new_media_url TEXT DEFAULT NULL,
    new_media_type VARCHAR(20) DEFAULT NULL,
    new_scheduled_time TIME DEFAULT NULL,
    new_status VARCHAR(50) DEFAULT NULL,
    new_engagement_tip TEXT DEFAULT NULL,
    new_hashtags TEXT[] DEFAULT NULL,
    new_platform_data JSONB DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE content_calendar 
    SET 
        content_text = COALESCE(new_content_text, content_text),
        media_url = COALESCE(new_media_url, media_url),
        media_type = COALESCE(new_media_type, media_type),
        scheduled_time = COALESCE(new_scheduled_time, scheduled_time),
        status = COALESCE(new_status, status),
        engagement_tip = COALESCE(new_engagement_tip, engagement_tip),
        hashtags = COALESCE(new_hashtags, hashtags),
        platform_specific_data = COALESCE(new_platform_data, platform_specific_data),
        last_modified = NOW(),
        modified_by = 'user'
    WHERE id = content_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Create a function to delete content
CREATE OR REPLACE FUNCTION delete_content_item(content_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM content_calendar WHERE id = content_id;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Enable RLS on new tables
ALTER TABLE content_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_schedules ENABLE ROW LEVEL SECURITY;

-- Create policies for new tables
CREATE POLICY "Service role full access" ON content_media FOR ALL USING (true);
CREATE POLICY "Service role full access" ON content_schedules FOR ALL USING (true);
CREATE POLICY "Authenticated users read access" ON content_media FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "Authenticated users read access" ON content_schedules FOR SELECT USING (auth.role() = 'authenticated');

-- Grant permissions
GRANT ALL ON content_media TO anon, authenticated;
GRANT ALL ON content_schedules TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_content_for_date TO anon, authenticated;
GRANT EXECUTE ON FUNCTION update_content_item TO anon, authenticated;
GRANT EXECUTE ON FUNCTION delete_content_item TO anon, authenticated;

-- Success message
SELECT 'Enhanced Content Calendar schema created successfully!' as message;
