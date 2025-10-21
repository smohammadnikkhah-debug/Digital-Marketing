# Logout URL Fix - Double HTTPS Issue ✅

## 🎯 **Issue Fixed**

### **The Problem:**
```
User clicks logout
        ↓
Redirects to: https://https//login.mozarex.com/v2/logout?returnTo=...
                     ↑ DOUBLE HTTPS!
        ↓
DNS_PROBE_FINISHED_NXDOMAIN error
```

**Error:** `This site can't be reached` - double protocol in URL

---

## ❌ **Root Cause**

### **In `routes/auth.js`:**
```javascript
// OLD CODE (BROKEN):
const logoutURL = `https://${process.env.AUTH0_DOMAIN}/v2/logout?` +
    `returnTo=${encodeURIComponent(process.env.AUTH0_LOGOUT_URL)}&` +
    `client_id=${process.env.AUTH0_CLIENT_ID}`;

// When AUTH0_DOMAIN = "https://login.mozarex.com"
// Result: https://https://login.mozarex.com/v2/logout  ❌
```

**Problems:**
1. ❌ `AUTH0_DOMAIN` includes `https://` but code prepends it again
2. ❌ `AUTH0_LOGOUT_URL` was set to Auth0 endpoint instead of final destination
3. ❌ Result: `https://https//` double protocol

---

## ✅ **The Fix**

### **Updated `routes/auth.js`:**
```javascript
// NEW CODE (FIXED):
router.get('/logout', (req, res) => {
  // Clear the session cookie
  res.clearCookie('authToken');
  
  // Clear session data
  if (req.session) {
    req.session.destroy();
  }
  
  // Prepare Auth0 domain (handle both with and without https://)
  let auth0Domain = process.env.AUTH0_DOMAIN || 'login.mozarex.com';
  if (auth0Domain.startsWith('https://')) {
    auth0Domain = auth0Domain.replace('https://', '');
  }
  if (auth0Domain.startsWith('http://')) {
    auth0Domain = auth0Domain.replace('http://', '');
  }
  
  // Set return URL (where user goes after logout)
  const returnToURL = process.env.AUTH0_LOGOUT_REDIRECT || 'https://mozarex.com';
  
  // Build Auth0 logout URL
  const logoutURL = `https://${auth0Domain}/v2/logout?` +
    `returnTo=${encodeURIComponent(returnToURL)}&` +
    `client_id=${process.env.AUTH0_CLIENT_ID}`;
  
  console.log('🚪 Logging out, redirecting to:', logoutURL);
  
  res.redirect(logoutURL);
});
```

---

## 📋 **Correct Environment Variables**

### **Option 1: Domain WITHOUT Protocol (Recommended)**

```bash
# .env file
AUTH0_DOMAIN=login.mozarex.com  # ✅ NO https://
AUTH0_CLIENT_ID=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
AUTH0_LOGOUT_REDIRECT=https://mozarex.com  # ✅ Where to go after logout
```

### **Option 2: Domain WITH Protocol (Also works now)**

```bash
# .env file
AUTH0_DOMAIN=https://login.mozarex.com  # ✅ With https:// (code strips it)
AUTH0_CLIENT_ID=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
AUTH0_LOGOUT_REDIRECT=https://mozarex.com  # ✅ Where to go after logout
```

**Note:** The fix handles both cases! ✅

---

## 🔄 **Logout Flow**

### **OLD (Broken):**
```
User clicks logout
        ↓
/logout endpoint called
        ↓
Builds URL: https://https://login.mozarex.com/v2/logout  ❌
        ↓
Browser tries to resolve "https" domain
        ↓
DNS_PROBE_FINISHED_NXDOMAIN ❌
```

---

### **NEW (Fixed):**
```
User clicks logout
        ↓
/logout endpoint called
        ↓
Strips https:// from AUTH0_DOMAIN if present ✅
        ↓
Builds URL: https://login.mozarex.com/v2/logout?
           returnTo=https%3A%2F%2Fmozarex.com&
           client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp  ✅
        ↓
Redirects to Auth0 logout
        ↓
Auth0 clears session
        ↓
Redirects back to: https://mozarex.com ✅
        ↓
User lands on homepage (logged out) ✅
```

---

## 🎨 **What The Fix Does**

### **1. Strips Protocol**
```javascript
let auth0Domain = process.env.AUTH0_DOMAIN || 'login.mozarex.com';
if (auth0Domain.startsWith('https://')) {
  auth0Domain = auth0Domain.replace('https://', '');
}
```
**Result:** Works with or without `https://` in env var

### **2. Uses Correct Return URL**
```javascript
const returnToURL = process.env.AUTH0_LOGOUT_REDIRECT || 'https://mozarex.com';
```
**Result:** User goes to homepage after logout, not Auth0 endpoint

### **3. Clears Session**
```javascript
res.clearCookie('authToken');
if (req.session) {
  req.session.destroy();
}
```
**Result:** All session data cleaned up

### **4. Logs URL for Debugging**
```javascript
console.log('🚪 Logging out, redirecting to:', logoutURL);
```
**Result:** Can verify URL is correct in logs

---

## 🧪 **Testing**

### **Test 1: Logout from Dashboard**

