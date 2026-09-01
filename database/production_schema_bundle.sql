-- ==============================================================================
-- AIVEKAI PARTNER PROGRAM & PAYOUTS PRODUCTION SCHEMA BUNDLE (HARDENED)
-- Target Project: nrunrjfmqczeowakjnjh
-- Preserves existing tables: profiles, weight_entries, spam_reports, usage_logs, chat_messages, openai_keys
-- Reconciled & Hardened:
--   1. Explicit SECURITY DEFINER privileges & least privilege matrix
--   2. Atomic row-level lock concurrency & partial unique index on active payouts
--   3. Strict semantic naming on subscription_attribution_links
--   4. Non-destructive financial audit history
-- ==============================================================================

-- Enable Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==============================================================================
-- 1. PARTNER REFERRALS & OFFERS (partner_referrals_schema.sql)
-- ==============================================================================

-- 1.1. Referral Offers Table
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

-- 1.2. Partners Table
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
    holding_period_days INT NOT NULL DEFAULT 30,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS partners_referral_code_upper_idx ON public.partners (UPPER(referral_code));

-- 1.3. Partner Attributions Table (Foreign Key to public.profiles(id))
CREATE TABLE IF NOT EXISTS public.partner_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE RESTRICT,
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

-- 1.4. Subscription Attribution Links Junction & Audit Table (Semantically Corrected)
CREATE TABLE IF NOT EXISTS public.subscription_attribution_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE RESTRICT,
    attribution_id UUID NOT NULL REFERENCES public.partner_attributions(id) ON DELETE CASCADE,
    attribution_source TEXT NOT NULL CHECK (attribution_source IN ('kochava_deferred_link', 'kochava_deep_link', 'manual_referral_code', 'admin')),
    first_store_platform TEXT CHECK (first_store_platform IN ('apple', 'google', 'stripe', 'web', 'other')),
    first_transaction_id TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT uq_sub_attribution_customer UNIQUE (customer_id)
);

CREATE INDEX IF NOT EXISTS idx_sub_attr_links_partner ON public.subscription_attribution_links(partner_id);

-- ==============================================================================
-- 2. SUBSCRIPTION EVENTS & AUDIT (subscription_events_commission_schema.sql)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.store_notification_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (provider IN ('apple', 'google', 'stripe')),
    notification_id TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    verification_status TEXT NOT NULL CHECK (verification_status IN ('verified', 'failed_signature', 'unauthenticated', 'unresolved_customer')),
    notification_type TEXT NOT NULL,
    notification_subtype TEXT,
    payload_hash TEXT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('processed', 'ignored', 'failed', 'pending', 'unresolved')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_provider_notification UNIQUE(provider, notification_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_audits_provider ON public.store_notification_audits(provider, notification_id);
CREATE INDEX IF NOT EXISTS idx_notification_audits_status ON public.store_notification_audits(verification_status, processing_status);

CREATE TABLE IF NOT EXISTS public.subscription_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id TEXT,
    correlation_status TEXT NOT NULL DEFAULT 'correlated' CHECK (correlation_status IN ('correlated', 'unresolved')),
    platform TEXT NOT NULL CHECK (platform IN ('apple', 'google', 'stripe', 'web')),
    store_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('initial_purchase', 'renewal', 'refund', 'revocation', 'cancellation', 'expiration')),
    product_id TEXT NOT NULL,
    google_purchase_token TEXT,
    google_order_id TEXT,
    google_linked_purchase_token TEXT,
    apple_transaction_id TEXT,
    apple_original_transaction_id TEXT,
    apple_web_order_line_item_id TEXT,
    offer_identifier TEXT,
    gross_amount_minor INT NOT NULL DEFAULT 0,
    estimated_net_revenue_minor INT NOT NULL DEFAULT 0,
    final_net_revenue_minor INT,
    revenue_status TEXT NOT NULL DEFAULT 'estimated' CHECK (revenue_status IN ('estimated', 'finalized', 'adjusted')),
    estimated_store_fee_rate NUMERIC(5,2) NOT NULL DEFAULT 15.00,
    estimated_tax_amount_minor INT NOT NULL DEFAULT 0,
    estimation_method TEXT NOT NULL DEFAULT 'standard_store_tier',
    currency TEXT NOT NULL DEFAULT 'USD',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_event_reference JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_platform_event_id UNIQUE(platform, store_event_id)
);

CREATE INDEX IF NOT EXISTS idx_sub_events_customer ON public.subscription_events(customer_id);
CREATE INDEX IF NOT EXISTS idx_sub_events_apple_orig_tx ON public.subscription_events(apple_original_transaction_id);
CREATE INDEX IF NOT EXISTS idx_sub_events_google_order ON public.subscription_events(google_order_id);
CREATE INDEX IF NOT EXISTS idx_sub_events_google_token ON public.subscription_events(google_purchase_token);
CREATE INDEX IF NOT EXISTS idx_sub_events_correlation ON public.subscription_events(correlation_status);
CREATE INDEX IF NOT EXISTS idx_sub_events_revenue_status ON public.subscription_events(revenue_status);

