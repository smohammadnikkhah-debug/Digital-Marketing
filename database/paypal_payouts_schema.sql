-- ==============================================================================
-- PHASE 7A: PAYPAL PAYOUTS EXECUTION & AUDIT SCHEMA EXTENSIONS (HARDENED)
-- ==============================================================================

-- 1. Extend partner_payouts with PayPal execution, snapshot, and reversal fields
ALTER TABLE partner_payouts
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

-- Ensure check constraint includes 'submitting' and 'reversed'
ALTER TABLE partner_payouts DROP CONSTRAINT IF EXISTS partner_payouts_status_check;
ALTER TABLE partner_payouts ADD CONSTRAINT partner_payouts_status_check
CHECK (status IN ('draft', 'approved', 'submitting', 'submitted', 'paid', 'failed', 'cancelled', 'reversed'));

CREATE INDEX IF NOT EXISTS idx_partner_payouts_provider_batch ON partner_payouts(provider_batch_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_provider_item ON partner_payouts(provider_item_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_sender_batch ON partner_payouts(sender_batch_id);
CREATE INDEX IF NOT EXISTS idx_partner_payouts_provider_status ON partner_payouts(provider_status);

-- 2. PayPal Webhook Events Audit Table
CREATE TABLE IF NOT EXISTS paypal_webhook_events (
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

CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_event_id ON paypal_webhook_events(paypal_event_id);
CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_batch_id ON paypal_webhook_events(provider_batch_id);
CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_item_id ON paypal_webhook_events(provider_item_id);
CREATE INDEX IF NOT EXISTS idx_paypal_webhooks_status ON paypal_webhook_events(processing_status);

-- Enable RLS
ALTER TABLE paypal_webhook_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Deny direct write paypal_webhook_events" ON paypal_webhook_events;
CREATE POLICY "Deny direct write paypal_webhook_events" ON paypal_webhook_events FOR ALL USING (false);

-- ==============================================================================
-- SECURE SERVER DEFINER RPCS FOR PAYPAL TRANSITIONS
-- ==============================================================================

-- 3. Atomic Payout Acquisition (Locks approved -> submitting to prevent double-submission)
CREATE OR REPLACE FUNCTION acquire_payout_for_submission(
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
    -- Atomic update: only succeeds if current status is strictly 'approved'
    UPDATE partner_payouts
    SET 
        status = 'submitting',
        sender_batch_id = COALESCE(sender_batch_id, p_sender_batch_id),
        provider_request_id = COALESCE(provider_request_id, p_provider_request_id),
        payout_destination_snapshot = COALESCE(payout_destination_snapshot, p_destination_snapshot)
    WHERE id = p_payout_id AND status = 'approved'
    RETURNING * INTO v_payout;
    
    IF NOT FOUND THEN
        -- Check current status to return descriptive error
        SELECT status INTO v_payout FROM partner_payouts WHERE id = p_payout_id;
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

-- 4. Mark Payout Submitted (Transitions submitting -> submitted once PayPal API responds)
CREATE OR REPLACE FUNCTION mark_payout_submitted(
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
    UPDATE partner_payouts
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

-- 5. Confirm Payout Success (Transitions Submitted -> Paid & Linked Commissions -> Paid)
CREATE OR REPLACE FUNCTION confirm_partner_payout_success(
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
    SELECT * INTO v_payout FROM partner_payouts WHERE id = p_payout_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
    END IF;
    
    IF v_payout.status = 'paid' THEN
        -- Idempotent duplicate success handling
        RETURN jsonb_build_object('success', true, 'payout_id', p_payout_id, 'status', 'paid', 'idempotent', true);
    END IF;
    
    IF v_payout.status != 'submitted' AND v_payout.status != 'submitting' THEN
        RETURN jsonb_build_object('success', false, 'error', 'invalid_state_for_success', 'current_status', v_payout.status);
    END IF;
    
    -- Transition payout to paid
    UPDATE partner_payouts
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
    
    -- Transition linked commissions to paid
    UPDATE partner_commissions
    SET 
        status = 'paid',
        paid_at = NOW(),
        payout_id = p_payout_id
    WHERE id IN (
        SELECT commission_id FROM partner_payout_items WHERE payout_id = p_payout_id
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'paid'
    );
END;
$$;

-- 6. Record Pre-Delivery Failure (Transitions Submitted/Submitting -> Failed & Releases Commissions)
CREATE OR REPLACE FUNCTION record_partner_payout_failure(
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
    SELECT * INTO v_payout FROM partner_payouts WHERE id = p_payout_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
    END IF;
    
    IF v_payout.status = 'paid' THEN
        RETURN jsonb_build_object('success', false, 'error', 'cannot_fail_already_paid_payout_use_reversal');
    END IF;
    
    -- Update payout to failed
    UPDATE partner_payouts
    SET 
        status = 'failed',
        failed_at = NOW(),
        provider_status = 'FAILED',
        provider_failure_code = p_failure_code,
        provider_failure_message = p_failure_message
    WHERE id = p_payout_id;
    
    -- Delete linked payout items to release eligible commissions back to available pool
    DELETE FROM partner_payout_items WHERE payout_id = p_payout_id;
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'failed',
        'commissions_released', true
    );
END;
$$;

-- 7. Record Post-Delivery Reversal / Return (Transitions Paid/Submitted -> Reversed WITHOUT auto-releasing commissions)
CREATE OR REPLACE FUNCTION record_partner_payout_reversal(
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
    SELECT * INTO v_payout FROM partner_payouts WHERE id = p_payout_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'payout_not_found');
    END IF;
    
    -- Mark payout as reversed with reason
    UPDATE partner_payouts
    SET 
        status = 'reversed',
        reversed_at = NOW(),
        provider_status = 'RETURNED',
        reversal_reason = p_reversal_code || ': ' || p_reversal_message
    WHERE id = p_payout_id;
    
    -- CRITICAL FINANCIAL SAFETY: Do NOT delete partner_payout_items or mark commissions available.
    -- Commissions remain locked to this reversed payout record for manual administrative audit & re-issuance.
    UPDATE partner_commissions
    SET status = 'reversed'
    WHERE id IN (
        SELECT commission_id FROM partner_payout_items WHERE payout_id = p_payout_id
    );
    
    RETURN jsonb_build_object(
        'success', true,
        'payout_id', p_payout_id,
        'status', 'reversed',
        'commissions_held_for_audit', true
    );
END;
$$;

-- Revoke execute from public/anon/authenticated on financial mutation RPCs
REVOKE EXECUTE ON FUNCTION acquire_payout_for_submission(UUID, TEXT, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION mark_payout_submitted(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION confirm_partner_payout_success(UUID, TEXT, TEXT, INT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION record_partner_payout_failure(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION record_partner_payout_reversal(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;

-- Grant execution to backend service role
GRANT EXECUTE ON FUNCTION acquire_payout_for_submission(UUID, TEXT, TEXT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION mark_payout_submitted(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION confirm_partner_payout_success(UUID, TEXT, TEXT, INT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION record_partner_payout_failure(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION record_partner_payout_reversal(UUID, TEXT, TEXT) TO service_role;
