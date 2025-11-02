# Content Calendar Plan-Based Limits - UPDATED ✅

## 🎯 New Content Generation Limits

Updated content calendar to generate content based on subscription plan:

| Plan | Blogs/Month | Social Posts/Month | Frequency |
|------|-------------|-------------------|-----------|
| **Starter** | 4 | 4 | Weekly (once per week) |
| **Pro** | 30 | 30 | Daily (every day) |
| **Free Tier** | 2 | 2 | Twice per month |

---

## 📋 Plan Details

### **Starter Plan (Weekly Content)**
```javascript
{
  blogs: 4,         // 4 blog posts per month
  socialPosts: 4    // 4 social media posts per month
}
```

**Distribution:**
- **Blog Posts:** Generated on days 7, 14, 21, 28 (weekly)
- **Social Posts:** 
  - Twitter: 1-2 posts
  - Instagram: 1-2 posts  
  - TikTok: 1-2 posts
- **Total Content:** 8 pieces per month (4 blogs + 4 social)

---

### **Professional Plan (Daily Content)**
```javascript
{
  blogs: 30,        // 30 blog posts per month
  socialPosts: 30   // 30 social media posts per month
}
```

**Distribution:**
- **Blog Posts:** 1 per day (days 1-30)
- **Social Posts:**
  - Twitter: ~10 posts per month
  - Instagram: ~10 posts per month
  - TikTok: ~10 posts per month
- **Total Content:** 60 pieces per month (30 blogs + 30 social)

---

### **Free Tier (Limited)**
```javascript
{
  blogs: 2,         // 2 blog posts per month
  socialPosts: 2    // 2 social media posts per month
}
```

**Distribution:**
- **Blog Posts:** 2 per month
- **Social Posts:** 2 per month (1-2 platforms)
- **Total Content:** 4 pieces per month

---

## 🔄 How It Works

### **1. User Navigates to Content Calendar**
```javascript
// Frontend: seo-tools-content-calendar.html
// User clicks "Generate Content" button
```

### **2. System Checks User's Plan**
```javascript
// Backend: server.js - /api/content-calendar/generate
const { data: user } = await supabaseService.supabase
  .from('users')
  .select('plan')
  .eq('customer_id', customerId)
  .maybeSingle();

const userPlan = user.plan; // 'price_1SB8IyBFUEdVmecWKH5suX6H' or other
```

### **3. Checks Plan Limits**
```javascript
// services/intelligentContentGenerator.js
const limitsCheck = await intelligentContentGenerator.checkPlanLimits(
  supabaseService.supabase,
  website.id,
  userPlan,
  month,
  year
);

// Returns:
// {
//   plan: 'price_1SB8IyBFUEdVmecWKH5suX6H',
//   limits: { blogs: 4, socialPosts: 4 },
//   current: { blogs: 0, socialPosts: 0 },
//   canGenerate: { blogs: true, socialPosts: true },
//   remaining: { blogs: 4, socialPosts: 4 }
// }
```

### **4. Generates Content Based on Plan**
```javascript
// services/intelligentContentGenerator.js
const limits = this.getContentLimits(plan);
// For Starter: { blogs: 4, socialPosts: 4 }
// For Pro: { blogs: 30, socialPosts: 30 }

const blogsPerMonth = limits.blogs;
const socialPostsPerMonth = limits.socialPosts;

// Distribute days evenly throughout the month
const blogDays = this.distributeDaysEvenly(daysInMonth, blogsPerMonth);
// Starter: [7, 14, 21, 28]
// Pro: [1, 2, 3, ... 30]
```

---

## 📊 Content Distribution Algorithm

### **Starter Plan (4 blogs)**
```
Month: 30 days
Content: 4 pieces

Distribution:
Day 7  → Blog Post #1 + Social Posts
Day 14 → Blog Post #2 + Social Posts
Day 21 → Blog Post #3 + Social Posts
Day 28 → Blog Post #4 + Social Posts
```

### **Pro Plan (30 blogs)**
```
Month: 30 days
Content: 30 pieces

Distribution:
Day 1  → Blog Post #1  + Social Posts
Day 2  → Blog Post #2  + Social Posts
Day 3  → Blog Post #3  + Social Posts
...
Day 30 → Blog Post #30 + Social Posts
```

---

## 🎨 Frontend Display

### **Content Calendar View:**

**Starter Plan:**
```
Week 1: [empty] [empty] [empty] [empty] [empty] [empty] [BLOG]
Week 2: [empty] [empty] [empty] [empty] [empty] [empty] [BLOG]
Week 3: [empty] [empty] [empty] [empty] [empty] [empty] [BLOG]
Week 4: [empty] [empty] [empty] [empty] [empty] [empty] [BLOG]
```

**Pro Plan:**
```
Week 1: [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG]
Week 2: [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG]
Week 3: [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG]
Week 4: [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG] [BLOG]
```

---

## 🔐 Plan Verification

