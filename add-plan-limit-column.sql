-- Add plan_limit column to customers table
ALTER TABLE customers 
ADD COLUMN IF NOT EXISTS plan_limit INTEGER DEFAULT 1;

-- Update existing customers based on their plan_id
UPDATE customers 
SET plan_limit = CASE 
  WHEN plan_id LIKE '%Starter%' OR plan_id LIKE '%S9k6k%' OR plan_id LIKE '%SB8Iy%' THEN 1
  WHEN plan_id LIKE '%Professional%' OR plan_id LIKE '%S9kCw%' OR plan_id LIKE '%SB8gW%' THEN 3
  WHEN plan_id LIKE '%Business%' THEN 10
  ELSE 1
END
WHERE plan_limit IS NULL OR plan_limit = 1;

-- Add comment
COMMENT ON COLUMN customers.plan_limit IS 'Maximum number of websites allowed for this customer based on their plan';
