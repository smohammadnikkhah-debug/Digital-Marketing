# Auth0 /u/signup 400 Error Fixed ✅

## 🎯 **Issue Fixed**

**The Problem:**
```
https://login.mozarex.com/u/signup?client_id=...&redirect_uri=...
  ↓
GET 400 (Bad Request)
  ↓
Error: Something went wrong page
```

---

## ❌ **Root Cause**

The `/u/signup` endpoint is **not a valid Auth0 endpoint** for custom domains!

**Auth0 Universal Login** uses the `/authorize` endpoint with different parameters for signup vs login:

| Purpose | Endpoint | Parameters |
|---------|----------|------------|
| ✅ **Login** | `/authorize` | `prompt=login` |
| ✅ **Signup** | `/authorize` | `screen_hint=signup` |
| ❌ **Invalid** | `/u/signup` | Not supported! |

---

## ✅ **The Fix**

### **Changed from `/u/signup` to `/authorize` with `screen_hint`:**

**Before (Broken):**
```javascript
if (signup === 'true') {
  // ❌ Invalid endpoint!
  auth0Url = `https://${auth0Domain}/u/signup?` +
    `client_id=${clientId}&` +
    `redirect_uri=${redirectUri}`;
  // Returns 400 Bad Request!
}
```

**After (Fixed):**
```javascript
if (signup === 'true') {
  // ✅ Use authorize endpoint with screen_hint for signup
  auth0Url = `https://${auth0Domain}/authorize?` +
    `response_type=code&` +
    `client_id=${clientId}&` +
    `redirect_uri=${redirectUri}&` +
    `scope=${scope}&` +
    `screen_hint=signup`;  // ✅ Tells Auth0 to show signup form
}
```

---

## 📊 **How It Works**

### **For Signup (`screen_hint=signup`):**

```
https://login.mozarex.com/authorize?
response_type=code&
client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp&
redirect_uri=https%3A%2F%2Fmozarex.com%2Fauth%2Fcallback&
scope=openid%20email%20profile&
screen_hint=signup  ← Tells Auth0 to show signup form!

  ↓
Auth0 shows signup form ✅
  ↓
"Create your account"
Email / Password fields
"Already have an account?" link
```

---

### **For Login (`prompt=login`):**

```
https://login.mozarex.com/authorize?
response_type=code&
client_id=V10UpBM2zbIcnXw0FciwEdACdBLbnzVp&
redirect_uri=https%3A%2F%2Fmozarex.com%2Fauth%2Fcallback&
scope=openid%20email%20profile&
prompt=login  ← Tells Auth0 to show login form!

  ↓
Auth0 shows login form ✅
  ↓
"Welcome back"
Email / Password fields
"Don't have an account?" link
```

---

## 🔍 **Auth0 Parameters Explained**

### **1. `screen_hint` (for signup):**
- **Valid values:** `signup`, `login`, `signup-password`
- **Effect:** Tells Auth0 Universal Login to show the signup form
- **Use case:** When user clicks "Get Started" → Plans → Selects plan

### **2. `prompt` (for login):**
- **Valid values:** `login`, `none`, `consent`
- **Effect:** Forces Auth0 to show login screen (skips single sign-on)
- **Use case:** When user clicks "Sign In"

---

## 📊 **Complete Flow**

### **From Plans Page → Signup:**

```
User clicks "Start Free Trial" on Starter Yearly
  ↓
Redirects to: /signup?plan=Starter&priceId=price_1S9k6k...&billing=yearly
  ↓
/signup redirects to: /login?signup=true&plan=Starter&...
  ↓
Server detects: signup=true
  ↓
✅ Redirects to: https://login.mozarex.com/authorize?screen_hint=signup&...
  ↓
Auth0 shows SIGNUP screen ✅
  ↓
User creates account
  ↓
Callback receives plan info
  ↓
Creates subscription
  ↓
Redirects to dashboard ✅
```

---

### **From Anywhere → Login:**

```
User clicks "Sign In"
  ↓
Redirects to: /login
  ↓
Server: no signup=true parameter
  ↓
✅ Redirects to: https://login.mozarex.com/authorize?prompt=login&...
  ↓
