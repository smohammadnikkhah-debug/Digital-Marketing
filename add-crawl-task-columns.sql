-- Add columns to websites table for tracking OnPage crawl tasks
-- These columns allow us to track the status of full website crawl tasks

ALTER TABLE public.websites
ADD COLUMN IF NOT EXISTS analysis_task_id TEXT,
ADD COLUMN IF NOT EXISTS analysis_status TEXT DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS analysis_started_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS analysis_completed_at TIMESTAMPTZ;

-- Add index for faster lookups by task status
CREATE INDEX IF NOT EXISTS idx_websites_analysis_status ON public.websites(analysis_status);

-- Add index for task ID lookups
CREATE INDEX IF NOT EXISTS idx_websites_analysis_task_id ON public.websites(analysis_task_id);

-- Update existing rows to have 'pending' status if NULL
UPDATE public.websites
SET analysis_status = 'pending'
WHERE analysis_status IS NULL;

-- Add comment explaining the columns
COMMENT ON COLUMN public.websites.analysis_task_id IS 'DataForSEO OnPage task ID for full website crawl';
COMMENT ON COLUMN public.websites.analysis_status IS 'Status of the crawl task: pending, in_progress, completed, failed, timed_out';
COMMENT ON COLUMN public.websites.analysis_started_at IS 'Timestamp when the crawl task was created';
COMMENT ON COLUMN public.websites.analysis_completed_at IS 'Timestamp when the crawl task completed';

