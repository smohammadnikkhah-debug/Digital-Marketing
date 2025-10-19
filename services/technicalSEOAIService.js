const OpenAI = require('openai');

class TechnicalSEOAIService {
  constructor() {
    this.openai = null;
    const apiKey = process.env.OPENAI_API_KEY;
    
    if (apiKey && apiKey !== 'your_openai_api_key_here' && apiKey.startsWith('sk-')) {
      try {
        this.openai = new OpenAI({ apiKey });
        console.log('✅ Technical SEO AI Service initialized successfully');
      } catch (error) {
        console.error('❌ Failed to initialize OpenAI API:', error.message);
      }
    } else {
      console.log('⚠️ OpenAI API key not configured for Technical SEO AI Service');
    }
  }

  // Generate Meta Optimization recommendations
  async generateMetaOptimizationRecommendations(crawlData) {
    try {
      console.log('🏷️ Generating Meta Optimization recommendations...');
      
      if (!crawlData) {
        console.error('❌ No crawl data provided');
        throw new Error('No crawl data provided');
      }
      
      const pages = crawlData.onPage?.pages || [];
      console.log('📊 Pages available for meta analysis:', pages.length);
      
      if (pages.length === 0) {
        console.warn('⚠️ No pages found in crawl data, using fallback');
        return this.getFallbackMetaRecommendations([], crawlData.domain);
      }
      
      // Extract meta data from pages
      const metaData = pages.slice(0, 10).map(page => ({
        url: page.url,
        title: page.title,
        titleLength: (page.title || '').length,
        metaDescription: page.meta?.description,
        metaDescriptionLength: (page.meta?.description || '').length,
        h1: page.meta?.htags?.h1,
        canonical: page.meta?.canonical
      }));
      
      console.log('📊 Meta data extracted:', { pages: metaData.length });

      const prompt = `As an expert SEO consultant, analyze the following meta optimization data and provide specific, actionable recommendations:

META OPTIMIZATION DATA:
${JSON.stringify(metaData, null, 2)}

Domain: ${crawlData.domain}
Total Pages Analyzed: ${metaData.length}

Provide detailed recommendations in the following JSON format:
{
  "score": <number 0-100>,
  "summary": "<brief overview>",
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "<issue title>",
      "description": "<detailed description>",
      "affectedPages": ["<url1>", "<url2>"],
      "recommendation": "<specific action to take>"
    }
  ],
  "quickWins": [
    "<actionable quick win 1>",
    "<actionable quick win 2>"
  ],
  "bestPractices": [
    "<best practice recommendation 1>",
    "<best practice recommendation 2>"
  ]
}

Focus on:
1. Title tag optimization (length, keywords, uniqueness)
2. Meta description optimization (length, CTR optimization)
3. H1 tag optimization (presence, uniqueness, keyword usage)
4. Canonical tag issues
5. Missing or duplicate meta tags

Return ONLY valid JSON, no markdown or additional text.`;

      if (!this.openai) {
        return this.getFallbackMetaRecommendations(metaData, crawlData.domain);
      }

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2000,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      // Remove markdown code blocks if present
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const recommendations = JSON.parse(jsonContent);

      return {
        success: true,
        category: 'Meta Optimization',
        ...recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Meta Optimization AI Error:', error.message);
      console.error('Error stack:', error.stack);
      return this.getFallbackMetaRecommendations(crawlData?.onPage?.pages || [], crawlData?.domain || 'unknown');
    }
  }

  // Generate Content Improvements recommendations
  async generateContentImprovementsRecommendations(crawlData) {
    try {
      const pages = crawlData.onPage?.pages || [];
      
      // Extract content data from pages
      const contentData = pages.slice(0, 10).map(page => ({
        url: page.url,
        wordCount: page.content?.plainTextSize || 0,
        headings: {
          h1: page.meta?.htags?.h1?.length || 0,
          h2: page.meta?.htags?.h2?.length || 0,
          h3: page.meta?.htags?.h3?.length || 0
        },
        internalLinks: page.links_count || 0,
        images: page.meta?.images || 0
      }));

      const prompt = `As an expert content strategist, analyze the following content data and provide specific, actionable recommendations:

CONTENT DATA:
${JSON.stringify(contentData, null, 2)}

Domain: ${crawlData.domain}
Total Pages Analyzed: ${contentData.length}

Provide detailed recommendations in the following JSON format:
{
  "score": <number 0-100>,
  "summary": "<brief overview>",
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "<issue title>",
      "description": "<detailed description>",
      "affectedPages": ["<url1>", "<url2>"],
      "recommendation": "<specific action to take>"
    }
  ],
  "quickWins": [
    "<actionable quick win 1>",
    "<actionable quick win 2>"
  ],
  "bestPractices": [
    "<best practice recommendation 1>",
    "<best practice recommendation 2>"
  ]
}

Focus on:
1. Content length optimization (thin content issues)
2. Heading structure and hierarchy
3. Internal linking strategy
4. Content freshness and relevance
5. Keyword usage and density

Return ONLY valid JSON, no markdown or additional text.`;

      if (!this.openai) {
        return this.getFallbackContentRecommendations(contentData, crawlData.domain);
      }

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2000,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const recommendations = JSON.parse(jsonContent);

      return {
        success: true,
        category: 'Content Improvements',
        ...recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Content Improvements AI Error:', error);
      return this.getFallbackContentRecommendations(crawlData.onPage?.pages || [], crawlData.domain);
    }
  }

  // Generate Technical Fixes recommendations
  async generateTechnicalFixesRecommendations(crawlData) {
    try {
      const pages = crawlData.onPage?.pages || [];
      
      // Extract technical data from pages
      const technicalData = {
        totalPages: pages.length,
        statusCodes: pages.reduce((acc, page) => {
          const code = page.status_code || 200;
          acc[code] = (acc[code] || 0) + 1;
          return acc;
        }, {}),
        redirectChains: pages.filter(p => p.redirect_url).length,
        brokenLinks: pages.filter(p => p.broken_links > 0).length,
        crawlDepth: pages.map(p => p.depth || 0),
        robotsTxt: crawlData.onPage?.robotsTxt || 'unknown',
        sitemapXml: crawlData.onPage?.sitemapXml || 'unknown'
      };

      const prompt = `As an expert technical SEO specialist, analyze the following technical SEO data and provide specific, actionable recommendations:

TECHNICAL SEO DATA:
${JSON.stringify(technicalData, null, 2)}

Domain: ${crawlData.domain}
Total Pages: ${pages.length}

Provide detailed recommendations in the following JSON format:
{
  "score": <number 0-100>,
  "summary": "<brief overview>",
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "<issue title>",
      "description": "<detailed description>",
      "affectedPages": ["<url1>", "<url2>"],
      "recommendation": "<specific action to take>"
    }
  ],
  "quickWins": [
    "<actionable quick win 1>",
    "<actionable quick win 2>"
  ],
  "bestPractices": [
    "<best practice recommendation 1>",
    "<best practice recommendation 2>"
  ]
}

Focus on:
1. HTTP status code issues (404s, 500s, 301s)
2. Redirect chains and loops
3. Broken internal/external links
4. Robots.txt optimization
5. XML sitemap issues
6. Crawl depth and site architecture

Return ONLY valid JSON, no markdown or additional text.`;

      if (!this.openai) {
        return this.getFallbackTechnicalRecommendations(technicalData, crawlData.domain);
      }

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2000,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const recommendations = JSON.parse(jsonContent);

      return {
        success: true,
        category: 'Technical Fixes',
        ...recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Technical Fixes AI Error:', error);
      return this.getFallbackTechnicalRecommendations({}, crawlData.domain);
    }
  }

  // Generate Images recommendations
  async generateImagesRecommendations(crawlData) {
    try {
      const pages = crawlData.onPage?.pages || [];
      
      // Extract image data from pages
      const imageData = pages.slice(0, 10).map(page => ({
        url: page.url,
        totalImages: page.meta?.images || 0,
        imagesWithoutAlt: page.meta?.images_without_alt || 0,
        imageSize: page.meta?.images_size || 0
      }));

      const prompt = `As an expert SEO specialist, analyze the following image optimization data and provide specific, actionable recommendations:

IMAGE OPTIMIZATION DATA:
${JSON.stringify(imageData, null, 2)}

Domain: ${crawlData.domain}
Total Pages Analyzed: ${imageData.length}

Provide detailed recommendations in the following JSON format:
{
  "score": <number 0-100>,
  "summary": "<brief overview>",
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "<issue title>",
      "description": "<detailed description>",
      "affectedPages": ["<url1>", "<url2>"],
      "recommendation": "<specific action to take>"
    }
  ],
  "quickWins": [
    "<actionable quick win 1>",
    "<actionable quick win 2>"
  ],
  "bestPractices": [
    "<best practice recommendation 1>",
    "<best practice recommendation 2>"
  ]
}

Focus on:
1. Missing alt text optimization
2. Image file size optimization
3. Image format recommendations (WebP, AVIF)
4. Lazy loading implementation
5. Responsive image techniques

Return ONLY valid JSON, no markdown or additional text.`;

      if (!this.openai) {
        return this.getFallbackImagesRecommendations(imageData, crawlData.domain);
      }

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2000,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const recommendations = JSON.parse(jsonContent);

      return {
        success: true,
        category: 'Images',
        ...recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Images AI Error:', error);
      return this.getFallbackImagesRecommendations([], crawlData.domain);
    }
  }

  // Generate Performance recommendations
  async generatePerformanceRecommendations(crawlData) {
    try {
      const pages = crawlData.onPage?.pages || [];
      
      // Extract performance data from pages
      const performanceData = pages.slice(0, 10).map(page => ({
        url: page.url,
        loadTime: page.page_timing?.time_to_interactive || 0,
        pageSize: page.total_transfer_size || 0,
        resourcesCount: page.resources?.length || 0,
        domContentLoaded: page.page_timing?.dom_complete || 0
      }));

      const prompt = `As an expert web performance specialist, analyze the following performance data and provide specific, actionable recommendations:

PERFORMANCE DATA:
${JSON.stringify(performanceData, null, 2)}

Domain: ${crawlData.domain}
Total Pages Analyzed: ${performanceData.length}

Provide detailed recommendations in the following JSON format:
{
  "score": <number 0-100>,
  "summary": "<brief overview>",
  "issues": [
    {
      "severity": "high|medium|low",
      "title": "<issue title>",
      "description": "<detailed description>",
      "affectedPages": ["<url1>", "<url2>"],
      "recommendation": "<specific action to take>"
    }
  ],
  "quickWins": [
    "<actionable quick win 1>",
    "<actionable quick win 2>"
  ],
  "bestPractices": [
    "<best practice recommendation 1>",
    "<best practice recommendation 2>"
  ]
}

Focus on:
1. Page load time optimization
2. Resource optimization (CSS, JS, images)
3. Caching strategies
4. Core Web Vitals (LCP, FID, CLS)
5. Mobile performance optimization
6. CDN implementation

Return ONLY valid JSON, no markdown or additional text.`;

      if (!this.openai) {
        return this.getFallbackPerformanceRecommendations(performanceData, crawlData.domain);
      }

      const response = await this.openai.chat.completions.create({
        model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 2000,
        temperature: 0.7
      });

      const content = response.choices[0].message.content.trim();
      const jsonContent = content.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
      const recommendations = JSON.parse(jsonContent);

      return {
        success: true,
        category: 'Performance',
        ...recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('Performance AI Error:', error);
      return this.getFallbackPerformanceRecommendations([], crawlData.domain);
    }
  }

  // Fallback recommendations when OpenAI is not available
  getFallbackMetaRecommendations(metaData, domain) {
    const issues = [];
    let score = 100;

    metaData.forEach(page => {
      if (!page.title || page.titleLength === 0) {
        issues.push({
          severity: 'high',
          title: 'Missing Title Tag',
          description: `Page ${page.url} is missing a title tag`,
          affectedPages: [page.url],
          recommendation: 'Add a unique, descriptive title tag (50-60 characters) with your primary keyword'
        });
        score -= 10;
      } else if (page.titleLength > 60) {
        issues.push({
          severity: 'medium',
          title: 'Title Tag Too Long',
          description: `Title tag is ${page.titleLength} characters`,
          affectedPages: [page.url],
          recommendation: 'Shorten title to 50-60 characters for optimal SERP display'
        });
        score -= 5;
      }

      if (!page.metaDescription || page.metaDescriptionLength === 0) {
        issues.push({
          severity: 'medium',
          title: 'Missing Meta Description',
          description: `Page ${page.url} is missing a meta description`,
          affectedPages: [page.url],
          recommendation: 'Add a compelling meta description (150-160 characters) with a call-to-action'
        });
        score -= 5;
      }
    });

    return {
      success: true,
      category: 'Meta Optimization',
      score: Math.max(score, 0),
      summary: `Analyzed ${metaData.length} pages for meta optimization. ${issues.length} issues found.`,
      issues: issues.slice(0, 10),
      quickWins: [
        'Add missing title tags to all pages',
        'Ensure all title tags are 50-60 characters',
        'Add unique meta descriptions to all pages',
        'Include primary keywords in title tags'
      ],
      bestPractices: [
        'Use unique title tags for each page',
        'Include target keywords naturally in titles and descriptions',
        'Write compelling meta descriptions that encourage clicks',
        'Keep titles under 60 characters and descriptions under 160 characters'
      ],
      timestamp: new Date().toISOString()
    };
  }

  getFallbackContentRecommendations(contentData, domain) {
    const issues = [];
    let score = 100;

    contentData.forEach(page => {
      if (page.wordCount < 300) {
        issues.push({
          severity: 'high',
          title: 'Thin Content',
          description: `Page has only ${page.wordCount} words`,
          affectedPages: [page.url],
          recommendation: 'Expand content to at least 300 words with valuable, relevant information'
        });
        score -= 10;
      }

      if (page.headings.h1 === 0) {
        issues.push({
          severity: 'high',
          title: 'Missing H1 Tag',
          description: 'Page is missing an H1 tag',
          affectedPages: [page.url],
          recommendation: 'Add a single, descriptive H1 tag with your primary keyword'
        });
        score -= 10;
      }
    });

    return {
      success: true,
      category: 'Content Improvements',
      score: Math.max(score, 0),
      summary: `Analyzed ${contentData.length} pages for content quality. ${issues.length} issues found.`,
      issues: issues.slice(0, 10),
      quickWins: [
        'Add H1 tags to pages that are missing them',
        'Expand thin content pages to 300+ words',
        'Improve internal linking between related pages',
        'Add more H2/H3 subheadings for better structure'
      ],
      bestPractices: [
        'Aim for 800-1500 words per page for better rankings',
        'Use clear heading hierarchy (H1, H2, H3)',
        'Include 3-5 internal links per page',
        'Update content regularly to keep it fresh'
      ],
      timestamp: new Date().toISOString()
    };
  }

  getFallbackTechnicalRecommendations(technicalData, domain) {
    return {
      success: true,
      category: 'Technical Fixes',
      score: 75,
      summary: `Technical SEO analysis complete. Several optimization opportunities identified.`,
      issues: [
        {
          severity: 'high',
          title: 'Fix 404 Errors',
          description: 'Multiple pages returning 404 status codes',
          affectedPages: [],
          recommendation: 'Identify and fix all broken pages or implement proper 301 redirects'
        },
        {
          severity: 'medium',
          title: 'Optimize Redirect Chains',
          description: 'Multiple redirect chains detected',
          affectedPages: [],
          recommendation: 'Reduce redirect chains to direct 301 redirects'
        }
      ],
      quickWins: [
        'Submit XML sitemap to Google Search Console',
        'Fix broken internal links',
        'Optimize robots.txt file',
        'Implement proper canonical tags'
      ],
      bestPractices: [
        'Keep crawl depth under 3 clicks from homepage',
        'Use 301 redirects for moved pages',
        'Maintain clean URL structure',
        'Regular technical audits monthly'
      ],
      timestamp: new Date().toISOString()
    };
  }

  getFallbackImagesRecommendations(imageData, domain) {
    const issues = [];
    let score = 100;

    imageData.forEach(page => {
      if (page.imagesWithoutAlt > 0) {
        issues.push({
          severity: 'medium',
          title: 'Missing Image Alt Text',
          description: `${page.imagesWithoutAlt} images without alt text`,
          affectedPages: [page.url],
          recommendation: 'Add descriptive alt text to all images for better accessibility and SEO'
        });
        score -= 5;
      }
    });

    return {
      success: true,
      category: 'Images',
      score: Math.max(score, 0),
      summary: `Analyzed images across ${imageData.length} pages. ${issues.length} issues found.`,
      issues: issues.slice(0, 10),
      quickWins: [
        'Add alt text to all images',
        'Compress large image files',
        'Convert images to WebP format',
        'Implement lazy loading'
      ],
      bestPractices: [
        'Use descriptive, keyword-rich alt text',
        'Keep image file sizes under 100KB',
        'Use modern image formats (WebP, AVIF)',
        'Implement responsive images for different devices'
      ],
      timestamp: new Date().toISOString()
    };
  }

  getFallbackPerformanceRecommendations(performanceData, domain) {
    return {
      success: true,
      category: 'Performance',
      score: 70,
      summary: `Performance analysis complete. Several optimization opportunities for faster load times.`,
      issues: [
        {
          severity: 'high',
          title: 'Slow Page Load Times',
          description: 'Pages taking longer than 3 seconds to load',
          affectedPages: [],
          recommendation: 'Optimize images, enable compression, and minimize HTTP requests'
        },
        {
          severity: 'medium',
          title: 'Large Page Sizes',
          description: 'Page sizes exceeding recommended limits',
          affectedPages: [],
          recommendation: 'Reduce page size by compressing resources and removing unused code'
        }
      ],
      quickWins: [
        'Enable Gzip compression',
        'Optimize and compress images',
        'Minify CSS and JavaScript files',
        'Enable browser caching'
      ],
      bestPractices: [
        'Target page load time under 3 seconds',
        'Optimize Core Web Vitals (LCP, FID, CLS)',
        'Use a CDN for static assets',
        'Implement lazy loading for images and videos'
      ],
      timestamp: new Date().toISOString()
    };
  }
}

module.exports = new TechnicalSEOAIService();

