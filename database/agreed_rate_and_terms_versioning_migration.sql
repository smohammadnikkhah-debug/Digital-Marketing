-- ==============================================================================
-- TRANSACTIONAL MIGRATION: Agreed Commission Rate, Schedules & Terms Acceptance
-- ==============================================================================

BEGIN;

-- 1. Single Source of Truth for Program Settings
CREATE TABLE IF NOT EXISTS public.partner_program_settings (
    key TEXT PRIMARY KEY,
    value_numeric NUMERIC(5,2),
    value_text TEXT,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID
);

-- Seed current standard rate (30.00%) & current terms version
INSERT INTO public.partner_program_settings (key, value_numeric, description)
VALUES ('standard_partner_commission_rate', 30.00, 'Default commercial offer rate for new partner applications')
ON CONFLICT (key) DO NOTHING;

INSERT INTO public.partner_program_settings (key, value_text, description)
VALUES ('current_terms_version', 'v1.0-2026-09', 'Active Partner Program Terms version identifier')
ON CONFLICT (key) DO NOTHING;

-- 2. Partner Commission Rate History & Future Schedules
CREATE TABLE IF NOT EXISTS public.partner_commission_rate_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE CASCADE,
    previous_rate NUMERIC(5,2) NOT NULL,
    new_rate NUMERIC(5,2) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'applied', 'cancelled')),
    notification_status TEXT NOT NULL DEFAULT 'pending' CHECK (notification_status IN ('pending', 'sent', 'failed', 'not_required')),
    notification_sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_rate_history_partner_eff ON public.partner_commission_rate_history(partner_id, effective_at);
CREATE INDEX IF NOT EXISTS idx_rate_history_status ON public.partner_commission_rate_history(status);

-- 3. PostgreSQL Authoritative Rate Resolution Function (Supports Strict-Before)
CREATE OR REPLACE FUNCTION public.resolve_partner_agreed_commission_rate(
    p_partner_id UUID,
    p_transaction_timestamp TIMESTAMPTZ DEFAULT NOW(),
    p_strict_before BOOLEAN DEFAULT FALSE
) RETURNS NUMERIC(5,2) AS $$
DECLARE
    v_scheduled_rate NUMERIC(5,2);
    v_base_rate NUMERIC(5,2);
BEGIN
    IF p_strict_before THEN
        SELECT new_rate INTO v_scheduled_rate
        FROM public.partner_commission_rate_history
        WHERE partner_id = p_partner_id
          AND status != 'cancelled'
          AND effective_at < p_transaction_timestamp
        ORDER BY effective_at DESC, created_at DESC
        LIMIT 1;
    ELSE
        SELECT new_rate INTO v_scheduled_rate
        FROM public.partner_commission_rate_history
        WHERE partner_id = p_partner_id
          AND status != 'cancelled'
          AND effective_at <= p_transaction_timestamp
        ORDER BY effective_at DESC, created_at DESC
        LIMIT 1;
    END IF;
    
    IF v_scheduled_rate IS NOT NULL THEN
        RETURN v_scheduled_rate;
    END IF;
    
    SELECT commission_rate INTO v_base_rate
    FROM public.partners
    WHERE id = p_partner_id;
    
    RETURN v_base_rate;
END;
$$ LANGUAGE plpgsql STABLE;

-- 4. Terms Acceptance Metadata (Explicit & Nullable for Legacy Records)
ALTER TABLE public.partner_applications 
  ADD COLUMN IF NOT EXISTS terms_version TEXT,
  ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS terms_acceptance_action TEXT;

-- 5. Fail-Closed DDL Constraint: Remove hard-coded default on partners table
ALTER TABLE public.partners ALTER COLUMN commission_rate DROP DEFAULT;

-- 6. Enable RLS and Policies for Settings & Rate History
ALTER TABLE public.partner_program_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_commission_rate_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on partner_program_settings" ON public.partner_program_settings;
CREATE POLICY "Service role full access on partner_program_settings" ON public.partner_program_settings
  FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Public read on partner_program_settings" ON public.partner_program_settings;
CREATE POLICY "Public read on partner_program_settings" ON public.partner_program_settings
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Service role full access on partner_commission_rate_history" ON public.partner_commission_rate_history;
CREATE POLICY "Service role full access on partner_commission_rate_history" ON public.partner_commission_rate_history
  FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Partners can read own rate history" ON public.partner_commission_rate_history;
CREATE POLICY "Partners can read own rate history" ON public.partner_commission_rate_history
  FOR SELECT USING (
    partner_id IN (
      SELECT partner_id FROM public.partner_users WHERE auth_user_id = auth.uid()
    )
  );

COMMIT;
