const OpenAI = require('openai');
const crypto = require('crypto');
const planLimitsConfig = require('../plan-limits-config');

class IntelligentContentGenerator {
  constructor() {
    this.openai = null;
    const apiKey = process.env.OPENAI_API_KEY;
    
    if (apiKey && apiKey !== 'your_openai_api_key_here' && apiKey.startsWith('sk-')) {
      try {
        this.openai = new OpenAI({ apiKey });
        console.log('✅ Intelligent Content Generator initialized successfully');
      } catch (error) {
        console.error('❌ Failed to initialize OpenAI API:', error.message);
      }
    } else {
      console.log('⚠️ OpenAI API key not configured for Content Generator');
    }
  }
  
  /**
   * Get content limits from plan-limits-config.js
   */
  getContentLimits(planId) {
    return planLimitsConfig.getContentLimits(planId);
  }

  /**
   * Extract keywords and services from crawled data using AI
   */
  async extractKeywordsAndServices(crawlData, domain) {
    try {
      console.log('🔍 Extracting keywords and services from crawl data...');
      
      const pages = crawlData.onPage?.pages || [];
      const existingKeywords = crawlData.keywords?.keywords || [];
      
      // Build context from crawled data
      const context = {
        domain: domain,
        titles: pages.slice(0, 5).map(p => p.title).filter(Boolean),
        h1Tags: pages.flatMap(p => p.meta?.htags?.h1 || []).slice(0, 10),
        h2Tags: pages.flatMap(p => p.meta?.htags?.h2 || []).slice(0, 10),
        metaDescriptions: pages.slice(0, 3).map(p => p.meta?.description).filter(Boolean),
        existingKeywords: existingKeywords.slice(0, 20).map(k => k.keyword || k)
      };

      if (!this.openai) {
        return this.extractKeywordsFromDataFallback(context, domain);
      }

      const prompt = `Analyze this website data and extract the main keywords and services/products offered:

WEBSITE DATA:
Domain: ${domain}
Page Titles: ${context.titles.join(' | ')}
H1 Tags: ${context.h1Tags.join(' | ')}
H2 Tags: ${context.h2Tags.join(' | ')}
Meta Descriptions: ${context.metaDescriptions.join(' | ')}
Existing Keywords: ${context.existingKeywords.join(', ')}

Extract and return a JSON object with:
{
  "primaryKeywords": ["keyword1", "keyword2", ...],  // 5-10 main keywords
  "services": ["service1", "service2", ...],  // 3-5 main services/products
  "businessType": "description of business",
  "targetAudience": "description of target audience",
  "contentThemes": ["theme1", "theme2", ...]  // 5-10 content themes for blog/social
}

If data is minimal, analyze the domain name and infer likely business type and keywords.
Return ONLY valid JSON, no markdown.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 800,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const extracted = JSON.parse(jsonContent);

      console.log('✅ Extracted:', {
        keywords: extracted.primaryKeywords?.length || 0,
        services: extracted.services?.length || 0,
        themes: extracted.contentThemes?.length || 0
      });

      return {
        success: true,
        ...extracted
      };

    } catch (error) {
      console.error('❌ Error extracting keywords:', error.message);
      return this.extractKeywordsFromDataFallback(context, domain);
    }
  }

  /**
   * Fallback keyword extraction without AI
   */
  extractKeywordsFromDataFallback(context, domain) {
    const domainWords = domain.replace(/\.com|\.net|\.org|\.io/g, '').split(/[-_.]/).filter(w => w.length > 2);
    
    return {
      success: true,
      primaryKeywords: [...domainWords, ...context.existingKeywords.slice(0, 5)],
      services: domainWords.map(w => `${w} services`),
      businessType: `${domainWords.join(' ')} business`,
      targetAudience: 'General audience',
      contentThemes: [
        'Industry insights',
        'How-to guides',
        'Best practices',
        'Tips and tricks',
        'Case studies'
      ]
    };
  }

  /**
   * Generate blog post using AI
   */
  async generateBlogPost(websiteData, keyword, usedTopics = []) {
    try {
      console.log('📝 Generating blog post for keyword:', keyword);

      if (!this.openai) {
        return this.generateDemoBlogPost(keyword);
      }

      const prompt = `Create a comprehensive SEO-optimized blog post for a ${websiteData.businessType} website.

BUSINESS CONTEXT:
- Domain: ${websiteData.domain}
- Services: ${websiteData.services?.join(', ')}
- Target Audience: ${websiteData.targetAudience}
- Target Keyword: ${keyword}

REQUIREMENTS:
- Title: Engaging, includes keyword (50-60 characters)
- Length: 800-1200 words
- Structure: Intro, 3-5 main sections with H2 headings, conclusion
- SEO: Natural keyword usage, semantic keywords
- Style: Professional, informative, engaging
- Value: Actionable insights and practical tips

AVOID THESE TOPICS (already used):
${usedTopics.join(', ')}

Return JSON:
{
  "title": "Blog post title with keyword",
  "metaDescription": "SEO meta description (150-160 chars)",
  "content": "Full blog post content in HTML format with <h2>, <p>, <ul>, etc.",
  "keywords": ["primary", "secondary", "tertiary"],
  "excerpt": "Brief summary (100-150 words)",
  "estimatedReadTime": "5-7 min",
  "seoScore": 85
}

Return ONLY valid JSON.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2500,
        temperature: 0.8
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const blogPost = JSON.parse(jsonContent);

      console.log('✅ Blog post generated:', blogPost.title);

      return {
        success: true,
        type: 'blog',
        ...blogPost,
        keyword: keyword,
        generatedAt: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Error generating blog post:', error.message);
      return this.generateDemoBlogPost(keyword);
    }
  }

  /**
   * Generate social media post for Twitter
   */
  async generateTwitterPost(websiteData, keyword, blogTitle = null) {
    try {
      console.log('🐦 Generating Twitter post for:', keyword);

      if (!this.openai) {
        return this.generateDemoTwitterPost(keyword);
      }

      const prompt = `Create an engaging Twitter post for a ${websiteData.businessType} business.

CONTEXT:
- Business: ${websiteData.domain}
- Services: ${websiteData.services?.join(', ')}
- Topic: ${keyword}
${blogTitle ? `- Related Blog: ${blogTitle}` : ''}

REQUIREMENTS:
- Length: 200-280 characters (Twitter limit)
- Include: Hook + value + call-to-action
- Style: Professional yet conversational
- Hashtags: 2-3 relevant hashtags
- Emoji: 1-2 relevant emojis (not excessive)

Return JSON:
{
  "content": "Tweet text with hashtags",
  "hashtags": ["hashtag1", "hashtag2"],
  "callToAction": "Visit our website|Learn more|etc",
  "characterCount": 250
}

Return ONLY valid JSON.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 300,
        temperature: 0.9
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const tweet = JSON.parse(jsonContent);

      return {
        success: true,
        type: 'twitter',
        ...tweet,
        keyword: keyword
      };

    } catch (error) {
      console.error('❌ Error generating Twitter post:', error.message);
      return this.generateDemoTwitterPost(keyword);
    }
  }

  /**
   * Generate Instagram post
   */
  async generateInstagramPost(websiteData, keyword, blogTitle = null) {
    try {
      console.log('📸 Generating Instagram post for:', keyword);

      if (!this.openai) {
        return this.generateDemoInstagramPost(keyword);
      }

      const prompt = `Create an engaging Instagram post for a ${websiteData.businessType} business.

CONTEXT:
- Business: ${websiteData.domain}
- Services: ${websiteData.services?.join(', ')}
- Topic: ${keyword}
${blogTitle ? `- Related Blog: ${blogTitle}` : ''}

REQUIREMENTS:
- Caption: 150-300 characters, engaging and visual
- Hashtags: 5-10 relevant hashtags
- Call-to-action: Clear CTA
- Image suggestion: Description of ideal image/graphic
- Style: Visual, inspiring, professional

Return JSON:
{
  "caption": "Instagram caption text",
  "hashtags": ["hashtag1", "hashtag2", ...],
  "imageSuggestion": "Description of ideal image",
  "callToAction": "Link in bio|Swipe up|etc"
}

Return ONLY valid JSON.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 400,
        temperature: 0.9
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const post = JSON.parse(jsonContent);

      return {
        success: true,
        type: 'instagram',
        ...post,
        keyword: keyword
      };

    } catch (error) {
      console.error('❌ Error generating Instagram post:', error.message);
      return this.generateDemoInstagramPost(keyword);
    }
  }

  /**
   * Generate TikTok video script
   */
  async generateTikTokScript(websiteData, keyword, blogTitle = null) {
    try {
      console.log('🎵 Generating TikTok script for:', keyword);

      if (!this.openai) {
        return this.generateDemoTikTokScript(keyword);
      }

      const prompt = `Create an engaging TikTok video script for a ${websiteData.businessType} business.

CONTEXT:
- Business: ${websiteData.domain}
- Services: ${websiteData.services?.join(', ')}
- Topic: ${keyword}
${blogTitle ? `- Related Blog: ${blogTitle}` : ''}

REQUIREMENTS:
- Duration: 15-30 seconds
- Hook: First 3 seconds must grab attention
- Format: Scene-by-scene script
- Style: Casual, authentic, valuable
- Hashtags: 3-5 trending relevant hashtags
- CTA: Clear call-to-action at end

Return JSON:
{
  "hook": "Opening hook (first 3 seconds)",
  "script": "Full video script with scenes",
  "hashtags": ["hashtag1", "hashtag2", ...],
  "videoSuggestions": "Visual suggestions for filming",
  "duration": "15-30 seconds",
  "callToAction": "CTA text"
}

Return ONLY valid JSON.`;

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 500,
        temperature: 0.9
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const script = JSON.parse(jsonContent);

      return {
        success: true,
        type: 'tiktok',
        ...script,
        keyword: keyword
      };

    } catch (error) {
      console.error('❌ Error generating TikTok script:', error.message);
      return this.generateDemoTikTokScript(keyword);
    }
  }

  /**
   * Check if topic has been used before
   */
  async isTopicUsed(supabase, websiteId, topic, keyword) {
    try {
      const topicHash = this.generateHash(topic + keyword);
      
      const { data, error } = await supabase
        .from('content_memory')
        .select('id, topic, keyword')
        .eq('website_id', websiteId)
        .eq('content_hash', topicHash)
        .maybeSingle();

      if (data) {
        console.log('⚠️ Topic already used:', { topic, keyword });
        return true;
      }

      return false;
    } catch (error) {
      console.error('Error checking topic usage:', error);
      return false; // Assume not used if error
    }
  }

  /**
   * Get used topics for deduplication
   */
  async getUsedTopics(supabase, websiteId, contentType = null, limit = 50) {
    try {
      let query = supabase
        .from('content_memory')
        .select('topic, keyword')
        .eq('website_id', websiteId)
        .order('created_at', { ascending: false })
        .limit(limit);

      if (contentType) {
        query = query.eq('content_type', contentType);
      }

      const { data, error } = await query;

      if (error) {
        console.error('Error fetching used topics:', error);
        return [];
      }

      return data.map(d => d.topic);
    } catch (error) {
      console.error('Error getting used topics:', error);
      return [];
    }
  }

  /**
   * Store generated content in memory
   */
  async storeContentMemory(supabase, websiteId, contentType, content, keyword, targetDate = null) {
    try {
      const contentHash = this.generateHash(content.title || content.caption || content.content);
      
      const { data, error } = await supabase
        .from('content_memory')
        .insert({
          website_id: websiteId,
          content_type: contentType,
          keyword: keyword,
          topic: content.title || content.caption || keyword,
          content_hash: contentHash,
          full_content: JSON.stringify(content),
          metadata: {
            hashtags: content.hashtags || [],
            callToAction: content.callToAction || null,
            imageSuggestion: content.imageSuggestion || null
          },
          target_date: targetDate,
          status: 'draft'
        })
        .select()
        .single();

      if (error) {
        // If duplicate, that's okay - content memory working as intended
        if (error.code === '23505') {
          console.log('ℹ️ Content already exists in memory (duplicate prevention worked)');
          return { success: true, duplicate: true };
        }
        console.error('Error storing content memory:', error);
        return { success: false, error: error.message };
      }

      console.log('✅ Content stored in memory:', contentType, '-', content.title || keyword);
      return { success: true, data: data };

    } catch (error) {
      console.error('Error in storeContentMemory:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Generate content hash for duplicate detection
   */
  generateHash(text) {
    return crypto.createHash('sha256').update(text.toLowerCase().trim()).digest('hex');
  }

  /**
   * Generate complete content calendar for a month
   */
  async generateMonthlyContent(supabase, websiteId, crawlData, domain, plan = 'starter', month, year) {
    try {
      console.log(`📅 Generating monthly content for ${domain} (${plan} plan)`);

      // Step 1: Extract keywords and services from crawl data
      const extracted = await this.extractKeywordsAndServices(crawlData, domain);
      
      // Step 2: Get already used topics to avoid duplication
      const usedBlogTopics = await this.getUsedTopics(supabase, websiteId, 'blog');
      const usedSocialTopics = await this.getUsedTopics(supabase, websiteId, null, 100);

      // Step 3: Determine content limits based on plan from plan-limits-config.js
      const limits = this.getContentLimits(plan);
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      
      console.log('📊 Content limits from plan-limits-config.js:', { plan, limits });
      
      // Calculate content distribution
      const blogsPerMonth = limits.blogs;
      const socialPostsPerMonth = limits.socialPosts;
      const postsPerPlatform = Math.floor(socialPostsPerMonth / 3); // Divide among Twitter, Instagram, TikTok

      console.log('📊 Content distribution:', { blogsPerMonth, socialPostsPerMonth, postsPerPlatform });

      // Step 4: Generate content calendar
      const calendar = [];
      const keywords = extracted.primaryKeywords || [];
      const themes = extracted.contentThemes || [];

      // Generate blogs throughout the month
      const blogDays = this.distributeDaysEvenly(daysInMonth, blogsPerMonth);
      
      for (let i = 0; i < blogDays.length; i++) {
        const day = blogDays[i];
        const keyword = keywords[i % keywords.length];
        const targetDate = new Date(year, month, day);

        // Generate blog post
        const blogPost = await this.generateBlogPost(
          { ...extracted, domain },
          keyword,
          usedBlogTopics
        );

        if (blogPost.success) {
          // Store in content memory
          await this.storeContentMemory(supabase, websiteId, 'blog', blogPost, keyword, targetDate);

          // Generate social posts for this blog
          const socialPosts = await this.generateSocialPostsForBlog(
            { ...extracted, domain },
            keyword,
            blogPost.title
          );

          calendar.push({
            date: targetDate,
            day: day,
            content: {
              blog: blogPost,
              twitter: socialPosts.twitter,
              instagram: socialPosts.instagram,
              tiktok: socialPosts.tiktok
            }
          });

          // Store social posts in content memory
          if (socialPosts.twitter) {
            await this.storeContentMemory(supabase, websiteId, 'twitter', socialPosts.twitter, keyword, targetDate);
          }
          if (socialPosts.instagram) {
            await this.storeContentMemory(supabase, websiteId, 'instagram', socialPosts.instagram, keyword, targetDate);
          }
          if (socialPosts.tiktok) {
            await this.storeContentMemory(supabase, websiteId, 'tiktok', socialPosts.tiktok, keyword, targetDate);
          }
        }
      }

      // Generate additional standalone social posts
      const socialDays = this.distributeDaysEvenly(daysInMonth, postsPerPlatform - blogsPerMonth);
      
      for (let i = 0; i < Math.min(socialDays.length, 10); i++) {
        const day = socialDays[i];
        const theme = themes[i % themes.length];
        const targetDate = new Date(year, month, day);

        const socialPosts = await this.generateSocialPostsForBlog(
          { ...extracted, domain },
          theme,
          null
        );

        // Find existing calendar entry or create new
        let calendarEntry = calendar.find(c => c.day === day);
        if (!calendarEntry) {
          calendarEntry = {
            date: targetDate,
            day: day,
            content: {}
          };
          calendar.push(calendarEntry);
        }

        // Add social posts
        if (!calendarEntry.content.twitter && socialPosts.twitter) {
          calendarEntry.content.twitter = socialPosts.twitter;
          await this.storeContentMemory(supabase, websiteId, 'twitter', socialPosts.twitter, theme, targetDate);
        }
        if (!calendarEntry.content.instagram && socialPosts.instagram) {
          calendarEntry.content.instagram = socialPosts.instagram;
          await this.storeContentMemory(supabase, websiteId, 'instagram', socialPosts.instagram, theme, targetDate);
        }
      }

      console.log(`✅ Generated ${calendar.length} content items for the month`);

      return {
        success: true,
        calendar: calendar.sort((a, b) => a.day - b.day),
        metadata: {
          domain: domain,
          plan: plan,
          month: month,
          year: year,
          totalItems: calendar.length,
          blogsGenerated: blogDays.length,
          socialPostsGenerated: calendar.filter(c => c.content.twitter || c.content.instagram).length
        }
      };

    } catch (error) {
      console.error('❌ Error generating monthly content:', error);
      return {
        success: false,
        error: error.message,
        calendar: []
      };
    }
  }

  /**
   * Generate all social posts for a blog
   */
  async generateSocialPostsForBlog(websiteData, keyword, blogTitle) {
    const [twitter, instagram, tiktok] = await Promise.all([
      this.generateTwitterPost(websiteData, keyword, blogTitle),
      this.generateInstagramPost(websiteData, keyword, blogTitle),
      this.generateTikTokScript(websiteData, keyword, blogTitle)
    ]);

    return { twitter, instagram, tiktok };
  }

  /**
   * Distribute days evenly throughout the month
   */
  distributeDaysEvenly(daysInMonth, count) {
    if (count === 0) return [];
    if (count >= daysInMonth) return Array.from({ length: daysInMonth }, (_, i) => i + 1);

    const days = [];
    const interval = Math.floor(daysInMonth / count);

    for (let i = 0; i < count; i++) {
      const day = Math.min((i * interval) + Math.floor(interval / 2), daysInMonth);
      days.push(Math.max(1, day));
    }

    return days;
  }

  /**
   * Demo/fallback content generators
   */
  generateDemoBlogPost(keyword) {
    return {
      success: true,
      type: 'blog',
      title: `The Ultimate Guide to ${keyword}`,
      metaDescription: `Discover everything you need to know about ${keyword}. Expert tips, best practices, and actionable insights.`,
      content: `<h2>Introduction to ${keyword}</h2><p>Lorem ipsum dolor sit amet...</p>`,
      keywords: [keyword, `${keyword} tips`, `best ${keyword}`],
      excerpt: `Learn the essentials of ${keyword} and how to implement effective strategies for your business.`,
      estimatedReadTime: '5-7 min',
      seoScore: 75,
      keyword: keyword
    };
  }

  generateDemoTwitterPost(keyword) {
    return {
      success: true,
      type: 'twitter',
      content: `🚀 Mastering ${keyword}! Here are 3 quick tips to get started. Read our latest blog for the full guide! #${keyword.replace(/\s+/g, '')} #DigitalMarketing`,
      hashtags: [keyword.replace(/\s+/g, ''), 'DigitalMarketing'],
      callToAction: 'Read more',
      characterCount: 150,
      keyword: keyword
    };
  }

  generateDemoInstagramPost(keyword) {
    return {
      success: true,
      type: 'instagram',
      caption: `✨ Everything you need to know about ${keyword}! Swipe for tips 👉`,
      hashtags: [keyword.replace(/\s+/g, ''), 'DigitalMarketing', 'BusinessTips', 'Marketing', 'GrowthHacks'],
      imageSuggestion: `Professional graphic featuring ${keyword} with modern design`,
      callToAction: 'Link in bio',
      keyword: keyword
    };
  }

  generateDemoTikTokScript(keyword) {
    return {
      success: true,
      type: 'tiktok',
      hook: `Wait... you don't know about ${keyword}? 😱`,
      script: `Hook: "Wait... you don't know about ${keyword}?" \nScene 1: Show problem \nScene 2: Introduce solution \nScene 3: Quick demo \nEnd: CTA to learn more`,
      hashtags: [keyword.replace(/\s+/g, ''), 'Tutorial', 'LearnOnTikTok'],
      videoSuggestions: 'Quick cuts, energetic music, text overlays',
      duration: '15-30 seconds',
      callToAction: 'Follow for more tips',
      keyword: keyword
    };
  }

  /**
   * Check plan limits before generating content
   */
  async checkPlanLimits(supabase, websiteId, plan, month, year) {
    try {
      const startDate = new Date(year, month, 1);
      const endDate = new Date(year, month + 1, 0);

      // Count existing content for this month
      const { data: blogCount } = await supabase
        .from('content_memory')
        .select('id', { count: 'exact' })
        .eq('website_id', websiteId)
        .eq('content_type', 'blog')
        .gte('target_date', startDate.toISOString().split('T')[0])
        .lte('target_date', endDate.toISOString().split('T')[0]);

      const { data: socialCount } = await supabase
        .from('content_memory')
        .select('id', { count: 'exact' })
        .eq('website_id', websiteId)
        .in('content_type', ['twitter', 'instagram', 'tiktok'])
        .gte('target_date', startDate.toISOString().split('T')[0])
        .lte('target_date', endDate.toISOString().split('T')[0]);

      // Get limits from plan-limits-config.js
      const limits = this.getContentLimits(plan);
      const currentBlogCount = blogCount?.length || 0;
      const currentSocialCount = socialCount?.length || 0;

      console.log('📊 Plan limits from config:', { plan, limits });

      return {
        success: true,
        plan: plan,
        limits: limits,
        current: {
          blogs: currentBlogCount,
          socialPosts: currentSocialCount
        },
        canGenerate: {
          blogs: currentBlogCount < limits.blogs,
          socialPosts: currentSocialCount < limits.socialPosts
        },
        remaining: {
          blogs: Math.max(0, limits.blogs - currentBlogCount),
          socialPosts: Math.max(0, limits.socialPosts - currentSocialCount)
        }
      };
    } catch (error) {
      console.error('Error checking plan limits:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }
}

module.exports = new IntelligentContentGenerator();

