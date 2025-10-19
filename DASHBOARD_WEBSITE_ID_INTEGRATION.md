# Dashboard Integration Guide: Pass Website ID to Technical SEO

## 🎯 **What Changed**

The Technical SEO AI page now requires **both** `domain` AND `website_id` to be stored in localStorage when the user clicks "View Details" on the dashboard.

### Why This Change?

1. **Customer ID is now required** - The API extracts `customer_id` from the authenticated session
2. **Specific website selection** - When multiple websites have the same domain (different customers), we need to know WHICH specific website the user clicked on, not just "the most recent one"

---

## 📋 **Required Dashboard Updates**

### Step 1: Find the "View Details" Button Handler

In your dashboard file (e.g., `dashboard-mantis-v2.html` or similar), find where you handle the "View Details" button click.

**Current Code (What you probably have):**
```javascript
function viewDomainDetails(domain) {
    // Store domain in localStorage
    localStorage.setItem('lastAnalyzedDomain', domain);
    
    // Navigate to Technical SEO page
    window.location.href = '/technical-seo';
}
```

### Step 2: Update to Include Website ID

**New Code (What you need):**
```javascript
function viewDomainDetails(domain, websiteId) {
    // Store BOTH domain and website_id in localStorage
    localStorage.setItem('lastAnalyzedDomain', domain);
    localStorage.setItem('lastAnalyzedWebsiteId', websiteId);  // ADD THIS LINE
    
    console.log('📊 Storing website data:', { domain, websiteId });
    
    // Navigate to Technical SEO page
    window.location.href = '/technical-seo';
}
```

### Step 3: Update Button HTML

Make sure the button passes the `website_id`:

**Before:**
```html
<button onclick="viewDomainDetails('example.com')">
    View Details
</button>
```

**After:**
```html
<button onclick="viewDomainDetails('example.com', '${website.id}')">
    View Details
</button>
```

Or if using event listeners:

**Before:**
```javascript
detailsBtn.addEventListener('click', () => {
    viewDomainDetails(website.domain);
});
```

**After:**
```javascript
detailsBtn.addEventListener('click', () => {
    viewDomainDetails(website.domain, website.id);  // Pass website.id
});
```

---

## 🔍 **Finding the Dashboard Code**

### Search for these patterns in your dashboard file:

```bash
# Pattern 1: Function name
grep -r "viewDomainDetails" frontend/

# Pattern 2: localStorage
grep -r "lastAnalyzedDomain" frontend/

# Pattern 3: Technical SEO navigation
grep -r "technical-seo" frontend/
```

### Common files to check:
- `frontend/dashboard-mantis-v2.html`
- `frontend/dashboard.html`
- `frontend/seo-dashboard.html`

---

## 📊 **Example: Complete Dashboard Integration**

### Full Example with API Response Handling:

```javascript
// When loading websites from API
async function loadCustomerWebsites() {
    try {
        const response = await fetch('/api/customer/websites');
        const data = await response.json();
        
        if (data.success && data.websites) {
            data.websites.forEach(websiteData => {
                const website = websiteData.website;  // Contains: id, domain, etc.
                const analysis = websiteData.analysis; // Contains: analysis data
                
                // Create card for each website
                const card = createWebsiteCard(website, analysis);
                container.appendChild(card);
            });
        }
    } catch (error) {
        console.error('Error loading websites:', error);
    }
}

// Create website card with View Details button
function createWebsiteCard(website, analysis) {
    const card = document.createElement('div');
    card.className = 'website-card';
    
    card.innerHTML = `
        <h3>${website.domain}</h3>
        <p>Score: ${analysis?.score || 'N/A'}</p>
        <button 
            class="view-details-btn" 
            onclick="viewDomainDetails('${website.domain}', '${website.id}')">
            View Technical SEO
        </button>
    `;
    
    return card;
}

// Handle View Details click - UPDATED VERSION
function viewDomainDetails(domain, websiteId) {
    console.log('📊 User clicked View Details:', { domain, websiteId });
    
    // Store BOTH domain and website_id
    localStorage.setItem('lastAnalyzedDomain', domain);
    localStorage.setItem('lastAnalyzedWebsiteId', websiteId);
    
    // Navigate to Technical SEO page
    window.location.href = '/technical-seo';
}
```

---

## 🧪 **Testing the Integration**

### 1. Test LocalStorage Values

Before navigating to Technical SEO, open browser console and check:

