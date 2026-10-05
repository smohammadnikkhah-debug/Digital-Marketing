-- ==============================================================================
-- MOZAREX WEBSITE REVIEWS INFRASTRUCTURE SCHEMA (Phase 1)
-- Table: public.website_audits
-- ==============================================================================

-- 1. Create table
CREATE TABLE IF NOT EXISTS public.website_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Prospect Business Information
    business_name TEXT NOT NULL,
    business_type TEXT,
    suburb TEXT,
    website_url TEXT NOT NULL,
    canonical_domain TEXT NOT NULL,
    contact_email TEXT,
    
    -- Structured Findings (JSONB)
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Commercial Scope & Proposal
    proposed_price NUMERIC,
    currency TEXT NOT NULL DEFAULT 'AUD',
    
    -- Security & Storage
    public_token TEXT UNIQUE NOT NULL,
    pdf_storage_path TEXT,
    report_pdf_path TEXT,
    report_pdf_sha256 CHAR(64),
    report_pdf_bytes INTEGER,
    report_pdf_filename TEXT,
    report_pdf_source TEXT NOT NULL DEFAULT 'generated' CHECK (report_pdf_source IN ('generated', 'uploaded')),
    report_pdf_uploaded_at TIMESTAMPTZ,
    
    -- Lifecycle Status
    status TEXT NOT NULL DEFAULT 'draft' 
        CHECK (status IN ('draft', 'generating', 'ready', 'approved', 'sent', 'archived', 'failed')),
    
    -- Analytics & Engagement Metrics
    view_count INTEGER NOT NULL DEFAULT 0,
    download_count INTEGER NOT NULL DEFAULT 0,
    first_viewed_at TIMESTAMPTZ,
    last_viewed_at TIMESTAMPTZ,
    first_downloaded_at TIMESTAMPTZ,
    last_downloaded_at TIMESTAMPTZ,
    
    -- Approval & Dispatch Workflow (Phase 2+)
    email_sent_at TIMESTAMPTZ,
    email_message_id TEXT,
    approved_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create Performance & Lookup Indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_website_audits_public_token 
    ON public.website_audits (public_token);

CREATE INDEX IF NOT EXISTS idx_website_audits_canonical_domain 
    ON public.website_audits (canonical_domain);

CREATE INDEX IF NOT EXISTS idx_website_audits_website_url 
    ON public.website_audits (website_url);

CREATE INDEX IF NOT EXISTS idx_website_audits_contact_email 
    ON public.website_audits (contact_email);

CREATE INDEX IF NOT EXISTS idx_website_audits_status 
    ON public.website_audits (status);

CREATE INDEX IF NOT EXISTS idx_website_audits_created_at 
    ON public.website_audits (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_website_audits_report_pdf_sha256
    ON public.website_audits (report_pdf_sha256);

-- 3. Automatic updated_at Trigger
CREATE OR REPLACE FUNCTION public.set_website_audits_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_website_audits_updated_at ON public.website_audits;
CREATE TRIGGER trg_website_audits_updated_at
    BEFORE UPDATE ON public.website_audits
    FOR EACH ROW
    EXECUTE FUNCTION public.set_website_audits_updated_at();

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.website_audits ENABLE ROW LEVEL SECURITY;

-- Block all direct public/anonymous operations by default
-- Allow service_role complete access for backend functions and Grokbot API worker
DROP POLICY IF EXISTS "Service role full access on website_audits" ON public.website_audits;
CREATE POLICY "Service role full access on website_audits"
    ON public.website_audits
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- 5. Private Supabase Storage Bucket Setup Documentation / SQL (if storage schema accessible)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'mozarex-website-reviews',
    'mozarex-website-reviews',
    false,
    20971520, -- 20MB limit
    ARRAY['application/pdf']::text[]
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 20971520,
    allowed_mime_types = ARRAY['application/pdf']::text[];