-- ==============================================================================
-- 3. FINANCIAL COMMISSIONS LEDGER & SNAPSHOTS (financial_ledger_hardening_schema.sql)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.partner_commissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE RESTRICT,
    customer_id TEXT NOT NULL,
    subscription_event_id UUID REFERENCES public.subscription_events(id) ON DELETE RESTRICT,
    referral_attribution_id UUID REFERENCES public.partner_attributions(id) ON DELETE SET NULL,
    transaction_id TEXT,
    store TEXT CHECK (store IN ('apple', 'google', 'stripe', 'web', 'other')),
    commission_rate NUMERIC(5,2) NOT NULL,
    eligible_revenue_minor INT NOT NULL,
    commission_amount_minor INT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AUD',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'available', 'paid', 'reversed')),
    revenue_status TEXT NOT NULL DEFAULT 'estimated' CHECK (revenue_status IN ('estimated', 'finalized', 'adjusted')),
    reconciliation_type TEXT NOT NULL DEFAULT 'provisional' CHECK (reconciliation_type IN ('provisional', 'reconciled', 'adjustment')),
    holding_period_days INT NOT NULL DEFAULT 30,
    earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    available_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    payout_id UUID,
    reversal_for_commission_id UUID REFERENCES public.partner_commissions(id),
    reversal_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_event_commission UNIQUE(subscription_event_id)
);

CREATE INDEX IF NOT EXISTS idx_commissions_partner ON public.partner_commissions(partner_id);
CREATE INDEX IF NOT EXISTS idx_commissions_customer ON public.partner_commissions(customer_id);
CREATE INDEX IF NOT EXISTS idx_commissions_status ON public.partner_commissions(status, revenue_status);
CREATE INDEX IF NOT EXISTS idx_commissions_available_at ON public.partner_commissions(available_at);
CREATE INDEX IF NOT EXISTS idx_commissions_currency ON public.partner_commissions(currency);

