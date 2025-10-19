# Technical SEO AI - Troubleshooting Guide

## Error: "Failed to fetch AI recommendations"

This error occurs when the frontend cannot successfully retrieve AI recommendations from the backend. Here are the steps to diagnose and fix the issue:

---

## 🔍 Quick Diagnosis Steps

### 1. Check if the Server is Running
```bash
# Make sure the server is running on the correct port
# Look for this message in your terminal:
# "Server running on port 3000"
```

### 2. Check Browser Console
Open Developer Tools (F12) and look for:
- Network errors (404, 500, etc.)
- CORS errors
- Connection refused errors

### 3. Check Server Console
Look for error messages in your server terminal:
- `❌ No crawl data found for domain:`
- `❌ Technical SEO AI recommendations error:`

---

## 🛠️ Common Issues and Solutions

### Issue 1: No Domain Selected

**Symptoms:**
- Error message: "Failed to fetch AI recommendations"
- Console shows: `currentDomain: null` or `currentDomain: None selected`

**Solution:**
1. Go to the main dashboard: `/dashboard-mantis-v2`
2. Analyze a website using the URL input
3. Wait for the analysis to complete
4. Then navigate to `/technical-seo`

**Why it happens:** The Technical SEO page needs a domain to be stored in localStorage from a previous analysis.

---

### Issue 2: No Crawl Data Available

**Symptoms:**
- Server console shows: `❌ No crawl data found for domain: example.com`
- Frontend shows: "No crawl data found for this domain"

**Solution:**
1. Ensure the domain was successfully analyzed from the dashboard
2. Check Supabase database for the domain:
   ```bash
   node debug-technical-seo-ai.js your-domain.com
   ```
3. Re-analyze the website if needed

**Why it happens:** The domain hasn't been crawled yet, or the crawl data wasn't stored properly.

---

### Issue 3: Server Error (500)

**Symptoms:**
- HTTP 500 Internal Server Error
- Server console shows detailed error stack trace

**Solution:**
1. Check server logs for the exact error
2. Common causes:
   - OpenAI API error (check API key validity)
   - Supabase connection error (check credentials)
   - Invalid data structure in crawl data

**Debug command:**
```bash
node debug-technical-seo-ai.js your-domain.com
```

---

### Issue 4: OpenAI API Issues

**Symptoms:**
- Recommendations are generic/fallback only
- Server console: `⚠️ OpenAI API key not configured`

**Solution:**
1. Check `.env` file has valid OpenAI API key:
   ```env
   OPENAI_API_KEY=sk-your-actual-key-here
   OPENAI_MODEL=gpt-3.5-turbo
   ```
2. Restart the server after adding/updating the key
3. Verify API key is valid at: https://platform.openai.com/api-keys

**Note:** The system will work with fallback recommendations if OpenAI is not configured.

---

### Issue 5: CORS Errors

**Symptoms:**
- Browser console shows CORS policy error
- Frontend can't reach backend API

**Solution:**
Check that your server has CORS enabled (it should be by default in `server.js`):
```javascript
app.use(cors());
```

---

## 🧪 Testing & Debugging

### Run the Debug Script

Use the included debug script to test all components:

```bash
# Test with a specific domain
node debug-technical-seo-ai.js example.com

# The script will check:
# 1. Environment variables
# 2. Supabase connection
# 3. Crawl data availability
# 4. AI recommendations generation
```

**Expected Output:**
```
✅ All tests completed successfully!
📝 Summary:
   - Supabase connection: ✅ Working
   - Crawl data retrieval: ✅ Working
   - AI recommendations: ✅ Working
```

---

### Check Server Logs

With the enhanced logging, you should see:

**Successful Request:**
```
🤖 Technical SEO AI Recommendations Request: { domain: 'example.com', category: 'meta-optimization' }
📊 Fetching crawl data from Supabase...
✅ Crawl data retrieved: { domain: 'example.com', hasOnPage: true, pagesCount: 12 }
🏷️ Generating Meta Optimization recommendations...
📊 Pages available for meta analysis: 12
📊 Meta data extracted: { pages: 10 }
```

**Failed Request:**
```
❌ No crawl data found for domain: example.com
```

---

## 🔧 Step-by-Step Fix Guide

### If Nothing is Working:

1. **Restart the Server**
   ```bash
   # Stop the server (Ctrl+C)
   # Start it again
   npm start
   ```

2. **Clear Browser Cache**
   - Open DevTools (F12)
   - Right-click refresh button → "Empty Cache and Hard Reload"

