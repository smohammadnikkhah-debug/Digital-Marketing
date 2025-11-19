# 🔗 DataForSEO MCP Integration Setup Guide

## ✅ **Current Status**
Your DataForSEO MCP integration is **ready to configure**! 

## 🎯 **What is MCP?**
MCP (Model Context Protocol) allows AI tools like Cursor to directly access DataForSEO's comprehensive SEO database without requiring expensive Labs subscriptions.

## 🚀 **Setup Instructions**

### **Step 1: Update Your Credentials**

1. **Open the `mcp.json` file** in your project root
2. **Replace the placeholder values** with your actual DataForSEO credentials:

```json
{
  "mcpServers": {
    "dfs": {
      "command": "npx",
      "args": ["-y", "dataforseo-mcp-server"],
      "env": {
        "DATAFORSEO_USERNAME": "your_actual_login_here",
        "DATAFORSEO_PASSWORD": "your_actual_password_here"
      }
    }
  }
}
```

### **Step 2: Install DataForSEO MCP Server**

Run this command to install the DataForSEO MCP server:

```bash
npm install -g dataforseo-mcp-server
```

### **Step 3: Configure Cursor (if using Cursor IDE)**

1. **Open Cursor** and start a **New chat**
2. **Click the three dots (Settings)** in the chat window
3. **Select "Chat Settings"** → **"Tools & Integrations"** (or **"MCP Tools"** on Windows)
4. **Click "Add Custom MCP"**
5. **Copy the contents** of your `mcp.json` file into the configuration
6. **Save and close** the JSON file

### **Step 4: Test the Integration**

Once configured, you can use DataForSEO directly in Cursor with prompts like:

- "Get keyword data for 'sentius.com.au'"
- "Analyze backlinks for 'sentius.com.au'"
- "Get SERP data for 'SEO services'"
- "Find competitors for 'sentius.com.au'"

## 📊 **Available DataForSEO MCP Tools**

The MCP integration provides access to:

### **🔍 SERP Analysis**
- Google search results
- Featured snippets
- Local pack results
- Shopping results
- Knowledge panels

### **🔑 Keyword Research**
- Search volume data
- Keyword difficulty
- CPC data
- Related keywords
- Long-tail variations

### **🔗 Backlink Analysis**
- Domain authority
- Referring domains
- Link quality metrics
- Anchor text analysis
- Toxic link detection

### **🏢 Competitor Analysis**
- Top competitors
- Shared keywords
- Content gaps
- Ranking comparisons
- Market share analysis

### **📈 Domain Analytics**
- Traffic estimates
- Ranking keywords
- Organic visibility
- Click-through rates
- Performance trends

## 🎉 **Benefits of MCP Integration**

✅ **No Labs Subscription Required** - Access core DataForSEO data without expensive subscriptions
✅ **Real-time Data** - Fresh SEO insights directly in your AI environment
✅ **Comprehensive Analysis** - Full access to DataForSEO's database
✅ **AI-Powered Insights** - Combine DataForSEO data with AI analysis
✅ **Cost-Effective** - Use only the data you need

## 🔧 **Troubleshooting**

### **If MCP tools don't appear:**
- Check that `dataforseo-mcp-server` is installed globally
- Verify your credentials in `mcp.json`
- Restart Cursor after configuration

### **If you get authentication errors:**
- Double-check your DataForSEO username and password
- Ensure your DataForSEO account has sufficient credits
- Verify the credentials match your DataForSEO dashboard

### **If tools are limited:**
- Cursor supports up to 40 active MCP tools
- You can disable unused tools in the MCP settings
- Or specify `ENABLED_MODULES` in the configuration

## 💡 **Pro Tips**

1. **Start Simple**: Begin with basic keyword research
2. **Use Specific Prompts**: "Get top 10 keywords for 'sentius.com.au'"
3. **Combine with AI**: Ask for analysis and recommendations
4. **Monitor Usage**: Keep track of your DataForSEO API usage
5. **Explore Features**: Try different data types and endpoints

## 🎯 **Next Steps**

1. **Update your credentials** in `mcp.json`
2. **Install the MCP server** globally
3. **Configure Cursor** (if using Cursor IDE)
4. **Test with sentius.com.au** to verify the integration
5. **Start using real DataForSEO data** in your SEO analysis!

---

**Your DataForSEO MCP integration is ready to unlock the full power of professional SEO analysis!** 🎉✨

Just update your credentials and start getting real SEO data for `sentius.com.au` and any other website you want to analyze!
















