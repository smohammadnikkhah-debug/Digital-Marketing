-- ==============================================================================
-- PHASE 6: AIVEKAI PARTNER & ADMIN WEB PORTAL SCHEMA & RPC LAYER
-- ==============================================================================

-- 1. Partner User Authorization Mapping
CREATE TABLE IF NOT EXISTS partner_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID NOT NULL UNIQUE,
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'partner' CHECK (role IN ('partner', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_partner_users_auth ON partner_users(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_partner_users_partner ON partner_users(partner_id);

-- 2. Partner Applications Table
CREATE TABLE IF NOT EXISTS partner_applications (
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

CREATE INDEX IF NOT EXISTS idx_partner_applications_status ON partner_applications(status);
CREATE INDEX IF NOT EXISTS idx_partner_applications_email ON partner_applications(email);

-- 3. Partner Payout Accounts
CREATE TABLE IF NOT EXISTS partner_payout_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'bank_transfer',
    provider_account_reference TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'AUD',
    country TEXT NOT NULL DEFAULT 'AU',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending_verification', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payout_accounts_partner ON partner_payout_accounts(partner_id);

-- 4. Payout Settings (Configurable Minimum Thresholds)
CREATE TABLE IF NOT EXISTS payout_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    currency TEXT NOT NULL UNIQUE,
    minimum_payout_minor INT NOT NULL DEFAULT 10000, -- 100.00 (in minor units/cents)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert standard minimum thresholds if not exist
INSERT INTO payout_settings (currency, minimum_payout_minor)
VALUES ('AUD', 10000), ('USD', 10000)
ON CONFLICT (currency) DO NOTHING;

-- 5. Partner Payouts Table
CREATE TABLE IF NOT EXISTS partner_payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL DEFAULT 'AUD',
    amount_minor INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'submitted', 'paid', 'failed', 'cancelled')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL DEFAULT 'manual_batch',
    provider_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_partner_payouts_partner ON partner_payouts(partner_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_status ON partner_payouts(status);

-- 6. Partner Payout Items (Linking Ledger Entries 1:1)
CREATE TABLE IF NOT EXISTS partner_payout_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payout_id UUID NOT NULL REFERENCES partner_payouts(id) ON DELETE CASCADE,
    commission_id UUID NOT NULL REFERENCES partner_commissions(id) ON DELETE RESTRICT,
    amount_minor INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payout_commission UNIQUE(commission_id)
);

CREATE INDEX IF NOT EXISTS idx_payout_items_payout ON partner_payout_items(payout_id);

-- 7. Admin Audit Logs
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_action ON admin_audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_target ON admin_audit_logs(target_type, target_id);

-- ==============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

ALTER TABLE partner_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_payout_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE payout_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE partner_payout_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_logs ENABLE ROW LEVEL SECURITY;

-- Deny all direct client write access across portal tables
DROP POLICY IF EXISTS "Deny direct write partner_users" ON partner_users;
CREATE POLICY "Deny direct write partner_users" ON partner_users FOR ALL USING (false);

DROP POLICY IF EXISTS "Deny direct write partner_applications" ON partner_applications;
CREATE POLICY "Deny direct write partner_applications" ON partner_applications FOR ALL USING (false);

DROP POLICY IF EXISTS "Deny direct write partner_payout_accounts" ON partner_payout_accounts;
CREATE POLICY "Deny direct write partner_payout_accounts" ON partner_payout_accounts FOR ALL USING (false);

DROP POLICY IF EXISTS "Deny direct write partner_payouts" ON partner_payouts;
CREATE POLICY "Deny direct write partner_payouts" ON partner_payouts FOR ALL USING (false);

DROP POLICY IF EXISTS "Deny direct write partner_payout_items" ON partner_payout_items;
CREATE POLICY "Deny direct write partner_payout_items" ON partner_payout_items FOR ALL USING (false);

DROP POLICY IF EXISTS "Deny direct write admin_audit_logs" ON admin_audit_logs;
CREATE POLICY "Deny direct write admin_audit_logs" ON admin_audit_logs FOR ALL USING (false);

-- ==============================================================================
-- SECURE SERVER DEFINER RPCS
-- ==============================================================================

-- 1. Partner Dashboard Summary RPC
CREATE OR REPLACE FUNCTION get_partner_dashboard_summary()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_auth_id UUID;
    v_partner_id UUID;
    v_partner RECORD;
    v_currency TEXT;
    v_avail_minor INT := 0;
    v_pending_minor INT := 0;
    v_est_minor INT := 0;
    v_paid_minor INT := 0;
    v_total_customers INT := 0;
    v_active_subscribers INT := 0;
    v_paid_conversions INT := 0;
    v_clicks INT := 0;
    v_balances JSONB := '{}'::jsonb;
BEGIN
    v_auth_id := auth.uid();
    IF v_auth_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'unauthorized');
    END IF;
    
    SELECT partner_id INTO v_partner_id FROM partner_users WHERE auth_user_id = v_auth_id;
    IF v_partner_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'partner_not_found');
    END IF;
    
    SELECT * INTO v_partner FROM partners WHERE id = v_partner_id;
    
    -- Count total attributed customers
    SELECT COUNT(*) INTO v_total_customers
    FROM partner_attributions
    WHERE partner_id = v_partner_id;
    
    -- Count paid conversions
    SELECT COUNT(DISTINCT customer_id) INTO v_paid_conversions
    FROM partner_commissions
    WHERE partner_id = v_partner_id AND status != 'reversed' AND commission_amount_minor > 0;
    
    -- Aggregate balances grouped by currency
    FOR v_currency IN
        SELECT DISTINCT currency FROM partner_commissions WHERE partner_id = v_partner_id
    LOOP
        -- Available & Finalized
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_avail_minor
        FROM partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND status = 'available' AND revenue_status = 'finalized';
          
        -- Pending
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_pending_minor
        FROM partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND status = 'pending';
          
        -- Estimated
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_est_minor
        FROM partner_commissions
        WHERE partner_id = v_partner_id AND currency = v_currency
          AND revenue_status = 'estimated' AND status != 'reversed';
          
        -- Paid
        SELECT COALESCE(SUM(commission_amount_minor), 0) INTO v_paid_minor
        FROM partner_commissions
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

-- 2. Partner Anonymized Commission History RPC
CREATE OR REPLACE FUNCTION get_partner_commission_history(
    p_page INT DEFAULT 1,
    p_limit INT DEFAULT 20
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_auth_id UUID;
    v_partner_id UUID;
    v_offset INT;
    v_total_count INT;
    v_items JSONB;
BEGIN
    v_auth_id := auth.uid();
    IF v_auth_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'unauthorized');
    END IF;
    
    SELECT partner_id INTO v_partner_id FROM partner_users WHERE auth_user_id = v_auth_id;
    IF v_partner_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'partner_not_found');
    END IF;
    
    v_offset := (p_page - 1) * p_limit;
    
    SELECT COUNT(*) INTO v_total_count
    FROM partner_commissions
    WHERE partner_id = v_partner_id;
    
    SELECT jsonb_agg(item) INTO v_items FROM (
        SELECT 
            c.id,
            e.event_type AS type,
            c.eligible_revenue_minor,
            c.commission_rate,
            c.commission_amount_minor,
            c.currency,
            c.status,
            c.revenue_status,
            c.earned_at,
            c.available_at
        FROM partner_commissions c
        JOIN subscription_events e ON e.id = c.subscription_event_id
        WHERE c.partner_id = v_partner_id
        ORDER BY c.earned_at DESC
        LIMIT p_limit OFFSET v_offset
    ) item;
    
    RETURN jsonb_build_object(
        'success', true,
        'page', p_page,
        'limit', p_limit,
        'total_count', v_total_count,
        'commissions', COALESCE(v_items, '[]'::jsonb)
    );