3. **Verify Environment Variables**
   ```bash
   # Check your .env file exists and has:
   SUPABASE_URL=your-url
   SUPABASE_SERVICE_ROLE_KEY=your-key
   OPENAI_API_KEY=sk-your-key  # Optional but recommended
   ```

4. **Test with a Fresh Domain**
   - Go to `/dashboard-mantis-v2`
   - Analyze a new website
   - Wait for completion
   - Go to `/technical-seo`

5. **Run Debug Script**
   ```bash
   node debug-technical-seo-ai.js your-domain.com
   ```

6. **Check Database**
   - Log into Supabase dashboard
   - Check `analysis` table for your domain
   - Ensure `onPage.pages` array has data

---

## 📊 Understanding the Data Flow

```
1. User analyzes domain from dashboard
   ↓
2. Website crawl data saved to Supabase
   ↓
3. User navigates to /technical-seo
   ↓
4. Frontend loads domain from localStorage
   ↓
5. Frontend requests AI recommendations
   ↓
6. Backend fetches crawl data from Supabase
   ↓
7. Backend sends data to OpenAI (or uses fallback)
   ↓
8. AI generates recommendations
   ↓
9. Frontend displays recommendations
```

**Break points to check:**
- Step 2: Is data in Supabase? → Check database
- Step 4: Is domain in localStorage? → Check browser console
- Step 6: Can backend fetch data? → Check server logs
- Step 8: Can AI generate? → Check OpenAI API status

---

## 🚨 Critical Checklist

Before using Technical SEO AI, ensure:

- [ ] Server is running (`npm start`)
- [ ] `.env` file has Supabase credentials
- [ ] At least one domain has been analyzed
- [ ] Browser has localStorage enabled
- [ ] No browser extensions blocking requests
- [ ] CORS is enabled on server
- [ ] Port 3000 is available and accessible

---

## 💡 Pro Tips

1. **Use the Debug Script First**
   - Run `node debug-technical-seo-ai.js` before reporting issues
   - It will tell you exactly what's wrong

2. **Check Multiple Browsers**
   - Try Chrome, Firefox, or Edge
   - Incognito mode can help identify extension issues

3. **Monitor Both Consoles**
   - Keep browser DevTools open
   - Keep server terminal visible
   - Match errors between frontend and backend

4. **Start Fresh**
   - Clear localStorage: `localStorage.clear()` in browser console
   - Restart server
   - Analyze a new domain
   - Try again

---

## 📞 Still Having Issues?

If you've tried all the above and still have problems:

1. **Collect Information:**
   - Browser console errors (screenshot)
   - Server console errors (copy text)
   - Output from debug script
   - Domain you're trying to analyze

2. **Check These Files:**
   - `server.js` - API endpoint (lines 4747-4837)
   - `services/technicalSEOAIService.js` - AI service
   - `frontend/technical-seo-dashboard.html` - Frontend code

3. **Verify Installation:**
   ```bash
   # Make sure dependencies are installed
   npm install
   
   # Check if OpenAI package is installed
   npm list openai
   ```

---

## ✅ Success Indicators

You'll know everything is working when you see:

**Frontend:**
- Submenu tabs are visible
- Loading spinner appears briefly
- AI recommendations load with scores, issues, and suggestions
- Different categories show different recommendations

**Server Console:**
```
🤖 Generating AI recommendations for example.com, category: meta-optimization
✅ Crawl data retrieved: { domain: 'example.com', hasOnPage: true, pagesCount: 12 }
🏷️ Generating Meta Optimization recommendations...
✅ Meta recommendations generated!
```

**Browser Console:**
```
✅ Loading technical SEO for domain: example.com
🤖 Loading AI recommendations for meta-optimization on domain: example.com
✅ AI recommendations loaded: { success: true, score: 85, ... }
```

---

## 🎯 Quick Reference

| Error | Solution |
|-------|----------|
| "No domain selected" | Analyze a domain from dashboard first |
| "No crawl data found" | Re-analyze the website |
| "Failed to fetch" | Check server is running |
| "500 Internal Error" | Check server logs for details |
| Generic recommendations | OpenAI API key not configured (optional) |

---

## 🔄 Emergency Reset

If absolutely nothing works:

```bash
# 1. Stop server
Ctrl+C

# 2. Clear browser data
# Open DevTools → Application → Clear Storage → Clear Site Data

# 3. Restart server
npm start

# 4. Test with debug script
node debug-technical-seo-ai.js example.com

# 5. If debug script passes, try the UI again
```

---

Remember: The system has **fallback recommendations** built-in, so even without OpenAI, you should get helpful suggestions! 🎉

