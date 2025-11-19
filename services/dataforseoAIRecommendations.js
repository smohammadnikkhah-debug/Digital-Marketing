const OpenAI = require('openai');

class DataForSEOAIRecommendations {
  constructor() {
    this.openai = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });
    
    if (process.env.OPENAI_API_KEY && !process.env.OPENAI_API_KEY.includes('your_')) {
      console.log('✅ DataForSEO AI Recommendations initialized successfully');
    } else {
      console.log('⚠️ OpenAI API key not configured for DataForSEO AI recommendations');
    }
  }

  // Generate AI recommendations for On-Page SEO
  async generateOnPageRecommendations(onPageData) {
    try {
      if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY.includes('your_')) {
        return this.getFallbackOnPageRecommendations(onPageData);
      }

      const prompt = `As an expert SEO consultant, analyze the following on-page SEO data and provide specific, actionable recommendations:

ON-PAGE SEO DATA:
- Title: ${onPageData.title || 'Not found'}
- Meta Description: ${onPageData.metaDescription || 'Not found'}
- H1 Tags: ${JSON.stringify(onPageData.h1Tags || [])}
- H2 Tags: ${JSON.stringify(onPageData.h2Tags || [])}
- Images without alt text: ${onPageData.images?.missingAlt || 0}
- Total images: ${onPageData.images?.total || 0}
- Internal links: ${onPageData.links?.internal || 0}
- External links: ${onPageData.links?.external || 0}
- Page load time: ${onPageData.performance?.loadTime || 'Unknown'}
- Word count: ${onPageData.content?.wordCount || 'Unknown'}
- Schema markup: ${onPageData.schema || 'None detected'}

Provide a structured response with:
1. **CRITICAL ISSUES** (must fix immediately)
2. **OPTIMIZATION OPPORTUNITIES** (quick wins)
3. **CONTENT IMPROVEMENTS** (enhance content)
4. **TECHNICAL RECOMMENDATIONS** (advanced fixes)
5. **PRIORITY ACTION PLAN** (step-by-step)

Be specific with examples and actionable steps. Focus on what will have the biggest impact on rankings.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1000,
        temperature: 0.7
      });

      return {
        success: true,
        recommendations: response.choices[0].message.content,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('OpenAI On-Page recommendations error:', error.message);
      return this.getFallbackOnPageRecommendations(onPageData);
    }
  }

  // Generate AI recommendations for Keyword Analysis
  async generateKeywordRecommendations(keywordsData) {
    try {
      if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY.includes('your_')) {
        return this.getFallbackKeywordRecommendations(keywordsData);
      }

      const topKeywords = keywordsData.keywords?.slice(0, 10) || [];
      const keywordList = topKeywords.map(k => `${k.keyword} (Position: ${k.position}, Volume: ${k.searchVolume})`).join('\n');

      const prompt = `As an expert SEO strategist, analyze these keyword data and provide strategic recommendations:

KEYWORD DATA:
Top Keywords:
${keywordList}

Keyword Density Analysis:
${JSON.stringify(keywordsData.keywordDensity || {})}

Total Keywords Found: ${keywordsData.totalKeywords || 0}

Provide a comprehensive keyword strategy with:
1. **KEYWORD GAPS** (missing opportunities)
2. **RANKING IMPROVEMENTS** (how to climb SERPs)
3. **LONG-TAIL OPPORTUNITIES** (specific phrases to target)
4. **CONTENT STRATEGY** (what content to create)
5. **COMPETITIVE ANALYSIS** (how to outrank competitors)
6. **IMPLEMENTATION ROADMAP** (step-by-step plan)

Focus on actionable strategies that will drive organic traffic growth. Include specific keyword suggestions and content ideas.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1200,
        temperature: 0.7
      });

      return {
        success: true,
        recommendations: response.choices[0].message.content,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('OpenAI Keyword recommendations error:', error.message);
      return this.getFallbackKeywordRecommendations(keywordsData);
    }
  }

  // Generate AI recommendations for Competitor Analysis
  async generateCompetitorRecommendations(competitorsData) {
    try {
      if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY.includes('your_')) {
        return this.getFallbackCompetitorRecommendations(competitorsData);
      }

      const competitors = competitorsData.competitors?.slice(0, 5) || [];
      const competitorList = competitors.map(c => `${c.domain} (Common Keywords: ${c.commonKeywords}, Domain Rating: ${c.domainRating}, Traffic: ${c.organicTraffic})`).join('\n');

      const prompt = `As a competitive intelligence expert, analyze this competitor data and provide strategic recommendations:

COMPETITOR DATA:
Top Competitors:
${competitorList}

Total Competitors Found: ${competitorsData.competitors?.length || 0}

Provide a competitive strategy with:
1. **COMPETITIVE GAPS** (opportunities competitors miss)
2. **WEAK COMPETITORS** (easier targets to outrank)
3. **CONTENT OPPORTUNITIES** (content gaps to exploit)
4. **LINK BUILDING STRATEGY** (how to compete for backlinks)
5. **TECHNICAL ADVANTAGES** (technical SEO opportunities)
6. **MARKET POSITIONING** (how to differentiate)

Focus on actionable strategies to gain competitive advantage. Include specific tactics and implementation steps.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1200,
        temperature: 0.7
      });

      return {
        success: true,
        recommendations: response.choices[0].message.content,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('OpenAI Competitor recommendations error:', error.message);
      return this.getFallbackCompetitorRecommendations(competitorsData);
    }
  }

  // Generate AI recommendations for Backlinks Analysis
  async generateBacklinkRecommendations(backlinksData) {
    try {
      if (!process.env.OPENAI_API_KEY || process.env.OPENAI_API_KEY.includes('your_')) {
        return this.getFallbackBacklinkRecommendations(backlinksData);
      }

      const topBacklinks = backlinksData.topBacklinks?.slice(0, 10) || [];
      const backlinkList = topBacklinks.map(b => `${b.domain} (DA: ${b.domainAuthority}, Links: ${b.linkCount})`).join('\n');

      const prompt = `As a link building expert, analyze this backlink data and provide strategic recommendations:

BACKLINK DATA:
Total Backlinks: ${backlinksData.totalBacklinks || 0}
Domain Authority: ${backlinksData.domainAuthority || 'Unknown'}
Referring Domains: ${backlinksData.referringDomains || 0}

Top Backlink Sources:
${backlinkList}

Link Quality Distribution:
- High Authority (DA 70+): ${backlinksData.qualityDistribution?.high || 0}
- Medium Authority (DA 30-69): ${backlinksData.qualityDistribution?.medium || 0}
- Low Authority (DA <30): ${backlinksData.qualityDistribution?.low || 0}

Provide a comprehensive link building strategy with:
1. **LINK QUALITY AUDIT** (current link profile assessment)
2. **LINK OPPORTUNITIES** (specific sites to target)
3. **CONTENT FOR LINKING** (linkable assets to create)
4. **OUTREACH STRATEGY** (how to acquire quality links)
5. **RISK MITIGATION** (avoiding penalties)
6. **MEASUREMENT PLAN** (tracking link building success)

Focus on white-hat strategies that will improve domain authority and rankings.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1200,
        temperature: 0.7
      });

      return {
        success: true,
        recommendations: response.choices[0].message.content,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('OpenAI Backlink recommendations error:', error.message);
      return this.getFallbackBacklinkRecommendations(backlinksData);
    }
  }

  // Fallback recommendations when OpenAI is not available
  getFallbackOnPageRecommendations(onPageData) {
    const issues = [];
    const recommendations = [];

    // Title analysis
    if (!onPageData.title) {
      issues.push("❌ **CRITICAL**: No title tag found");
      recommendations.push("Add a compelling title tag (50-60 characters) with your primary keyword");
    } else if (onPageData.title.length > 60) {
      issues.push("⚠️ **OPTIMIZATION**: Title tag too long");
      recommendations.push("Shorten title to 50-60 characters for better SERP display");
    }

    // Meta description analysis
    if (!onPageData.metaDescription) {
      issues.push("❌ **CRITICAL**: No meta description");
      recommendations.push("Add a compelling meta description (150-160 characters) with call-to-action");
    } else if (onPageData.metaDescription.length > 160) {
      issues.push("⚠️ **OPTIMIZATION**: Meta description too long");
      recommendations.push("Shorten meta description to 150-160 characters");
    }

    // Images analysis
    const missingAlt = onPageData.images?.missingAlt || 0;
    if (missingAlt > 0) {
      issues.push(`⚠️ **OPTIMIZATION**: ${missingAlt} images missing alt text`);
      recommendations.push("Add descriptive alt text to all images for better accessibility and SEO");
    }

    // Content analysis
    const wordCount = onPageData.content?.wordCount || 0;
    if (wordCount < 300) {
      issues.push("⚠️ **CONTENT**: Page content too thin");
      recommendations.push("Increase content length to 300+ words with valuable, relevant information");
    }

    // Performance analysis
    const loadTime = onPageData.performance?.loadTime;
    if (loadTime && loadTime > 3) {
      issues.push("⚠️ **PERFORMANCE**: Slow page load time");
      recommendations.push("Optimize images, enable compression, and minimize HTTP requests");
    }

    return {
      success: true,
      recommendations: `
# 🚨 **IMMEDIATE ACTION PLAN**

## **Critical Issues Found:**
${issues.join('\n')}

## **Quick Wins:**
${recommendations.join('\n')}

## **Next Steps:**
1. Fix critical issues first
2. Optimize title and meta description
3. Add alt text to images
4. Improve content quality and length
5. Optimize page speed

**Priority**: Focus on user experience and technical SEO fundamentals for maximum impact.
      `,
      timestamp: new Date().toISOString()
    };
  }

  getFallbackKeywordRecommendations(keywordsData) {
    const totalKeywords = keywordsData.totalKeywords || 0;
    const topKeywords = keywordsData.keywords?.slice(0, 5) || [];

    return {
      success: true,
      recommendations: `
# 🎯 **KEYWORD STRATEGY PLAN**

## **Current Status:**
- Total Keywords: ${totalKeywords}
- Top Performing Keywords: ${topKeywords.map(k => k.keyword).join(', ')}

## **Strategic Recommendations:**

### **1. KEYWORD GAPS**
- Research long-tail keywords with lower competition
- Target question-based keywords (How to, What is, Why does)
- Focus on local keywords if applicable

### **2. CONTENT OPTIMIZATION**
- Create comprehensive content around top keywords
- Use semantic keywords and LSI terms
- Develop topic clusters for better authority

### **3. RANKING IMPROVEMENTS**
- Optimize on-page elements for target keywords
- Build quality backlinks to high-potential pages
- Improve user engagement metrics

### **4. COMPETITIVE ANALYSIS**
- Monitor competitor keyword strategies
- Identify content gaps in competitor sites
- Target keywords where competitors are weak

## **Implementation Priority:**
1. **Week 1**: Fix on-page optimization
2. **Week 2**: Create keyword-rich content
3. **Week 3**: Build quality backlinks
4. **Week 4**: Monitor and adjust strategy

**Focus**: Target 5-10 high-value keywords with realistic ranking potential.
      `,
      timestamp: new Date().toISOString()
    };
  }

  getFallbackCompetitorRecommendations(competitorsData) {
    const competitors = competitorsData.competitors?.slice(0, 3) || [];

    return {
      success: true,
      recommendations: `
# 🏆 **COMPETITIVE STRATEGY**

## **Top Competitors Identified:**
${competitors.map(c => `- ${c.domain} (${c.commonKeywords} shared keywords)`).join('\n')}

## **Competitive Opportunities:**

### **1. CONTENT GAPS**
- Analyze competitor content and find missing topics
- Create better, more comprehensive content
- Target underserved keyword niches

### **2. TECHNICAL ADVANTAGES**
- Improve page speed (many competitors have slow sites)
- Enhance mobile experience
- Implement better site architecture

### **3. LINK BUILDING**
- Identify where competitors get their backlinks
- Create superior content for link acquisition
- Target high-authority sites in your niche

### **4. USER EXPERIENCE**
- Provide better user experience than competitors
- Improve site navigation and usability
- Add interactive elements and tools

## **Action Plan:**
1. **Audit** competitor strengths and weaknesses
2. **Identify** content and keyword gaps
3. **Create** superior content and user experience
4. **Build** relationships for link acquisition
5. **Monitor** competitive landscape regularly

**Goal**: Outrank competitors by providing superior value and user experience.
      `,
      timestamp: new Date().toISOString()
    };
  }

  getFallbackBacklinkRecommendations(backlinksData) {
    const totalBacklinks = backlinksData.totalBacklinks || 0;
    const referringDomains = backlinksData.referringDomains || 0;

    return {
      success: true,
      recommendations: `
# 🔗 **LINK BUILDING STRATEGY**

## **Current Backlink Profile:**
- Total Backlinks: ${totalBacklinks}
- Referring Domains: ${referringDomains}
- Domain Authority: ${backlinksData.domainAuthority || 'Unknown'}

## **Link Building Opportunities:**

### **1. QUALITY OVER QUANTITY**
- Focus on high-authority, relevant domains
- Avoid low-quality link farms and directories
- Prioritize editorial links over paid placements

### **2. CONTENT FOR LINKING**
- Create linkable assets (guides, tools, studies)
- Develop industry reports and surveys
- Build useful resources and calculators

### **3. OUTREACH STRATEGY**
- Identify websites linking to competitors
- Create personalized outreach campaigns
- Offer value in exchange for links

### **4. RELATIONSHIP BUILDING**
- Network with industry influencers
- Participate in relevant communities
- Guest post on quality sites

## **Implementation Steps:**
1. **Audit** current backlink profile
2. **Create** high-value content assets
3. **Identify** link opportunities
4. **Execute** outreach campaigns
5. **Monitor** and maintain relationships

**Focus**: Build 10-20 high-quality backlinks per month for sustainable growth.
      `,
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = new DataForSEOAIRecommendations();
















