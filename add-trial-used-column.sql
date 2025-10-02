-- Add trial_used column to customers table
-- Run this SQL command in your Supabase SQL Editor

-- Add trial_used column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'customers' 
        AND column_name = 'trial_used'
    ) THEN
        ALTER TABLE customers ADD COLUMN trial_used BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Update existing customers to have trial_used = false by default
UPDATE customers 
SET trial_used = FALSE 
WHERE trial_used IS NULL;

-- Add comment to the column
COMMENT ON COLUMN customers.trial_used IS 'Indicates if the customer has used their free trial';

-- Verification query (run this to check the migration)
-- SELECT 'Customers with trial_used column' as check_type, COUNT(*) as count FROM customers WHERE trial_used IS NOT NULL;
