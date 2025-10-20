# Plan Limits Configuration Guide ✅

## 🎯 **Overview**

All plan limits are now **centrally configured** in `plan-limits-config.js`. This makes it easy to adjust limits for websites and content generation without touching service code.

---

## 📁 **Configuration File**

**File:** `plan-limits-config.js`

This single file controls:
- ✅ Website limits (how many websites per plan)
- ✅ Content generation limits (blogs and social posts per month)
- ✅ Support for Stripe price IDs and legacy plan names

---

## 📊 **Current Content Limits**

### **Configured Limits:**

```javascript
PLAN_CONTENT_LIMITS = {
  // Free Tier
  'free': {
    blogs: 2,
    socialPosts: 10
  },
  
  // Starter Plans
  'starter': {
    blogs: 10,
    socialPosts: 50
  },
  'price_1SB8IyBFUEdVmecWKH5suX6H': { // Starter Monthly
    blogs: 10,
    socialPosts: 50
  },
  'price_1S9k6kBFUEdVmecWiYNLbXia': { // Starter Yearly
    blogs: 10,
    socialPosts: 50
  },
  
  // Professional Plans
  'professional': {
    blogs: 50,
    socialPosts: 200
  },
  'pro': {
    blogs: 50,
    socialPosts: 200
  },
  'price_1SB8gWBFUEdVmecWkHXlvki6': { // Professional Monthly
    blogs: 50,
    socialPosts: 200
  },
  'price_1S9kCwBFUEdVmecWP4DTGzBy': { // Professional Yearly
    blogs: 50,
    socialPosts: 200
  },
  
  // Enterprise Plans (Unlimited)
  'enterprise': {
    blogs: 999,
    socialPosts: 999
  },
  'business': {
    blogs: 999,
    socialPosts: 999
  },
  
  // Legacy Content Limits
  'basicContent': {
    blogs: 0,      // No blog generation
    socialPosts: 0  // No social posts
  },
  'proContent': {
    blogs: 15,
    socialPosts: 75
  }
}
```

---

## 🔧 **How to Modify Limits**

### **Option 1: Change Existing Plan Limits**

Want to give Starter plan more content?

```javascript
// In plan-limits-config.js, change:

'starter': {
  blogs: 10,        // Change to 15
  socialPosts: 50   // Change to 100
},
```

**Result:** All Starter users get 15 blogs + 100 social posts per month

---

### **Option 2: Add New Plan**

Adding a new "Premium" plan?

```javascript
// In PLAN_CONTENT_LIMITS, add:

'premium': {
  blogs: 30,
  socialPosts: 150
},
'price_1XXXXX': { // Your new Stripe price ID
  blogs: 30,
  socialPosts: 150
},
```

**Result:** New plan with 30 blogs + 150 social posts per month

---

### **Option 3: Modify Legacy Plans**

```javascript
// Change basicContent or proContent:

'basicContent': {
  blogs: 5,        // Was 0, now 5
  socialPosts: 20  // Was 0, now 20
},
```

**Result:** Legacy basic users can now generate content

---

## 🔄 **How Plans Are Resolved**

### **System checks in this order:**

```javascript
1. Check for Stripe Price ID (e.g., 'price_1SB8IyBFUEdVmecWKH5suX6H')
2. Check for plan name (e.g., 'starter', 'professional')
3. Check for legacy names (e.g., 'basicContent', 'proContent')
4. Fallback to DEFAULT_CONTENT_LIMITS
```

### **Example:**

```javascript
User has plan: 'price_1SB8IyBFUEdVmecWKH5suX6H'
  ↓
System finds: { blogs: 10, socialPosts: 50 }
  ↓
User can generate: 10 blogs + 50 social posts this month
```

```javascript
User has plan: 'proContent'
  ↓
System finds: { blogs: 15, socialPosts: 75 }
  ↓
User can generate: 15 blogs + 75 social posts this month
```

```javascript
User has unknown plan: 'random-plan-id'
  ↓
System uses default: { blogs: 10, socialPosts: 50 }
  ↓
User can generate: 10 blogs + 50 social posts this month
```

---

## 📊 **Current Limits Table**

