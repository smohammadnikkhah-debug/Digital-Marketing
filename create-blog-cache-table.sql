-- Create blog content cache table
CREATE TABLE IF NOT EXISTS blog_content_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id VARCHAR(255), -- Auth0 user ID for user-specific content
    domain VARCHAR(255) NOT NULL,
    topic VARCHAR(500) NOT NULL,
    keywords TEXT[] NOT NULL,
    target_audience VARCHAR(255),
    tone VARCHAR(100),
    word_count INTEGER,
    include_images BOOLEAN DEFAULT false,
    seo_optimized BOOLEAN DEFAULT true,
    content_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 hash of generation parameters
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    content TEXT NOT NULL,
    seo_score INTEGER,
    seo_grade VARCHAR(50),
    seo_analysis TEXT,
    word_count_actual INTEGER,
    is_latest BOOLEAN DEFAULT true, -- Marks the latest content for this user/domain combination
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '30 days') -- Cache expires after 30 days
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_blog_cache_domain ON blog_content_cache(domain);
CREATE INDEX IF NOT EXISTS idx_blog_cache_content_hash ON blog_content_cache(content_hash);
CREATE INDEX IF NOT EXISTS idx_blog_cache_expires_at ON blog_content_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_blog_cache_created_at ON blog_content_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_blog_cache_user_id ON blog_content_cache(user_id);
CREATE INDEX IF NOT EXISTS idx_blog_cache_is_latest ON blog_content_cache(is_latest);
CREATE INDEX IF NOT EXISTS idx_blog_cache_user_domain_latest ON blog_content_cache(user_id, domain, is_latest);

-- Create function to clean up expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_blog_cache()
RETURNS void AS $$
BEGIN
    DELETE FROM blog_content_cache 
    WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- Enable Row Level Security
ALTER TABLE blog_content_cache ENABLE ROW LEVEL SECURITY;

-- Create RLS policy (allow all operations for now - adjust based on your auth needs)
CREATE POLICY "Allow all operations on blog_content_cache" ON blog_content_cache
    FOR ALL USING (true);

-- Add comments
COMMENT ON TABLE blog_content_cache IS 'Caches generated blog content to avoid repeated OpenAI API calls';
COMMENT ON COLUMN blog_content_cache.content_hash IS 'SHA-256 hash of generation parameters for cache key';
COMMENT ON COLUMN blog_content_cache.expires_at IS 'When this cache entry expires and should be regenerated';