```javascript
// Click "View Details" button, then check:
console.log('Domain:', localStorage.getItem('lastAnalyzedDomain'));
console.log('Website ID:', localStorage.getItem('lastAnalyzedWebsiteId'));

// Should show:
// Domain: ethanzargo.com
// Website ID: 123 (or some UUID)
```

### 2. Test Technical SEO Request

Open Network tab in DevTools and watch the Technical SEO API call:

**Expected Request Payload:**
```json
{
  "domain": "ethanzargo.com",
  "websiteId": "123",
  "category": "meta-optimization"
}
```

**Expected Server Logs:**
```
👤 Customer ID from session: abc-123-customer-id
🔍 Fetching crawl data using website_id: 123
✅ Crawl data retrieved by website_id
```

### 3. Test Error Cases

#### Case 1: No Website ID (Legacy Support)
```javascript
// Should still work with just domain (uses customer_id to find website)
localStorage.setItem('lastAnalyzedDomain', 'example.com');
localStorage.removeItem('lastAnalyzedWebsiteId');
```

#### Case 2: No Authentication
```javascript
// Should show: "Authentication required"
// User needs to log in first
```

---

## 🚨 **Common Issues & Solutions**

### Issue 1: Website ID is Undefined

**Symptom:**
```javascript
console.log('Website ID:', localStorage.getItem('lastAnalyzedWebsiteId'));
// Output: null
```

**Cause:** Dashboard not passing `website.id` to the function

**Solution:** Check that your API response includes the `id` field:
```javascript
console.log('Website data:', website);
// Should show: { id: 123, domain: 'example.com', ... }
```

### Issue 2: Customer ID is Null

**Symptom:**
```
❌ Authentication required - no customer_id
```

**Cause:** User not properly authenticated or session expired

**Solutions:**
1. Ensure user is logged in
2. Check that auth token is being sent with request
3. Verify session/JWT token is valid
4. Check cookies are enabled

### Issue 3: Multiple Websites Same Domain

**Symptom:** Wrong website data shown

**Solution:** This is exactly why we need `website_id`! Ensure you're passing it correctly.

---

## 🎯 **Checklist Before Deployment**

- [ ] Dashboard passes `website_id` to `viewDomainDetails()`
- [ ] LocalStorage stores both `domain` and `websiteId`
- [ ] Button onClick handler updated with both parameters
- [ ] Tested with authenticated user
- [ ] Tested with multiple websites
- [ ] Checked browser console for errors
- [ ] Verified server logs show customer_id
- [ ] Verified AI recommendations load correctly

---

## 📝 **Quick Reference**

### What the Frontend Needs to Do:

```javascript
// 1. When user clicks "View Details"
localStorage.setItem('lastAnalyzedDomain', domain);
localStorage.setItem('lastAnalyzedWebsiteId', websiteId);

// 2. Navigate to Technical SEO
window.location.href = '/technical-seo';
```

### What Happens on Technical SEO Page:

```javascript
// 1. Load from localStorage
const domain = localStorage.getItem('lastAnalyzedDomain');
const websiteId = localStorage.getItem('lastAnalyzedWebsiteId');

// 2. Send to API
fetch('/api/technical-seo/ai-recommendations', {
    method: 'POST',
    body: JSON.stringify({
        domain: domain,
        websiteId: websiteId,  // Preferred
        category: 'meta-optimization'
    })
});
```

### What Happens on Server:

```javascript
// 1. Extract customer_id from session
const customerId = await getCustomerIdFromRequest(req);

// 2. Get data by websiteId (preferred) or domain + customer_id
if (websiteId) {
    // Direct database query with website_id
} else {
    // Fallback: use domain + customer_id
}
```

---

## 🎉 **Benefits of This Approach**

1. ✅ **Accurate Data** - Get exact website user clicked on
2. ✅ **Multi-Tenant Support** - Handle multiple customers with same domain
3. ✅ **Security** - customer_id verification ensures data isolation
4. ✅ **Performance** - Direct lookup by website_id is faster
5. ✅ **Backward Compatible** - Still works with just domain (uses customer_id)

---

## 💡 **Need Help?**

If you're stuck, check these files:
- `server.js` (line 4747-4860) - API endpoint
- `frontend/technical-seo-dashboard.html` (line 1451-1700) - Frontend logic
- `services/supabaseService.js` (line 309-378) - Data retrieval

Look for these console messages to debug:
- `📊 Storing website data:` - Dashboard
- `🔍 Getting analysis data for:` - Supabase service
- `👤 Customer ID from session:` - API endpoint
- `🔍 Fetching crawl data using website_id:` - API endpoint

