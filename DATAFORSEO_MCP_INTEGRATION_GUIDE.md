# 🔗 DataForSEO MCP Integration - Complete Setup Guide

## Overview

This project now includes comprehensive **Model Context Protocol (MCP)** integration with DataForSEO, providing direct access to professional SEO analysis tools without requiring expensive Labs subscriptions.

## 🎯 What is MCP?

**Model Context Protocol (MCP)** allows AI tools like Cursor to directly access DataForSEO's comprehensive SEO database. This integration provides:

- **Direct API Access**: No need for expensive DataForSEO Labs subscriptions
- **Real-time Data**: Access to live SEO metrics and analysis
- **Comprehensive Tools**: 20+ DataForSEO endpoints available
- **AI Integration**: Seamless integration with AI-powered analysis

## 🚀 Quick Start

### 1. Install DataForSEO MCP Server

```bash
npm install -g dataforseo-mcp-server
```

### 2. Configure MCP Settings

Update your `mcp.json` file with your DataForSEO credentials:

```json
{
  "mcpServers": {
    "dataforseo": {
      "command": "npx",
      "args": ["-y", "dataforseo-mcp-server"],
      "env": {
        "DATAFORSEO_USERNAME": "your_dataforseo_login",
        "DATAFORSEO_PASSWORD": "your_dataforseo_password"
      }
    }
  }
}
```

### 3. Start the Server

```bash
npm start
```

### 4. Access MCP Dashboard

Visit: `http://localhost:3000/dataforseo-mcp-dashboard`

## 📊 Available MCP Tools

### Keyword Analysis
- **Keyword Overview**: Search volume, competition, CPC, difficulty
- **Keyword Suggestions**: Related keywords and search terms
- **Keyword Ideas**: Content strategy keywords
- **Keyword Difficulty**: Ranking difficulty scores
- **Search Volume**: Monthly search volume data

### SERP Analysis
- **SERP Analysis**: Search results page analysis
- **Competitor Analysis**: Domain performance comparison
- **Domain Rank**: Authority and traffic metrics

### Backlink Analysis
- **Backlink Summary**: Total backlinks and referring domains
- **Detailed Backlinks**: Individual backlink analysis
- **Backlink Competitors**: Link building opportunities

### On-Page Analysis
- **Content Parsing**: Page structure and content analysis
- **Lighthouse Analysis**: Performance and SEO metrics
- **Instant Pages**: Quick page analysis

### Trends & Demographics
- **Google Trends**: Search trend data
- **Demographics**: Age and gender breakdowns
- **Content Analysis**: Citation and sentiment analysis

### Business Data
- **Business Listings**: Local business information
- **Location Data**: Geographic analysis

## 🔧 API Endpoints

### Core MCP Endpoints

```javascript
// Keyword Analysis
POST /api/dataforseo/mcp/keyword-overview
POST /api/dataforseo/mcp/keyword-suggestions
POST /api/dataforseo/mcp/keyword-ideas
POST /api/dataforseo/mcp/keyword-difficulty
POST /api/dataforseo/mcp/search-volume

// SERP Analysis
POST /api/dataforseo/mcp/serp-analysis
POST /api/dataforseo/mcp/competitor-analysis
POST /api/dataforseo/mcp/domain-rank

// Backlink Analysis
POST /api/dataforseo/mcp/backlink-analysis
POST /api/dataforseo/mcp/detailed-backlinks

// On-Page Analysis
POST /api/dataforseo/mcp/onpage-analysis
POST /api/dataforseo/mcp/lighthouse-analysis

// Trends & Content
POST /api/dataforseo/mcp/google-trends
POST /api/dataforseo/mcp/content-analysis

// Business Data
POST /api/dataforseo/mcp/business-listings

// Utility
GET /api/dataforseo/mcp/support-check
GET /api/dataforseo/mcp/available-tools
```

### Example API Usage

```javascript
// Get keyword overview
const response = await fetch('/api/dataforseo/mcp/keyword-overview', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    keywords: ['seo tools', 'digital marketing'],
    location: 'United States',
    language: 'en'
  })
});

const data = await response.json();
console.log(data.data.keywords);
```

## 🎨 Frontend Integration

### MCP Dashboard

The MCP dashboard (`/dataforseo-mcp-dashboard`) provides:

- **Real-time Analysis**: Live SEO data from DataForSEO
- **Interactive Tools**: Easy-to-use forms for each analysis type
- **Visual Results**: Charts, tables, and statistics
- **Comprehensive Reports**: Detailed analysis results

### Key Features

- **Status Monitoring**: Check MCP tool availability
- **Batch Analysis**: Analyze multiple keywords/domains
- **Export Results**: Download analysis data
- **Historical Tracking**: Compare results over time

## 🔍 Service Architecture

### MCP Services

1. **DataForSEOMCPService**: Basic MCP integration
2. **DataForSEOMCPIntegration**: Frontend MCP integration
3. **DataForSEOMCPDirectService**: Direct MCP tool access