| Plan | Plan ID | Blogs/Month | Social/Month | Total |
|------|---------|-------------|--------------|-------|
| **Free** | `free` | 2 | 10 | 12 |
| **Starter Monthly** | `price_1SB8IyBFUEdVmecWKH5suX6H` | 10 | 50 | 60 |
| **Starter Yearly** | `price_1S9k6kBFUEdVmecWiYNLbXia` | 10 | 50 | 60 |
| **Professional Monthly** | `price_1SB8gWBFUEdVmecWkHXlvki6` | 50 | 200 | 250 |
| **Professional Yearly** | `price_1S9kCwBFUEdVmecWP4DTGzBy` | 50 | 200 | 250 |
| **Enterprise** | `enterprise` | 999 | 999 | ∞ |
| **Business** | `business` | 999 | 999 | ∞ |
| **Basic Content** | `basicContent` | 0 | 0 | 0 |
| **Pro Content** | `proContent` | 15 | 75 | 90 |
| **Default** | (unknown) | 10 | 50 | 60 |

---

## 🔌 **API Functions**

### **Available Functions:**

#### 1. **getContentLimits(planId)**
Returns content limits for a plan

```javascript
const limits = getContentLimits('starter');
// Returns: { blogs: 10, socialPosts: 50 }

const limits = getContentLimits('proContent');
// Returns: { blogs: 15, socialPosts: 75 }
```

#### 2. **canGenerateMoreBlogs(planId, currentBlogCount)**
Checks if plan allows more blogs

```javascript
const canGenerate = canGenerateMoreBlogs('starter', 5);
// Returns: true (5 < 10)

const canGenerate = canGenerateMoreBlogs('starter', 10);
// Returns: false (10 >= 10)
```

#### 3. **canGenerateMoreSocialPosts(planId, currentSocialCount)**
Checks if plan allows more social posts

```javascript
const canGenerate = canGenerateMoreSocialPosts('professional', 150);
// Returns: true (150 < 200)
```

---

## 🧪 **Testing Different Plans**

### **Test Free Plan:**

```javascript
// User with 'free' plan:
const limits = getContentLimits('free');
console.log(limits);
// Output: { blogs: 2, socialPosts: 10 }

// Generate content:
// → Will generate 2 blogs
// → Will generate 10 social posts (distributed across platforms)
// → Total: 12 pieces of content
```

### **Test Starter Plan:**

```javascript
// User with 'price_1SB8IyBFUEdVmecWKH5suX6H' (Starter Monthly):
const limits = getContentLimits('price_1SB8IyBFUEdVmecWKH5suX6H');
console.log(limits);
// Output: { blogs: 10, socialPosts: 50 }

// Generate content:
// → Will generate 10 blogs
// → Will generate 50 social posts
// → Each blog gets 3 social posts (Twitter, Instagram, TikTok) = 30
// → Plus 20 standalone social posts
// → Total: 60 pieces of content
```

### **Test Pro Content (Legacy):**

```javascript
// User with 'proContent' plan:
const limits = getContentLimits('proContent');
console.log(limits);
// Output: { blogs: 15, socialPosts: 75 }

// Generate content:
// → Will generate 15 blogs
// → Will generate 75 social posts
// → Total: 90 pieces of content
```

---

## 🎛️ **Customization Examples**

### **Example 1: Increase Starter Limits**

**Scenario:** Want to give Starter users more value

```javascript
// Change in plan-limits-config.js:

'starter': {
  blogs: 20,        // Increased from 10
  socialPosts: 100  // Increased from 50
},
```

**Effect:**
- ✅ Starter users can generate 20 blogs/month
- ✅ Starter users can generate 100 social posts/month
- ✅ More competitive offering

---

### **Example 2: Create Mid-Tier Plan**

**Scenario:** Add "Growth" plan between Starter and Professional

```javascript
// Add to PLAN_CONTENT_LIMITS:

'growth': {
  blogs: 25,
  socialPosts: 125
},
'price_1GROWTH_MONTHLY': {
  blogs: 25,
  socialPosts: 125
},
'price_1GROWTH_YEARLY': {
  blogs: 25,
  socialPosts: 125
},
```