END;
$$;

-- 3. Partner Campaign Performance RPC
CREATE OR REPLACE FUNCTION get_partner_campaign_performance()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_auth_id UUID;
    v_partner_id UUID;
    v_campaigns JSONB;
BEGIN
    v_auth_id := auth.uid();
    IF v_auth_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'unauthorized');
    END IF;
    
    SELECT partner_id INTO v_partner_id FROM partner_users WHERE auth_user_id = v_auth_id;
    IF v_partner_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'partner_not_found');
    END IF;
    
    SELECT jsonb_agg(c) INTO v_campaigns FROM (
        SELECT 
            COALESCE(a.kochava_metadata->>'campaign', 'default') AS campaign_name,
            COUNT(DISTINCT a.customer_id) AS attributed_customers,
            COUNT(DISTINCT comm.customer_id) AS paid_subscribers,
            COALESCE(SUM(comm.eligible_revenue_minor), 0) AS total_eligible_revenue_minor,
            COALESCE(SUM(comm.commission_amount_minor), 0) AS total_commission_minor,
            MAX(comm.currency) AS currency
        FROM partner_attributions a
        LEFT JOIN partner_commissions comm ON comm.customer_id = a.customer_id AND comm.status != 'reversed'
        WHERE a.partner_id = v_partner_id
        GROUP BY COALESCE(a.kochava_metadata->>'campaign', 'default')
        ORDER BY total_commission_minor DESC
    ) c;
    
    RETURN jsonb_build_object(
        'success', true,
        'campaigns', COALESCE(v_campaigns, '[]'::jsonb)
    );
END;
$$;

