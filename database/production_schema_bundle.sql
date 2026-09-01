-- ==============================================================================
-- AIVEKAI PARTNER PROGRAM & PAYOUTS PRODUCTION SCHEMA BUNDLE
-- Target Project: nrunrjfmqczeowakjnjh
-- Dependency Order: 
--   1. partner_referrals_schema.sql
--   2. financial_ledger_hardening_schema.sql
--   3. subscription_events_commission_schema.sql
--   4. partner_portal_schema.sql
--   5. paypal_payouts_schema.sql
--   6. admin_schema.sql
-- ==============================================================================

-- Enable Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================================================================
-- 1. PARTNER REFERRALS & ATTRIBUTIONS (partner_referrals_schema.sql)
-- ==============================================================================

-- 1.1. Create Referral Offers Table
CREATE TABLE IF NOT EXISTS public.referral_offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    discount_percent DECIMAL(5, 2) NOT NULL CHECK (discount_percent > 0 AND discount_percent <= 100),
    billing_period TEXT NOT NULL DEFAULT 'yearly' CHECK (billing_period IN ('yearly', 'monthly')),
    discount_duration_periods INTEGER NOT NULL DEFAULT 1 CHECK (discount_duration_periods >= 1),
    apple_offer_identifier TEXT,
    google_offer_identifier TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ,
    new_subscribers_only BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 1.2. Create Partners Table
CREATE TABLE IF NOT EXISTS public.partners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT,
    company_name TEXT,
    referral_code TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'paused', 'terminated')),
    commission_rate DECIMAL(5, 2) NOT NULL DEFAULT 30.00 CHECK (commission_rate >= 0 AND commission_rate <= 100),
    customer_discount_percent DECIMAL(5, 2) CHECK (customer_discount_percent > 0 AND customer_discount_percent <= 100),
    referral_offer_id UUID REFERENCES public.referral_offers(id) ON DELETE SET NULL,
    apple_offer_identifier TEXT,
    google_offer_identifier TEXT,
    kochava_partner_key TEXT UNIQUE,
    accept_new_referrals BOOLEAN NOT NULL DEFAULT TRUE,
    earn_commission_existing_customers BOOLEAN NOT NULL DEFAULT TRUE,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS partners_referral_code_upper_idx ON public.partners (UPPER(referral_code));

-- 1.3. Create Partner Attributions Table (1 permanent attribution per customer)
CREATE TABLE IF NOT EXISTS public.partner_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE,
    partner_id UUID REFERENCES public.partners(id) ON DELETE RESTRICT NOT NULL,
    referral_offer_id UUID REFERENCES public.referral_offers(id) ON DELETE SET NULL,
    source TEXT NOT NULL CHECK (source IN ('kochava_deferred_link', 'kochava_deep_link', 'manual_referral_code', 'admin')),
    referral_code TEXT,
    kochava_metadata JSONB,
    attributed_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    locked_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_partner_attributions_customer ON public.partner_attributions(customer_id);
CREATE INDEX IF NOT EXISTS idx_partner_attributions_partner ON public.partner_attributions(partner_id);

