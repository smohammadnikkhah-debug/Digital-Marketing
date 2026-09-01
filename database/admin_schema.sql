-- ==============================================================================
-- AIVEKAI ADMIN USERS SCHEMA
-- Phase 7C: Secure Admin Authentication & Authorization
-- ==============================================================================

CREATE TABLE IF NOT EXISTS aivekai_admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Case-insensitive unique index on normalized username
CREATE UNIQUE INDEX IF NOT EXISTS aivekai_admin_users_username_lower_idx 
ON aivekai_admin_users (lower(trim(username)));

-- Index on auth_user_id for fast session resolution
CREATE INDEX IF NOT EXISTS aivekai_admin_users_auth_user_idx 
ON aivekai_admin_users (auth_user_id);

-- Enable Row Level Security
ALTER TABLE aivekai_admin_users ENABLE ROW LEVEL SECURITY;

-- Service Role full access policy
CREATE POLICY "Service role full access on aivekai_admin_users"
    ON aivekai_admin_users
    FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role')
    WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- Authenticated admins can view their own profile
CREATE POLICY "Admins can view own administrative profile"
    ON aivekai_admin_users
    FOR SELECT
    USING (auth.uid() = auth_user_id AND is_active = true);
