const OpenAI = require('openai');
const boostrampService = require('./boostrampService');

class SEOResponseService {
  constructor() {
    this.apiKey = process.env.OPENAI_API_KEY;
    this.openai = null;
    this.conversationHistory = new Map(); // Store chat history per user

    // Initialize OpenAI only if API key is available
    if (this.apiKey && this.apiKey !== 'your_openai_api_key_here' && this.apiKey.startsWith('sk-')) {
      try {
        this.openai = new OpenAI({
          apiKey: this.apiKey
        });
        console.log('✅ OpenAI API initialized successfully for SEO responses');
      } catch (error) {
        console.error('❌ Failed to initialize OpenAI API:', error.message);
        this.openai = null;
      }
    } else {
      console.log('⚠️ OpenAI API key not configured. SEO responses will be limited.');
    }
  }

  // Process customer request and generate SEO response using Boostramp data
  async processCustomerRequest(userId, request, websiteUrl = null) {
    try {
      console.log(`🔍 Processing customer request: "${request}" for website: ${websiteUrl || 'N/A'}`);

      // Step 1: Analyze website if URL provided
      let websiteAnalysis = null;
      if (websiteUrl) {
        try {
          websiteAnalysis = await boostrampService.scrapeWebsite(websiteUrl);
          console.log('✅ Website analysis completed');
        } catch (error) {
          console.warn('⚠️ Website analysis failed:', error.message);
        }
      }

      // Step 2: Generate intelligent response using OpenAI + Boostramp data
      const response = await this.generateIntelligentResponse(request, websiteAnalysis, userId);

      return {
        success: true,
        response: response,
        websiteData: websiteAnalysis,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Error processing customer request:', error.message);
      return {
        success: false,
        response: 'Sorry, I encountered an error processing your request. Please try again.',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  // Generate intelligent SEO response using OpenAI and Boostramp data
  async generateIntelligentResponse(request, websiteAnalysis, userId) {
    try {
      // Check if OpenAI is available
      if (!this.openai) {
        return this.generateFallbackResponse(request, websiteAnalysis);
      }

      // Get conversation history
      const history = await this.initializeChat(userId);
      
      // Create context-aware prompt
      let contextPrompt = `You are an expert SEO consultant with access to comprehensive website analysis data. 
      
Customer Request: "${request}"

`;

      // Add website analysis data if available
      if (websiteAnalysis) {
        contextPrompt += `Website Analysis Data:
- URL: ${websiteAnalysis.url || 'Not provided'}
- Title: ${websiteAnalysis.title || 'Missing'}
- Meta Description: ${websiteAnalysis.metaDescription || 'Missing'}
- Word Count: ${websiteAnalysis.content?.wordCount || 0}
- H1 Tags: ${websiteAnalysis.headings?.h1 || 0}
- H2 Tags: ${websiteAnalysis.headings?.h2 || 0}
- Images: ${websiteAnalysis.images?.total || 0} (${websiteAnalysis.images?.missingAlt || 0} missing alt text)
- Internal Links: ${websiteAnalysis.links?.internal || 0}
- External Links: ${websiteAnalysis.links?.external || 0}
- Load Time: ${websiteAnalysis.performance?.loadTime || 'Unknown'}
- SSL Certificate: ${websiteAnalysis.technical?.sslCertificate ? 'Yes' : 'No'}
- Mobile Friendly: ${websiteAnalysis.technical?.mobileFriendly ? 'Yes' : 'No'}
- Keywords Found: ${websiteAnalysis.keywords?.extracted?.slice(0, 10).join(', ') || 'None detected'}

`;
      }

      contextPrompt += `Based on this data and the customer's request, provide:
1. Specific, actionable recommendations
2. Priority level (High/Medium/Low) for each recommendation
3. Expected impact on SEO performance
4. Step-by-step implementation guide
5. Tools or resources they might need

Be professional, detailed, and focus on practical solutions.`;

      // Add context to history
      history.push({ role: 'system', content: contextPrompt });
      history.push({ role: 'user', content: request });

      // Generate AI response
      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: history,
        max_tokens: 1500,
        temperature: 0.7
      });

      const aiResponse = completion.choices[0].message.content;
      
      // Add AI response to history
      history.push({ role: 'assistant', content: aiResponse });

      return aiResponse;

    } catch (error) {
      console.error('❌ Error generating intelligent response:', error.message);
      return this.generateFallbackResponse(request, websiteAnalysis);
    }
  }

  // Generate fallback response when OpenAI is not available
  generateFallbackResponse(request, websiteAnalysis) {
    const lowerRequest = request.toLowerCase();

    // Keyword research requests
    if (lowerRequest.includes('keyword') || lowerRequest.includes('research')) {
      return `🔍 **Keyword Research Strategy**

Based on your request, here's a comprehensive keyword research approach:

**1. Primary Keyword Tools:**
• Google Keyword Planner (free)
• SEMrush, Ahrefs, Moz (premium)
• Ubersuggest, Answer The Public

**2. Research Process:**
• Start with 5-10 seed keywords related to your business
• Analyze search volume (aim for 100-10K monthly searches)
• Check competition level (start with low competition)
• Look for long-tail variations (3+ words)
• Analyze SERP features (featured snippets, images, videos)

**3. Keyword Categories:**
• **Primary Keywords**: Main business terms
• **Long-tail Keywords**: Specific phrases with lower competition
• **LSI Keywords**: Related terms for content context
• **Local Keywords**: Include location if relevant

**4. Implementation:**
• Use primary keywords in title tags and H1
• Include secondary keywords in H2/H3 tags
• Naturally integrate keywords in content
• Monitor rankings and adjust strategy

${websiteAnalysis ? this.getWebsiteSpecificKeywordAdvice(websiteAnalysis) : ''}

**Next Steps:** Start with Google Keyword Planner and identify 20-30 target keywords for your website.`;

    }

    // Content optimization requests
    if (lowerRequest.includes('content') || lowerRequest.includes('optimization') || lowerRequest.includes('writing')) {
      return `📝 **Content Optimization Guide**

Here's how to optimize your content for better SEO performance:

**1. Content Structure:**
• Use H1 for main title (include primary keyword)
• Use H2/H3 for subheadings (include secondary keywords)
• Write 300-500+ words per page
• Include bullet points and numbered lists
• Add internal and external links

**2. Keyword Integration:**
• Use primary keyword 2-3 times naturally
• Include keywords in first 100 words
• Use variations and synonyms
• Avoid keyword stuffing (keep density under 2%)

**3. Content Quality:**
• Answer user questions completely
• Provide unique, valuable information
• Include relevant images with alt text
• Write for humans, not just search engines
• Update content regularly

**4. Technical Elements:**
• Optimize meta titles (50-60 characters)
• Write compelling meta descriptions (150-160 characters)
• Use descriptive URLs
• Include schema markup when relevant

${websiteAnalysis ? this.getWebsiteSpecificContentAdvice(websiteAnalysis) : ''}

**Priority Actions:** Focus on improving your title tags and meta descriptions first, then work on content structure and keyword integration.`;

    }

    // Technical SEO requests
    if (lowerRequest.includes('technical') || lowerRequest.includes('site speed') || lowerRequest.includes('mobile')) {
      return `⚙️ **Technical SEO Optimization**

Here's your technical SEO improvement plan:

**1. Site Speed Optimization:**
• Optimize images (WebP format, compression)
• Enable browser caching
• Minify CSS, JavaScript, HTML
• Use CDN for faster loading
• Target <3 seconds load time

**2. Mobile Optimization:**
• Ensure responsive design
• Test mobile-friendly navigation
• Optimize touch-friendly buttons
• Improve mobile loading speed
• Test with Google Mobile-Friendly Test

**3. Site Structure:**
• Clean, logical URL structure
• Submit XML sitemap to Google Search Console
• Create proper robots.txt file
• Fix broken links (404 errors)
• Implement breadcrumbs

**4. Core Web Vitals:**
• **LCP** (Largest Contentful Paint): <2.5s
• **FID** (First Input Delay): <100ms
• **CLS** (Cumulative Layout Shift): <0.1

${websiteAnalysis ? this.getWebsiteSpecificTechnicalAdvice(websiteAnalysis) : ''}

**Tools to Use:** Google PageSpeed Insights, Search Console, and Mobile-Friendly Test for monitoring and optimization.`;

    }

    // Meta tags requests
    if (lowerRequest.includes('meta') || lowerRequest.includes('title') || lowerRequest.includes('description')) {
      return `🏷️ **Meta Tags Optimization**

Here's how to optimize your meta tags for better SEO:

**1. Title Tags:**
• Keep under 60 characters
• Include primary keyword at the beginning
• Make it compelling and click-worthy
• Include brand name when relevant
• Unique for each page

**2. Meta Descriptions:**
• Keep under 160 characters
• Include primary keyword naturally
• Write compelling call-to-action
• Accurately describe page content
• Encourage clicks from SERPs

**3. Header Tags (H1-H6):**
• One H1 per page (include primary keyword)
• Use H2-H6 for content structure
• Include secondary keywords
• Create logical hierarchy
• Make them descriptive

**4. Alt Text for Images:**
• Describe what's in the image
• Include relevant keywords naturally
• Keep under 125 characters
• Be specific and descriptive
• Don't stuff keywords

${websiteAnalysis ? this.getWebsiteSpecificMetaAdvice(websiteAnalysis) : ''}

**Implementation:** Start by optimizing your homepage title and meta description, then work through your most important pages.`;

    }

    // General SEO help
    return `🚀 **SEO Optimization Strategy**

I'm here to help with your SEO questions! Here are the main areas I can assist with:

**🔍 Keyword Research**
• Finding the right keywords for your business
• Analyzing competition and search volume
• Long-tail keyword strategies
• Local SEO keyword optimization

**📝 Content Optimization**
• Writing SEO-friendly content
• On-page optimization techniques
• Content structure and formatting
• Content marketing strategies

**⚙️ Technical SEO**
• Site speed optimization
• Mobile optimization
• Core Web Vitals improvement
• Site structure and navigation

**🏷️ Meta Tags & Headers**
• Title tag optimization
• Meta description writing
• Header tag structure
• Image alt text optimization

**💡 Quick Tips:**
• Focus on user experience first
• Create valuable, original content
• Build quality backlinks
• Monitor your progress with analytics
• Stay updated with Google algorithm changes

${websiteAnalysis ? this.getWebsiteSpecificGeneralAdvice(websiteAnalysis) : ''}

**Ask me about any specific SEO topic, and I'll provide detailed guidance tailored to your website!**`;
  }

  // Get website-specific keyword advice
  getWebsiteSpecificKeywordAdvice(analysis) {
    const keywords = analysis.keywords?.extracted || [];
    const wordCount = analysis.content?.wordCount || 0;
    
    let advice = '\n**Website-Specific Keyword Advice:**\n';
    
    if (keywords.length > 0) {
      advice += `• Your top keywords: ${keywords.slice(0, 5).join(', ')}\n`;
      advice += `• Consider targeting these keywords in your content\n`;
    } else {
      advice += `• No keywords detected - focus on keyword research first\n`;
    }
    
    if (wordCount < 300) {
      advice += `• Your content is ${wordCount} words - aim for 300+ words for better SEO\n`;
    }
    
    return advice;
  }

  // Get website-specific content advice
  getWebsiteSpecificContentAdvice(analysis) {
    let advice = '\n**Website-Specific Content Advice:**\n';
    
    if (!analysis.title) {
      advice += `• ⚠️ Missing title tag - add one immediately\n`;
    } else if (analysis.title.length < 30) {
      advice += `• Title tag is too short (${analysis.title.length} chars) - expand to 30-60 characters\n`;
    }
    
    if (!analysis.metaDescription) {
      advice += `• ⚠️ Missing meta description - add one for better click-through rates\n`;
    } else if (analysis.metaDescription.length < 120) {
      advice += `• Meta description is too short (${analysis.metaDescription.length} chars) - expand to 120-160 characters\n`;
    }
    
    if (analysis.headings?.h1 === 0) {
      advice += `• ⚠️ No H1 tag found - add one for better page structure\n`;
    } else if (analysis.headings?.h1 > 1) {
      advice += `• Multiple H1 tags found - use only one per page\n`;
    }
    
    const wordCount = analysis.content?.wordCount || 0;
    if (wordCount < 300) {
      advice += `• Content is only ${wordCount} words - aim for 300+ words for better SEO\n`;
    }
    
    return advice;
  }

  // Get website-specific technical advice
  getWebsiteSpecificTechnicalAdvice(analysis) {
    let advice = '\n**Website-Specific Technical Issues:**\n';
    
    if (!analysis.technical?.sslCertificate) {
      advice += `• ⚠️ No SSL certificate - install HTTPS immediately\n`;
    }
    
    if (!analysis.technical?.mobileFriendly) {
      advice += `• ⚠️ Not mobile-friendly - add viewport meta tag\n`;
    }
    
    if (!analysis.technical?.canonical) {
      advice += `• Missing canonical URL - add to prevent duplicate content\n`;
    }
    
    const loadTime = parseFloat(analysis.performance?.loadTime?.replace('s', '') || '0');
    if (loadTime > 3) {
      advice += `• Load time is ${analysis.performance?.loadTime} - optimize for <3 seconds\n`;
    }
    
    const missingAlt = analysis.images?.missingAlt || 0;
    if (missingAlt > 0) {
      advice += `• ${missingAlt} images missing alt text - add for accessibility\n`;
    }
    
    return advice;
  }

  // Get website-specific meta advice
  getWebsiteSpecificMetaAdvice(analysis) {
    let advice = '\n**Your Current Meta Tags Status:**\n';
    
    if (analysis.title) {
      advice += `• Title: "${analysis.title}" (${analysis.title.length} chars)\n`;
      if (analysis.title.length < 30 || analysis.title.length > 60) {
        advice += `  ⚠️ Length issue - aim for 30-60 characters\n`;
      }
    } else {
      advice += `• ⚠️ No title tag found\n`;
    }
    
    if (analysis.metaDescription) {
      advice += `• Meta Description: "${analysis.metaDescription.substring(0, 50)}..." (${analysis.metaDescription.length} chars)\n`;
      if (analysis.metaDescription.length < 120 || analysis.metaDescription.length > 160) {
        advice += `  ⚠️ Length issue - aim for 120-160 characters\n`;
      }
    } else {
      advice += `• ⚠️ No meta description found\n`;
    }
    
    advice += `• H1 Tags: ${analysis.headings?.h1 || 0} (should be exactly 1)\n`;
    advice += `• H2 Tags: ${analysis.headings?.h2 || 0}\n`;
    
    return advice;
  }

  // Get website-specific general advice
  getWebsiteSpecificGeneralAdvice(analysis) {
    let advice = '\n**Your Website Analysis Summary:**\n';
    
    const score = this.calculateQuickScore(analysis);
    advice += `• Overall SEO Score: ${score}/100\n`;
    
    if (score < 50) {
      advice += `• Priority: High - Focus on basic SEO elements first\n`;
    } else if (score < 75) {
      advice += `• Priority: Medium - Optimize existing elements\n`;
    } else {
      advice += `• Priority: Low - Fine-tune advanced elements\n`;
    }
    
    advice += `• Word Count: ${analysis.content?.wordCount || 0} words\n`;
    advice += `• Images: ${analysis.images?.total || 0} total, ${analysis.images?.missingAlt || 0} missing alt text\n`;
    advice += `• Links: ${analysis.links?.internal || 0} internal, ${analysis.links?.external || 0} external\n`;
    
    return advice;
  }

  // Calculate quick SEO score
  calculateQuickScore(analysis) {
    let score = 0;
    
    if (analysis.title) score += 20;
    if (analysis.metaDescription) score += 15;
    if (analysis.headings?.h1 === 1) score += 15;
    if (analysis.technical?.sslCertificate) score += 10;
    if (analysis.technical?.mobileFriendly) score += 10;
    if (analysis.content?.wordCount > 300) score += 10;
    if (analysis.links?.internal > 0) score += 10;
    if (analysis.links?.external > 0) score += 10;
    
    return score;
  }

  // Initialize chat history for user
  async initializeChat(userId) {
    if (!this.conversationHistory.has(userId)) {
      this.conversationHistory.set(userId, []);
    }
    return this.conversationHistory.get(userId);
  }

  // Clear chat history for user
  clearChatHistory(userId) {
    this.conversationHistory.delete(userId);
  }
}

module.exports = new SEOResponseService();