-- Partner Balance Snapshots Table (Daily/Monthly Ledger State Audit)
CREATE TABLE IF NOT EXISTS public.partner_balance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES public.partners(id) ON DELETE CASCADE,
    currency TEXT NOT NULL DEFAULT 'AUD',
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    available_balance_minor INT NOT NULL DEFAULT 0,
    pending_balance_minor INT NOT NULL DEFAULT 0,
    estimated_balance_minor INT NOT NULL DEFAULT 0,
    paid_balance_minor INT NOT NULL DEFAULT 0,
    reversed_balance_minor INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_partner_balance_snapshot UNIQUE (partner_id, currency, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_balance_snapshots_partner ON public.partner_balance_snapshots(partner_id, snapshot_date);

-- Append-Only Ledger Immutability Rule Trigger
CREATE OR REPLACE FUNCTION public.check_commission_ledger_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.commission_amount_minor != NEW.commission_amount_minor OR
           OLD.eligible_revenue_minor != NEW.eligible_revenue_minor OR
           OLD.partner_id != NEW.partner_id THEN
            RAISE EXCEPTION 'Immutable financial ledger violation: financial amounts cannot be updated in-place. Use adjustments or reversals.';
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
    provider TEXT NOT NULL DEFAULT 'paypal',
    provider_account_reference TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AUD',
    country TEXT NOT NULL DEFAULT 'AU',
    status TEXT NOT NULL DEFAULT 'configured' CHECK (status IN ('configured', 'pending_verification', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payout_accounts_partner ON public.partner_payout_accounts(partner_id);

-- 4.4. Payout Settings
CREATE TABLE IF NOT EXISTS public.payout_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    currency TEXT NOT NULL UNIQUE,
    minimum_payout_minor INT NOT NULL DEFAULT 10000,
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
    payout_destination_snapshot JSONB,
    provider_batch_id TEXT,
    provider_item_id TEXT,
    provider_status TEXT,
    provider_request_id TEXT,
    sender_batch_id TEXT UNIQUE,
    provider_confirmed_at TIMESTAMPTZ,
    provider_failure_code TEXT,
    provider_failure_message TEXT,
    provider_fee_minor INT DEFAULT 0,
    provider_fee_currency TEXT,
    reversal_reason TEXT,
    reversed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_partner_payouts_partner ON public.partner_payouts(partner_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_status ON public.partner_payouts(status);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_provider_batch ON public.partner_payouts(provider_batch_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_sender_batch ON public.partner_payouts(sender_batch_id);

-- 4.6. Partner Payout Items (With Non-Destructive Release Tracking & Active Unique Index)
CREATE TABLE IF NOT EXISTS public.partner_payout_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payout_id UUID NOT NULL REFERENCES public.partner_payouts(id) ON DELETE CASCADE,
    commission_id UUID NOT NULL REFERENCES public.partner_commissions(id) ON DELETE RESTRICT,
    amount_minor INT NOT NULL,
    is_released BOOLEAN NOT NULL DEFAULT FALSE,
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Concurrency Hardening: Partial Unique Index to guarantee 1 active payout item per commission
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_payout_commission
ON public.partner_payout_items (commission_id)
WHERE is_released = FALSE;

CREATE INDEX IF NOT EXISTS idx_payout_items_payout ON public.partner_payout_items(payout_id);
CREATE INDEX IF NOT EXISTS idx_payout_items_commission ON public.partner_payout_items(commission_id);

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

-- 4.8. PayPal Webhook Events Table
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

-- 4.9. Admin Users Table
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
ALTER TABLE public.subscription_attribution_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.store_notification_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_commissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.partner_balance_snapshots ENABLE ROW LEVEL SECURITY;
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

-- Public Select Policies
DROP POLICY IF EXISTS "Allow public read active referral offers" ON public.referral_offers;
CREATE POLICY "Allow public read active referral offers" ON public.referral_offers FOR SELECT USING (active = true);

-- ==============================================================================
-- 5. RPC IMPLEMENTATIONS & CONCURRENCY-HARDENED FUNCTIONS
-- ==============================================================================

-- 5.1. Validate and Apply Referral RPC (Customer-Facing)
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

    -- Check if new subscribers only against existing profiles table
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
    )
    ON CONFLICT (customer_id) DO NOTHING
    RETURNING id INTO v_attribution_id;

    IF v_attribution_id IS NULL THEN
        RETURN jsonb_build_object('valid', false, 'reason', 'already_attributed', 'message', 'A referral has already been applied.');
    END IF;

    -- Insert into subscription attribution links junction with strict attribution_source semantics
    INSERT INTO public.subscription_attribution_links (
        customer_id,
        partner_id,
        attribution_id,
        attribution_source
    ) VALUES (
        p_customer_id,
        v_partner.id,
        v_attribution_id,
        p_source
    ) ON CONFLICT (customer_id) DO NOTHING;

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

-- 5.2. Query Customer Referral Offer RPC (Customer-Facing)
CREATE OR REPLACE FUNCTION public.get_customer_referral_offer(
    p_customer_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_rec RECORD;
BEGIN
    SELECT 
        pa.id AS attribution_id,
        p.name AS partner_name,
        p.referral_code,
        ro.id AS offer_id,
        ro.name AS offer_name,
        COALESCE(p.customer_discount_percent, ro.discount_percent, 20.00) AS discount_percent,
        ro.billing_period,
        ro.discount_duration_periods,
        COALESCE(p.apple_offer_identifier, ro.apple_offer_identifier, 'referral_annual_20') AS apple_offer_identifier,
        COALESCE(p.google_offer_identifier, ro.google_offer_identifier, 'referral-annual-20') AS google_offer_identifier
    INTO v_rec
    FROM public.partner_attributions pa
    JOIN public.partners p ON p.id = pa.partner_id
    LEFT JOIN public.referral_offers ro ON ro.id = pa.referral_offer_id
    WHERE pa.customer_id = p_customer_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('has_referral', false);
    END IF;

    RETURN jsonb_build_object(
        'has_referral', true,
        'partner_name', v_rec.partner_name,
        'referral_code', v_rec.referral_code,
        'referral_offer', jsonb_build_object(
            'id', v_rec.offer_id,
            'name', COALESCE(v_rec.offer_name, 'Annual Partner Discount'),
            'discount_percent', v_rec.discount_percent,
            'billing_period', COALESCE(v_rec.billing_period, 'yearly'),
            'discount_duration_periods', COALESCE(v_rec.discount_duration_periods, 1),
            'apple_offer_identifier', v_rec.apple_offer_identifier,
            'google_offer_identifier', v_rec.google_offer_identifier
        )
    );
END;
$$;

-- 5.3. Process Verified Store Subscription Event & Record Commission Ledger (Server-Only)
CREATE OR REPLACE FUNCTION public.process_verified_store_event(p_event_data JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_customer_id TEXT;
    v_correlation_status TEXT := 'correlated';
    v_platform TEXT;
    v_event_type TEXT;
    v_store_event_id TEXT;
    v_product_id TEXT;
    
    v_google_token TEXT;
    v_google_order_id TEXT;
    v_google_linked_token TEXT;
    
    v_apple_tx_id TEXT;
    v_apple_orig_tx_id TEXT;
    v_apple_web_order_id TEXT;
    
    v_offer_id TEXT;
    v_gross_minor INT;
    v_fee_rate NUMERIC(5,2);
    v_tax_minor INT;
    v_est_net_minor INT;
    v_final_net_minor INT;
    v_rev_status TEXT := 'estimated';
    v_currency TEXT;
    v_occurred_at TIMESTAMPTZ;
    v_event_id UUID;
    v_existing_event_id UUID;
    
    v_partner_id UUID;
    v_comm_rate NUMERIC(5,2);
    v_partner_status TEXT;
    v_earn_existing BOOLEAN;
    v_holding_days INT;
    v_comm_minor INT;
    v_comm_id UUID;
    
    v_orig_comm RECORD;
    v_ratio NUMERIC;
    v_adj_comm_minor INT;
BEGIN
    v_platform := p_event_data->>'platform';
    v_event_type := p_event_data->>'event_type';
    v_store_event_id := COALESCE(p_event_data->>'store_event_id', p_event_data->>'store_transaction_id');
    v_product_id := COALESCE(p_event_data->>'product_id', '');
    v_customer_id := p_event_data->>'customer_id';
    
    v_google_token := p_event_data->>'google_purchase_token';
    v_google_order_id := p_event_data->>'google_order_id';
    v_google_linked_token := p_event_data->>'google_linked_purchase_token';
    
    v_apple_tx_id := COALESCE(p_event_data->>'apple_transaction_id', CASE WHEN v_platform = 'apple' THEN v_store_event_id ELSE NULL END);
    v_apple_orig_tx_id := COALESCE(p_event_data->>'apple_original_transaction_id', p_event_data->>'original_transaction_id');
    v_apple_web_order_id := p_event_data->>'apple_web_order_line_item_id';
    
    v_offer_id := p_event_data->>'offer_identifier';
    v_gross_minor := COALESCE((p_event_data->>'gross_amount_minor')::int, ROUND(COALESCE((p_event_data->>'gross_amount')::numeric, 0.0) * 100));
    v_fee_rate := COALESCE((p_event_data->>'estimated_store_fee_rate')::numeric, 15.00);
    v_tax_minor := COALESCE((p_event_data->>'estimated_tax_amount_minor')::int, 0);
    v_currency := COALESCE(p_event_data->>'currency', 'AUD');
    v_occurred_at := COALESCE((p_event_data->>'occurred_at')::timestamptz, NOW());
    
    IF v_platform IS NULL OR v_event_type IS NULL OR v_store_event_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'missing_mandatory_fields');
    END IF;
    
    IF v_customer_id IS NULL OR TRIM(v_customer_id) = '' THEN
        v_correlation_status := 'unresolved';
    END IF;
    
    v_est_net_minor := ROUND((v_gross_minor - v_tax_minor) * ((100.0 - v_fee_rate) / 100.0));
    
    IF p_event_data->>'final_net_revenue_minor' IS NOT NULL THEN
        v_final_net_minor := (p_event_data->>'final_net_revenue_minor')::int;
        v_rev_status := 'finalized';
    END IF;
    
    -- Idempotency check
    SELECT id INTO v_existing_event_id FROM public.subscription_events
    WHERE platform = v_platform AND store_event_id = v_store_event_id;
    
    IF v_existing_event_id IS NOT NULL THEN
        RETURN jsonb_build_object(
            'success', true,
            'idempotent', true,
            'subscription_event_id', v_existing_event_id,
            'message', 'Event already ingested.'
        );
    END IF;
    
    -- Insert subscription event
    INSERT INTO public.subscription_events (
        customer_id, correlation_status, platform, store_event_id,
        event_type, product_id,
        google_purchase_token, google_order_id, google_linked_purchase_token,
        apple_transaction_id, apple_original_transaction_id, apple_web_order_line_item_id,
        offer_identifier, gross_amount_minor, estimated_net_revenue_minor,
        final_net_revenue_minor, revenue_status, estimated_store_fee_rate,
        estimated_tax_amount_minor, currency, occurred_at, raw_event_reference
    ) VALUES (
        v_customer_id, v_correlation_status, v_platform, v_store_event_id,
        v_event_type, v_product_id,
        v_google_token, v_google_order_id, v_google_linked_token,
        v_apple_tx_id, v_apple_orig_tx_id, v_apple_web_order_id,
        v_offer_id, v_gross_minor, v_est_net_minor,
        v_final_net_minor, v_rev_status, v_fee_rate,
        v_tax_minor, v_currency, v_occurred_at, p_event_data
    ) RETURNING id INTO v_event_id;
    
    IF v_correlation_status = 'unresolved' THEN
        RETURN jsonb_build_object(
            'success', true,
            'subscription_event_id', v_event_id,
            'correlation_status', 'unresolved',
            'commission_created', false,
            'message', 'Store event recorded. Customer correlation pending.'
        );
    END IF;
    
    IF v_event_type IN ('cancellation', 'expiration') THEN
        RETURN jsonb_build_object(
            'success', true,
            'subscription_event_id', v_event_id,
            'commission_created', false,
            'event_type', v_event_type,
            'message', 'Non-financial event recorded. Prior commissions preserved.'
        );
    END IF;
    
    -- Refund / Revocation Events
    IF v_event_type IN ('refund', 'revocation') THEN
        SELECT c.*, e.gross_amount_minor AS orig_gross_minor INTO v_orig_comm
        FROM public.partner_commissions c
        JOIN public.subscription_events e ON e.id = c.subscription_event_id
        WHERE (
            (v_apple_orig_tx_id IS NOT NULL AND e.apple_original_transaction_id = v_apple_orig_tx_id) OR
            (v_apple_tx_id IS NOT NULL AND e.apple_transaction_id = v_apple_tx_id) OR
            (v_google_order_id IS NOT NULL AND e.google_order_id = v_google_order_id) OR
            (v_google_token IS NOT NULL AND e.google_purchase_token = v_google_token) OR
            (c.customer_id = v_customer_id)
        )
        AND c.status != 'reversed'
        AND c.commission_amount_minor > 0
        ORDER BY c.created_at DESC
        LIMIT 1;
        
        IF v_orig_comm.id IS NOT NULL THEN
            IF v_gross_minor < 0 AND ABS(v_gross_minor) < v_orig_comm.orig_gross_minor THEN
                v_ratio := ABS(v_gross_minor)::numeric / v_orig_comm.orig_gross_minor::numeric;
                v_adj_comm_minor := ROUND(v_orig_comm.commission_amount_minor * v_ratio);
                
                INSERT INTO public.partner_commissions (
                    partner_id, customer_id, subscription_event_id,
                    commission_rate, eligible_revenue_minor, commission_amount_minor,
                    currency, status, revenue_status, reconciliation_type,
                    holding_period_days, earned_at, available_at, reversal_for_commission_id
                ) VALUES (
                    v_orig_comm.partner_id, v_customer_id, v_event_id,
                    v_orig_comm.commission_rate, -ROUND(v_orig_comm.eligible_revenue_minor * v_ratio), -v_adj_comm_minor,
                    v_orig_comm.currency, 'available', 'finalized', 'adjustment',
                    0, v_occurred_at, v_occurred_at, v_orig_comm.id
                ) RETURNING id INTO v_comm_id;
                
                RETURN jsonb_build_object(
                    'success', true,
                    'subscription_event_id', v_event_id,
                    'partial_refund_adjusted', true,
                    'adjustment_commission_id', v_comm_id,
                    'offset_amount_minor', -v_adj_comm_minor
                );
            ELSIF v_orig_comm.status = 'pending' THEN
                UPDATE public.partner_commissions
                SET status = 'reversed', revenue_status = 'finalized'
                WHERE id = v_orig_comm.id;
                
                RETURN jsonb_build_object(
                    'success', true,
                    'subscription_event_id', v_event_id,
                    'commission_reversed', true,
                    'reversed_commission_id', v_orig_comm.id,
                    'status', 'reversed'
                );
            ELSE
                INSERT INTO public.partner_commissions (
                    partner_id, customer_id, subscription_event_id,
                    commission_rate, eligible_revenue_minor, commission_amount_minor,
                    currency, status, revenue_status, reconciliation_type,
                    holding_period_days, earned_at, available_at, reversal_for_commission_id
                ) VALUES (
                    v_orig_comm.partner_id, v_customer_id, v_event_id,
                    v_orig_comm.commission_rate, -v_orig_comm.eligible_revenue_minor, -v_orig_comm.commission_amount_minor,
                    v_orig_comm.currency, 'available', 'finalized', 'adjustment',
                    0, v_occurred_at, v_occurred_at, v_orig_comm.id
                ) RETURNING id INTO v_comm_id;
                
                RETURN jsonb_build_object(
                    'success', true,
                    'subscription_event_id', v_event_id,
                    'negative_adjustment_created', true,
                    'adjustment_commission_id', v_comm_id,
                    'offset_amount_minor', -v_orig_comm.commission_amount_minor
                );
            END IF;
        ELSE
            RETURN jsonb_build_object(
                'success', true,
                'subscription_event_id', v_event_id,
                'commission_reversed', false,
                'message', 'No prior matching commission found to reverse.'
            );
        END IF;
    END IF;
    
    -- Commissionable Initial Purchase / Renewal
    IF v_event_type IN ('initial_purchase', 'renewal') THEN
        SELECT a.partner_id INTO v_partner_id
        FROM public.partner_attributions a
        WHERE a.customer_id::text = v_customer_id;
        
        IF v_partner_id IS NULL THEN
            RETURN jsonb_build_object(
                'success', true,
                'subscription_event_id', v_event_id,
                'commission_created', false,
                'reason', 'no_partner_attribution'
            );
        END IF;
        
        SELECT p.commission_rate, p.status, p.earn_commission_existing_customers, COALESCE(p.holding_period_days, 30)
        INTO v_comm_rate, v_partner_status, v_earn_existing, v_holding_days
        FROM public.partners p
        WHERE p.id = v_partner_id;
        
        IF v_partner_status != 'active' OR v_earn_existing = false THEN
            RETURN jsonb_build_object(
                'success', true,
                'subscription_event_id', v_event_id,
                'commission_created', false,
                'partner_id', v_partner_id,
                'reason', 'partner_earning_disabled'
            );
        END IF;
        
        v_comm_minor := ROUND(v_est_net_minor * (v_comm_rate / 100.0));
        
        INSERT INTO public.partner_commissions (
            partner_id, customer_id, subscription_event_id,
            commission_rate, eligible_revenue_minor, commission_amount_minor,
            currency, status, revenue_status, reconciliation_type,
            holding_period_days, earned_at, available_at
        ) VALUES (
            v_partner_id, v_customer_id, v_event_id,
            v_comm_rate, v_est_net_minor, v_comm_minor,
            v_currency, 'pending', v_rev_status, 'provisional',
            v_holding_days, v_occurred_at, v_occurred_at + (v_holding_days || ' days')::interval
        ) RETURNING id INTO v_comm_id;
        
        RETURN jsonb_build_object(
            'success', true,
            'subscription_event_id', v_event_id,
            'commission_created', true,
            'commission_id', v_comm_id,
            'partner_id', v_partner_id,
            'commission_rate', v_comm_rate,
            'eligible_revenue_minor', v_est_net_minor,
            'commission_amount_minor', v_comm_minor,
            'revenue_status', v_rev_status,
            'available_at', v_occurred_at + (v_holding_days || ' days')::interval
        );
    END IF;
    
    RETURN jsonb_build_object('success', true, 'subscription_event_id', v_event_id);
END;
$$;

-- 5.4. Alias Function for process_subscription_event (Server-Only)
CREATE OR REPLACE FUNCTION public.process_subscription_event(p_event_data JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RETURN public.process_verified_store_event(p_event_data);
END;
$$;

-- 5.5. Finalize Subscription Revenue RPC (Server-Only)
CREATE OR REPLACE FUNCTION public.finalize_subscription_revenue(
    p_subscription_event_id UUID,
    p_final_net_revenue_minor INT,
    p_reconciliation_data JSONB DEFAULT '{}'::jsonb
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_comm RECORD;
    v_new_comm_minor INT;
    v_adj_minor INT;
    v_adj_id UUID;
BEGIN
    UPDATE public.subscription_events
    SET final_net_revenue_minor = p_final_net_revenue_minor,
        revenue_status = 'finalized'
    WHERE id = p_subscription_event_id;
    
    SELECT * INTO v_comm FROM public.partner_commissions
    WHERE subscription_event_id = p_subscription_event_id;
    
    IF v_comm.id IS NOT NULL THEN
        v_new_comm_minor := ROUND(p_final_net_revenue_minor * (v_comm.commission_rate / 100.0));
        
        IF v_comm.status = 'pending' THEN
            UPDATE public.partner_commissions
            SET eligible_revenue_minor = p_final_net_revenue_minor,
                commission_amount_minor = v_new_comm_minor,
                revenue_status = 'finalized',
                reconciliation_type = 'reconciled'
            WHERE id = v_comm.id;
            
            RETURN jsonb_build_object(
                'success', true,
                'commission_id', v_comm.id,
                'status', 'pending',
                'updated_commission_amount_minor', v_new_comm_minor
            );
        ELSIF v_comm.status = 'paid' THEN
            v_adj_minor := v_new_comm_minor - v_comm.commission_amount_minor;
            IF v_adj_minor != 0 THEN
                INSERT INTO public.partner_commissions (
                    partner_id, customer_id, subscription_event_id,
                    commission_rate, eligible_revenue_minor, commission_amount_minor,
                    currency, status, revenue_status, reconciliation_type,
                    holding_period_days, earned_at, available_at, reversal_for_commission_id
                ) VALUES (
                    v_comm.partner_id, v_comm.customer_id, p_subscription_event_id,
                    v_comm.commission_rate, p_final_net_revenue_minor - v_comm.eligible_revenue_minor, v_adj_minor,
                    v_comm.currency, 'available', 'finalized', 'adjustment',
                    0, NOW(), NOW(), v_comm.id
                ) RETURNING id INTO v_adj_id;
                
                RETURN jsonb_build_object(
                    'success', true,
                    'post_payout_adjustment_created', true,
                    'adjustment_commission_id', v_adj_id,
                    'adjustment_minor', v_adj_minor
                );
            END IF;
        END IF;
    END IF;
    
    RETURN jsonb_build_object('success', true, 'subscription_event_id', p_subscription_event_id);
END;
$$;

-- 5.6. Release Pending Commissions RPC (Server-Only)
CREATE OR REPLACE FUNCTION public.release_pending_commissions()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_count INT;
BEGIN
    UPDATE public.partner_commissions
    SET status = 'available'
    WHERE status = 'pending'
      AND available_at <= NOW()
      AND revenue_status = 'finalized';
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    
    RETURN jsonb_build_object(
        'success', true,
        'released_count', v_count,
        'processed_at', NOW()
    );
END;
$$;

-- 5.7. Partner Dashboard Summary RPC (Guarded by auth.uid())
CREATE OR REPLACE FUNCTION public.get_partner_dashboard_summary()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_auth_id UUID;
    v_partner_id UUID;
    v_partner RECORD;
    v_total_customers INT := 0;
    v_paid_conversions INT := 0;
    v_balances JSONB := '{}'::jsonb;
    v_currency TEXT;
    v_avail_minor INT;
    v_pending_minor INT;
    v_est_minor INT;
    v_paid_minor INT;
BEGIN
    v_auth_id := auth.uid();
    IF v_auth_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'unauthorized');
    END IF;
    
    SELECT partner_id INTO v_partner_id FROM public.partner_users WHERE auth_user_id = v_auth_id;
    IF v_partner_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'partner_not_found');
    END IF;
    
    SELECT * INTO v_partner FROM public.partners WHERE id = v_partner_id;
    
    SELECT COUNT(DISTINCT customer_id) INTO v_total_customers 
    FROM public.partner_attributions 
    WHERE partner_id = v_partner_id;
    
    SELECT COUNT(DISTINCT customer_id) INTO v_paid_conversions
    FROM public.partner_commissions
    WHERE partner_id = v_partner_id AND status != 'reversed' AND commission_amount_minor > 0;
    
    FOR v_currency IN
        SELECT DISTINCT currency FROM public.partner_commissions WHERE partner_id = v_partner_id
    LOOP
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_avail_minor
        FROM public.partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND status = 'available' AND revenue_status = 'finalized';
          
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_pending_minor
        FROM public.partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND status = 'pending';
          
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_est_minor
        FROM public.partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND revenue_status = 'estimated' AND status != 'reversed';
          
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_paid_minor
        FROM public.partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND status = 'paid';
          
        v_balances := jsonb_set(
            v_balances,
            ARRAY[v_currency],
            jsonb_build_object(
                'available_minor', v_avail_minor,
                'pending_minor', v_pending_minor,
                'estimated_minor', v_est_minor,
                'paid_minor', v_paid_minor
            )
        );
    END LOOP;
    
    RETURN jsonb_build_object(
        'success', true,
        'partner_id', v_partner_id,
        'partner_name', v_partner.name,
        'referral_code', v_partner.referral_code,
        'commission_rate', v_partner.commission_rate,
        'status', v_partner.status,
        'total_customers', v_total_customers,
        'paid_conversions', v_paid_conversions,
        'conversion_rate', CASE WHEN v_total_customers > 0 THEN ROUND((v_paid_conversions::numeric / v_total_customers::numeric) * 100, 1) ELSE 0.0 END,
        'smart_link', 'https://aivekai.smart.link/referral?referral_code=' || v_partner.referral_code,
        'currency_balances', v_balances
    );
END;
$$;

-- 5.8. Concurrency-Hardened Create Partner Payout Batch RPC (Server-Only)
CREATE OR REPLACE FUNCTION public.create_partner_payout_batch(
    p_partner_id UUID,
    p_currency TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_min_threshold_minor INT;
    v_total_available_minor INT := 0;
    v_item_count INT := 0;
    v_payout_id UUID;
    v_comm RECORD;
    v_earliest TIMESTAMPTZ := NULL;
    v_latest TIMESTAMPTZ := NULL;
    v_commission_ids UUID[] := '{}';
    v_commission_amounts INT[] := '{}';
BEGIN
    -- 1. Look up minimum payout threshold
    SELECT minimum_payout_minor INTO v_min_threshold_minor
    FROM public.payout_settings
    WHERE currency = p_currency;
    
    IF v_min_threshold_minor IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'no_payout_threshold_configured',
            'currency', p_currency
        );
    END IF;
    
    -- 2. Concurrency Lock: Lock all eligible, unallocated commission rows first
    FOR v_comm IN
        SELECT c.id, c.commission_amount_minor, c.earned_at
        FROM public.partner_commissions c
        WHERE c.partner_id = p_partner_id
          AND c.currency = p_currency
          AND c.status = 'available'
          AND c.revenue_status = 'finalized'
          AND NOT EXISTS (
              SELECT 1 FROM public.partner_payout_items pi 
              WHERE pi.commission_id = c.id AND pi.is_released = FALSE
          )
        ORDER BY c.earned_at ASC
        FOR UPDATE OF c
    LOOP
        v_commission_ids := array_append(v_commission_ids, v_comm.id);
        v_commission_amounts := array_append(v_commission_amounts, v_comm.commission_amount_minor);
        v_total_available_minor := v_total_available_minor + v_comm.commission_amount_minor;
        v_item_count := v_item_count + 1;
        
        IF v_earliest IS NULL OR v_comm.earned_at < v_earliest THEN
            v_earliest := v_comm.earned_at;
        END IF;
        IF v_latest IS NULL OR v_comm.earned_at > v_latest THEN
            v_latest := v_comm.earned_at;
        END IF;
    END LOOP;
    
    -- 3. Validate threshold against locked rows
    IF v_item_count = 0 OR v_total_available_minor < v_min_threshold_minor THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'below_minimum_threshold',
            'available_minor', v_total_available_minor,
            'item_count', v_item_count,
            'minimum_threshold_minor', v_min_threshold_minor
        );
    END IF;
    
    -- 4. Insert draft payout batch with exact sum of locked items
    INSERT INTO public.partner_payouts (
        partner_id, currency, amount_minor, status,
        period_start, period_end
    ) VALUES (
        p_partner_id, p_currency, v_total_available_minor, 'draft',
        COALESCE(v_earliest, NOW()), COALESCE(v_latest, NOW())
    ) RETURNING id INTO v_payout_id;
    
    -- 5. Insert payout items linking locked commissions to this batch
    FOR i IN 1 .. v_item_count LOOP
        INSERT INTO public.partner_payout_items (
            payout_id, commission_id, amount_minor, is_released
        ) VALUES (
            v_payout_id, v_commission_ids[i], v_commission_amounts[i], FALSE
        );
    END LOOP;
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', v_payout_id,
        'partner_id', p_partner_id,
        'currency', p_currency,
        'amount_minor', v_total_available_minor,
        'item_count', v_item_count,
        'status', 'draft'
    );
END;
$$;

-- 5.9. Atomic Payout Acquisition RPC (Server-Only)
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

-- 5.10. Mark Payout Submitted RPC (Server-Only)
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

-- 5.11. Confirm Payout Success RPC (Server-Only)
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
        SELECT commission_id FROM public.partner_payout_items WHERE payout_id = p_payout_id AND is_released = FALSE
    );
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'paid');
END;
$$;

-- 5.12. Record Pre-Delivery Payout Failure (Server-Only, Non-Destructive)
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
    
    -- Preserve audit records non-destructively by setting is_released = TRUE
    UPDATE public.partner_payout_items
    SET is_released = TRUE, released_at = NOW()
    WHERE payout_id = p_payout_id;
    
    -- Release linked commissions back to available pool
    UPDATE public.partner_commissions
    SET payout_id = NULL
    WHERE id IN (
        SELECT commission_id FROM public.partner_payout_items WHERE payout_id = p_payout_id
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'failed',
        'commissions_released', true,
        'audit_history_preserved', true
    );
END;
$$;

-- 5.13. Record Post-Delivery Payout Reversal / Return RPC (Server-Only)
CREATE OR REPLACE FUNCTION public.record_partner_payout_reversal(
    p_payout_id UUID,
    p_reversal_code TEXT,
    p_reversal_message TEXT
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
    
    UPDATE public.partner_payouts
    SET 
        status = 'reversed',
        reversed_at = NOW(),
        provider_status = 'RETURNED',
        reversal_reason = p_reversal_code || ': ' || p_reversal_message
    WHERE id = p_payout_id;
    
    -- Commissions remain locked to this reversed payout record for manual audit
    UPDATE public.partner_commissions
    SET status = 'reversed', reversal_reason = 'Payout returned by PayPal: ' || p_reversal_message
    WHERE id IN (
        SELECT commission_id FROM public.partner_payout_items WHERE payout_id = p_payout_id AND is_released = FALSE
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'reversed',
        'commissions_held_for_audit', true
    );
END;
$$;

-- 5.14. Admin Adjust Commission RPC (Server-Only)
CREATE OR REPLACE FUNCTION public.create_partner_adjustment(
    p_partner_id UUID,
    p_amount_minor INT,
    p_currency TEXT,
    p_reason TEXT,
    p_admin_user_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_adj_id UUID;
    v_event_id UUID;
BEGIN
    INSERT INTO public.subscription_events (
        customer_id, platform, store_event_id, event_type, product_id,
        gross_amount_minor, estimated_net_revenue_minor, final_net_revenue_minor,
        revenue_status, currency, raw_event_reference
    ) VALUES (
        'manual_adjustment', 'web', 'adj_' || gen_random_uuid(), 'initial_purchase', 'manual_adjustment',
        p_amount_minor, p_amount_minor, p_amount_minor,
        'finalized', p_currency, jsonb_build_object('reason', p_reason, 'admin', p_admin_user_id)
    ) RETURNING id INTO v_event_id;
    
    INSERT INTO public.partner_commissions (
        partner_id, customer_id, subscription_event_id,
        commission_rate, eligible_revenue_minor, commission_amount_minor,
        currency, status, revenue_status, reconciliation_type,
        holding_period_days, earned_at, available_at
    ) VALUES (
        p_partner_id, 'manual_adjustment', v_event_id,
        100.0, p_amount_minor, p_amount_minor,
        p_currency, 'available', 'finalized', 'adjustment',
        0, NOW(), NOW()
    ) RETURNING id INTO v_adj_id;
    
    INSERT INTO public.admin_audit_logs (
        admin_user_id, action, target_type, target_id, new_values, notes
    ) VALUES (
        p_admin_user_id, 'create_financial_adjustment', 'partner_commissions', v_adj_id::text,
        jsonb_build_object('partner_id', p_partner_id, 'amount_minor', p_amount_minor, 'currency', p_currency),
        p_reason
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'adjustment_commission_id', v_adj_id,
        'partner_id', p_partner_id,
        'amount_minor', p_amount_minor,
        'currency', p_currency
    );
END;
$$;

-- ==============================================================================
-- 6. EXPLICIT FUNCTION PRIVILEGE HARDENING (LEAST PRIVILEGE)
-- ==============================================================================

-- 6.1. Revoke default EXECUTE on all functions from PUBLIC, anon, and authenticated
REVOKE EXECUTE ON FUNCTION public.process_verified_store_event(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.process_subscription_event(JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.finalize_subscription_revenue(UUID, INT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.release_pending_commissions() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.create_partner_payout_batch(UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.acquire_payout_for_submission(UUID, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.mark_payout_submitted(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.confirm_partner_payout_success(UUID, TEXT, TEXT, INT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.record_partner_payout_failure(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.record_partner_payout_reversal(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.create_partner_adjustment(UUID, INT, TEXT, TEXT, UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.get_partner_dashboard_summary() FROM PUBLIC, anon;

-- 6.2. Grant server-only & financial mutation RPCs exclusively to service_role
GRANT EXECUTE ON FUNCTION public.process_verified_store_event(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.process_subscription_event(JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.finalize_subscription_revenue(UUID, INT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.release_pending_commissions() TO service_role;
GRANT EXECUTE ON FUNCTION public.create_partner_payout_batch(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.acquire_payout_for_submission(UUID, TEXT, TEXT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_payout_submitted(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.confirm_partner_payout_success(UUID, TEXT, TEXT, INT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_partner_payout_failure(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_partner_payout_reversal(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.create_partner_adjustment(UUID, INT, TEXT, TEXT, UUID) TO service_role;

-- 6.3. Grant partner dashboard summary to authenticated (guarded by auth.uid()) & service_role
GRANT EXECUTE ON FUNCTION public.get_partner_dashboard_summary() TO authenticated, service_role;

-- 6.4. Grant customer-facing referral functions to anon, authenticated, and service_role
GRANT EXECUTE ON FUNCTION public.validate_and_apply_referral(UUID, TEXT, TEXT, JSONB) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.get_customer_referral_offer(UUID) TO anon, authenticated, service_role;

-- ==============================================================================
-- 7. Remote App Configuration Table & Remote Kill Switches
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public.app_remote_config (
    key TEXT PRIMARY KEY,
    value_boolean BOOLEAN,
    value_text TEXT,
    value_json JSONB,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.app_remote_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read access to app_remote_config" ON public.app_remote_config;
CREATE POLICY "Allow public read access to app_remote_config"
ON public.app_remote_config
FOR SELECT
TO anon, authenticated
USING (TRUE);

DROP POLICY IF EXISTS "Allow service_role full management on app_remote_config" ON public.app_remote_config;
CREATE POLICY "Allow service_role full management on app_remote_config"
ON public.app_remote_config
FOR ALL
TO service_role
USING (TRUE)
WITH CHECK (TRUE);

-- Seed GoMarketMe remote flag: MUST DEFAULT TO FALSE (disabled by default)
INSERT INTO public.app_remote_config (key, value_boolean, description)
VALUES ('gomarketme_enabled', FALSE, 'Remote kill-switch for GoMarketMe SDK integration (default: false)')
ON CONFLICT (key) DO UPDATE
SET description = EXCLUDED.description;

