-- Fix unique constraint issue on websites table
-- Remove the unique constraint on domain field to allow multiple customers to add the same domain

-- First, let's check the current constraints
SELECT 
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name,
    tc.constraint_type
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
WHERE 
    tc.table_name = 'websites' 
    AND tc.constraint_type = 'UNIQUE';

-- Remove the unique constraint on domain field
ALTER TABLE websites DROP CONSTRAINT IF EXISTS websites_domain_key;

-- Add a composite unique constraint on (domain, customer_id) instead
-- This allows multiple customers to have the same domain, but prevents duplicate entries for the same customer
ALTER TABLE websites ADD CONSTRAINT websites_domain_customer_unique UNIQUE (domain, customer_id);

-- Verify the changes
SELECT 
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name,
    tc.constraint_type
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
WHERE 
    tc.table_name = 'websites' 
    AND tc.constraint_type = 'UNIQUE';