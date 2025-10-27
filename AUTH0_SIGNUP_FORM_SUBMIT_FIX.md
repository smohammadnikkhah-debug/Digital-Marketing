# Auth0 Signup Form Submit Fix ✅

## 🎯 **Issue**

When user fills out the signup form on Auth0's Universal Login page and clicks "Sign up", the form submits a POST request to:

```
POST https://login.mozarex.com/u/signup?state=...
```

And returns a **400 Bad Request** error.

---

## ❌ **Root Cause**

Auth0 Universal Login **internally handles** the signup form submission and POSTs to `/u/signup` (which is part of the Universal Login flow). This is **expected behavior** and the error is likely happening because:

1. **Missing or incorrect Auth0 configuration** in Auth0 Dashboard
2. **Auth0 custom domain not properly configured**
3. **Redirect URI mismatch**

---

## ✅ **Solution**

We need to ensure Auth0 is configured correctly in the Auth0 Dashboard:

### **1. Check Application Settings**

Go to: **Auth0 Dashboard → Applications → Your App**

#### **Allowed Callback URLs:**
```
https://mozarex.com/auth/callback
https://mozarex.com/api/auth/callback
http://localhost:3000/auth/callback
```

#### **Allowed Logout URLs:**
```
https://mozarex.com
http://localhost:3000
```

#### **Allowed Web Origins:**
```
https://mozarex.com
http://localhost:3000
```

---

### **2. Check Custom Domain Configuration**

Go to: **Auth0 Dashboard → Branding → Custom Domains**

#### **Verify:**
- ✅ Custom domain `login.mozarex.com` is configured
- ✅ DNS records are correctly set up
- ✅ SSL certificate is active
- ✅ Status shows "Active" (not "Pending")

---

### **3. Check Universal Login Settings**

Go to: **Auth0 Dashboard → Branding → Universal Login**

#### **Verify:**
- ✅ Universal Login is enabled
- ✅ If using custom HTML, don't reference `/u/signup` endpoint
- ✅ Login form submits to `/authorize` endpoint

---

## 🔍 **Alternative Fix**

If the issue persists, we can try using Auth0's hosted login page with explicit `connection` parameter:

### **Option 1: Use Database Connection Explicitly**

```javascript
if (signup === 'true') {
  auth0Url = `https://${auth0Domain}/authorize?` +
    `response_type=code&` +
    `client_id=${clientId}&` +
    `redirect_uri=${redirectUri}&` +
    `scope=${scope}&` +
    `connection=Username-Password-Authentication`;  // Explicit connection
}
```

### **Option 2: Use Auth0 Management API**

Enable Universal Login with signup enabled in Auth0 Dashboard:

Go to: **Auth0 Dashboard → Branding → Universal Login → Login**

Make sure "Allow Sign Up" is enabled in the Login page settings.

---

## 🧪 **Debugging Steps**

### **1. Check Server Logs**

```bash
# Restart server and watch logs
npm start

# Then try to sign up
# Watch for:
```

**Expected logs:**
```
🔐 /login route called: { signup: 'true', plan: 'Starter', ... }
🔗 Auth0 domain (cleaned): login.mozarex.com
✅ Signup mode: Redirecting to Auth0 authorize page (no prompt, shows signup)
🔗 Redirecting to Auth0: https://login.mozarex.com/authorize?response_type=code&client_id=...&redirect_uri=...&scope=openid%20email%20profile&state=...
```

### **2. Check Browser Network Tab**

Look for:
- Initial redirect to `/authorize` ✅
- POST to `/u/signup` ❌ (should not happen with proper config)
- Callback to `/auth/callback` ✅

### **3. Check Auth0 Logs**

Go to: **Auth0 Dashboard → Monitoring → Logs**

Look for:
- "Failed Login" errors
- "Authorization API Error" messages
- Any 400 errors related to signup

---

## 📊 **Expected Behavior**

### **Correct Flow:**

```
1. User clicks "Get Started" → Plans → Select Plan
   ↓