-- 1.4. Referral Validation and Application Function
CREATE OR REPLACE FUNCTION public.validate_and_apply_referral(
    p_customer_id UUID,
    p_referral_code TEXT,
    p_source TEXT DEFAULT 'manual_referral_code',
    p_kochava_metadata JSONB DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_norm_code TEXT;
    v_partner RECORD;
    v_offer RECORD;
    v_existing_attr RECORD;
    v_profile RECORD;
    v_attribution_id UUID;
    v_effective_apple_offer TEXT;
    v_effective_google_offer TEXT;
    v_effective_discount DECIMAL(5,2);
BEGIN
    v_norm_code := UPPER(TRIM(p_referral_code));
    
    IF v_norm_code IS NULL OR v_norm_code = '' THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'invalid_code', 'message', 'That referral code doesn''t appear to be valid.');
    END IF;

    -- Check if customer already has a locked attribution
    SELECT pa.*, p.referral_code AS partner_code, ro.name AS offer_name, ro.discount_percent
    INTO v_existing_attr
    FROM public.partner_attributions pa
    JOIN public.partners p ON p.id = pa.partner_id
    LEFT JOIN public.referral_offers ro ON ro.id = pa.referral_offer_id
    WHERE pa.customer_id = p_customer_id;

    IF FOUND THEN
        IF UPPER(v_existing_attr.partner_code) = v_norm_code THEN
            RETURN jsonb_build_object(
                'valid', true,
                'partner_attribution_created', false,
                'already_attributed', true,
                'message', 'Referral code already active.',
                'referral_offer', jsonb_build_object(
                    'id', v_existing_attr.referral_offer_id,
                    'name', COALESCE(v_existing_attr.offer_name, 'Annual Partner Discount'),
                    'discount_percent', COALESCE(v_existing_attr.discount_percent, 20.00),
                    'billing_period', 'yearly',
                    'discount_duration_periods', 1,
                    'apple_offer_identifier', 'referral_annual_20',
                    'google_offer_identifier', 'referral-annual-20'
                )
            );
        ELSE
            RETURN jsonb_build_object('valid', false, 'reason', 'already_attributed', 'message', 'A referral has already been applied.');
        END IF;
    END IF;

    -- Find partner by normalized referral code
    SELECT * INTO v_partner FROM public.partners WHERE UPPER(referral_code) = v_norm_code;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'invalid_code', 'message', 'That referral code doesn''t appear to be valid.');
    END IF;

    IF v_partner.status <> 'active' OR v_partner.approved_at IS NULL OR v_partner.accept_new_referrals = FALSE THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'partner_unavailable', 'message', 'This referral code is currently unavailable.');
    END IF;

    -- Find associated referral offer
    IF v_partner.referral_offer_id IS NOT NULL THEN
        SELECT * INTO v_offer FROM public.referral_offers WHERE id = v_partner.referral_offer_id;
    ELSE
        SELECT * INTO v_offer FROM public.referral_offers WHERE active = TRUE AND billing_period = 'yearly' ORDER BY created_at ASC LIMIT 1;
    END IF;

    IF v_offer IS NULL OR v_offer.active = FALSE THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'offer_unavailable', 'message', 'This referral code is currently unavailable.');
    END IF;

    IF (v_offer.starts_at IS NOT NULL AND now() < v_offer.starts_at) OR 
       (v_offer.ends_at IS NOT NULL AND now() > v_offer.ends_at) THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'offer_expired', 'message', 'This referral offer has expired.');
    END IF;

    -- Check if new subscribers only
    IF v_offer.new_subscribers_only THEN
        SELECT * INTO v_profile FROM public.profiles WHERE id = p_customer_id;
        IF FOUND AND v_profile.subscription_status = 'premium' THEN
            RETURN jsonb_build_object('valid', false, 'reason', 'new_subscribers_only', 'message', 'This referral offer is only available for new subscribers.');
        END IF;
    END IF;

    v_effective_discount := COALESCE(v_partner.customer_discount_percent, v_offer.discount_percent, 20.00);
    v_effective_apple_offer := COALESCE(v_partner.apple_offer_identifier, v_offer.apple_offer_identifier, 'referral_annual_20');
    v_effective_google_offer := COALESCE(v_partner.google_offer_identifier, v_offer.google_offer_identifier, 'referral-annual-20');

    INSERT INTO public.partner_attributions (
        customer_id,
        partner_id,
        referral_offer_id,
        source,
        referral_code,
        kochava_metadata,
        attributed_at,
        locked_at
    ) VALUES (
        p_customer_id,
        v_partner.id,
        v_offer.id,
        p_source,
        v_norm_code,
        p_kochava_metadata,
        now(),
        now()
    ) RETURNING id INTO v_attribution_id;

    RETURN jsonb_build_object(
        'valid', true,
        'partner_attribution_created', true,
        'attribution_id', v_attribution_id,
        'partner_id', v_partner.id,
        'partner_name', v_partner.name,
        'referral_offer', jsonb_build_object(
            'id', v_offer.id,
            'name', v_offer.name,
            'discount_percent', v_effective_discount,
            'billing_period', v_offer.billing_period,
            'discount_duration_periods', v_offer.discount_duration_periods,
            'apple_offer_identifier', v_effective_apple_offer,
            'google_offer_identifier', v_effective_google_offer
        )
    );
END;
$$;

-- ==============================================================================
-- 2. FINANCIAL LEDGER HARDENING (financial_ledger_hardening_schema.sql)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.partner_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID REFERENCES public.partners(id) ON DELETE RESTRICT NOT NULL,
    customer_id UUID NOT NULL,
    referral_attribution_id UUID REFERENCES public.partner_attributions(id) ON DELETE SET NULL,
    subscription_event_id UUID,
    transaction_id TEXT NOT NULL,
    store TEXT NOT NULL CHECK (store IN ('apple', 'google', 'stripe', 'other')),
    currency TEXT NOT NULL DEFAULT 'AUD',
    gross_amount_minor INT NOT NULL,
    tax_vat_amount_minor INT NOT NULL DEFAULT 0,
    store_fee_amount_minor INT NOT NULL DEFAULT 0,
    eligible_revenue_minor INT NOT NULL,
    commission_rate_basis_points INT NOT NULL CHECK (commission_rate_basis_points >= 0 AND commission_rate_basis_points <= 10000),
    commission_amount_minor INT NOT NULL,
    revenue_status TEXT NOT NULL DEFAULT 'estimated' CHECK (revenue_status IN ('estimated', 'finalized')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'available', 'paid', 'reversed')),
    payout_id UUID,
    is_initial_period BOOLEAN NOT NULL DEFAULT TRUE,
    subscription_period_number INT NOT NULL DEFAULT 1,
    reversal_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    finalized_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    reversed_at TIMESTAMPTZ,
    CONSTRAINT uq_partner_commissions_tx_store UNIQUE (transaction_id, store)
);