**Effect:**
- ✅ New tier with 25 blogs + 125 social posts
- ✅ Users with 'growth' plan get these limits
- ✅ Fills gap between Starter (10/50) and Professional (50/200)

---

### **Example 3: Enable Basic Content**

**Scenario:** Allow basicContent users to generate some content

```javascript
// Change in plan-limits-config.js:

'basicContent': {
  blogs: 5,        // Was 0, now 5
  socialPosts: 25  // Was 0, now 25
},
```

**Effect:**
- ✅ basicContent users can now generate content
- ✅ Limited to 5 blogs + 25 social posts/month

---

## 🔍 **How the System Uses These Limits**

### **In Content Generation:**

```javascript
// 1. Get user's plan
const userPlan = 'starter'; // From database

// 2. Get limits from config
const limits = getContentLimits(userPlan);
// Returns: { blogs: 10, socialPosts: 50 }

// 3. Check current usage
const currentBlogs = 5; // From content_memory table

// 4. Check if can generate more
const canGenerate = currentBlogs < limits.blogs;
// Returns: true (5 < 10, can generate 5 more)

// 5. Generate up to limit
const blogsToGenerate = limits.blogs - currentBlogs;
// Generate 5 more blogs
```

---

## 📈 **Enforcement Flow**

```
User requests content generation
        ↓
System gets user's plan ID from database
        ↓
System calls: getContentLimits(planId)
        ↓
Config returns: { blogs: X, socialPosts: Y }
        ↓
System queries content_memory for current month usage
        ↓
Calculates: remaining = limit - current
        ↓
    ┌─────────────────┐
    │ Has remaining?  │
    └─────────────────┘
         ↓          ↓
        YES        NO
         ↓          ↓
    Generate    Return 403
    content     "Limit reached"
         ↓
    Store in database
         ↓
    Return to user
```

---

## 🎯 **Real-World Scenarios**

### **Scenario 1: Starter User, First Time**

```javascript
Plan: 'starter'
Limits: { blogs: 10, socialPosts: 50 }
Current usage: { blogs: 0, socialPosts: 0 }
  ↓
Can generate: { blogs: true, socialPosts: true }
Remaining: { blogs: 10, socialPosts: 50 }
  ↓
Result: ✅ Generates full month of content
```

### **Scenario 2: Starter User, Already Used 10 Blogs**

```javascript
Plan: 'starter'
Limits: { blogs: 10, socialPosts: 50 }
Current usage: { blogs: 10, socialPosts: 30 }
  ↓
Can generate: { blogs: false, socialPosts: true }
Remaining: { blogs: 0, socialPosts: 20 }
  ↓
Result: ⚠️ Can only generate 20 more social posts
```

### **Scenario 3: Professional User**

```javascript
Plan: 'professional'
Limits: { blogs: 50, socialPosts: 200 }
Current usage: { blogs: 20, socialPosts: 80 }
  ↓
Can generate: { blogs: true, socialPosts: true }
Remaining: { blogs: 30, socialPosts: 120 }
  ↓
Result: ✅ Plenty of content remaining
```

### **Scenario 4: ProContent User (Legacy)**

```javascript
Plan: 'proContent'
Limits: { blogs: 15, socialPosts: 75 }
Current usage: { blogs: 0, socialPosts: 0 }
  ↓
Can generate: { blogs: true, socialPosts: true }
Remaining: { blogs: 15, socialPosts: 75 }
  ↓
Result: ✅ Generates 15 blogs + 75 social posts
```

---

## 🔧 **Modifying Limits**

### **Step 1: Open Configuration File**

```bash
# Edit this file:
plan-limits-config.js
```

### **Step 2: Find the Plan**

```javascript
// Locate the plan you want to modify:
PLAN_CONTENT_LIMITS = {
  'starter': {
    blogs: 10,        // ← Change this
    socialPosts: 50   // ← Or this
  },
  ...
}
```

### **Step 3: Update Values**

```javascript
// Example: Give Starter users more content
'starter': {
  blogs: 20,        // Increased from 10
  socialPosts: 100  // Increased from 50
},
```

### **Step 4: Restart Server**

```bash
# Stop server (Ctrl+C)
npm start
```

