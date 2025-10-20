# AI Content Calendar - Quick Start Guide ⚡

## 🚀 **Get Started in 3 Steps**

### **Step 1: Create Database Table** (1 minute)

```bash
# Open Supabase SQL Editor and run:
```

```sql
-- Copy and paste from: create-content-memory-table.sql
-- Or run this directly:

CREATE TABLE IF NOT EXISTS content_memory (
    id SERIAL PRIMARY KEY,
    website_id INTEGER REFERENCES websites(id) ON DELETE CASCADE,
    content_type VARCHAR(50) NOT NULL,
    keyword VARCHAR(255),
    topic VARCHAR(500) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    full_content TEXT,
    metadata JSONB,
    target_date DATE,
    status VARCHAR(50) DEFAULT 'draft',
    generated_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_content_memory_website_id ON content_memory(website_id);
CREATE INDEX idx_content_memory_keyword ON content_memory(keyword);
CREATE INDEX idx_content_memory_content_hash ON content_memory(content_hash);
CREATE UNIQUE INDEX idx_content_memory_unique ON content_memory(website_id, content_hash);
```

### **Step 2: Restart Server** (10 seconds)

```bash
# Stop server (Ctrl+C)
npm start
```

### **Step 3: Generate Content** (90 seconds)

1. Go to: `http://localhost:3000/seo-tools-content-calendar`
2. Wait for AI to analyze and generate (~60-90 seconds)
3. See your calendar filled with content! 🎉

---

## 🎯 **What You Get**

### **Automatic Content Generation:**

✅ **Blogs:** SEO-optimized, 800-1200 words each  
✅ **Twitter:** Engaging tweets with hashtags  
✅ **Instagram:** Visual captions with image suggestions  
✅ **TikTok:** Video scripts with hooks  

### **Smart Features:**

✅ **Personalized:** Based on YOUR website data  
✅ **No Duplicates:** Tracks all generated content  
✅ **Plan Limits:** Respects free/starter/pro limits  
✅ **Keyword-Rich:** Uses your actual ranked keywords  

---

## 📊 **Plan Limits**

| Plan | Blogs/Month | Social Posts/Month |
|------|-------------|-------------------|
| **Free** | 2 | 10 |
| **Starter** | 10 | 50 |
| **Professional** | 50 | 200 |
| **Enterprise** | Unlimited | Unlimited |

---

## 🤖 **How AI Generates Content**

### **Step 1: Analyze Your Website**
```
AI scans:
- Your page titles
- H1 and H2 headings
- Meta descriptions
- Ranked keywords
- Domain name

Extracts:
- Main keywords
- Your services/products
- Business type
- Target audience
```

### **Step 2: Generate Content**
```
For each blog:
  → Uses extracted keyword
  → Avoids used topics
  → Creates 800-1200 word post
  → SEO-optimized structure
  → Matching social posts

Stores in database to prevent duplication
```

### **Step 3: Display in Calendar**
```
Calendar shows:
  → Blogs (purple)
  → Twitter (blue)
  → Instagram (pink)
  → TikTok (black)

Click to view full content
```

---

## 📱 **Example Generated Content**

### **For "ethanzargo.com":**

**Blog:**
```
Title: "Professional Web Design: The Complete 2024 Guide"
Content: 1,100 words with H2 headings, actionable tips
Keywords: web design, professional websites, UX design
Read Time: 7 minutes
SEO Score: 88/100
```

**Twitter:**
```
🎨 Want a website that converts? Our latest guide reveals
5 web design secrets used by top brands! 

#WebDesign #UXDesign
```

**Instagram:**
```
✨ Your website is your digital storefront! Make it count 
with these professional design tips 👇

[Image: Modern website design showcase]
#WebDesign #DigitalMarketing #UXDesign #WebDevelopment
```

**TikTok:**
```
Hook: "Your website is costing you clients... here's why"

Scene 1: Show bad website example (3 sec)
Scene 2: Reveal the problem (5 sec)
Scene 3: Show the solution (7 sec)
CTA: "Follow for web design tips!"

#WebDesign #BusinessTips
```

---

## ✅ **Verification Checklist**

After setup, verify:

- [ ] content_memory table exists in Supabase
- [ ] Server restarted successfully
- [ ] Content Calendar page loads
- [ ] AI generation starts automatically
- [ ] Status shows: "✅ Generated X blogs and Y social posts!"
- [ ] Calendar grid shows content dots
- [ ] Click day to see content details
- [ ] Plan limits displayed correctly
- [ ] No duplicate topics in database

