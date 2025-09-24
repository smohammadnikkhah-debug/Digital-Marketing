-- Add company column to users table
ALTER TABLE public.users 
ADD COLUMN company TEXT;

-- Add comment to the column
COMMENT ON COLUMN public.users.company IS 'User company name';