### **Stripe Price IDs:**

```javascript
// Starter Plans
'price_1SB8IyBFUEdVmecWKH5suX6H'  // Starter Monthly  → 4 pieces/month
'price_1S9k6kBFUEdVmecWiYNLbXia'  // Starter Yearly   → 4 pieces/month

// Professional Plans
'price_1SB8gWBFUEdVmecWkHXlvki6'  // Pro Monthly      → 30 pieces/month
'price_1S9kCwBFUEdVmecWP4DTGzBy'  // Pro Yearly       → 30 pieces/month
```

---

## 📁 Files Modified

### **1. Plan Configuration**
✅ `plan-limits-config.js` (lines 23-42)
```javascript
// Updated content limits:
// Starter: 10 → 4 (blogs and social)
// Pro: 50 → 30 (blogs and social)
```

---

## 🎯 User Experience

### **Starter User:**
1. Opens Content Calendar
2. Clicks "Generate Content"
3. System generates:
   - 4 blog posts (weekly schedule)
   - 4 social media posts
   - Distributed across 4 weeks
4. User sees: "✅ Generated 4 blogs and 4 social posts!"

### **Pro User:**
1. Opens Content Calendar
2. Clicks "Generate Content"
3. System generates:
   - 30 blog posts (daily schedule)
   - 30 social media posts
   - Distributed across 30 days
4. User sees: "✅ Generated 30 blogs and 30 social posts!"

---

## ⚠️ Limit Enforcement

### **Monthly Limits:**
```javascript
// If user tries to generate again in same month:
if (currentBlogCount >= limits.blogs) {
  return {
    success: false,
    error: 'Content limit reached for this month'
  };
}
```

### **Plan Limit Info Display:**
```javascript
// Frontend shows:
📊 Plan Limits (Starter)
Blogs: 4/4 used
Social Posts: 4/4 used

// Or for Pro:
📊 Plan Limits (Professional)
Blogs: 30/30 used
Social Posts: 30/30 used
```

---

## 🧪 Testing

### **Test Starter Plan:**
1. Login as Starter user
2. Navigate to Content Calendar
3. Click "Generate Content"
4. Verify: 4 blog posts generated
5. Verify: Content spread across 4 weeks
6. Try generating again → Should show limit reached

### **Test Pro Plan:**
1. Login as Pro user
2. Navigate to Content Calendar
3. Click "Generate Content"
4. Verify: 30 blog posts generated
5. Verify: Content for every day of month
6. Try generating again → Should use cached data

---

## 💡 Key Benefits

1. **Clear Plan Differentiation**
   - Starter: Weekly content (affordable, manageable)
   - Pro: Daily content (comprehensive, professional)

2. **Fair Usage**
   - Limits enforced per month
   - Can't exceed plan allowance
   - Cached content reused (no duplicate API calls)

3. **Scalable**
   - Easy to add new plans
   - Simple to adjust limits
   - Centralized configuration

4. **Cost Efficient**
   - Caches generated content
   - Reuses content within same month
   - Only generates new content when needed

---

## 📊 API Response Structure

### **Success Response:**
```json
{
  "success": true,
  "calendar": [
    {
      "date": "2025-11-07T00:00:00.000Z",
      "day": 7,
      "content": {
        "blog": { "title": "...", "content": "..." },
        "twitter": { "tweet": "..." },
        "instagram": { "caption": "..." },
        "tiktok": { "caption": "..." }
      }
    }
  ],
  "metadata": {
    "domain": "example.com",
    "plan": "price_1SB8IyBFUEdVmecWKH5suX6H",
    "month": 10,
    "year": 2025,
    "blogsGenerated": 4,
    "socialPostsGenerated": 4,
    "fromCache": false
  },
  "limits": {
    "plan": "price_1SB8IyBFUEdVmecWKH5suX6H",
    "limits": { "blogs": 4, "socialPosts": 4 },
    "current": { "blogs": 4, "socialPosts": 4 },
    "remaining": { "blogs": 0, "socialPosts": 0 }
  }
}
```

### **Limit Reached Response:**
```json
{
  "success": false,
  "error": "Content limit reached for this month",
  "limits": {
    "plan": "price_1SB8IyBFUEdVmecWKH5suX6H",
    "limits": { "blogs": 4, "socialPosts": 4 },
    "current": { "blogs": 4, "socialPosts": 4 },
    "remaining": { "blogs": 0, "socialPosts": 0 }
  }
}
```

---

## ✅ Summary

**Updated Content Limits:**
- ✅ Starter Plan: 4 pieces/month (weekly)
- ✅ Pro Plan: 30 pieces/month (daily)
- ✅ Plan verification working
- ✅ Limit enforcement active
- ✅ Content distribution optimized

**Result:** Content calendar now generates the correct amount of content based on user's subscription plan!

---

**Last Updated:** November 2, 2025  
**Version:** 2.0  
**Status:** ✅ Active  
**Configuration:** plan-limits-config.js

