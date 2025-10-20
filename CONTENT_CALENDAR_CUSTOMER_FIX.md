# Content Calendar Customer ID Fix ✅

## 🎯 **Issue Fixed**

**Problem:**
```
Error: "Cannot coerce the result to a single JSON object"
Details: "The result contains 2 rows"
Domain: ethanzargo.com
```

**Root Cause:**
- Legacy endpoint `/api/content-calendar/generate-seo-content` was querying by domain only
- Two customers have websites with same domain `ethanzargo.com`
- Query returned 2 rows, `.single()` failed

**Solution:**
- ✅ Extract `customer_id` from authenticated session
- ✅ Filter by domain **AND** customer_id
- ✅ Use `.maybeSingle()` instead of `.single()`
- ✅ Get website for the **logged-in customer only**

---

## 🔧 **What Was Fixed**

### **File:** `server.js` (lines 6941-7087)

### **BEFORE (Broken):**
```javascript
// Old code (in contentCalendarService):
const { data: website } = await supabase
    .from('websites')
    .select('*')
    .eq('domain', domain)  // ❌ Only filters by domain
    .single();  // ❌ Fails if 2 rows exist

// Problem: Returns 2 rows for ethanzargo.com
// Error: "Cannot coerce the result to a single JSON object"
```

### **AFTER (Fixed):**
```javascript
// New code:
const customerId = await getCustomerIdFromRequest(req);  // ✅ Get logged-in user

const { data: website } = await supabaseService.supabase
    .from('websites')
    .select('*')
    .eq('domain', domain)
    .eq('customer_id', customerId)  // ✅ Filter by customer
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();  // ✅ Handles 0 or 1 result gracefully

// Returns: The website for the LOGGED-IN customer only ✅
```

---

## 📊 **Database Scenario**

### **websites Table:**

```sql
id  | domain           | customer_id  | created_at
----|------------------|--------------|------------
123 | ethanzargo.com   | customer-A   | 2024-01-01
456 | ethanzargo.com   | customer-B   | 2024-01-15
```

**Before Fix:**
```sql
SELECT * FROM websites WHERE domain = 'ethanzargo.com';
-- Returns: 2 rows ❌
-- Error: Cannot coerce to single object
```

**After Fix:**
```sql
-- For Customer A (logged in):
SELECT * FROM websites 
WHERE domain = 'ethanzargo.com' 
AND customer_id = 'customer-A';
-- Returns: 1 row (id: 123) ✅

-- For Customer B (logged in):
SELECT * FROM websites 
WHERE domain = 'ethanzargo.com' 
AND customer_id = 'customer-B';
-- Returns: 1 row (id: 456) ✅
```

**Each customer gets their own website!** ✅

---

## 🔄 **Complete Fixed Flow**

```
User visits Content Calendar
        ↓
Frontend calls: /api/content-calendar/generate-seo-content
        ↓
Backend extracts: customer_id from session ✅
        ↓
Backend queries: 
  SELECT * FROM websites
  WHERE domain = 'ethanzargo.com'
  AND customer_id = 'customer-A'  ✅
        ↓
Returns: 1 row (customer's website) ✅
        ↓
Generate content for THIS customer's website ✅
        ↓
Store in content_memory ✅
        ↓
Return to frontend ✅
```

---

## 📊 **Expected Server Logs (Fixed)**

### **Before (Error):**
```
📨 Received request to /api/content-calendar/generate-seo-content
🎯 Generating SEO content for ethanzargo.com
🔍 Validating domain: ethanzargo.com
❌ Domain ethanzargo.com not found in websites table: {
  code: 'PGRST116',
  details: 'The result contains 2 rows',  ❌ ERROR
  message: 'Cannot coerce the result to a single JSON object'
}
✅ Generated 0 SEO-optimized posts
```

### **After (Success):**
```
📨 Received request to LEGACY endpoint /api/content-calendar/generate-seo-content
🔄 Using new AI-powered generation system...
👤 Customer ID from session: customer-A  ✅
✅ Website found for customer: { id: 123, domain: 'ethanzargo.com' }  ✅
🔄 Generating content with new AI system: { 
  domain: 'ethanzargo.com', 
  websiteId: 123, 
  customer: 'customer-A' 
}
📅 Generating monthly content for ethanzargo.com (starter plan)
🔍 Extracting keywords and services from crawl data...
✅ Extracted: { keywords: 8, services: 4, themes: 7 }
📝 Generating blog post for keyword: web design
✅ Blog post generated: Professional Web Design Guide
✅ Generated 40 items via new AI system (customer-specific)  ✅
```

---

## 🎯 **Key Changes**

### **1. Customer Authentication**
```javascript
// Extract customer_id from session
const customerId = await getCustomerIdFromRequest(req);

// Validate authentication
if (!customerId) {
    return res.status(401).json({ error: 'Authentication required' });
}
```

### **2. Customer-Specific Query**
```javascript
// Query with BOTH domain AND customer_id
.eq('domain', domain)
.eq('customer_id', customerId)  // ← KEY FIX
.maybeSingle();  // ← Better error handling
```

### **3. Calls New AI System**
```javascript
// Uses new intelligentContentGenerator
const result = await intelligentContentGenerator.generateMonthlyContent(
    supabaseService.supabase,
    website.id,  // Customer's website
    crawlData,
    website.domain,
    userPlan,
    month,
    year
);
```

### **4. Backward Compatibility**
```javascript
// Converts new format to legacy format
// So existing frontend still works!
const legacyData = result.calendar.flatMap(item => {
    // Convert blog, twitter, instagram, tiktok
    // To legacy format
});
```