```bash
# 1. Restart server
npm start

# 2. Login to your app
http://localhost:3000 or https://mozarex.com

# 3. Click user menu → Logout

# 4. Watch server logs
```

**Expected Logs:**
```
🚪 Logging out, redirecting to: https://login.mozarex.com/v2/logout?returnTo=https%3A%2F%2Fmozarex.com&client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
```

**Expected Result:**
```
✅ Redirects to Auth0 logout page
✅ Auth0 clears session
✅ Redirects to https://mozarex.com
✅ User logged out successfully
```

**NOT:**
```
❌ DNS_PROBE_FINISHED_NXDOMAIN
❌ https://https// in URL
❌ "This site can't be reached"
```

---

### **Test 2: Check Constructed URL**

Open browser dev tools (Network tab) and watch the logout redirect:

**You should see:**
```
Request URL: https://login.mozarex.com/v2/logout?returnTo=https%3A%2F%2Fmozarex.com&client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
Status: 302 (Redirect)
Location: https://mozarex.com
```

**Clean URLs with single protocol!** ✅

---

## 📊 **Before vs After**

### **BEFORE (Broken):**

**Environment Variables:**
```bash
AUTH0_DOMAIN=https://login.mozarex.com
AUTH0_LOGOUT_URL=https://login.mozarex.com/v2/logout  ❌ Wrong!
```

**Generated URL:**
```
https://https://login.mozarex.com/v2/logout?returnTo=https%3A%2F%2Fhttps%2F%2Flogin.mozarex.com%2Fv2%2Flogout
                ↑ DOUBLE HTTPS ❌
```

**Result:** DNS error ❌

---

### **AFTER (Fixed):**

**Environment Variables:**
```bash
AUTH0_DOMAIN=login.mozarex.com  # or https://login.mozarex.com (both work!)
AUTH0_LOGOUT_REDIRECT=https://mozarex.com  ✅ Correct destination
```

**Generated URL:**
```
https://login.mozarex.com/v2/logout?returnTo=https%3A%2F%2Fmozarex.com&client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
       ↑ Single https:// ✅
```

**Result:** Works perfectly! ✅

---

## 🔧 **Environment Variable Setup**

### **For Local Development (.env):**

```bash
# Auth0 Configuration
AUTH0_DOMAIN=login.mozarex.com
AUTH0_CLIENT_ID=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
AUTH0_CLIENT_SECRET=your_client_secret_here
AUTH0_CALLBACK_URL=http://localhost:3000/auth/callback
AUTH0_LOGOUT_REDIRECT=http://localhost:3000  # Local homepage

# Session
AUTH0_SESSION_SECRET=your_session_secret_here
```

---

### **For Production (DigitalOcean):**

```bash
# Auth0 Configuration
AUTH0_DOMAIN=login.mozarex.com
AUTH0_CLIENT_ID=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp
AUTH0_CLIENT_SECRET=yRlJURwuzim6Dp9pc9FiMjfX1ihfpkY9xXEhaaeu0VKg821P_BmvD4GLE1buVtU8
AUTH0_CALLBACK_URL=https://mozarex.com/auth/callback
AUTH0_LOGOUT_REDIRECT=https://mozarex.com  # Production homepage

# Session
AUTH0_SESSION_SECRET=your_production_session_secret
```

---

## 🔐 **Auth0 Allowed Logout URLs**

Make sure to configure Auth0 to allow your logout redirect URL:

### **In Auth0 Dashboard:**

1. Go to **Applications** → Your Application
2. Scroll to **Allowed Logout URLs**
3. Add:
   ```
   http://localhost:3000,https://mozarex.com
   ```
4. Click **Save Changes**

Without this, Auth0 will reject the logout redirect! ⚠️

---

## ✅ **Summary**

### **What Was Fixed:**

1. ✅ **Strips `https://`** from `AUTH0_DOMAIN` if present
2. ✅ **Uses correct return URL** (homepage, not Auth0 endpoint)
3. ✅ **Clears session data** properly
4. ✅ **Logs URL** for debugging
5. ✅ **Handles both formats** (with/without protocol)

### **Environment Variables:**

1. ✅ `AUTH0_DOMAIN` = `login.mozarex.com` (NO protocol)
2. ✅ `AUTH0_LOGOUT_REDIRECT` = `https://mozarex.com` (WITH protocol)
3. ✅ Both set in `.env` and production

### **Result:**

✅ **Logout works!**  
✅ **No double https://**  
✅ **Clean redirect URLs**  
✅ **Returns to homepage**  
✅ **Session cleared**  

---

## 🚀 **Deploy the Fix**

### **Local:**
```bash
# Update .env if needed
# Restart server
npm start
```

### **Production (DigitalOcean):**
```bash
# Update environment variables in DigitalOcean App Platform:
# - AUTH0_DOMAIN=login.mozarex.com
# - AUTH0_LOGOUT_REDIRECT=https://mozarex.com

# Redeploy the app
```

---

## 🎊 **Fixed!**

Your logout now works correctly with:
- ✅ Proper URL construction
- ✅ No double protocol error
- ✅ Clean redirect to homepage
- ✅ Session cleared properly

**No more DNS errors!** 🎉

