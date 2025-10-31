# Plan Limit Migration Guide

## Overview
We've updated the system to store `plan_limit` directly in the `customers` table for faster and more reliable website limit checking.

## Changes Made

### 1. Database Schema
- Added `plan_limit` column to `customers` table
- Professional plans = 3 websites
- Basic/Starter plans = 1 website

### 2. Code Updates
- ✅ `services/auth0Service.js`: Updated `createCustomer` to set `plan_limit` on customer creation
- ✅ `services/supabaseService.js`: Updated `validateWebsiteLimit` to read from `customers.plan_limit`
- ✅ `routes/subscription.js`: Updated upgrade endpoint to update `plan_limit` when upgrading

## Steps to Apply

### Step 1: Run SQL Migration
Run the SQL file `add-plan-limit-column.sql` in your Supabase SQL editor:

```sql
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
```

### Step 2: Verify Existing Customers
After running the migration, your existing customers should have their `plan_limit` set based on their current `plan_id`.

### Step 3: Test
1. Go to dashboard
2. Check website limit (should show correct limit based on plan)
3. Try adding a new website (should respect the limit)

## Plan Limits

- **Basic/Starter**: 1 website
- **Professional**: 3 websites
- **Business**: 10 websites (or unlimited depending on your configuration)

## Notes

- New customers will automatically get `plan_limit` set when they sign up
- Upgrading a plan will automatically update `plan_limit` in the customers table
- The dashboard now reads directly from `customers.plan_limit` for faster access
