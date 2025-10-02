const OpenAI = require('openai');
const express = require('express');
const { Server } = require('socket.io');
const http = require('http');

class AIChatService {
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
        console.log('✅ OpenAI API initialized successfully');
      } catch (error) {
        console.error('❌ Failed to initialize OpenAI API:', error.message);
        this.openai = null;
      }
    } else {
      console.log('⚠️ OpenAI API key not configured. AI chat features will be limited.');
    }
  }

  // Initialize AI chat with SEO context
  async initializeChat(userId) {
    const systemPrompt = `You are an expert SEO consultant and digital marketing specialist with access to real-time SEO data. Your role is to help users improve their website's SEO performance by providing:

1. **Actionable Recommendations**: Give specific, implementable advice
2. **Data-Driven Insights**: Use actual website analysis data when available
3. **Keyword Intelligence**: Provide keyword recommendations with search volumes and competition
4. **Technical Solutions**: Identify and fix specific SEO issues
5. **Content Strategy**: Suggest content improvements and new content ideas
6. **Competitive Analysis**: Compare against competitors and suggest improvements

**IMPORTANT GUIDELINES:**
- Always provide specific, actionable steps users can take immediately
- Use data from website analysis when available (keywords, rankings, competitors, backlinks)
- Give concrete examples and templates
- Focus on quick wins and high-impact improvements
- Ask clarifying questions to provide better recommendations
- Be conversational but professional
- Avoid generic advice - make it personalized and relevant

**RESPONSE FORMAT:**
- Start with a brief assessment
- Provide 3-5 specific actionable recommendations
- Include examples or templates when helpful
- End with next steps or follow-up questions

When users ask about their website, analyze it first and provide personalized recommendations based on the actual data.`;

    if (!this.conversationHistory.has(userId)) {
      this.conversationHistory.set(userId, [
        { role: 'system', content: systemPrompt }
      ]);
    }

    return this.conversationHistory.get(userId);
  }

  // Process user message and generate AI response
  async processMessage(userId, message, websiteData = null) {
    try {
      // Check if OpenAI is available
      if (!this.openai) {
        // Provide intelligent fallback responses based on common SEO questions
        const lowerMessage = message.toLowerCase();
        
        // Keyword Research responses
        if (lowerMessage.includes('keyword') || lowerMessage.includes('research')) {
          return {
            success: true,
            message: `🔍 **Smart Keyword Research Strategy**

**IMMEDIATE ACTION PLAN:**

**1. Quick Keyword Discovery (Do This Now):**
• Enter your website URL in our analysis tool to get current keyword data
• Check Google Search Console for your top-performing keywords
• Use Google's "People Also Ask" for related terms
• Analyze competitor websites for keyword gaps

**2. High-Impact Keywords to Target:**
• **Primary**: 1-2 word terms with high search volume (1000+ monthly)
• **Long-tail**: 3+ word phrases with lower competition (100-1000 monthly)
• **Local**: Include location if relevant to your business
• **Commercial**: Terms like "best," "review," "buy," "price"

**3. Data-Driven Approach:**
• Target keywords with 100-10K monthly searches
• Choose competition level: Low to Medium initially
• Focus on keywords you can realistically rank for
• Prioritize keywords with commercial intent

**4. Implementation Strategy:**
• Use primary keyword in H1 tag and first 100 words
• Include secondary keywords in H2/H3 tags
• Create content clusters around topic pillars
• Monitor rankings weekly and adjust strategy

**🚀 NEXT STEPS:**
1. **Analyze your website** using our SEO tool to see current keyword performance
2. **Identify 5-10 target keywords** based on your business goals
3. **Create content plan** around these keywords
4. **Track progress** monthly with ranking reports

**What's your website URL? I can analyze it and give you specific keyword recommendations!**`,
            timestamp: new Date().toISOString(),
            fallback: true
          };
        }
        
        // Content Optimization responses
        if (lowerMessage.includes('content') || lowerMessage.includes('optimization') || lowerMessage.includes('writing')) {
          return {
            success: true,
            message: `📝 **Content Optimization Action Plan**

**IMMEDIATE IMPROVEMENTS (Do This Week):**

**1. Title & Meta Optimization:**
• **Title Tag**: [Primary Keyword] - [Value Proposition] | [Brand]
  Example: "Digital Marketing Services - Boost Traffic 300% | YourBrand"
• **Meta Description**: Include benefit + keyword + call-to-action
  Example: "Increase your website traffic with our proven SEO strategies. Get 300% more leads in 90 days. Start free analysis!"

**2. Content Structure (High Impact):**
• **H1**: Include primary keyword (one per page)
• **H2/H3**: Use secondary keywords for subheadings
• **Word Count**: Aim for 800+ words for better rankings
• **Formatting**: Use bullet points, numbered lists, and short paragraphs

**3. Keyword Integration Strategy:**
• **First 100 words**: Include primary keyword naturally
• **Density**: 1-2% keyword density (don't overstuff)
• **LSI Keywords**: Include 3-5 related terms throughout content
• **Synonyms**: Use variations to avoid repetition

**4. Content Quality Boosters:**
• **Answer Questions**: Address "what," "why," "how," "when," "where"
• **Internal Links**: Link to 3-5 relevant pages on your site
• **External Links**: Link to 2-3 authoritative sources
• **Images**: Add 2-3 images with descriptive alt text
• **Call-to-Action**: Include clear next steps for readers

**🚀 QUICK WINS:**
1. **Analyze your current content** - Enter your URL for instant content audit
2. **Rewrite your top 3 pages** with better keyword integration
3. **Add FAQ sections** to capture featured snippets
4. **Create content clusters** around your main topics

**What's your website URL? I'll analyze your content and give you specific optimization recommendations!**`,
            timestamp: new Date().toISOString(),
            fallback: true
          };
        }
        
        // Technical SEO responses
        if (lowerMessage.includes('technical') || lowerMessage.includes('site speed') || lowerMessage.includes('mobile')) {
          return {
            success: true,
            message: `⚙️ **Technical SEO Action Plan**

**CRITICAL FIXES (Fix These First):**

**1. Site Speed Optimization (High Impact):**
• **Images**: Convert to WebP, compress to <100KB each
• **Caching**: Enable browser caching (1 year for static assets)
• **Minification**: Minify CSS, JavaScript, HTML files
• **CDN**: Use Cloudflare or similar for faster global loading
• **Target**: <3 seconds load time (currently most sites are 5-8 seconds)

**2. Mobile Optimization (Google Priority):**
• **Responsive Design**: Ensure mobile-friendly layout
• **Touch Elements**: Buttons at least 44px for easy tapping
• **Mobile Speed**: Optimize for mobile Core Web Vitals
• **Test**: Use Google Mobile-Friendly Test tool

**3. Core Web Vitals (Ranking Factor):**
• **LCP** (Largest Contentful Paint): <2.5s (currently 4-6s average)
• **FID** (First Input Delay): <100ms
• **CLS** (Cumulative Layout Shift): <0.1

**4. Site Structure (SEO Foundation):**
• **URLs**: Clean, descriptive URLs with keywords
• **Sitemap**: Submit XML sitemap to Google Search Console
• **Robots.txt**: Proper crawling instructions
• **404 Errors**: Fix broken links immediately
• **Breadcrumbs**: Implement for better navigation

**5. Security & Trust (Essential):**
• **HTTPS**: SSL certificate installed and working
• **Security Headers**: Implement security headers
• **Updates**: Keep CMS and plugins updated

**🚀 IMMEDIATE ACTIONS:**
1. **Run speed test** - Enter your URL for instant speed analysis
2. **Fix top 5 speed issues** identified in the report
3. **Test mobile friendliness** with Google's tool
4. **Submit sitemap** to Google Search Console
5. **Monitor Core Web Vitals** monthly

**What's your website URL? I'll run a complete technical audit and give you a prioritized fix list!**`,
            timestamp: new Date().toISOString(),
            fallback: true
          };
        }
        
        // Meta Tags responses
        if (lowerMessage.includes('meta') || lowerMessage.includes('title') || lowerMessage.includes('description')) {
          return {
            success: true,
            message: `🏷️ **Meta Tags Optimization**

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

**5. Additional Meta Tags:**
• Open Graph tags for social sharing
• Twitter Card meta tags
• Canonical URLs to prevent duplicate content
• Language and charset declarations

**Pro Tip**: A/B test different titles and descriptions to see what gets more clicks!`,
            timestamp: new Date().toISOString(),
            fallback: true
          };
        }
        
        // General SEO help
        return {
          success: true,
          message: `🚀 **SEO Optimization Guide**

I'm here to help with your SEO questions! Here are the main areas I can assist with:

**🔍 Keyword Research**
• Finding the right keywords
• Analyzing competition
• Long-tail keyword strategies

**📝 Content Optimization**
• Writing SEO-friendly content
• On-page optimization
• Content structure and formatting

**⚙️ Technical SEO**
• Site speed optimization
• Mobile optimization
• Core Web Vitals
• Site structure and navigation

**🏷️ Meta Tags & Headers**
• Title tag optimization
• Meta descriptions
• Header tag structure
• Image alt text

**💡 Quick Tips:**
• Focus on user experience first
• Create valuable, original content
• Build quality backlinks
• Monitor your progress with analytics
• Stay updated with Google algorithm changes

**Ask me about any specific SEO topic, and I'll provide detailed guidance!**`,
          timestamp: new Date().toISOString(),
          fallback: true
        };
      }

      const history = await this.initializeChat(userId);
      
      // Add user message to history
      history.push({ role: 'user', content: message });

      // If website data is provided, add context
      if (websiteData) {
        const contextMessage = `Website Analysis Data for ${websiteData.url}:
- Title: ${websiteData.onPage?.title || 'Not found'}
- Meta Description: ${websiteData.onPage?.metaDescription || 'Not found'}
- SEO Score: ${websiteData.score || 'N/A'}/100
- Load Time: ${websiteData.onPage?.performance?.loadTime || 'N/A'}
- Word Count: ${websiteData.onPage?.content?.wordCount || 'N/A'}
- Images: ${websiteData.onPage?.images?.total || 0} total, ${websiteData.onPage?.images?.missingAlt || 0} missing alt text
- Links: ${websiteData.onPage?.links?.internal || 0} internal, ${websiteData.onPage?.links?.external || 0} external
- Top Keywords: ${websiteData.keywords?.keywords?.slice(0, 3).map(k => k.keyword).join(', ') || 'None found'}
- Competitors: ${websiteData.competitors?.competitors?.slice(0, 2).map(c => c.domain).join(', ') || 'None found'}

Use this data to provide specific, actionable recommendations. Be conversational and helpful.`;
        
        history.push({ role: 'assistant', content: contextMessage });
      }

      // Generate AI response
      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: history,
        max_tokens: 1000,
        temperature: 0.7
      });

      const aiResponse = completion.choices[0].message.content;
      
      // Add AI response to history
      history.push({ role: 'assistant', content: aiResponse });

      return {
        success: true,
        message: aiResponse,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('AI Chat Error:', error);
      return {
        success: false,
        message: 'Sorry, I encountered an error. Please try again.',
        error: error.message
      };
    }
  }

  // Generate SEO content based on analysis
  async generateSEOContent(userId, contentType, websiteData) {
    try {
      // Check if OpenAI is available
      if (!this.openai) {
        // Provide helpful content templates
        const contentTemplates = {
          'title': `**SEO-Optimized Title Template:**

[Primary Keyword] - [Value Proposition] | [Brand Name]

**Examples:**
• "Digital Marketing Services - Boost Your Online Presence | YourBrand"
• "SEO Analysis Tool - Improve Your Website Rankings | YourBrand"
• "Content Marketing Guide - Drive More Traffic | YourBrand"

**Best Practices:**
• Keep under 60 characters
• Include primary keyword at the beginning
• Make it compelling and click-worthy
• Include your brand name when relevant`,

          'meta_description': `**Meta Description Template:**

[Benefit/Value] with [Your Service]. [Primary keyword] solutions for [target audience]. [Call-to-action] today!

**Examples:**
• "Boost your website traffic with our SEO services. Digital marketing solutions for small businesses. Get started today!"
• "Improve your search rankings with our analysis tool. SEO optimization for better visibility. Try it free!"
• "Drive more leads with content marketing. Professional writing services for growing businesses. Contact us now!"

**Best Practices:**
• Keep under 160 characters
• Include primary keyword naturally
• Write compelling call-to-action
• Accurately describe page content`,

          'heading': `**Header Structure Template:**

H1: [Primary Keyword] - [Compelling Value Proposition]
H2: Why Choose [Your Service]?
H3: Key Benefits of [Your Solution]
H2: How [Your Service] Works
H3: Step 1: [Process Step]
H3: Step 2: [Process Step]
H2: [Target Audience] Success Stories
H2: Get Started with [Your Service]

**Best Practices:**
• One H1 per page (include primary keyword)
• Use H2-H6 for content structure
• Include secondary keywords
• Create logical hierarchy`,

          'content': `**Content Structure Template:**

**Introduction (100-150 words)**
• Hook with a question or statistic
• Introduce the main topic
• Preview what readers will learn

**Main Content (300-400 words)**
• Problem/Solution section
• Benefits/Features section
• How-to or process section
• Examples or case studies

**Conclusion (50-100 words)**
• Summarize key points
• Include call-to-action
• Encourage engagement

**Content Tips:**
• Use bullet points and numbered lists
• Include relevant keywords naturally
• Add internal and external links
• Write for humans, not just search engines`,

          'blog_post': `**Blog Post Template:**

**Title:** [Compelling Headline with Primary Keyword]

**Introduction (150-200 words)**
• Hook the reader with a question or statistic
• Introduce the main topic
• Preview the value readers will get

**Body (500-800 words)**
• 3-5 sections with descriptive subheadings
• Use bullet points and numbered lists
• Include relevant keywords naturally
• Add internal and external links
• Provide actionable tips and examples

**Conclusion (100-150 words)**
• Summarize key points
• Include call-to-action
• Encourage comments and sharing

**Additional Elements:**
• Meta description
• Featured image with alt text
• Social sharing buttons
• Related posts section`
        };
        
        const content = contentTemplates[contentType] || `**Content Generation Templates Available:**

I can help you create:
• **Title tags** - SEO-optimized page titles
• **Meta descriptions** - Compelling SERP descriptions  
• **Headings** - Proper H1-H6 structure
• **Content** - Well-structured articles and pages
• **Blog posts** - Complete blog post templates

**Ask me to generate any of these content types!**`;
        
        return {
          success: true,
          content: content,
          timestamp: new Date().toISOString(),
          fallback: true
        };
      }

      const prompt = `Based on the website analysis data, generate ${contentType}:

Website Data:
- URL: ${websiteData.url}
- Current Title: ${websiteData.title}
- Current Meta Description: ${websiteData.metaDescription}
- Target Keywords: ${websiteData.keywords?.extracted?.slice(0, 5).join(', ') || 'Not specified'}
- Industry: ${websiteData.competitors?.industryKeywords?.join(', ') || 'General'}

Please generate:
1. An optimized title tag (50-60 characters)
2. An optimized meta description (150-160 characters)
3. H1 tag suggestion
4. 3-5 H2 tag suggestions
5. Content outline with target keywords

Make it SEO-friendly and engaging for users.`;

      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-4-turbo-preview',
        messages: [
          { role: 'system', content: 'You are an expert SEO content writer specializing in creating optimized, engaging content.' },
          { role: 'user', content: prompt }
        ],
        max_tokens: 1500,
        temperature: 0.8
      });

      return {
        success: true,
        content: completion.choices[0].message.content,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Content Generation Error:', error);
      return {
        success: false,
        content: 'Sorry, I could not generate content at this time.',
        error: error.message
      };
    }
  }

  // Clear conversation history
  clearHistory(userId) {
    this.conversationHistory.delete(userId);
  }

  // Get conversation history
  getHistory(userId) {
    return this.conversationHistory.get(userId) || [];
  }

  // Generate intelligent SEO recommendations using DataForSEO data
  async generateIntelligentRecommendations(userId, message, websiteUrl = null) {
    try {
      const dataforseoService = require('./dataforseoEnvironmentService');
      
      // If website URL is provided, get real data
      let seoData = null;
      if (websiteUrl) {
        try {
          let processedUrl = websiteUrl.trim();
          if (!processedUrl.match(/^https?:\/\//)) {
            processedUrl = 'https://' + processedUrl;
          }
          
          const analysis = await dataforseoService.analyzeWebsite(processedUrl);
          if (analysis.success) {
            seoData = analysis.analysis;
            console.log('✅ Got SEO data for intelligent recommendations');
          }
        } catch (error) {
          console.log('DataForSEO analysis failed for recommendations:', error.message);
        }
      }

      // Generate contextual recommendations based on message and data
      const lowerMessage = message.toLowerCase();
      
      // Keyword-focused recommendations
      if (lowerMessage.includes('keyword') || lowerMessage.includes('research') || lowerMessage.includes('ranking')) {
        return this.generateKeywordRecommendations(seoData, websiteUrl);
      }
      
      // Content-focused recommendations
      if (lowerMessage.includes('content') || lowerMessage.includes('writing') || lowerMessage.includes('blog')) {
        return this.generateContentRecommendations(seoData, websiteUrl);
      }
      
      // Technical SEO recommendations
      if (lowerMessage.includes('technical') || lowerMessage.includes('speed') || lowerMessage.includes('mobile')) {
        return this.generateTechnicalRecommendations(seoData, websiteUrl);
      }
      
      // Competitor-focused recommendations
      if (lowerMessage.includes('competitor') || lowerMessage.includes('competition')) {
        return this.generateCompetitorRecommendations(seoData, websiteUrl);
      }
      
      // General SEO recommendations
      return this.generateGeneralRecommendations(seoData, websiteUrl);
      
    } catch (error) {
      console.error('Intelligent recommendations error:', error);
      return null;
    }
  }

  // Generate keyword-specific recommendations
  generateKeywordRecommendations(seoData, websiteUrl) {
    if (seoData && seoData.keywords && seoData.keywords.keywords) {
      const topKeywords = seoData.keywords.keywords.slice(0, 5);
      const competitors = seoData.competitors?.competitors || [];
      
      return {
        success: true,
        message: `🎯 **Personalized Keyword Strategy for ${websiteUrl || 'Your Website'}**

**CURRENT KEYWORD PERFORMANCE:**
${topKeywords.map((kw, i) => `${i+1}. "${kw.keyword}" - Rank #${kw.position || 'Not ranked'} (${kw.searchVolume || 'Unknown'} searches/month)`).join('\n')}

**IMMEDIATE KEYWORD ACTIONS:**

**1. Ranking Opportunities:**
• Focus on keywords ranking #4-10 (quick wins)
• Target long-tail variations of your top keywords
• Create content for keywords your competitors rank for but you don't

**2. Content Strategy:**
• Write in-depth guides for your top-performing keywords
• Create FAQ pages for long-tail keyword variations
• Build topic clusters around your strongest keywords

**3. Competitor Analysis:**
${competitors.length > 0 ? `• Your strongest competitor: ${competitors[0].domain}
• Target keywords they rank for: ${competitors[0].commonKeywords || 0} shared keywords
• Opportunity: Focus on keywords they're missing` : '• Run competitor analysis to identify keyword gaps'}

**4. Quick Wins (This Week):**
• Optimize existing pages for keywords ranking #4-10
• Add internal links from high-traffic pages to target pages
• Create location-based content if relevant to your business

**🚀 NEXT STEPS:**
1. **Target 3-5 specific keywords** from the list above
2. **Create content calendar** around these keywords
3. **Monitor rankings weekly** and adjust strategy
4. **Expand to related keywords** once you rank well

**Need specific keyword recommendations? Share your business type and I'll suggest targeted keywords!**`,
        timestamp: new Date().toISOString(),
        dataDriven: true
      };
    }
    
    return {
      success: true,
      message: `🔍 **Keyword Research Action Plan**

**IMMEDIATE STEPS:**

**1. Discover Your Current Keywords:**
• Enter your website URL for instant keyword analysis
• Check Google Search Console for top-performing keywords
• Analyze what keywords are driving traffic to your site

**2. Target High-Value Keywords:**
• **Primary Keywords**: 1-2 words with high search volume
• **Long-tail Keywords**: 3+ words with lower competition
• **Local Keywords**: Include location if relevant
• **Commercial Keywords**: "buy," "best," "review," "price"

**3. Competitor Keyword Analysis:**
• Identify what keywords your competitors rank for
• Find keyword gaps you can exploit
• Analyze their content strategy

**4. Implementation Strategy:**
• Create content around target keywords
• Optimize existing pages for better rankings
• Build topic authority through content clusters

**What's your website URL? I'll analyze your current keyword performance and give you a personalized strategy!**`,
      timestamp: new Date().toISOString(),
      dataDriven: false
    };
  }

  // Generate content-specific recommendations
  generateContentRecommendations(seoData, websiteUrl) {
    if (seoData && seoData.onPage && seoData.onPage.content) {
      const content = seoData.onPage.content;
      const wordCount = content.wordCount || 0;
      const readability = content.readabilityScore || 0;
      
      return {
        success: true,
        message: `📝 **Content Optimization Strategy for ${websiteUrl || 'Your Website'}**

**CURRENT CONTENT ANALYSIS:**
• **Word Count**: ${wordCount} words (Target: 800+ words for better rankings)
• **Readability Score**: ${readability}/100 (Target: 60+ for better user engagement)
• **Content Quality**: ${wordCount < 300 ? 'Needs improvement - too short' : wordCount > 800 ? 'Good length' : 'Moderate - could be longer'}

**IMMEDIATE CONTENT IMPROVEMENTS:**

**1. Content Length Optimization:**
• **Current**: ${wordCount} words
• **Target**: 800-1500 words for better rankings
• **Action**: Expand existing content with more valuable information

**2. Content Structure Enhancement:**
• Add more H2/H3 subheadings for better readability
• Include bullet points and numbered lists
• Add FAQ sections to capture featured snippets
• Create content clusters around main topics

**3. Keyword Integration:**
• Include primary keywords in H1 and first 100 words
• Use secondary keywords in H2/H3 tags
• Add LSI keywords throughout content naturally
• Optimize for semantic search

**4. Content Quality Boosters:**
• Add internal links to relevant pages (3-5 links)
• Include external links to authoritative sources (2-3 links)
• Add images with descriptive alt text
• Include clear call-to-actions

**🚀 CONTENT ACTION PLAN:**
1. **Audit top 5 pages** and expand content to 800+ words
2. **Add FAQ sections** to capture more featured snippets
3. **Create content calendar** around your target keywords
4. **Build topic clusters** for better topical authority

**Need specific content ideas? Share your industry and I'll suggest content topics!**`,
        timestamp: new Date().toISOString(),
        dataDriven: true
      };
    }
    
    return {
      success: true,
      message: `📝 **Content Strategy Action Plan**

**HIGH-IMPACT CONTENT IMPROVEMENTS:**

**1. Content Length & Quality:**
• **Target**: 800-1500 words per page for better rankings
• **Structure**: Use clear H1, H2, H3 hierarchy
• **Formatting**: Bullet points, numbered lists, short paragraphs
• **Value**: Answer user questions completely

**2. Keyword-Optimized Content:**
• **Primary Keyword**: Use in H1 and first 100 words
• **Secondary Keywords**: Include in H2/H3 tags
• **LSI Keywords**: Add 3-5 related terms naturally
• **Density**: 1-2% keyword density (don't overstuff)

**3. Content Types That Rank:**
• **How-to Guides**: Step-by-step tutorials
• **List Posts**: "Top 10," "Best of" articles
• **FAQ Pages**: Answer common questions
• **Case Studies**: Real examples and results
• **Ultimate Guides**: Comprehensive resources

**4. Content Distribution Strategy:**
• **Blog Posts**: 2-3 per week for fresh content
• **Landing Pages**: Optimized for specific keywords
• **Resource Pages**: Comprehensive topic coverage
• **Video Content**: Transcribe for SEO benefits

**What's your website URL? I'll analyze your current content and give you specific optimization recommendations!**`,
      timestamp: new Date().toISOString(),
      dataDriven: false
    };
  }

  // Generate technical SEO recommendations
  generateTechnicalRecommendations(seoData, websiteUrl) {
    if (seoData && seoData.onPage && seoData.onPage.performance) {
      const perf = seoData.onPage.performance;
      const loadTime = perf.loadTime || 0;
      const mobileFriendly = seoData.onPage.technical?.mobileFriendly || false;
      
      return {
        success: true,
        message: `⚙️ **Technical SEO Analysis for ${websiteUrl || 'Your Website'}**

**CURRENT TECHNICAL STATUS:**
• **Page Load Time**: ${loadTime}s (Target: <3 seconds)
• **Mobile Friendly**: ${mobileFriendly ? '✅ Yes' : '❌ Needs improvement'}
• **SSL Certificate**: ${seoData.onPage.technical?.sslCertificate ? '✅ Secure' : '❌ Not secure'}
• **Overall Score**: ${seoData.score || 0}/100

**CRITICAL TECHNICAL FIXES:**

**1. Speed Optimization (High Priority):**
• **Current**: ${loadTime}s load time
• **Target**: <3 seconds for better rankings
• **Actions**: Optimize images, enable caching, use CDN
• **Impact**: 1 second improvement = 7% conversion increase

**2. Mobile Optimization:**
• **Status**: ${mobileFriendly ? 'Good' : 'Needs work'}
• **Actions**: ${mobileFriendly ? 'Maintain mobile-friendly design' : 'Fix responsive design issues'}
• **Test**: Use Google Mobile-Friendly Test tool

**3. Core Web Vitals:**
• **LCP** (Largest Contentful Paint): Target <2.5s
• **FID** (First Input Delay): Target <100ms
• **CLS** (Cumulative Layout Shift): Target <0.1

**4. Site Structure:**
• **URLs**: Clean, descriptive URLs with keywords
• **Sitemap**: Submit XML sitemap to Google
• **Internal Linking**: Improve internal link structure
• **404 Errors**: Fix broken links immediately

**🚀 TECHNICAL ACTION PLAN:**
1. **Optimize images** - Convert to WebP, compress to <100KB
2. **Enable caching** - Set browser caching for static assets
3. **Fix mobile issues** - Ensure responsive design works perfectly
4. **Submit sitemap** - Help Google crawl your site better

**Need a complete technical audit? I can analyze your site and give you a prioritized fix list!**`,
        timestamp: new Date().toISOString(),
        dataDriven: true
      };
    }
    
    return {
      success: true,
      message: `⚙️ **Technical SEO Action Plan**

**CRITICAL TECHNICAL FIXES:**

**1. Site Speed (Highest Impact):**
• **Target**: <3 seconds load time
• **Actions**: Optimize images, enable caching, use CDN
• **Tools**: Google PageSpeed Insights for testing
• **Impact**: 1 second faster = 7% more conversions

**2. Mobile Optimization:**
• **Responsive Design**: Works on all devices
• **Touch Elements**: Buttons at least 44px
• **Mobile Speed**: Optimize for mobile Core Web Vitals
• **Test**: Google Mobile-Friendly Test

**3. Core Web Vitals (Google Ranking Factor):**
• **LCP**: <2.5 seconds (largest content load)
• **FID**: <100ms (interaction response time)
• **CLS**: <0.1 (layout stability)

**4. Site Structure:**
• **Clean URLs**: Include keywords, avoid parameters
• **XML Sitemap**: Submit to Google Search Console
• **Robots.txt**: Proper crawling instructions
• **Internal Links**: Logical site architecture

**What's your website URL? I'll run a complete technical audit and give you specific fixes!**`,
      timestamp: new Date().toISOString(),
      dataDriven: false
    };
  }

  // Generate competitor-focused recommendations
  generateCompetitorRecommendations(seoData, websiteUrl) {
    if (seoData && seoData.competitors && seoData.competitors.competitors && seoData.competitors.competitors.length > 0) {
      const competitors = seoData.competitors.competitors;
      const strongest = competitors[0];
      
      return {
        success: true,
        message: `🏆 **Competitive Analysis for ${websiteUrl || 'Your Website'}**

**TOP COMPETITORS ANALYSIS:**
${competitors.slice(0, 3).map((comp, i) => `${i+1}. **${comp.domain}**
   • Domain Rating: ${comp.domainRating}/100
   • Common Keywords: ${comp.commonKeywords || 0}
   • Traffic: ${comp.organicTraffic || 'Unknown'}
   • Strength: ${comp.domainRating > 70 ? 'Strong' : comp.domainRating > 40 ? 'Medium' : 'Weak'}`).join('\n')}

**COMPETITIVE OPPORTUNITIES:**

**1. Keyword Gap Analysis:**
• **Target**: Keywords competitors rank for but you don't
• **Strategy**: Create content for these missing keywords
• **Priority**: Focus on keywords with medium competition first

**2. Content Gap Analysis:**
• **Analyze**: What content types competitors create
• **Identify**: Topics they cover that you don't
• **Create**: Better content on the same topics

**3. Backlink Opportunities:**
• **Research**: Where competitors get their backlinks
• **Outreach**: Contact the same sites for link opportunities
• **Create**: Linkable assets that attract similar links

**4. Technical Advantages:**
• **Speed**: If competitors are slow, focus on speed
• **Mobile**: If they're not mobile-friendly, make it your strength
• **User Experience**: Provide better UX than competitors

**🚀 COMPETITIVE ACTION PLAN:**
1. **Target 5-10 keywords** your top competitor ranks for
2. **Create superior content** on the same topics
3. **Build relationships** with sites linking to competitors
4. **Monitor competitor changes** monthly

**Want detailed competitor keyword research? I can analyze specific competitors for you!**`,
        timestamp: new Date().toISOString(),
        dataDriven: true
      };
    }
    
    return {
      success: true,
      message: `🏆 **Competitor Analysis Strategy**

**COMPETITIVE INTELLIGENCE PLAN:**

**1. Identify Top Competitors:**
• **Direct Competitors**: Same products/services
• **Indirect Competitors**: Similar target audience
• **Industry Leaders**: Top players in your space
• **Local Competitors**: If you serve specific locations

**2. Competitor Analysis Areas:**
• **Keywords**: What keywords do they rank for?
• **Content**: What content types do they create?
• **Backlinks**: Where do they get their links?
• **Technical**: How fast/optimized are their sites?

**3. Gap Analysis:**
• **Keyword Gaps**: Keywords they rank for but you don't
• **Content Gaps**: Topics they cover that you don't
• **Link Gaps**: High-quality sites linking to them
• **Technical Gaps**: Areas where you can outperform

**4. Competitive Advantages:**
• **Better Content**: Create superior content on same topics
• **Better UX**: Provide better user experience
• **Better Speed**: Optimize for faster loading
• **Better Mobile**: Ensure perfect mobile experience

**What's your website URL? I'll analyze your competitors and give you specific opportunities to beat them!**`,
      timestamp: new Date().toISOString(),
      dataDriven: false
    };
  }

  // Generate general SEO recommendations
  generateGeneralRecommendations(seoData, websiteUrl) {
    return {
      success: true,
      message: `🚀 **Comprehensive SEO Strategy**

**IMMEDIATE SEO ACTIONS (Do This Week):**

**1. Website Analysis (Start Here):**
• **Enter your website URL** for instant SEO audit
• **Identify top 5 issues** that need immediate attention
• **Get personalized recommendations** based on your data

**2. Quick Wins (High Impact, Low Effort):**
• **Fix broken links** and 404 errors
• **Optimize page titles** and meta descriptions
• **Add alt text** to images
• **Improve page load speed**
• **Ensure mobile-friendliness**

**3. Content Strategy:**
• **Audit existing content** for optimization opportunities
• **Create content calendar** around target keywords
• **Build topic clusters** for better authority
• **Add FAQ sections** to capture featured snippets

**4. Technical Foundation:**
• **Submit XML sitemap** to Google Search Console
• **Set up Google Analytics** and Search Console
• **Monitor Core Web Vitals** monthly
• **Fix crawl errors** and indexing issues

**5. Competitive Analysis:**
• **Identify top 3 competitors** in your space
• **Analyze their keyword strategy** and content approach
• **Find keyword gaps** you can exploit
• **Monitor their changes** monthly

**🎯 PERSONALIZED RECOMMENDATIONS:**
To get specific, actionable advice for your website:
1. **Share your website URL** for instant analysis
2. **Tell me your business goals** (more traffic, leads, sales)
3. **Specify your industry** for targeted keyword suggestions
4. **Share your current challenges** for focused solutions

**What's your website URL? I'll analyze it and give you a personalized SEO action plan!**`,
      timestamp: new Date().toISOString(),
      dataDriven: false
    };
  }
}

module.exports = new AIChatService();
