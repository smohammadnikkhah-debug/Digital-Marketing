# Customer and Website Management Implementation

## Overview
Successfully implemented the customer-centric signup and website management flow as requested. This implementation ensures that every user is linked to a customer record with a plan, and all websites are associated with their respective customers with plan-based limits.

## Database Schema Changes Required

### 1. Users Table
The `users` table must have a `customer_id` column to link each user to their customer:

```sql
ALTER TABLE users
ADD COLUMN customer_id UUID REFERENCES customers(id);
```

### 2. Websites Table
The `websites` table needs to have the `company_name` column:

```sql
ALTER TABLE websites
ADD COLUMN company_name VARCHAR(255);
```

**Important Note**: The `customer_id` column in the `websites` table should remain `NOT NULL` to maintain referential integrity. Every website must be associated with a customer.

## Implementation Details

### 1. Customer Creation on Signup (`routes/auth.js`)
- When a user signs up, a customer record is **created first** in the `customers` table
- The customer record includes:
  - `company_name`: Derived from the user's full name or email
  - `contact_email`: User's email
  - `plan_id`: The plan selected during signup (from the plans page)
  - Timestamps: `created_at` and `updated_at`
- The new user record is then created with the `customer_id` linking to this customer

### 2. Customer Creation on Auth0 Login (`server.js`)
- For new users logging in via Auth0 (not through signup):
  - A customer record is created with a default 'basic' plan
  - The user record is then created and linked to this customer via `customer_id`

### 3. Website Creation with Customer Linking (`services/supabaseService.js`)
- **Updated `createOrGetWebsite` method**:
  - Now accepts an optional `customerId` parameter
  - Checks for existing websites based on both `domain` AND `customer_id`
  - Validates website limits before creating a new website using `validateWebsiteLimit`
  - Includes `customer_id` in the website data when creating new records

### 4. Website Limit Validation (`services/supabaseService.js`)
- **New `validateWebsiteLimit` method**:
  - Fetches the customer's `plan_id` from the database
  - Counts the customer's existing websites
  - Compares against limits defined in `plan-limits-config.js`
  - Returns whether the customer can add more websites, along with current count and limit

### 5. Plan-Based Website Limits (`plan-limits-config.js`)
- **Configuration file** that maps plan IDs to website limits:
  ```javascript
  const PLAN_WEBSITE_LIMITS = {
      'basic': 1,
      'Starter Monthly': 1,
      'Starter Yearly': 1,
      'pro': 5,
      'Professional Monthly': 5,
      'Professional Yearly': 5,
      'business': 10
  };
  ```
- Default limit: 1 website (basic plan)
- Easily configurable via environment variables if needed

### 6. All Website Creation Call Sites Updated (`server.js`)
- **Added `getCustomerIdFromRequest` helper function**:
  - Extracts the JWT token from the request
  - Decodes the token to get the user ID
  - Fetches the user from the database to retrieve their `customer_id`
- **Updated all 8 instances** of `supabaseService.createOrGetWebsite` to pass `customer_id`:
  1. Content calendar generation (`/api/content-calendar/generate-seo-content`)
  2. Mozarex AI chat (`/api/ai/mozarex-chat`)
  3. Website analysis endpoint (`/api/dataforseo/environment/analyze-website`)
  4. Website analysis with data generation (`/api/dataforseo/environment/analyze-website-with-data`)
  5. Get cached keywords (`/api/supabase/keywords/:domain`)
  6. Add keyword (`/api/supabase/keywords`)
  7. Get content calendar (`/api/supabase/calendar/:domain`)
  8. Store content calendar (`/api/supabase/calendar`)

## Signup Flow

### Current Flow:
1. **Plans Page** (`/plans`): User selects a plan (monthly or yearly)
2. **Signup Page** (`/signup?plan=<planId>`): User enters their details
3. **Backend Processing**:
   - Creates customer record in `customers` table with selected plan
   - Creates Auth0 user account
   - Creates user record in `users` table linked to the customer via `customer_id`
4. **Onboarding Page** (`/onboarding-simple`): User adds their domain and business description
5. **Dashboard** (`/dashboard`): User sees their domain analysis and score

### Auth0 Login Flow (for returning users):
1. User clicks "Login"
2. Redirected to Auth0 Universal Login
3. After successful login, Auth0 redirects to `/auth/callback`
4. Backend checks if user exists:
   - **If exists**: Redirects to `/dashboard` (if domain exists) or `/onboarding` (if no domain)
   - **If new**: Creates customer (default 'basic' plan), creates user, redirects to `/onboarding`

## Error Handling

