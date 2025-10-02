-- Database Migration Required for Customer and Website Management
-- Run these SQL commands in your Supabase SQL Editor

-- 1. Create customers table
CREATE TABLE IF NOT EXISTS customers (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  company_name VARCHAR(255) NOT NULL,
  contact_email VARCHAR(255) UNIQUE NOT NULL,
  business_description TEXT,
  industry VARCHAR(255),
  plan_id VARCHAR(255) NOT NULL DEFAULT 'basic',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 1.1. Add plan_id column if it doesn't exist (for existing customers table)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'customers' 
        AND column_name = 'plan_id'
    ) THEN
        ALTER TABLE customers ADD COLUMN plan_id VARCHAR(255) NOT NULL DEFAULT 'basic';
    END IF;
END $$;

-- 2. Add customer_id column to users table
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id);

-- 2.1. Add plan column to users table if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' 
        AND column_name = 'plan'
    ) THEN
        ALTER TABLE users ADD COLUMN plan VARCHAR(255) DEFAULT 'basic';
    END IF;
END $$;

-- 3. Add customer_id and company_name columns to websites table
ALTER TABLE websites 
ADD COLUMN IF NOT EXISTS customer_id UUID REFERENCES customers(id) NOT NULL,
ADD COLUMN IF NOT EXISTS company_name VARCHAR(255);

-- 4. Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_customers_contact_email ON customers(contact_email);
CREATE INDEX IF NOT EXISTS idx_customers_plan_id ON customers(plan_id);
CREATE INDEX IF NOT EXISTS idx_users_customer_id ON users(customer_id);
CREATE INDEX IF NOT EXISTS idx_websites_customer_id ON websites(customer_id);

-- 5. Create trigger for customers table updated_at (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger 
        WHERE tgname = 'update_customers_updated_at' 
        AND tgrelid = 'customers'::regclass
    ) THEN
        CREATE TRIGGER update_customers_updated_at 
          BEFORE UPDATE ON customers 
          FOR EACH ROW 
          EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- 6. Add check constraint for plan_id in customers table
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_plan_id' 
        AND conrelid = 'customers'::regclass
    ) THEN
        ALTER TABLE customers 
        ADD CONSTRAINT check_plan_id 
        CHECK (plan_id IN ('basic', 'Starter Monthly', 'Starter Yearly', 'Professional Monthly', 'Professional Yearly', 'business'));
    END IF;
END $$;

-- 7. Add check constraint for plan in users table (if not already exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_plan' 
        AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users 
        ADD CONSTRAINT check_plan 
        CHECK (plan IN ('basic', 'Starter Monthly', 'Starter Yearly', 'Professional Monthly', 'Professional Yearly', 'business'));
    END IF;
END $$;

-- 8. Update existing users to have a default customer record
-- This creates a customer record for each existing user and links them
INSERT INTO customers (company_name, contact_email, plan_id)
SELECT 
  COALESCE(name, email) as company_name,
  email as contact_email,
  COALESCE(plan, 'basic') as plan_id
FROM users 
WHERE customer_id IS NULL
ON CONFLICT (contact_email) DO NOTHING;

-- 9. Update users table to link to their customer records
UPDATE users 
SET customer_id = c.id
FROM customers c
WHERE users.email = c.contact_email 
AND users.customer_id IS NULL;

-- 10. For any remaining users without customer_id, create a customer record
INSERT INTO customers (company_name, contact_email, plan_id)
SELECT 
  COALESCE(name, email) as company_name,
  email as contact_email,
  COALESCE(plan, 'basic') as plan_id
FROM users 
WHERE customer_id IS NULL
ON CONFLICT (contact_email) DO NOTHING;

-- 11. Final update to link remaining users
UPDATE users 
SET customer_id = c.id
FROM customers c
WHERE users.email = c.contact_email 
AND users.customer_id IS NULL;

-- 12. Update existing websites to have a default customer_id
-- This links existing websites to the first customer (you may need to adjust this logic)
UPDATE websites 
SET customer_id = (
  SELECT id FROM customers LIMIT 1
)
WHERE customer_id IS NULL;

-- 13. Set company_name for existing websites if null
UPDATE websites 
SET company_name = domain
WHERE company_name IS NULL;

-- Verification queries (run these to check the migration)
-- SELECT 'Users with customer_id' as check_type, COUNT(*) as count FROM users WHERE customer_id IS NOT NULL;
-- SELECT 'Users without customer_id' as check_type, COUNT(*) as count FROM users WHERE customer_id IS NULL;
-- SELECT 'Websites with customer_id' as check_type, COUNT(*) as count FROM websites WHERE customer_id IS NOT NULL;
-- SELECT 'Websites without customer_id' as check_type, COUNT(*) as count FROM websites WHERE customer_id IS NULL;
-- SELECT 'Total customers' as check_type, COUNT(*) as count FROM customers;