### **Step 5: Test**

```javascript
// Check in console:
const limits = require('./plan-limits-config').getContentLimits('starter');
console.log(limits);
// Should show: { blogs: 20, socialPosts: 100 }
```

---

## 📋 **Adding a New Plan**

### **Example: Adding "Agency" Plan**

**Step 1: Add to PLAN_CONTENT_LIMITS**

```javascript
// In plan-limits-config.js:

PLAN_CONTENT_LIMITS = {
  ...existing plans,
  
  // New Agency Plan
  'agency': {
    blogs: 100,
    socialPosts: 500
  },
  'price_1AGENCY_MONTHLY': {
    blogs: 100,
    socialPosts: 500
  },
  'price_1AGENCY_YEARLY': {
    blogs: 100,
    socialPosts: 500
  }
}
```

**Step 2: Restart Server**

```bash
npm start
```

**Step 3: Assign Plan to User**

```sql
-- In Supabase:
UPDATE users 
SET plan = 'agency' 
WHERE customer_id = 'abc-123';
```

**Result:** User can now generate 100 blogs + 500 social posts per month!

---

## 🎯 **Plan Comparison Table**

| Plan Name | Blogs | Social Posts | Total/Month | Best For |
|-----------|-------|--------------|-------------|----------|
| **Free** | 2 | 10 | 12 | Testing |
| **Starter** | 10 | 50 | 60 | Small business |
| **Professional** | 50 | 200 | 250 | Growing business |
| **Enterprise** | 999 | 999 | ∞ | Large organization |
| **Basic Content** | 0 | 0 | 0 | Disabled |
| **Pro Content** | 15 | 75 | 90 | Medium business |

---

## 💡 **Best Practices**

### **When Setting Limits:**

1. **Consider API Costs:**
   - Each blog ≈ $0.02-0.05 in OpenAI costs
   - Each social post ≈ $0.01-0.02
   - Calculate monthly costs per plan

2. **Balance Value & Cost:**
   - Free: Enough to test, not enough to rely on
   - Starter: Useful for regular posting
   - Professional: Serious content marketing
   - Enterprise: No limits (high-value customers)

3. **Social Posts Distribution:**
   - 3 platforms: Twitter, Instagram, TikTok
   - Each blog gets 1 post per platform = 3 social posts
   - Set social limit ≥ blogs × 3 for balance

4. **Monthly Reset:**
   - Limits are per month
   - Reset automatically each month
   - Previous months don't affect new limits

---

## 🔐 **Security Notes**

### **Limit Enforcement:**

✅ **Backend enforced** - Cannot be bypassed by frontend  
✅ **Database validated** - Checks content_memory table  
✅ **Per-customer** - Each customer tracked independently  
✅ **Per-website** - Multi-website support  

### **What Happens at Limit:**

```javascript
// When limit reached:
Response: 403 Forbidden
Message: "Content limit reached for this month"
Details: {
  current: { blogs: 10, socialPosts: 50 },
  limits: { blogs: 10, socialPosts: 50 },
  remaining: { blogs: 0, socialPosts: 0 }
}

// User sees:
"⚠️ Content limit reached. Upgrade plan or wait for next month."
```

---

## 📊 **Monitoring Usage**

### **Check Current Usage (SQL):**

```sql
-- For a specific website and month:
SELECT 
  content_type,
  COUNT(*) as count
FROM content_memory
WHERE website_id = 123
AND DATE_TRUNC('month', target_date) = '2024-01-01'
GROUP BY content_type;

-- Result:
-- blog        | 10
-- twitter     | 20
-- instagram   | 20
-- tiktok      | 10
-- (Total social: 50)
```

### **Check Remaining (API):**

```javascript
// Frontend can check limits:
const response = await fetch('/api/content-calendar/check-limits', {
  method: 'POST',
  body: JSON.stringify({ domain, websiteId, month, year })
});

// Returns:
{
  plan: 'starter',
  limits: { blogs: 10, socialPosts: 50 },
  current: { blogs: 5, socialPosts: 20 },
  remaining: { blogs: 5, socialPosts: 30 }
}
```

---

## 🎨 **UI Display of Limits**

### **In Content Calendar:**