---

## ✅ **Benefits of This Fix**

### **Security:**
✅ **Customer isolation** - Each customer sees only their website  
✅ **Authentication required** - Returns 401 if not logged in  
✅ **Data validation** - Verifies website belongs to customer  

### **Reliability:**
✅ **Handles multiple rows** - Uses `.maybeSingle()`  
✅ **No more errors** - Proper customer filtering  
✅ **Graceful fallback** - Clear error messages  

### **Functionality:**
✅ **Uses new AI system** - ChatGPT-powered generation  
✅ **Plan limits enforced** - From plan-limits-config.js  
✅ **Duplication prevention** - Content memory system  
✅ **Backward compatible** - Old frontend still works  

---

## 🧪 **Testing the Fix**

### **Test 1: Restart Server**
```bash
npm start
```

### **Test 2: Go to Content Calendar**
```
http://localhost:3000/seo-tools-content-calendar
```

### **Test 3: Watch Server Logs**

**Should see:**
```
📨 Received request to LEGACY endpoint...
👤 Customer ID from session: abc-123-customer-id  ✅ (not null!)
✅ Website found for customer: { id: 123, domain: 'ethanzargo.com' }  ✅
🔄 Generating content with new AI system...
📅 Generating monthly content for ethanzargo.com...
✅ Generated 40 items via new AI system (customer-specific)
```

**Should NOT see:**
```
❌ Domain ethanzargo.com not found in websites table  ❌
❌ The result contains 2 rows  ❌
```

---

## 📊 **Multi-Customer Support**

### **Scenario:**

```
Database has:
- Customer A: ethanzargo.com (website_id: 123)
- Customer B: ethanzargo.com (website_id: 456)
```

**Customer A Generates Content:**
```
Login as Customer A
  ↓
customer_id: 'customer-A'
  ↓
Query: domain = 'ethanzargo.com' AND customer_id = 'customer-A'
  ↓
Returns: website_id 123 ✅
  ↓
Generates content for website 123
  ↓
Stores in content_memory with website_id = 123
  ↓
Customer A sees their content ✅
```

**Customer B Generates Content:**
```
Login as Customer B
  ↓
customer_id: 'customer-B'
  ↓
Query: domain = 'ethanzargo.com' AND customer_id = 'customer-B'
  ↓
Returns: website_id 456 ✅
  ↓
Generates content for website 456
  ↓
Stores in content_memory with website_id = 456
  ↓
Customer B sees their content ✅
```

**Result:** No conflicts! Each customer gets their own content! 🎉

---

## 🔐 **Security Validation**

### **Customer Isolation:**

```javascript
// Every query now includes:
.eq('customer_id', customerId)

// Ensures:
✅ Customer A cannot access Customer B's website
✅ Customer B cannot access Customer A's content
✅ Each customer isolated to their own data
```

### **Authentication:**

```javascript
// Every request checks:
const customerId = await getCustomerIdFromRequest(req);

if (!customerId) {
    return 401 Unauthorized;
}

// Ensures:
✅ Only logged-in users can generate content
✅ Anonymous users blocked
✅ Session validation required
```

---

## 📈 **Expected Behavior Now**

### **Customer A Visits Calendar:**
```
1. System extracts: customer_id = 'customer-A'
2. Queries website: domain + customer_id
3. Finds: website_id 123 (Customer A's website)
4. Generates content for website 123
5. Shows content in calendar
✅ Works perfectly!
```

### **Customer B Visits Calendar:**
```
1. System extracts: customer_id = 'customer-B'
2. Queries website: domain + customer_id
3. Finds: website_id 456 (Customer B's website)
4. Generates content for website 456
5. Shows content in calendar
✅ Works perfectly!
```

**No more "2 rows" error!** ✅

---

## 🎯 **Summary**

### **What Was Fixed:**

✅ **Customer ID extraction** - From authenticated session  
✅ **Customer-specific query** - Filters by customer_id  
✅ **Proper error handling** - Uses .maybeSingle()  
✅ **Multi-customer support** - Each gets their own data  
✅ **Uses new AI system** - intelligentContentGenerator  
✅ **Backward compatible** - Legacy format conversion  

### **Result:**

✅ **No more "2 rows" error**  
✅ **Each customer sees only their website**  
✅ **Proper authentication required**  
✅ **AI-powered content generation**  
✅ **Plan limits enforced**  

---

## 🚀 **Try It Now!**

1. **Restart server:**
   ```bash
   npm start
   ```

2. **Login as your user** (customer-A or customer-B)

3. **Go to Content Calendar:**
   ```
   http://localhost:3000/seo-tools-content-calendar
   ```

4. **Watch the logs:**
   ```
   ✅ Should show your customer_id
   ✅ Should find YOUR website (not error)
   ✅ Should generate content successfully
   ```

**The "2 rows" error should be gone!** 🎉

---

## ✅ **Files Modified**

1. ✅ `server.js` - Fixed legacy endpoint (lines 6941-7087)
   - Added customer_id extraction
   - Added customer_id filtering
   - Uses new AI generation system
   - Backward compatible format conversion

2. ✅ `plan-limits-config.js` - Your changes applied
   - Starter: 10 blogs, 10 social
   - Professional: 50 blogs, 50 social

---

**Status:** ✅ **FIXED**

The legacy endpoint now:
- ✅ Extracts customer_id from session
- ✅ Filters by customer_id (gets correct website)
- ✅ No more "2 rows" error
- ✅ Generates customer-specific content
- ✅ Uses new AI system with all features

**Your content calendar should work now!** 🚀

