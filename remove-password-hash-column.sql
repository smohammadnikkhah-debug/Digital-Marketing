-- Remove password_hash column from users table since we're using Auth0
-- This script removes the password_hash column and related policies

-- Drop the password_hash column
ALTER TABLE public.users DROP COLUMN IF EXISTS password_hash;

-- Drop the index for password_hash
DROP INDEX IF EXISTS idx_users_password_hash;

-- Drop password-related RLS policies
DROP POLICY IF EXISTS "Users can insert with password_hash" ON public.users;
DROP POLICY IF EXISTS "Users can update their own password_hash" ON public.users;
DROP POLICY IF EXISTS "Service role can manage password_hash" ON public.users;

-- Keep the basic RLS policies for Auth0 integration
-- Users can insert their own records
DROP POLICY IF EXISTS "Users can insert their own data" ON public.users;
CREATE POLICY "Users can insert their own data" ON public.users
    FOR INSERT WITH CHECK (true);

-- Users can update their own records
DROP POLICY IF EXISTS "Users can update their own data" ON public.users;
CREATE POLICY "Users can update their own data" ON public.users
    FOR UPDATE USING (auth.uid()::text = auth0_id OR auth0_id IS NULL);

-- Service role can manage all user data
DROP POLICY IF EXISTS "Service role can manage users" ON public.users;
CREATE POLICY "Service role can manage users" ON public.users
    FOR ALL USING (auth.role() = 'service_role');

-- Users can read their own data
DROP POLICY IF EXISTS "Users can read their own data" ON public.users;
CREATE POLICY "Users can read their own data" ON public.users
    FOR SELECT USING (auth.uid()::text = auth0_id OR auth0_id IS NULL);