---

## 🚨 **Quick Fixes**

### **"Authentication required"**
→ Make sure you're logged in

### **"Website not found"**
→ Go to dashboard and analyze your website first

### **"Content limit reached"**
→ You've used all content for this month (upgrade plan or wait for next month)

### **"No content generated"**
→ Check server logs for specific error
→ Verify OpenAI API key is set
→ Check crawl data exists

---

## 💡 **Pro Tips**

### **Optimize Content Generation:**

1. **Analyze Website First:**
   - More crawl data = Better content
   - Keywords → More targeted content
   - Competitors → More competitive content

2. **Use Professional Plan:**
   - More blogs = More SEO value
   - More social = More engagement
   - Higher limits = More flexibility

3. **Review & Edit:**
   - AI content is good, but review it
   - Add your unique insights
   - Personalize with examples
   - Adjust tone if needed

4. **Track Performance:**
   - Mark content as "published"
   - Track engagement per platform
   - See which topics perform best
   - Use data for future content

---

## 📈 **Expected Timeline**

### **Initial Setup:**
```
Create table:     1 minute
Restart server:   10 seconds
Total:            1 minute 10 seconds
```

### **First Generation:**
```
Load page:        2 seconds
AI analyze:       10 seconds
Generate content: 60-90 seconds
Display:          2 seconds
Total:            ~2 minutes
```

### **Subsequent Months:**
```
Same as first generation
But AI knows what topics were used
Generates fresh, unique content
```

---

## 🎊 **What Makes This Special**

### **Compared to Other Tools:**

**Typical Content Tools:**
- ❌ Generic templates
- ❌ No business context
- ❌ Manual keyword entry
- ❌ No duplication check
- ❌ Single platform

**Mozarex AI Content Calendar:**
- ✅ Analyzes YOUR website
- ✅ Uses YOUR keywords
- ✅ Matches YOUR business
- ✅ Prevents duplicates automatically
- ✅ Generates for 4 platforms simultaneously
- ✅ Respects plan limits
- ✅ Stores for future reference

---

## 🔄 **Monthly Workflow**

### **January:**
```
1. Generate content → 10 blogs + 50 social posts
2. Review and schedule
3. Publish throughout month
4. Track engagement
```

### **February:**
```
1. Generate content → NEW topics (AI avoids January topics)
2. Review and schedule
3. Publish throughout month
4. Track engagement
```

### **Ongoing:**
```
✅ Always fresh topics
✅ Never repeat content
✅ Consistent posting schedule
✅ SEO-optimized blogs
✅ Engaging social posts
```

---

## 📞 **Need Help?**

### **Check Server Logs:**
```
Look for:
✅ "👤 Customer ID from session: X" (not null)
✅ "✅ Website found: { id: X }"
✅ "🔍 Extracting keywords..."
✅ "✅ Generated X content items"
```

### **Check Browser Console:**
```
Look for:
✅ "🤖 Generating AI content calendar"
✅ "✅ AI content calendar generated"
✅ Calendar renders with content
```

### **Check Database:**
```sql
-- Verify content was stored:
SELECT * FROM content_memory 
WHERE website_id = YOUR_WEBSITE_ID
ORDER BY created_at DESC
LIMIT 10;
```

---

## 🎯 **Quick Checklist**

Before contacting support, verify:

- [ ] content_memory table created in Supabase
- [ ] Server restarted after creating table
- [ ] User is logged in (customer_id not null)
- [ ] Website analyzed and in database
- [ ] OpenAI API key configured (optional but recommended)
- [ ] Plan limits not exceeded
- [ ] Browser console shows no errors
- [ ] Server logs show generation progress

---

## 🎉 **You're Ready!**

Everything is set up and ready to use. The AI Content Calendar will:

1. **Analyze** your website data
2. **Extract** keywords and services
3. **Generate** personalized content
4. **Prevent** duplicates
5. **Display** in beautiful calendar
6. **Track** all generated content

**Just visit the Content Calendar page and watch the magic happen!** ✨

---

**Implementation Status:** ✅ **COMPLETE**

All features implemented:
- ✅ AI keyword extraction
- ✅ Multi-platform content generation
- ✅ Duplicate prevention
- ✅ Plan limit enforcement
- ✅ Content memory system
- ✅ Calendar display

**Time to generate your first month of content!** 🚀

