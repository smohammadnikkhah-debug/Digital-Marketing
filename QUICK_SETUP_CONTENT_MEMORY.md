# Quick Setup: Content Memory Table

## 🎯 **One-Time Setup Required**

You need to create the `content_memory` table in Supabase.

---

## 📋 **Option 1: Manual Setup (Recommended - 2 minutes)**

### **Step 1: Go to Supabase SQL Editor**
```
https://supabase.com/dashboard/project/YOUR_PROJECT/sql/new
```

### **Step 2: Copy & Paste This SQL**

```sql
-- Content Memory Table
CREATE TABLE IF NOT EXISTS content_memory (
    id SERIAL PRIMARY KEY,
    website_id UUID REFERENCES websites(id) ON DELETE CASCADE,
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_content_memory_website_id ON content_memory(website_id);
CREATE INDEX IF NOT EXISTS idx_content_memory_keyword ON content_memory(keyword);
CREATE INDEX IF NOT EXISTS idx_content_memory_content_type ON content_memory(content_type);
CREATE INDEX IF NOT EXISTS idx_content_memory_target_date ON content_memory(target_date);
CREATE INDEX IF NOT EXISTS idx_content_memory_content_hash ON content_memory(content_hash);

-- Unique constraint to prevent exact duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_content_memory_unique 
ON content_memory(website_id, content_hash);
```

### **Step 3: Click "Run"**

### **Step 4: Verify**
- Go to "Table Editor" in Supabase
- You should see `content_memory` table
- Initial rows: 0

---

## 🔧 **Option 2: Run Script (Alternative)**

```bash
node create-content-memory-table.js
```

If it works:
```
✅ Content memory table created successfully!
```

If it doesn't auto-create, follow Option 1 above.

---

## ✅ **After Setup**

```bash
# Restart your server
npm start

# Test it
# Go to: http://localhost:3000/seo-tools-content-calendar
# Generate content
# Should see: "✅ Content stored in memory"
```

---

## 🎊 **What You Get**

✅ **No more errors** - "table not found" fixed  
✅ **Duplicate prevention** - Never generate same content twice  
✅ **Content caching** - Skip ChatGPT for existing topics  
✅ **Cost savings** - Fewer API calls to OpenAI  
✅ **Faster generation** - Cached content loads instantly  

---

## 📊 **Verification**

After generating content, check Supabase:

```sql
SELECT * FROM content_memory WHERE website_id = YOUR_WEBSITE_ID;
```

You should see rows like:
```
id | website_id | content_type | keyword      | topic
---+------------+--------------+--------------+---------------------------
1  | 123        | blog         | web design   | Complete Web Design Guide
2  | 123        | twitter      | web design   | Check out our portfolio
3  | 123        | instagram    | inspiration  | Behind the scenes
```

**✅ Done!** Your content calendar now stores and reuses content!

