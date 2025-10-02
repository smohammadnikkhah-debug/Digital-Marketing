-- Fix customer_id constraint in websites table
-- This migration makes customer_id nullable to fix the constraint error

-- Check if the column exists and modify it if needed
DO $$ 
BEGIN
    -- Check if customer_id column exists and is NOT NULL
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'websites' 
        AND column_name = 'customer_id'
        AND is_nullable = 'NO'
    ) THEN
        -- Make customer_id nullable
        ALTER TABLE websites ALTER COLUMN customer_id DROP NOT NULL;
        
        RAISE NOTICE 'Made customer_id column nullable in websites table';
    ELSE
        RAISE NOTICE 'customer_id column is already nullable or does not exist';
    END IF;
END $$;
