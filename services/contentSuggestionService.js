const OpenAI = require('openai');
const boostrampService = require('./boostrampService');

class ContentSuggestionService {
  constructor() {
    this.apiKey = process.env.OPENAI_API_KEY;
    this.openai = null;

    // Initialize OpenAI only if API key is available
    if (this.apiKey && this.apiKey !== 'your_openai_api_key_here' && this.apiKey.startsWith('sk-')) {
      try {
        this.openai = new OpenAI({
          apiKey: this.apiKey
        });
        console.log('✅ OpenAI API initialized successfully for content suggestions');
      } catch (error) {
        console.error('❌ Failed to initialize OpenAI API:', error.message);
        this.openai = null;
      }
    } else {
      console.log('⚠️ OpenAI API key not configured. Content suggestions will be limited.');
    }
  }

  // Generate comprehensive content suggestions based on website analysis
  async generateContentSuggestions(websiteAnalysis) {
    try {
      console.log('🔍 Generating AI-powered content suggestions...');

      const suggestions = {
        missingKeywords: await this.generateMissingKeywords(websiteAnalysis),
        contentIdeas: await this.generateContentIdeas(websiteAnalysis),
        visibilityBoost: await this.generateVisibilityStrategies(websiteAnalysis),
        technicalRecommendations: await this.generateTechnicalRecommendations(websiteAnalysis),
        competitorInsights: await this.generateCompetitorInsights(websiteAnalysis)
      };

      return {
        success: true,
        suggestions: suggestions,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Error generating content suggestions:', error.message);
      return {
        success: false,
        suggestions: this.generateFallbackSuggestions(websiteAnalysis),
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  // Generate missing keywords suggestions
  async generateMissingKeywords(analysis) {
    if (!this.openai) {
      return this.generateFallbackMissingKeywords(analysis);
    }

    try {
      const prompt = `Based on this website analysis, suggest 10 missing keywords that could improve SEO:

Website Data:
- Current keywords: ${analysis.keywords?.extracted?.join(', ') || 'None detected'}
- Content: ${analysis.content?.wordCount || 0} words
- Industry: ${this.detectIndustry(analysis)}
- Title: ${analysis.title || 'Missing'}

Suggest keywords that:
1. Are relevant to the business/industry
2. Have good search volume potential
3. Are not currently being targeted
4. Include long-tail variations
5. Consider local SEO if applicable

Format as a JSON array of keyword objects with "keyword", "searchVolume", "difficulty", and "reason" fields.`;

      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 800,
        temperature: 0.7
      });

      const response = completion.choices[0].message.content;
      return this.parseKeywordSuggestions(response);

    } catch (error) {
      console.error('Error generating missing keywords:', error.message);
      return this.generateFallbackMissingKeywords(analysis);
    }
  }

  // Generate content ideas
  async generateContentIdeas(analysis) {
    if (!this.openai) {
      return this.generateFallbackContentIdeas(analysis);
    }

    try {
      const prompt = `Based on this website analysis, suggest 5 content ideas that could improve SEO and user engagement:

Website Data:
- Current content: ${analysis.content?.wordCount || 0} words
- Keywords: ${analysis.keywords?.extracted?.join(', ') || 'None detected'}
- Industry: ${this.detectIndustry(analysis)}
- Current topics: ${this.extractTopics(analysis)}

Suggest content ideas that:
1. Target missing keywords
2. Provide value to users
3. Are likely to get backlinks
4. Address user questions/pain points
5. Include different content types (blog posts, guides, tools, etc.)

Format as a JSON array of content objects with "title", "type", "targetKeywords", "estimatedWords", and "valueProposition" fields.`;

      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1000,
        temperature: 0.7
      });

      const response = completion.choices[0].message.content;
      return this.parseContentIdeas(response);

    } catch (error) {
      console.error('Error generating content ideas:', error.message);
      return this.generateFallbackContentIdeas(analysis);
    }
  }