CREATE INDEX IF NOT EXISTS idx_partner_commissions_partner ON public.partner_commissions(partner_id);
CREATE INDEX IF NOT EXISTS idx_partner_commissions_customer ON public.partner_commissions(customer_id);
CREATE INDEX IF NOT EXISTS idx_partner_commissions_status ON public.partner_commissions(status);
CREATE INDEX IF NOT EXISTS idx_partner_commissions_currency ON public.partner_commissions(currency);

-- Append-Only Ledger Immutability Rule Trigger
CREATE OR REPLACE FUNCTION public.check_commission_ledger_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- Prevent changing financial values on existing ledger rows
        IF OLD.commission_amount_minor != NEW.commission_amount_minor OR
           OLD.eligible_revenue_minor != NEW.eligible_revenue_minor OR
           OLD.partner_id != NEW.partner_id OR
           OLD.transaction_id != NEW.transaction_id THEN
            RAISE EXCEPTION 'Immutable financial ledger violation: financial amounts cannot be updated. Use reversals or adjustments.';
        END IF;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Immutable financial ledger violation: ledger rows cannot be deleted.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_commission_ledger_immutable ON public.partner_commissions;
CREATE TRIGGER trg_commission_ledger_immutable
BEFORE UPDATE OR DELETE ON public.partner_commissions
FOR EACH ROW EXECUTE FUNCTION public.check_commission_ledger_immutable();

-- ==============================================================================
-- 3. SUBSCRIPTION EVENTS & ATTRIBUTIONS (subscription_events_commission_schema.sql)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.subscription_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    store TEXT NOT NULL CHECK (store IN ('apple', 'google', 'stripe', 'other')),
    event_type TEXT NOT NULL,
    store_transaction_id TEXT NOT NULL,
    original_transaction_id TEXT,
    product_id TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AUD',
    gross_amount_minor INT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    processed_at TIMESTAMPTZ,
    is_processed BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    CONSTRAINT uq_subscription_events_tx_type UNIQUE (store_transaction_id, event_type, store)
);

CREATE INDEX IF NOT EXISTS idx_sub_events_customer ON public.subscription_events(customer_id);
CREATE INDEX IF NOT EXISTS idx_sub_events_processed ON public.subscription_events(is_processed);

-- ==============================================================================
-- 4. PARTNER & ADMIN PORTAL SCHEMA (partner_portal_schema.sql)
-- ==============================================================================

