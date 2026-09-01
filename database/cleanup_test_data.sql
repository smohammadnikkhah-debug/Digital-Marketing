-- ==============================================================================
-- AivekAI Partner Program: Test/Dummy Data Inspection & Cleanup Script
-- ==============================================================================
-- NOTE: Do NOT run deletion queries without explicit production confirmation.
-- This script contains inspection queries and a transaction-safe cleanup block.

-- 1. INSPECT CURRENT TEST / DUMMY IDENTITIES
-- Run these SELECT queries first to verify test records:

-- Check for test partners (James Smith, Sarah Jenkins, etc.)
SELECT id, name, referral_code, contact_email, paypal_email, status, created_at
FROM public.partners
WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
   OR contact_email ILIKE '%example.com%'
   OR contact_email ILIKE '%test%';

-- Check for associated partner user mappings
SELECT id, auth_user_id, partner_id, role, is_active, created_at
FROM public.partner_users
WHERE partner_id IN (
    SELECT id FROM public.partners 
    WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
       OR contact_email ILIKE '%example.com%'
);

-- Check for test admin identities
SELECT id, auth_user_id, username, role, is_active, created_at
FROM public.aivekai_admin_users
WHERE username ILIKE '%test%' OR username ILIKE '%demo%';

-- Check for test payouts and commissions
SELECT id, partner_id, amount_minor, currency, status, provider_batch_id, created_at
FROM public.partner_payouts
WHERE partner_id IN (
    SELECT id FROM public.partners 
    WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
);

-- ==============================================================================
-- 2. SAFE TRANSACTIONAL CLEANUP SCRIPT (RUN ONLY UPON EXPLICIT APPROVAL)
-- ==============================================================================

/*
BEGIN;

-- A. Remove payout batch items and payouts for test partners
DELETE FROM public.partner_payout_items 
WHERE payout_id IN (
    SELECT id FROM public.partner_payouts 
    WHERE partner_id IN (
        SELECT id FROM public.partners WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
    )
);

DELETE FROM public.partner_payouts 
WHERE partner_id IN (
    SELECT id FROM public.partners WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
);

-- B. Remove test commissions
DELETE FROM public.partner_commissions 
WHERE partner_id IN (
    SELECT id FROM public.partners WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
);

-- C. Remove test partner payout accounts
DELETE FROM public.partner_payout_accounts 
WHERE partner_id IN (
    SELECT id FROM public.partners WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
);

-- D. Remove partner user mappings
DELETE FROM public.partner_users 
WHERE partner_id IN (
    SELECT id FROM public.partners WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO')
);

-- E. Remove partners
DELETE FROM public.partners 
WHERE referral_code IN ('JAMES', 'SARAH', 'DEMO') 
   OR contact_email ILIKE '%example.com%';

-- F. Remove test admin accounts (if any)
DELETE FROM public.aivekai_admin_users 
WHERE username ILIKE '%test%' OR username ILIKE '%demo%';

-- Verify and COMMIT (or ROLLBACK if needed)
-- COMMIT;
-- ROLLBACK;
*/