### Service Features

- **Error Handling**: Comprehensive error management
- **Data Processing**: Structured data formatting
- **Caching**: Optional result caching
- **Rate Limiting**: API rate limit management

## 📈 Usage Examples

### Keyword Research

```javascript
// Get keyword suggestions
const suggestions = await dataforseoMCPDirectService.getKeywordSuggestions(
  'digital marketing',
  'United States',
  'en'
);

// Analyze keyword difficulty
const difficulty = await dataforseoMCPDirectService.getKeywordDifficulty(
  ['seo tools', 'marketing automation'],
  'United States',
  'en'
);
```

### Competitor Analysis

```javascript
// Analyze competitors
const competitors = await dataforseoMCPDirectService.getCompetitorAnalysis(
  'example.com',
  'United States',
  'en'
);

// Get domain rank
const domainRank = await dataforseoMCPDirectService.getDomainRankOverview(
  'example.com',
  'United States',
  'en'
);
```

### Comprehensive Website Analysis

```javascript
// Full website analysis
const analysis = await dataforseoMCPDirectService.analyzeWebsite(
  'https://example.com',
  {
    location: 'United States',
    language: 'en'
  }
);
```

## 🛠️ Configuration

### Environment Variables

```bash
# DataForSEO Credentials
DATAFORSEO_USERNAME=your_username
DATAFORSEO_PASSWORD=your_password

# Server Configuration
PORT=3000
NODE_ENV=development
```

### MCP Configuration

The `mcp.json` file configures the MCP server connection:

```json
{
  "mcpServers": {
    "dataforseo": {
      "command": "npx",
      "args": ["-y", "dataforseo-mcp-server"],
      "env": {
        "DATAFORSEO_USERNAME": "your_username",
        "DATAFORSEO_PASSWORD": "your_password"
      }
    }
  }
}
```

## 🔧 Troubleshooting

### Common Issues

1. **MCP Tools Not Available**
   - Check if `dataforseo-mcp-server` is installed globally
   - Verify credentials in `mcp.json`
   - Restart Cursor/IDE

2. **API Errors**
   - Check DataForSEO account status
   - Verify API limits and quotas
   - Check network connectivity

3. **Data Processing Errors**
   - Verify input parameters
   - Check data format requirements
   - Review error logs

### Debug Mode

Enable debug logging:

```javascript
// In your service
console.log('MCP Tool Response:', result);
```

## 📊 Performance Optimization

### Caching

Implement result caching for frequently requested data:

```javascript
const cache = new Map();

async function getCachedKeywordData(keywords) {
  const key = JSON.stringify(keywords);
  if (cache.has(key)) {
    return cache.get(key);
  }
  
  const result = await dataforseoMCPDirectService.getKeywordOverview(keywords);
  cache.set(key, result);
  return result;
}
```

### Rate Limiting

Implement rate limiting to avoid API limits:

```javascript
const rateLimiter = {
  requests: 0,
  lastReset: Date.now(),
  
  async checkLimit() {
    const now = Date.now();
    if (now - this.lastReset > 60000) { // Reset every minute
      this.requests = 0;
      this.lastReset = now;
    }
    
    if (this.requests >= 100) { // Max 100 requests per minute
      throw new Error('Rate limit exceeded');
    }
    
    this.requests++;
  }
};
```

## 🚀 Advanced Features

### Batch Processing

Process multiple requests efficiently:

```javascript
async function batchKeywordAnalysis(keywords) {
  const batches = chunkArray(keywords, 10); // Process 10 at a time
  const results = [];
  
  for (const batch of batches) {
    const batchResults = await Promise.allSettled(
      batch.map(keyword => 
        dataforseoMCPDirectService.getKeywordOverview([keyword])
      )
    );
    results.push(...batchResults);
  }
  
  return results;
}
```

### Real-time Monitoring

Monitor MCP tool status:

```javascript
async function monitorMCPSupport() {
  const support = dataforseoMCPDirectService.isMCPSupported();
  const tools = dataforseoMCPDirectService.getAvailableTools();
  
  return {
    supported: support,
    availableTools: tools.length,
    tools: tools.map(t => t.name)
  };
}
```

## 📚 Additional Resources

- [DataForSEO API Documentation](https://docs.dataforseo.com/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Cursor MCP Integration Guide](https://docs.cursor.com/)

## 🎉 Benefits

### Cost Savings
- No need for expensive DataForSEO Labs subscriptions
- Direct API access through MCP
- Reduced API call costs

### Enhanced Capabilities
- Real-time SEO analysis
- Comprehensive data coverage
- AI-powered insights

### Developer Experience
- Easy integration with existing tools
- Comprehensive error handling
- Detailed documentation

---

**Your DataForSEO MCP integration is ready to unlock the full power of professional SEO analysis!** 🎉✨

For support or questions, please refer to the troubleshooting section or check the service logs.