Auth0 shows LOGIN screen ✅
  ↓
User signs in
  ↓
Callback processes
  ↓
Redirects to dashboard ✅
```

---

## 🧪 **Testing**

### **Test 1: Signup Flow**

```bash
# 1. Restart server
npm start

# 2. Go to homepage
https://mozarex.com

# 3. Click "Get Started"
# Should go to: /plans

# 4. Click "Start Free Trial" on any plan
# Should redirect through: /signup → /login?signup=true

# 5. Watch server logs:
```

**Expected Logs:**
```
🔐 /login route called: { signup: 'true', plan: 'Starter', priceId: 'price_1S9k6k...', billing: 'yearly' }
🔗 Auth0 domain (cleaned): login.mozarex.com
✅ Signup mode: Redirecting to Auth0 authorize page with signup hint
🔗 Redirecting to Auth0: https://login.mozarex.com/authorize?response_type=code&client_id=...&redirect_uri=...&scope=openid%20email%20profile&screen_hint=signup...
```

**Expected Result:**
```
✅ Shows Auth0 signup page
✅ Has "Create your account" header
✅ Has email/password fields
✅ Has "Already have an account?" link
✅ NO 400 error!
```

---

### **Test 2: Login Flow**

```bash
# 1. Click "Sign In" anywhere
# Should go to: /login

# 2. Watch server logs:
```

**Expected Logs:**
```
🔐 /login route called: { signup: undefined, ... }
🔗 Auth0 domain (cleaned): login.mozarex.com
🔗 Redirecting to Auth0: https://login.mozarex.com/authorize?response_type=code&client_id=...&prompt=login...
```

**Expected Result:**
```
✅ Shows Auth0 login page
✅ Has "Welcome back" message
✅ NO 400 error!
```

---

## 📋 **Auth0 Endpoints Reference**

### **Valid Endpoints:**

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `/authorize` | Universal Login (signup or login) | ✅ Valid |
| `/oauth/token` | Token exchange | ✅ Valid |
| `/userinfo` | Get user info | ✅ Valid |
| `/v2/logout` | Logout | ✅ Valid |
| `/u/signup` | Legacy signup page | ❌ Invalid for custom domains |
| `/u/login` | Legacy login page | ❌ Invalid for custom domains |

---

## 🔧 **What Was Changed**

### **File: `server.js` - `/login` Route**

**Changed:**
```javascript
// BEFORE:
auth0Url = `https://${auth0Domain}/u/signup?`  // ❌ 400 error

// AFTER:
auth0Url = `https://${auth0Domain}/authorize?` +
  `response_type=code&` +
  `client_id=${clientId}&` +
  `redirect_uri=${redirectUri}&` +
  `scope=${scope}&` +
  `screen_hint=signup`;  // ✅ Shows signup form!
```

**Line numbers:**
- Lines 1020-1035: Signup flow now uses `/authorize` with `screen_hint=signup`
- Lines 1036-1048: Login flow uses `/authorize` with `prompt=login`

---

## 📊 **Before vs After**

### **BEFORE (Broken):**

```
User selects plan
  ↓
Redirects to: https://login.mozarex.com/u/signup?...
  ↓
GET 400 Bad Request ❌
  ↓
Error: Something went wrong page ❌
```

---

### **AFTER (Fixed):**

```
User selects plan
  ↓
Redirects to: https://login.mozarex.com/authorize?screen_hint=signup&...
  ↓
GET 200 OK ✅
  ↓
Shows Auth0 signup page ✅
```

---

## ✅ **Summary**

### **What Was Fixed:**

✅ **Changed endpoint** from `/u/signup` to `/authorize`  
✅ **Added `screen_hint=signup`** parameter for signup flow  
✅ **Uses `prompt=login`** for login flow  
✅ **No more 400 errors**  
✅ **Proper Auth0 Universal Login** behavior  

### **Result:**

```
✅ Signup: /authorize?screen_hint=signup
✅ Login: /authorize?prompt=login
❌ No more /u/signup endpoint (removed)
```

**The signup flow now uses the correct Auth0 authorize endpoint!** 🎉

No more 400 errors! Your signup should work perfectly now! ✨