2. Redirects to: /login?signup=true&plan=...
   ↓
3. Server redirects to: https://login.mozarex.com/authorize?...
   ↓
4. Auth0 shows signup form ✅
   ↓
5. User fills form and clicks "Sign up"
   ↓
6. Auth0 processes signup internally ✅
   ↓
7. Redirects to: https://mozarex.com/auth/callback?code=...
   ↓
8. Server exchanges code for tokens ✅
   ↓
9. Server creates user in database ✅
   ↓
10. Redirects to dashboard ✅
```

---

## ❌ **Broken Flow (Current Issue):**

```
1. User clicks "Get Started" → Plans → Select Plan
   ↓
2. Redirects to: /login?signup=true&plan=...
   ↓
3. Server redirects to: https://login.mozarex.com/authorize?...
   ↓
4. Auth0 shows signup form ✅
   ↓
5. User fills form and clicks "Sign up"
   ↓
6. Auth0 tries to POST to: https://login.mozarex.com/u/signup
   ↓
7. Returns 400 Bad Request ❌
   ↓
8. User sees error ❌
```

---

## 🔧 **Possible Workarounds**

### **Workaround 1: Use Auth0 Hosted Pages**

Instead of custom domain, use Auth0's default hosted pages:

```
https://your-tenant.auth0.com/authorize?
```

This bypasses custom domain issues.

### **Workaround 2: Disable Custom Domain Temporarily**

Go to Auth0 Dashboard → Custom Domains → Pause domain

This will use `your-tenant.auth0.com` instead of `login.mozarex.com`.

### **Workaround 3: Contact Auth0 Support**

The POST to `/u/signup` returning 400 is likely an Auth0 configuration issue that requires support.

---

## ✅ **Quick Fix Applied**

Changed the `/login` route to not use `screen_hint=signup`:

**Before:**
```javascript
auth0Url = `https://${auth0Domain}/authorize?` +
  `response_type=code&` +
  `client_id=${clientId}&` +
  `redirect_uri=${redirectUri}&` +
  `scope=${scope}&` +
  `screen_hint=signup`;  // May cause issues
```

**After:**
```javascript
auth0Url = `https://${auth0Domain}/authorize?` +
  `response_type=code&` +
  `client_id=${clientId}&` +
  `redirect_uri=${redirectUri}&` +
  `scope=${scope}`;  // Let Auth0 decide which form to show
```

This removes the explicit `screen_hint=signup` parameter and lets Auth0 handle the flow naturally.

---

## 🎯 **Final Fix Applied**

### **1. Removed `screen_hint=signup` parameter**

**Code change:**
```javascript
// Signup flow - let Auth0 decide which form to show
auth0Url = `https://${auth0Domain}/authorize?` +
  `response_type=code&` +
  `client_id=${clientId}&` +
  `redirect_uri=${redirectUri}&` +
  `scope=${scope}`;  // No screen_hint, no prompt
```

### **2. Added detailed logging**

Now logs show:
- Auth0 domain (cleaned)
- Callback URL
- Client ID

This helps debug the Auth0 configuration.

---

## 🎯 **Next Steps**

1. **Restart server** and test signup flow
2. **Check server logs** for the callback URL being used
3. **Verify Auth0 Dashboard** has matching callback URL
4. **If still fails**, contact Auth0 support about `/u/signup` 400 error

---

## 📝 **Summary**

The POST to `/u/signup` is Auth0's internal behavior for handling signup forms. The 400 error is likely due to:

✅ **Auth0 configuration issue**  
✅ **Custom domain setup**  
✅ **Redirect URI mismatch**  

**Applied fixes:**
- ✅ Removed `screen_hint=signup` parameter
- ✅ Added detailed logging for debugging
- ✅ Let Auth0 handle the flow naturally

**Next step:** Test the signup flow and check Auth0 Dashboard configuration to ensure callback URLs match.

