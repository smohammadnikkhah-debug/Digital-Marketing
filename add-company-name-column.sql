-- Add company_name column to websites table if it doesn't exist
-- This migration fixes the error: "Could not find the 'company_name' column of 'websites' in the schema cache"

-- Check if the column exists and add it if it doesn't
DO $$ 
BEGIN
    -- Check if company_name column exists
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'websites' 
        AND column_name = 'company_name'
    ) THEN
        -- Add the company_name column
        ALTER TABLE websites ADD COLUMN company_name VARCHAR(255);
        
        -- Update existing records to use domain as company_name
        UPDATE websites 
        SET company_name = domain 
        WHERE company_name IS NULL;
        
        RAISE NOTICE 'Added company_name column to websites table';
    ELSE
        RAISE NOTICE 'company_name column already exists in websites table';
    END IF;
END $$;
