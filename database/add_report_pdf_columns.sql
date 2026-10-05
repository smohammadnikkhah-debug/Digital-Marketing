-- ==============================================================================
-- Migration: Add report_pdf columns to public.website_audits (Phase 1 PDF Upload)
-- ==============================================================================

ALTER TABLE public.website_audits
  ADD COLUMN IF NOT EXISTS report_pdf_path TEXT,
  ADD COLUMN IF NOT EXISTS report_pdf_sha256 CHAR(64),
  ADD COLUMN IF NOT EXISTS report_pdf_bytes INTEGER,
  ADD COLUMN IF NOT EXISTS report_pdf_filename TEXT,
  ADD COLUMN IF NOT EXISTS report_pdf_source TEXT NOT NULL DEFAULT 'generated' CHECK (report_pdf_source IN ('generated', 'uploaded')),
  ADD COLUMN IF NOT EXISTS report_pdf_uploaded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_website_audits_report_pdf_sha256 
  ON public.website_audits (report_pdf_sha256);