-- 4. Admin Create Payout Batch RPC
CREATE OR REPLACE FUNCTION create_partner_payout_batch(
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
    v_total_available_minor INT;
    v_payout_id UUID;
    v_comm RECORD;
    v_earliest TIMESTAMPTZ;
    v_latest TIMESTAMPTZ;
BEGIN
    -- Look up minimum threshold strictly from payout_settings
    SELECT minimum_payout_minor INTO v_min_threshold_minor
    FROM payout_settings
    WHERE currency = p_currency;
    
    IF v_min_threshold_minor IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'no_payout_threshold_configured',
            'currency', p_currency
        );
    END IF;
    
    -- Calculate total available and finalized commission with concurrency lock
    SELECT 
        COALESCE(SUM(c.commission_amount_minor), 0),
        MIN(c.earned_at),
        MAX(c.earned_at)
    INTO v_total_available_minor, v_earliest, v_latest
    FROM partner_commissions c
    LEFT JOIN partner_payout_items pi ON pi.commission_id = c.id
    WHERE c.partner_id = p_partner_id
      AND c.currency = p_currency
      AND c.status = 'available'
      AND c.revenue_status = 'finalized'
      AND pi.id IS NULL; -- Not already linked to an active payout
      
    IF v_total_available_minor < v_min_threshold_minor THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'below_minimum_threshold',
            'available_minor', v_total_available_minor,
            'minimum_threshold_minor', v_min_threshold_minor
        );
    END IF;
    
    -- Insert draft payout batch
    INSERT INTO partner_payouts (
        partner_id, currency, amount_minor, status,
        period_start, period_end
    ) VALUES (
        p_partner_id, p_currency, v_total_available_minor, 'draft',
        COALESCE(v_earliest, NOW()), COALESCE(v_latest, NOW())
    ) RETURNING id INTO v_payout_id;
    
    -- Link commission rows to payout items atomically with row lock
    FOR v_comm IN
        SELECT c.id, c.commission_amount_minor
        FROM partner_commissions c
        LEFT JOIN partner_payout_items pi ON pi.commission_id = c.id
        WHERE c.partner_id = p_partner_id
          AND c.currency = p_currency
          AND c.status = 'available'
          AND c.revenue_status = 'finalized'
          AND pi.id IS NULL
        FOR UPDATE OF c
    LOOP
        INSERT INTO partner_payout_items (
            payout_id, commission_id, amount_minor
        ) VALUES (
            v_payout_id, v_comm.id, v_comm.commission_amount_minor
        );
    END LOOP;
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', v_payout_id,
        'partner_id', p_partner_id,
        'currency', p_currency,
        'amount_minor', v_total_available_minor,
        'status', 'draft'
    );
END;
$$;

-- 4b. Admin Cancel Payout RPC (releases commissions back to available)
CREATE OR REPLACE FUNCTION cancel_partner_payout(p_payout_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE partner_payouts
    SET status = 'cancelled'
    WHERE id = p_payout_id AND status IN ('draft', 'approved');
    
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_cannot_be_cancelled');
    END IF;
    
    -- Delete linked payout items to release commissions back to available pool
    DELETE FROM partner_payout_items WHERE payout_id = p_payout_id;
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'cancelled');
END;
$$;

-- 5. Admin Approve Payout RPC
CREATE OR REPLACE FUNCTION approve_partner_payout(p_payout_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE partner_payouts
    SET status = 'approved', approved_at = NOW()
    WHERE id = p_payout_id AND status = 'draft';
    
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_in_draft');
    END IF;
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'approved');
END;
$$;

-- 6. Admin Mark Payout Paid RPC
CREATE OR REPLACE FUNCTION mark_partner_payout_paid(
    p_payout_id UUID,
    p_provider_ref TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE partner_payouts
    SET status = 'paid', paid_at = NOW(), provider_reference = p_provider_ref
    WHERE id = p_payout_id AND status IN ('approved', 'submitted');
    
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_approved_or_submitted');
    END IF;
    
    -- Transition all linked commission items to paid
    UPDATE partner_commissions
    SET status = 'paid', paid_at = NOW(), payout_id = p_payout_id
    WHERE id IN (
        SELECT commission_id FROM partner_payout_items WHERE payout_id = p_payout_id
    );
    
    RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'paid');
END;
$$;

-- 7. Admin Create Manual Financial Adjustment RPC
CREATE OR REPLACE FUNCTION create_partner_adjustment(
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
    -- Create dummy adjustment event for audit tracking
    INSERT INTO subscription_events (
        customer_id, platform, store_event_id, event_type, product_id,
        gross_amount_minor, estimated_net_revenue_minor, final_net_revenue_minor,
        revenue_status, currency, raw_event_reference
    ) VALUES (
        'manual_adjustment', 'web', 'adj_' || gen_random_uuid(), 'initial_purchase', 'manual_adjustment',
        p_amount_minor, p_amount_minor, p_amount_minor,
        'finalized', p_currency, jsonb_build_object('reason', p_reason, 'admin', p_admin_user_id)
    ) RETURNING id INTO v_event_id;
    
    INSERT INTO partner_commissions (
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
    
    INSERT INTO admin_audit_logs (
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

-- Revoke execute from public/anon/authenticated on financial mutation RPCs
REVOKE EXECUTE ON FUNCTION create_partner_payout_batch(UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION approve_partner_payout(UUID) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION mark_partner_payout_paid(UUID, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION create_partner_adjustment(UUID, INT, TEXT, TEXT, UUID) FROM PUBLIC, anon, authenticated;

-- Grant execution to backend service role
GRANT EXECUTE ON FUNCTION create_partner_payout_batch(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION approve_partner_payout(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION mark_partner_payout_paid(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION create_partner_adjustment(UUID, INT, TEXT, TEXT, UUID) TO service_role;
