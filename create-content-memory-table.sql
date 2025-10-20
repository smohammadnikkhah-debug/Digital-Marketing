-- Content Memory Table
-- Tracks all generated content to prevent duplication
CREATE TABLE IF NOT EXISTS content_memory (
    id SERIAL PRIMARY KEY,
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
    content_type VARCHAR(50) NOT NULL, -- 'blog', 'twitter', 'instagram', 'tiktok'
    keyword VARCHAR(255), -- Primary keyword used
    topic VARCHAR(500) NOT NULL, -- Main topic/title
    content_hash VARCHAR(64) NOT NULL, -- Hash of content to detect duplicates
    full_content TEXT, -- Full generated content
    metadata JSONB, -- Additional metadata (hashtags, image suggestions, etc.)
    target_date DATE, -- Scheduled publish date
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'scheduled', 'published'
    generated_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_content_memory_website_id ON content_memory(website_id);
CREATE INDEX IF NOT EXISTS idx_content_memory_keyword ON content_memory(keyword);
CREATE INDEX IF NOT EXISTS idx_content_memory_content_type ON content_memory(content_type);
CREATE INDEX IF NOT EXISTS idx_content_memory_target_date ON content_memory(target_date);
CREATE INDEX IF NOT EXISTS idx_content_memory_content_hash ON content_memory(content_hash);

-- Unique constraint to prevent exact duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_memory_unique 
ON content_memory(website_id, content_hash);

-- Add comment
COMMENT ON TABLE content_memory IS 'Stores generated content and prevents duplication across all platforms';
COMMENT ON COLUMN content_memory.content_hash IS 'SHA-256 hash of content for duplicate detection';
COMMENT ON COLUMN content_memory.metadata IS 'Stores hashtags, image URLs, video suggestions, etc.';