  // Generate visibility boost strategies
  async generateVisibilityStrategies(analysis) {
    if (!this.openai) {
      return this.generateFallbackVisibilityStrategies(analysis);
    }

    try {
      const prompt = `Based on this website analysis, suggest 5 strategies to boost visibility and rankings:

Website Data:
- SEO Score: ${analysis.score || 0}/100
- Current keywords: ${analysis.keywords?.extracted?.join(', ') || 'None detected'}
- Content length: ${analysis.content?.wordCount || 0} words
- Technical issues: ${this.identifyTechnicalIssues(analysis)}
- Link profile: ${analysis.links?.internal || 0} internal, ${analysis.links?.external || 0} external

Suggest strategies that:
1. Address current weaknesses
2. Leverage existing strengths
3. Are actionable and specific
4. Include both on-page and off-page tactics
5. Consider different timeframes (quick wins vs long-term)

Format as a JSON array of strategy objects with "strategy", "priority", "timeframe", "effort", and "expectedImpact" fields.`;

      const completion = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 1000,
        temperature: 0.7
      });

      const response = completion.choices[0].message.content;
      return this.parseVisibilityStrategies(response);

    } catch (error) {
      console.error('Error generating visibility strategies:', error.message);
      return this.generateFallbackVisibilityStrategies(analysis);
    }
  }

  // Generate technical recommendations
  async generateTechnicalRecommendations(analysis) {
    const recommendations = [];

    // Title optimization
    if (!analysis.title) {
      recommendations.push({
        category: 'Title Optimization',
        issue: 'Missing page title',
        priority: 'High',
        solution: 'Add a compelling title tag (50-60 characters) that includes your primary keyword',
        impact: 'Critical for SEO and user experience'
      });
    } else if (analysis.title.length < 30 || analysis.title.length > 60) {
      recommendations.push({
        category: 'Title Optimization',
        issue: `Title length issue (${analysis.title.length} characters)`,
        priority: 'Medium',
        solution: 'Optimize title length to 50-60 characters for better SERP display',
        impact: 'Improves click-through rates from search results'
      });
    }

    // Meta description optimization
    if (!analysis.metaDescription) {
      recommendations.push({
        category: 'Meta Description',
        issue: 'Missing meta description',
        priority: 'High',
        solution: 'Add a compelling meta description (150-160 characters) with a call-to-action',
        impact: 'Improves click-through rates and search visibility'
      });
    } else if (analysis.metaDescription.length < 120 || analysis.metaDescription.length > 160) {
      recommendations.push({
        category: 'Meta Description',
        issue: `Meta description length issue (${analysis.metaDescription.length} characters)`,
        priority: 'Medium',
        solution: 'Optimize meta description length to 150-160 characters',
        impact: 'Better SERP display and improved click-through rates'
      });
    }

    // Image optimization
    if (analysis.images?.missingAlt > 0) {
      recommendations.push({
        category: 'Image Optimization',
        issue: `${analysis.images.missingAlt} images missing alt text`,
        priority: 'Medium',
        solution: 'Add descriptive alt text to all images for accessibility and SEO',
        impact: 'Improves accessibility and image search rankings'
      });
    }

    // Heading structure
    if (analysis.headings?.h1 === 0) {
      recommendations.push({
        category: 'Heading Structure',
        issue: 'No H1 tag found',
        priority: 'High',
        solution: 'Add an H1 tag with your primary keyword',
        impact: 'Critical for page structure and SEO'
      });
    } else if (analysis.headings?.h1 > 1) {
      recommendations.push({
        category: 'Heading Structure',
        issue: `Multiple H1 tags (${analysis.headings.h1})`,
        priority: 'Medium',
        solution: 'Use only one H1 tag per page for better SEO structure',
        impact: 'Improves page hierarchy and SEO performance'
      });
    }

    // Content length
    if (analysis.content?.wordCount < 300) {
      recommendations.push({
        category: 'Content Optimization',
        issue: `Content too short (${analysis.content.wordCount} words)`,
        priority: 'Medium',
        solution: 'Increase content length to at least 300 words for better SEO',
        impact: 'Improves keyword density and user engagement'
      });
    }

    // SSL certificate
    if (!analysis.technical?.sslCertificate) {
      recommendations.push({
        category: 'Security',
        issue: 'No SSL certificate',
        priority: 'High',
        solution: 'Install SSL certificate to enable HTTPS',
        impact: 'Critical for user trust and SEO ranking factors'
      });
    }

    // Mobile optimization
    if (!analysis.technical?.mobileFriendly) {
      recommendations.push({
        category: 'Mobile Optimization',
        issue: 'Not mobile-friendly',
        priority: 'High',
        solution: 'Add viewport meta tag and ensure responsive design',
        impact: 'Critical for mobile search rankings and user experience'
      });
    }

    return recommendations;
  }

  // Generate competitor insights
  async generateCompetitorInsights(analysis) {
    return [
      {
        insight: 'Industry Analysis',
        description: 'Based on your content and keywords, you appear to be in a competitive market',
        recommendation: 'Focus on long-tail keywords and niche topics to differentiate',
        priority: 'Medium'
      },
      {
        insight: 'Content Gap Analysis',
        description: 'Your content length suggests room for expansion',
        recommendation: 'Create comprehensive guides and resources to compete with industry leaders',
        priority: 'High'
      },
      {
        insight: 'Technical Advantage',
        description: 'Address technical SEO issues to gain competitive advantage',
        recommendation: 'Fix basic technical issues before competitors do',
        priority: 'High'
      }
    ];
  }

  // Helper methods
  detectIndustry(analysis) {
    const keywords = analysis.keywords?.extracted || [];
    const title = analysis.title || '';
    const content = analysis.content?.wordCount || 0;
    
    // Simple industry detection based on keywords
    if (keywords.some(k => ['business', 'service', 'company'].includes(k))) {
      return 'Business Services';
    } else if (keywords.some(k => ['tech', 'software', 'digital'].includes(k))) {
      return 'Technology';
    } else if (keywords.some(k => ['health', 'medical', 'care'].includes(k))) {
      return 'Healthcare';
    } else if (keywords.some(k => ['education', 'learning', 'course'].includes(k))) {
      return 'Education';
    } else {
      return 'General Business';
    }
  }

  extractTopics(analysis) {
    const keywords = analysis.keywords?.extracted || [];
    return keywords.slice(0, 5).join(', ');
  }

  identifyTechnicalIssues(analysis) {
    const issues = [];
    if (!analysis.title) issues.push('Missing title');
    if (!analysis.metaDescription) issues.push('Missing meta description');
    if (analysis.images?.missingAlt > 0) issues.push('Missing alt text');
    if (!analysis.technical?.sslCertificate) issues.push('No SSL');
    if (!analysis.technical?.mobileFriendly) issues.push('Not mobile-friendly');
    return issues.join(', ') || 'None detected';
  }

  // Fallback methods when OpenAI is not available
  generateFallbackSuggestions(analysis) {
    return {
      missingKeywords: this.generateFallbackMissingKeywords(analysis),
      contentIdeas: this.generateFallbackContentIdeas(analysis),
      visibilityBoost: this.generateFallbackVisibilityStrategies(analysis),
      technicalRecommendations: this.generateTechnicalRecommendations(analysis),
      competitorInsights: this.generateCompetitorInsights(analysis)
    };
  }

  generateFallbackMissingKeywords(analysis) {
    const industry = this.detectIndustry(analysis);
    const baseKeywords = analysis.keywords?.extracted || [];
    
    const suggestions = [
      { keyword: `${industry.toLowerCase()} services`, searchVolume: 'Medium', difficulty: 'Medium', reason: 'Industry-specific service keyword' },
      { keyword: `best ${industry.toLowerCase()} company`, searchVolume: 'High', difficulty: 'High', reason: 'Commercial intent keyword' },
      { keyword: `${industry.toLowerCase()} solutions`, searchVolume: 'Medium', difficulty: 'Medium', reason: 'Solution-focused keyword' },
      { keyword: `professional ${industry.toLowerCase()}`, searchVolume: 'Low', difficulty: 'Low', reason: 'Long-tail professional keyword' },
      { keyword: `${industry.toLowerCase()} experts`, searchVolume: 'Medium', difficulty: 'Medium', reason: 'Authority-building keyword' }
    ];

    return suggestions.filter(s => !baseKeywords.includes(s.keyword)).slice(0, 5);
  }

  generateFallbackContentIdeas(analysis) {
    const industry = this.detectIndustry(analysis);
    
    return [
      {
        title: `Complete Guide to ${industry}`,
        type: 'Comprehensive Guide',
        targetKeywords: [`${industry.toLowerCase()} guide`, `${industry.toLowerCase()} tips`],
        estimatedWords: 2000,
        valueProposition: 'Comprehensive resource that establishes authority and targets multiple keywords'
      },
      {
        title: `Top 10 ${industry} Best Practices`,
        type: 'List Article',
        targetKeywords: [`${industry.toLowerCase()} best practices`, `${industry.toLowerCase()} tips`],
        estimatedWords: 1500,
        valueProposition: 'List format that is easy to read and share'
      },
      {
        title: `How to Choose the Right ${industry} Service`,
        type: 'How-to Guide',
        targetKeywords: [`choose ${industry.toLowerCase()}`, `${industry.toLowerCase()} selection`],
        estimatedWords: 1200,
        valueProposition: 'Addresses common customer questions and pain points'
      },
      {
        title: `${industry} Trends for 2024`,
        type: 'Trend Analysis',
        targetKeywords: [`${industry.toLowerCase()} trends`, `${industry.toLowerCase()} 2024`],
        estimatedWords: 1000,
        valueProposition: 'Timely content that can attract backlinks'
      },
      {
        title: `Common ${industry} Mistakes to Avoid`,
        type: 'Warning Guide',
        targetKeywords: [`${industry.toLowerCase()} mistakes`, `${industry.toLowerCase()} errors`],
        estimatedWords: 800,
        valueProposition: 'Negative keywords that often have less competition'
      }
    ];
  }

  generateFallbackVisibilityStrategies(analysis) {
    const score = analysis.score || 0;
    const strategies = [];

    if (score < 50) {
      strategies.push({
        strategy: 'Fix Basic Technical Issues',
        priority: 'High',
        timeframe: '1-2 weeks',
        effort: 'Medium',
        expectedImpact: 'Significant improvement in SEO score'
      });
    }

    strategies.push({
      strategy: 'Create High-Quality Content',
      priority: 'High',
      timeframe: '1-3 months',
      effort: 'High',
      expectedImpact: 'Improved rankings and organic traffic'
    });

    strategies.push({
      strategy: 'Build Quality Backlinks',
      priority: 'Medium',
      timeframe: '3-6 months',
      effort: 'High',
      expectedImpact: 'Increased domain authority and rankings'
    });

    strategies.push({
      strategy: 'Optimize for Local SEO',
      priority: 'Medium',
      timeframe: '2-4 weeks',
      effort: 'Medium',
      expectedImpact: 'Better local search visibility'
    });

    strategies.push({
      strategy: 'Improve User Experience',
      priority: 'Medium',
      timeframe: '1-2 months',
      effort: 'Medium',
      expectedImpact: 'Better engagement metrics and rankings'
    });

    return strategies;
  }

  // Parse AI responses
  parseKeywordSuggestions(response) {
    try {
      // Try to parse JSON response
      const jsonMatch = response.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      // Fallback to text parsing
    }
    
    // Fallback parsing
    return this.generateFallbackMissingKeywords({});
  }

  parseContentIdeas(response) {
    try {
      const jsonMatch = response.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      // Fallback to text parsing
    }
    
    return this.generateFallbackContentIdeas({});
  }

  parseVisibilityStrategies(response) {
    try {
      const jsonMatch = response.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      // Fallback to text parsing
    }
    
    return this.generateFallbackVisibilityStrategies({});
  }
}

module.exports = new ContentSuggestionService();