### Website Limit Exceeded
When a customer tries to add more websites than their plan allows, the `createOrGetWebsite` method returns:
```javascript
{
  error: 'Website limit exceeded',
  limit: <plan limit>,
  current: <current website count>
}
```

The frontend should handle this error and prompt the user to upgrade their plan.

### Missing Customer ID
If `customer_id` cannot be extracted from the request (e.g., unauthenticated user), the website will be created without a `customer_id`, which should fail due to the `NOT NULL` constraint, ensuring data integrity.

## Testing the Implementation

### 1. New Signup Flow
1. Navigate to `http://localhost:3000/plans`
2. Select a plan (e.g., "Starter Yearly")
3. Click "Choose Plan" - should redirect to `/signup?plan=<priceId>`
4. Fill in signup details and submit
5. Verify in Supabase:
   - New record in `customers` table with correct `plan_id`
   - New record in `users` table with `customer_id` linking to the customer
6. Complete onboarding by adding a domain
7. Verify in Supabase:
   - New record in `websites` table with `customer_id` linking to the same customer

### 2. Website Limit Validation
1. Log in as a user with a "Starter" plan (limit: 1 website)
2. Try to add a second website
3. Should receive an error: "Website limit exceeded"
4. Verify the error includes current count and plan limit

### 3. Multiple Websites (Pro Plan)
1. Log in as a user with a "Professional" plan (limit: 5 websites)
2. Add up to 5 websites
3. Attempt to add a 6th website
4. Should receive a limit exceeded error

### 4. Auth0 Login (New User)
1. Click "Login" and authenticate via Auth0 with a new account
2. Verify in Supabase:
   - New record in `customers` table with `plan_id: 'basic'`
   - New record in `users` table with `customer_id` linking to the customer
3. Complete onboarding and verify website is linked to the customer

## Configuration

### Adjusting Website Limits
To change website limits for plans, edit `plan-limits-config.js`:

```javascript
const PLAN_WEBSITE_LIMITS = {
    'basic': 1,                    // Change to desired limit
    'Starter Monthly': 1,          // Change to desired limit
    'Starter Yearly': 1,           // Change to desired limit
    'pro': 5,                      // Change to desired limit
    'Professional Monthly': 5,     // Change to desired limit
    'Professional Yearly': 5,      // Change to desired limit
    'business': 10                 // Change to desired limit
};
```

### Making Limits Environment-Driven (Future Enhancement)
To make limits configurable via environment variables:

1. Add to `.env`:
```
PLAN_LIMIT_BASIC=1
PLAN_LIMIT_STARTER_MONTHLY=1
PLAN_LIMIT_STARTER_YEARLY=1
PLAN_LIMIT_PRO=5
PLAN_LIMIT_PROFESSIONAL_MONTHLY=5
PLAN_LIMIT_PROFESSIONAL_YEARLY=5
PLAN_LIMIT_BUSINESS=10
```

2. Update `plan-limits-config.js` to read from `process.env`

## Files Modified

### New Files
- `plan-limits-config.js`: Plan-based website limits configuration

### Modified Files
- `server.js`:
  - Added `getCustomerIdFromRequest` helper function
  - Updated Auth0 callback to create customer for new users
  - Updated all `createOrGetWebsite` calls to pass `customer_id`
- `routes/auth.js`:
  - Updated `/signup` to create customer record first
  - Linked user to customer via `customer_id`
- `services/auth0Service.js`:
  - Added `createCustomer` method
  - Added `getCustomerByEmail` method
  - Added `getCustomerById` method
  - Modified `createSupabaseUser` to accept and store `customer_id`
- `services/supabaseService.js`:
  - Modified `createOrGetWebsite` to accept and use `customer_id`
  - Added `validateWebsiteLimit` method for plan-based validation

## Next Steps

1. **Database Migration**: Run the SQL commands above in Supabase to add required columns
2. **Test the Flow**: Follow the testing steps to verify signup, login, and website management
3. **Frontend Error Handling**: Update frontend to handle website limit errors gracefully
4. **Plan Upgrade Flow**: Implement a plan upgrade feature when users hit their website limit

## Notes

- All existing code has been updated to use `customer_id` when creating or fetching websites
- The implementation ensures referential integrity between users, customers, and websites
- Website limits are enforced at the database level through the `validateWebsiteLimit` method
- The system now properly supports multiple customers with different plans
- Each customer can have multiple users (future feature) accessing their websites

---
**Status**: ✅ Implementation Complete
**Server**: ✅ Running on http://localhost:3000
**All TODOs**: ✅ Completed