-- 4.1. Partner User Auth Mapping
CREATE TABLE IF NOT EXISTS public.partner_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'partner' CHECK (role IN ('partner', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_partner_users_auth ON public.partner_users(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_partner_users_partner ON public.partner_users(partner_id);

-- 4.2. Partner Applications Table
CREATE TABLE IF NOT EXISTS public.partner_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    business_name TEXT,
    email TEXT NOT NULL,
    country TEXT NOT NULL,
    website TEXT,
    instagram TEXT,
    tiktok TEXT,
    youtube TEXT,
    other_social TEXT,
    audience_size TEXT NOT NULL,
    audience_niche TEXT NOT NULL,
    promotion_plan TEXT NOT NULL,
    preferred_referral_code TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID
);

CREATE INDEX IF NOT EXISTS idx_partner_applications_status ON public.partner_applications(status);
CREATE INDEX IF NOT EXISTS idx_partner_applications_email ON public.partner_applications(email);

-- 4.3. Partner Payout Accounts
CREATE TABLE IF NOT EXISTS public.partner_payout_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'bank_transfer',
    provider_account_reference TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AUD',
    country TEXT NOT NULL DEFAULT 'AU',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending_verification', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payout_accounts_partner ON public.partner_payout_accounts(partner_id);

-- 4.4. Payout Settings
CREATE TABLE IF NOT EXISTS public.payout_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    currency TEXT NOT NULL UNIQUE,
    minimum_payout_minor INT NOT NULL DEFAULT 10000, -- 100.00
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.payout_settings (currency, minimum_payout_minor)
VALUES ('AUD', 10000), ('USD', 10000)
ON CONFLICT (currency) DO NOTHING;

-- 4.5. Partner Payouts Table
CREATE TABLE IF NOT EXISTS public.partner_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL DEFAULT 'AUD',
    amount_minor INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'submitting', 'submitted', 'paid', 'failed', 'cancelled', 'reversed')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL DEFAULT 'paypal',
    provider_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_partner_payouts_partner ON public.partner_payouts(partner_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_status ON public.partner_payouts(status);

-- 4.6. Partner Payout Items
CREATE TABLE IF NOT EXISTS public.partner_payout_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payout_id UUID NOT NULL REFERENCES public.partner_payouts(id) ON DELETE CASCADE,
    commission_id UUID NOT NULL REFERENCES public.partner_commissions(id) ON DELETE RESTRICT,
    amount_minor INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payout_commission UNIQUE(commission_id)
);

CREATE INDEX IF NOT EXISTS idx_payout_items_payout ON public.partner_payout_items(payout_id);

-- 4.7. Admin Audit Logs
CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_action ON public.admin_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_target ON public.admin_audit_logs(target_type, target_id);

-- ==============================================================================
-- 5. PAYPAL PAYOUTS EXECUTION & AUDIT (paypal_payouts_schema.sql)
-- ==============================================================================

-- 5.1. Add PayPal Execution Columns to partner_payouts
ALTER TABLE public.partner_payouts
ADD COLUMN IF NOT EXISTS payout_destination_snapshot JSONB,
ADD COLUMN IF NOT EXISTS provider_batch_id TEXT,
ADD COLUMN IF NOT EXISTS provider_item_id TEXT,
ADD COLUMN IF NOT EXISTS provider_status TEXT,
ADD COLUMN IF NOT EXISTS provider_request_id TEXT,
ADD COLUMN IF NOT EXISTS sender_batch_id TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS provider_confirmed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS provider_failure_code TEXT,
ADD COLUMN IF NOT EXISTS provider_failure_message TEXT,
ADD COLUMN IF NOT EXISTS provider_fee_minor INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS provider_fee_currency TEXT,
ADD COLUMN IF NOT EXISTS reversal_reason TEXT,
ADD COLUMN IF NOT EXISTS reversed_at TIMESTAMPTZ;

-- 5.2. PayPal Webhooks Table
CREATE TABLE IF NOT EXISTS public.paypal_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paypal_event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processed', 'ignored', 'failed')),
    provider_batch_id TEXT,
    provider_item_id TEXT,
    payload_hash TEXT,
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_event_id ON public.paypal_webhook_events(paypal_event_id);
CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_batch_id ON public.paypal_webhook_events(provider_batch_id);

-- ==============================================================================
-- 6. ADMIN AUTH & USER MANAGEMENT (admin_schema.sql)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.aivekai_admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS aivekai_admin_users_username_lower_idx 
ON public.aivekai_admin_users (lower(trim(username)));

CREATE INDEX IF NOT EXISTS aivekai_admin_users_auth_user_idx 
ON public.aivekai_admin_users (auth_user_id);

-- ==============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

ALTER TABLE public.referral_offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partners ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_attributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_commissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_payout_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payout_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_payout_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paypal_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aivekai_admin_users ENABLE ROW LEVEL SECURITY;

-- Service Role Full Access Policies
DROP POLICY IF EXISTS "Service role full access on partner_applications" ON public.partner_applications;
CREATE POLICY "Service role full access on partner_applications" ON public.partner_applications FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on partners" ON public.partners;
CREATE POLICY "Service role full access on partners" ON public.partners FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on partner_users" ON public.partner_users;
CREATE POLICY "Service role full access on partner_users" ON public.partner_users FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on partner_commissions" ON public.partner_commissions;
CREATE POLICY "Service role full access on partner_commissions" ON public.partner_commissions FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on partner_payouts" ON public.partner_payouts;
CREATE POLICY "Service role full access on partner_payouts" ON public.partner_payouts FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on partner_payout_items" ON public.partner_payout_items;
CREATE POLICY "Service role full access on partner_payout_items" ON public.partner_payout_items FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on aivekai_admin_users" ON public.aivekai_admin_users;
CREATE POLICY "Service role full access on aivekai_admin_users" ON public.aivekai_admin_users FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on admin_audit_logs" ON public.admin_audit_logs;
CREATE POLICY "Service role full access on admin_audit_logs" ON public.admin_audit_logs FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

DROP POLICY IF EXISTS "Service role full access on paypal_webhook_events" ON public.paypal_webhook_events;
CREATE POLICY "Service role full access on paypal_webhook_events" ON public.paypal_webhook_events FOR ALL USING (auth.jwt() ->> 'role' = 'service_role') WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- ==============================================================================
-- 7. SECURE RPCS FOR PAYOUTS & DASHBOARD
-- ==============================================================================

-- 7.1. Atomic Payout Acquisition
CREATE OR REPLACE FUNCTION public.acquire_payout_for_submission(
    p_payout_id UUID,
    p_sender_batch_id TEXT,
    p_provider_request_id TEXT,
    p_destination_snapshot JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_payout RECORD;
BEGIN
    UPDATE public.partner_payouts
    SET 
        status = 'submitting',
        sender_batch_id = COALESCE(sender_batch_id, p_sender_batch_id),
        provider_request_id = COALESCE(provider_request_id, p_provider_request_id),
        payout_destination_snapshot = COALESCE(payout_destination_snapshot, p_destination_snapshot)
    WHERE id = p_payout_id AND status = 'approved'
    RETURNING * INTO v_payout;
    
    IF NOT FOUND THEN
        SELECT status INTO v_payout FROM public.partner_payouts WHERE id = p_payout_id;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
        END IF;
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_in_approved_state', 'current_status', v_payout.status);
    END IF;
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'submitting',
        'sender_batch_id', v_payout.sender_batch_id
    );
END;
$$;

-- 7.2. Mark Payout Submitted
CREATE OR REPLACE FUNCTION public.mark_payout_submitted(
    p_payout_id UUID,
    p_provider_batch_id TEXT,
    p_provider_status TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE public.partner_payouts
    SET 
        status = 'submitted',
        provider = 'paypal',
        provider_batch_id = p_provider_batch_id,
        provider_status = p_provider_status,
        submitted_at = NOW()
    WHERE id = p_payout_id AND status = 'submitting';
    
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_in_submitting_state');
    END IF;
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'submitted');
END;
$$;

-- 7.3. Confirm Payout Success
CREATE OR REPLACE FUNCTION public.confirm_partner_payout_success(
    p_payout_id UUID,
    p_provider_batch_id TEXT,
    p_provider_item_id TEXT,
    p_fee_minor INT DEFAULT 0,
    p_fee_currency TEXT DEFAULT 'AUD'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_payout RECORD;
BEGIN
    SELECT * INTO v_payout FROM public.partner_payouts WHERE id = p_payout_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
    END IF;
    
    IF v_payout.status = 'paid' THEN
        RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'paid', 'idempotent', true);
    END IF;
    
    IF v_payout.status != 'submitted' AND v_payout.status != 'submitting' THEN
        RETURN jsonb_build_object('success', false, 'error', 'invalid_state_for_success', 'current_status', v_payout.status);
    END IF;
    
    UPDATE public.partner_payouts
    SET 
        status = 'paid',
        paid_at = NOW(),
        provider_confirmed_at = NOW(),
        provider_status = 'SUCCESS',
        provider_batch_id = COALESCE(p_provider_batch_id, provider_batch_id),
        provider_item_id = COALESCE(p_provider_item_id, provider_item_id),
        provider_fee_minor = p_fee_minor,
        provider_fee_currency = p_fee_currency
    WHERE id = p_payout_id;
    
    UPDATE public.partner_commissions
    SET 
        status = 'paid',
        paid_at = NOW(),
        payout_id = p_payout_id
    WHERE id IN (
        SELECT commission_id FROM public.partner_payout_items WHERE payout_id = p_payout_id
    );
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'paid');
END;
$$;

-- 7.4. Record Payout Failure
CREATE OR REPLACE FUNCTION public.record_partner_payout_failure(
    p_payout_id UUID,
    p_failure_code TEXT,
    p_failure_message TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_payout RECORD;
BEGIN
    SELECT * INTO v_payout FROM public.partner_payouts WHERE id = p_payout_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
    END IF;
    
    IF v_payout.status = 'paid' THEN
        RETURN jsonb_build_object('success', false, 'error', 'cannot_fail_already_paid_payout_use_reversal');
    END IF;
    
    UPDATE public.partner_payouts
    SET 
        status = 'failed',
        failed_at = NOW(),
        provider_status = 'FAILED',
        provider_failure_code = p_failure_code,
        provider_failure_message = p_failure_message
    WHERE id = p_payout_id;
    
    DELETE FROM public.partner_payout_items WHERE payout_id = p_payout_id;
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'failed', 'commissions_released', true);
END;
$$;