```
┌──────────────────────────────────────┐
│ 📊 Plan Limits (Starter)              │
├──────────────────────────────────────┤
│ Blogs: 10/10 used (0 remaining)      │
│ Social Posts: 30/50 used (20 remaining) │
└──────────────────────────────────────┘
```

### **When Limit Reached:**

```
┌──────────────────────────────────────┐
│ ⚠️ Content Limit Reached              │
├──────────────────────────────────────┤
│ You've used all 10 blogs for this   │
│ month. Upgrade to Professional for  │
│ 50 blogs/month!                      │
│                                      │
│ [Upgrade Plan] [View Next Month]    │
└──────────────────────────────────────┘
```

---

## 🔄 **Plan Migration**

### **When User Upgrades:**

```javascript
// User upgrades from Starter to Professional mid-month

Old Plan: 'starter' (10 blogs, 50 social)
Current Usage: 10 blogs, 50 social
  ↓
Upgrade to: 'professional' (50 blogs, 200 social)
  ↓
New Limits: 50 blogs, 200 social
Current Usage: Still 10 blogs, 50 social
  ↓
Can NOW Generate: 40 more blogs, 150 more social! ✅
```

**Implementation:**
```sql
-- Update user's plan:
UPDATE users 
SET plan = 'professional'
WHERE customer_id = 'abc-123';

-- User immediately gets new limits!
```

---

## 📝 **Configuration Checklist**

When modifying limits, ensure:

- [ ] Both `blogs` and `socialPosts` values set
- [ ] Values are realistic (1-999)
- [ ] Social posts ≥ blogs × 3 (for balance)
- [ ] Stripe price IDs match exactly
- [ ] Server restarted after changes
- [ ] Tested with actual user

---

## 🚀 **Quick Reference**

### **Common Operations:**

**Change Starter plan limits:**
```javascript
'starter': { blogs: 15, socialPosts: 75 }
```

**Add new plan:**
```javascript
'my-new-plan': { blogs: 30, socialPosts: 150 }
```

**Disable plan:**
```javascript
'plan-to-disable': { blogs: 0, socialPosts: 0 }
```

**Enable unlimited:**
```javascript
'vip-plan': { blogs: 999, socialPosts: 999 }
```

---

## ✅ **Verification**

### **Test in Node.js Console:**

```javascript
// Test the config:
const config = require('./plan-limits-config');

// Test different plans:
console.log('Free:', config.getContentLimits('free'));
console.log('Starter:', config.getContentLimits('starter'));
console.log('Professional:', config.getContentLimits('professional'));
console.log('ProContent:', config.getContentLimits('proContent'));
console.log('BasicContent:', config.getContentLimits('basicContent'));
```

**Expected Output:**
```javascript
Free: { blogs: 2, socialPosts: 10 }
Starter: { blogs: 10, socialPosts: 50 }
Professional: { blogs: 50, socialPosts: 200 }
ProContent: { blogs: 15, socialPosts: 75 }
BasicContent: { blogs: 0, socialPosts: 0 }
```

---

## 🎉 **Summary**

### **Centralized Configuration:**
✅ **Single source of truth** - `plan-limits-config.js`  
✅ **Easy to modify** - Change numbers, restart server  
✅ **Supports all plans** - Stripe IDs and legacy names  
✅ **Backward compatible** - Works with existing plans  
✅ **Flexible** - Add new plans anytime  

### **Current Configuration:**
✅ Free: 2 blogs + 10 social  
✅ Starter: 10 blogs + 50 social  
✅ Professional: 50 blogs + 200 social  
✅ Enterprise: Unlimited  
✅ BasicContent: 0 blogs + 0 social (disabled)  
✅ ProContent: 15 blogs + 75 social  

---

## 📞 **Need to Change Limits?**

1. **Edit:** `plan-limits-config.js`
2. **Find:** Your plan in `PLAN_CONTENT_LIMITS`
3. **Change:** `blogs` and/or `socialPosts` values
4. **Restart:** `npm start`
5. **Test:** Generate content and verify

**That's it!** No code changes needed - just configuration! 🎯

---

**Configuration is now centralized and easily maintainable!** ✅

