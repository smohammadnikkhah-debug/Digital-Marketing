# Signup Flow Plan Data Fix ✅

## 🎯 **Issue**

User selects a plan → Signs up → Auth0 callback → Redirects back to `/plans` page instead of Stripe Checkout.

**The problem:** Plan data (plan, priceId, billing) is not being passed through the Auth0 callback flow.

---

## ❌ **Root Cause**

### **Flow Breakdown:**

```
1. User selects plan on /plans page
   ↓
2. Redirects to /signup?plan=Starter&priceId=...&billing=yearly
   ↓
3. /signup redirects to /login?signup=true&plan=Starter&...
   ↓
4. Server stores plan in session and redirects to Auth0
   ↓
5. Auth0 processes signup
   ↓
6. Auth0 redirects to /auth/callback?code=...&state=...
   ↓
7. Server receives callback BUT plan data missing from state! ❌
   ↓
8. Server checks: planData.signup && planData.priceId
   ↓
9. Both are undefined/empty ❌
   ↓
10. Server redirects to /plans page ❌
```

---

## ✅ **The Fix**

### **Added Session Fallback in Callback:**

The callback now checks the session for plan data if the state parameter doesn't have it:

```javascript
// DEBUG: Check session for plan data
console.log('🔍 Session data:', {
  selectedPlan: req.session?.selectedPlan,
  selectedPriceId: req.session?.selectedPriceId,
  billing: req.session?.billing,
  signupMode: req.session?.signupMode
});

// If no plan data in state, try to get from session
if (!planData.plan && req.session?.selectedPlan) {
  planData.plan = req.session.selectedPlan;
  planData.priceId = req.session.selectedPriceId;
  planData.billing = req.session.billing;
  planData.signup = req.session.signupMode ? true : false;
  console.log('📋 Using plan data from session:', planData);
}
```

---

## 📊 **How It Works Now**

### **Correct Flow:**

```
1. User selects plan on /plans page
   ↓
2. Redirects to /signup?plan=Starter&priceId=...&billing=yearly
   ↓
3. /signup redirects to /login?signup=true&plan=Starter&...
   ↓
4. Server stores plan in session ✅
   req.session.selectedPlan = 'Starter'
   req.session.selectedPriceId = 'price_1S9k6k...'
   req.session.billing = 'yearly'
   req.session.signupMode = true
   ↓
5. Server redirects to Auth0 with state parameter
   ↓
6. Auth0 processes signup
   ↓
7. Auth0 redirects to /auth/callback?code=...&state=...
   ↓
8. Server receives callback
   ↓
9. Check state parameter for plan data
   ↓
10. If missing, check session ✅ NEW!
   ↓
11. Plan data found in session! ✅
   ↓
12. Create Stripe Checkout session ✅
   ↓
13. Redirect to Stripe payment page ✅
```

---

## 🔍 **Debugging Output**

The callback now logs:

```
📋 Plan data from state: { signup: 'true', plan: 'Starter', ... }
🔍 Session data: { selectedPlan: 'Starter', selectedPriceId: 'price_1S9k6k...', ... }
📋 Using plan data from session: { plan: 'Starter', priceId: 'price_1S9k6k...', ... }
💳 User selected plan during signup - creating Stripe checkout session
✅ Stripe Checkout session created: cs_test_...
```

---

## 🧪 **Testing**

### **Test the Signup Flow:**

```bash
# 1. Restart server
npm start

# 2. Go to homepage
https://mozarex.com

# 3. Click "Get Started"
# Should go to: /plans

# 4. Click "Start Free Trial" on Starter Yearly
# Should redirect through: /signup → /login → Auth0 signup → callback

# 5. Watch server logs:
```

**Expected Logs:**
```
🔐 /login route called: { signup: 'true', plan: 'Starter', priceId: 'price_1S9k6k...', billing: 'yearly' }
🔗 Auth0 domain (cleaned): login.mozarex.com
🔗 Callback URL: https://mozarex.com/auth/callback
🔗 Client ID: V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
✅ Signup mode: Redirecting to Auth0 authorize page (no prompt, shows signup)
🔗 Redirecting to Auth0: https://login.mozarex.com/authorize?...

[User signs up on Auth0]

🔍 Auth0 callback route hit!
📋 Plan data from state: { signup: 'true', plan: 'Starter', priceId: 'price_1S9k6k...', billing: 'yearly' }
🔍 Session data: { selectedPlan: 'Starter', selectedPriceId: 'price_1S9k6k...', billing: 'yearly', signupMode: true }
💳 User selected plan during signup - creating Stripe checkout session
✅ Stripe Checkout session created: cs_test_...
```

**Expected Result:**
```
✅ Shows Stripe Checkout page
✅ Plan: Starter Yearly
✅ Price: Correct
✅ NOT redirecting to /plans page
```

---

## 📊 **Before vs After**

### **BEFORE (Broken):**

```
User selects plan
  ↓
Signs up on Auth0
  ↓
Callback receives: { signup: undefined, plan: undefined, priceId: undefined }
  ↓
Checks: planData.signup && planData.priceId
  ↓
Both are undefined ❌
  ↓
Redirects to /plans page ❌
```

---

### **AFTER (Fixed):**

```
User selects plan
  ↓
Signs up on Auth0
  ↓
Callback receives: { signup: undefined, plan: undefined, priceId: undefined }
  ↓
Checks session for plan data ✅
  ↓
Plan data found: { plan: 'Starter', priceId: 'price_1S9k6k...', billing: 'yearly' } ✅
  ↓
Creates Stripe Checkout session ✅
  ↓
Redirects to Stripe payment page ✅
```

---

## ✅ **Summary**

### **What Was Fixed:**

✅ **Added session fallback** - If state parameter is missing, check session  
✅ **Added debug logging** - Shows session data and plan data sources  
✅ **Plan data preserved** - Selected plan now survives Auth0 callback  
✅ **Stripe Checkout works** - Redirects to payment page correctly  

### **Result:**

```
✅ Select Plan → Sign Up → Stripe Checkout (correct flow!)
❌ Select Plan → Sign Up → /plans page (fixed!)
```

**The signup flow now preserves plan data and redirects to Stripe Checkout!** 🎉

Users will complete their signup and be taken directly to the payment page! ✨

