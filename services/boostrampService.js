const axios = require('axios');
const cheerio = require('cheerio');

class BoostrampService {
  constructor() {
    this.apiKey = process.env.BOOSTRAMP_API_KEY;
    this.baseUrl = process.env.BOOSTRAMP_BASE_URL || 'https://app.boostramp.com/api';
    this.defaultLocationCode = process.env.DEFAULT_LOCATION_CODE || 1;
    this.sessionToken = null;
  }

  // Authenticate with Boostramp API and get session token
  async authenticate() {
    try {
      if (!this.apiKey || this.apiKey === 'your_api_key_here' || this.apiKey === null) {
        throw new Error('Boostramp API key not configured. Please set BOOSTRAMP_API_KEY environment variable.');
      }

      const response = await axios.post(`${this.baseUrl}/login.php`, {
        api_key: this.apiKey
      });

      if (response.data && response.data.token) {
        this.sessionToken = response.data.token;
        console.log('✅ Successfully authenticated with Boostramp API');
        return true;
      } else {
        throw new Error('Failed to authenticate with Boostramp API');
      }
    } catch (error) {
      console.error('❌ Boostramp authentication error:', error.message);
      throw error;
    }
  }

  // Create a new project for the website
  async createProject(url) {
    try {
      if (!this.sessionToken) {
        await this.authenticate();
      }

      const response = await axios.post(`${this.baseUrl}/project.php?func=create`, {
        token: this.sessionToken,
        url: url,
        name: `SEO Analysis - ${new URL(url).hostname}`
      });

      return response.data;
    } catch (error) {
      console.error('❌ Error creating project:', error.message);
      throw error;
    }
  }

  // Get on-page SEO analysis
  async getOnPageAnalysis(projectId) {
    try {
      if (!this.sessionToken) {
        await this.authenticate();
      }

      const response = await axios.get(`${this.baseUrl}/page.php?func=getPages`, {
        params: {
          token: this.sessionToken,
          project_id: projectId
        }
      });

      return response.data;
    } catch (error) {
      console.error('❌ Error getting on-page analysis:', error.message);
      throw error;
    }
  }

  // Get backlink analysis
  async getBacklinkAnalysis(projectId) {
    try {
      if (!this.sessionToken) {
        await this.authenticate();
      }

      const response = await axios.get(`${this.baseUrl}/backlink.php?func=getBacklinks`, {
        params: {
          token: this.sessionToken,
          project_id: projectId
        }
      });

      return response.data;
    } catch (error) {
      console.error('❌ Error getting backlink analysis:', error.message);
      throw error;
    }
  }

  // Get keyword suggestions
  async getKeywordSuggestions(keyword, locationCode = null) {
    try {
      if (!this.sessionToken) {
        await this.authenticate();
      }

      const response = await axios.get(`${this.baseUrl}/tools.php?func=getKeywords`, {
        params: {
          token: this.sessionToken,
          keyword: keyword,
          location_code: locationCode || this.defaultLocationCode
        }
      });

      return response.data;
    } catch (error) {
      console.error('❌ Error getting keyword suggestions:', error.message);
      throw error;
    }
  }

  // Perform comprehensive web scraping analysis
  async scrapeWebsite(url) {
    try {
      const startTime = Date.now();
      const response = await axios.get(url, {
        timeout: 15000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
      });
      const loadTime = Date.now() - startTime;

      const $ = cheerio.load(response.data);
      const hostname = new URL(url).hostname;
      
      // Extract comprehensive SEO elements
      const analysis = {
        // Basic SEO
        title: $('title').text().trim(),
        metaDescription: $('meta[name="description"]').attr('content') || '',
        metaKeywords: $('meta[name="keywords"]').attr('content') || '',
        
        // Performance metrics
        performance: {
          loadTime: `${(loadTime / 1000).toFixed(2)}s`,
          pageSize: Math.round(response.data.length / 1024), // KB
          responseTime: loadTime
        },
        
        // Heading structure
        headings: {
          h1: $('h1').length,
          h2: $('h2').length,
          h3: $('h3').length,
          h4: $('h4').length,
          h5: $('h5').length,
          h6: $('h6').length,
          h1Text: $('h1').map((i, el) => $(el).text().trim()).get(),
          h2Text: $('h2').map((i, el) => $(el).text().trim()).get(),
          h3Text: $('h3').map((i, el) => $(el).text().trim()).get()
        },
        
        // Image analysis
        images: {
          total: $('img').length,
          missingAlt: $('img:not([alt])').length,
          oversized: $('img').filter((i, el) => {
            const width = $(el).attr('width');
            const height = $(el).attr('height');
            return width && height && (parseInt(width) > 1920 || parseInt(height) > 1080);
          }).length,
          lazyLoaded: $('img[loading="lazy"]').length,
          webpFormat: $('img[src*=".webp"]').length
        },
        
        // Comprehensive link analysis
        links: {
          internal: $('a[href^="/"], a[href*="' + hostname + '"]').length,
          external: $('a[href^="http"]').not(`a[href*="${hostname}"]`).length,
          noFollow: $('a[rel*="nofollow"]').length,
          externalDomains: this.extractExternalDomains($, hostname),
          internalPages: this.extractInternalPages($, hostname),
          brokenLinks: 0, // Would need additional checking
          socialLinks: this.extractSocialLinks($),
          totalLinks: $('a[href]').length,
          linksWithoutText: $('a[href]:not(:has(*))').filter((i, el) => $(el).text().trim() === '').length
        },
        
        // Technical SEO
        technical: {
          canonical: $('link[rel="canonical"]').attr('href') || '',
          robots: $('meta[name="robots"]').attr('content') || '',
          viewport: $('meta[name="viewport"]').attr('content') || '',
          charset: $('meta[charset]').attr('charset') || '',
          language: $('html').attr('lang') || '',
          openGraph: this.extractOpenGraph($),
          twitterCard: this.extractTwitterCard($),
          schemaMarkup: this.extractSchemaMarkup($),
          sitemap: $('link[rel="sitemap"]').attr('href') || '',
          favicon: $('link[rel="icon"]').attr('href') || '',
          sslCertificate: url.startsWith('https:'),
          mobileFriendly: this.checkMobileFriendly($)
        },
        
        // Content analysis
        content: {
          wordCount: this.countWords($('body').text()),
          paragraphCount: $('p').length,
          listCount: $('ul, ol').length,
          formCount: $('form').length,
          scriptCount: $('script').length,
          stylesheetCount: $('link[rel="stylesheet"]').length,
          readabilityScore: this.calculateReadability($('body').text()),
          keywordDensity: this.calculateKeywordDensity($('body').text())
        },
        
        // Keywords and SEO elements
        keywords: {
          extracted: this.extractKeywords($('body').text()),
          metaKeywords: $('meta[name="keywords"]').attr('content') || '',
          titleKeywords: this.extractKeywords($('title').text()),
          headingKeywords: this.extractKeywords($('h1, h2, h3').text()),
          altTextKeywords: this.extractKeywords($('img[alt]').map((i, el) => $(el).attr('alt')).get().join(' '))
        },
        
        // Competitor analysis (basic)
        competitors: {
          similarDomains: [], // Would need additional analysis
          industryKeywords: this.getIndustryKeywords($('body').text()),
          marketPosition: 'Unknown' // Would need additional data
        },
        
        // Content recommendations
        contentRecommendations: this.generateContentRecommendations($, url)
      };

      return analysis;
    } catch (error) {
      console.error('❌ Error scraping website:', error.message);
      throw error;
    }
  }

  // Helper methods for comprehensive analysis
  extractExternalDomains($, hostname) {
    const domains = new Set();
    $('a[href^="http"]').each((i, el) => {
      try {
        const href = $(el).attr('href');
        if (href && !href.includes(hostname)) {
          const domain = new URL(href).hostname;
          domains.add(domain);
        }
      } catch (e) {
        // Invalid URL, skip
      }
    });
    return Array.from(domains);
  }

  extractInternalPages($, hostname) {
    const pages = new Set();
    $('a[href^="/"], a[href*="' + hostname + '"]').each((i, el) => {
      const href = $(el).attr('href');
      if (href) {
        pages.add(href);
      }
    });
    return Array.from(pages);
  }

  extractSocialLinks($) {
    const socialPlatforms = ['facebook', 'twitter', 'linkedin', 'instagram', 'youtube', 'tiktok'];
    const socialLinks = {};
    
    $('a[href]').each((i, el) => {
      const href = $(el).attr('href');
      socialPlatforms.forEach(platform => {
        if (href.includes(platform)) {
          if (!socialLinks[platform]) socialLinks[platform] = [];
          socialLinks[platform].push(href);
        }
      });
    });
    
    return socialLinks;
  }

  extractOpenGraph($) {
    const og = {};
    $('meta[property^="og:"]').each((i, el) => {
      const property = $(el).attr('property');
      const content = $(el).attr('content');
      if (property && content) {
        og[property.replace('og:', '')] = content;
      }
    });
    return og;
  }

  extractTwitterCard($) {
    const twitter = {};
    $('meta[name^="twitter:"]').each((i, el) => {
      const name = $(el).attr('name');
      const content = $(el).attr('content');
      if (name && content) {
        twitter[name.replace('twitter:', '')] = content;
      }
    });
    return twitter;
  }

  extractSchemaMarkup($) {
    const schemas = [];
    $('script[type="application/ld+json"]').each((i, el) => {
      try {
        const json = JSON.parse($(el).html());
        schemas.push(json);
      } catch (e) {
        // Invalid JSON, skip
      }
    });
    return schemas;
  }

  checkMobileFriendly($) {
    const viewport = $('meta[name="viewport"]').attr('content');
    return viewport && viewport.includes('width=device-width');
  }

  countWords(text) {
    return text.trim().split(/\s+/).filter(word => word.length > 0).length;
  }

  calculateReadability(text) {
    const words = this.countWords(text);
    const sentences = text.split(/[.!?]+/).length;
    const syllables = this.countSyllables(text);
    
    if (words === 0 || sentences === 0) return 0;
    
    // Flesch Reading Ease Score
    const score = 206.835 - (1.015 * (words / sentences)) - (84.6 * (syllables / words));
    return Math.max(0, Math.min(100, score));
  }

  countSyllables(text) {
    const words = text.toLowerCase().match(/\b\w+\b/g) || [];
    let syllables = 0;
    
    words.forEach(word => {
      if (word.length <= 3) {
        syllables += 1;
      } else {
        syllables += word.replace(/[^aeiou]/g, '').length;
        if (word.endsWith('e')) syllables -= 1;
        if (word.endsWith('le') && word.length > 2) syllables += 1;
      }
    });
    
    return Math.max(1, syllables);
  }

  calculateKeywordDensity(text) {
    const words = text.toLowerCase().match(/\b\w+\b/g) || [];
    const wordCount = {};
    
    words.forEach(word => {
      if (word.length > 3) {
        wordCount[word] = (wordCount[word] || 0) + 1;
      }
    });
    
    const totalWords = words.length;
    const density = {};
    
    Object.keys(wordCount).forEach(word => {
      if (wordCount[word] > 1) {
        density[word] = ((wordCount[word] / totalWords) * 100).toFixed(2);
      }
    });
    
    return density;
  }

  extractKeywords(text) {
    const words = text.toLowerCase().match(/\b\w+\b/g) || [];
    const wordCount = {};
    
    words.forEach(word => {
      if (word.length > 3) {
        wordCount[word] = (wordCount[word] || 0) + 1;
      }
    });
    
    return Object.keys(wordCount)
      .sort((a, b) => wordCount[b] - wordCount[a])
      .slice(0, 20);
  }

  getIndustryKeywords(text) {
    const industryTerms = [
      'business', 'service', 'product', 'company', 'industry', 'market',
      'customer', 'client', 'solution', 'technology', 'digital', 'online',
      'marketing', 'sales', 'support', 'contact', 'about', 'team'
    ];
    
    const foundTerms = industryTerms.filter(term => 
      text.toLowerCase().includes(term)
    );
    
    return foundTerms;
  }

  generateContentRecommendations($, url) {
    const recommendations = [];
    const title = $('title').text().trim();
    const metaDesc = $('meta[name="description"]').attr('content') || '';
    const h1Count = $('h1').length;
    const wordCount = this.countWords($('body').text());
    
    // Title recommendations
    if (!title) {
      recommendations.push('Add a compelling title tag (50-60 characters)');
    } else if (title.length < 30) {
      recommendations.push('Expand your title tag to 50-60 characters for better SEO');
    } else if (title.length > 60) {
      recommendations.push('Shorten your title tag to under 60 characters');
    }
    
    // Meta description recommendations
    if (!metaDesc) {
      recommendations.push('Add a meta description (150-160 characters)');
    } else if (metaDesc.length < 120) {
      recommendations.push('Expand your meta description to 150-160 characters');
    }
    
    // Heading structure recommendations
    if (h1Count === 0) {
      recommendations.push('Add an H1 tag to improve page structure');
    } else if (h1Count > 1) {
      recommendations.push('Use only one H1 tag per page');
    }
    
    // Content length recommendations
    if (wordCount < 300) {
      recommendations.push('Increase content length to at least 300 words for better SEO');
    } else if (wordCount > 2000) {
      recommendations.push('Consider breaking long content into multiple pages');
    }
    
    // Image recommendations
    const imgCount = $('img').length;
    const missingAlt = $('img:not([alt])').length;
    if (imgCount > 0 && missingAlt > 0) {
      recommendations.push(`Add alt text to ${missingAlt} images for accessibility`);
    }
    
    // Link recommendations
    const externalLinks = $('a[href^="http"]').not(`a[href*="${new URL(url).hostname}"]`).length;
    if (externalLinks === 0) {
      recommendations.push('Add external links to authoritative sources');
    }
    
    return recommendations;
  }

  // Comprehensive SEO analysis combining Boostramp and scraping
  async analyzeWebsite(url) {
    try {
      console.log(`🔍 Starting comprehensive SEO analysis for: ${url}`);
      
      // Step 1: Basic web scraping
      const scrapedData = await this.scrapeWebsite(url);
      
      // Step 2: Create project in Boostramp
      const project = await this.createProject(url);
      
      // Step 3: Get Boostramp analysis (if project created successfully)
      let boostrampData = null;
      if (project && project.project_id) {
        try {
          const [onPageData, backlinkData] = await Promise.all([
            this.getOnPageAnalysis(project.project_id),
            this.getBacklinkAnalysis(project.project_id)
          ]);
          
          boostrampData = {
            onPage: onPageData,
            backlinks: backlinkData
          };
        } catch (boostrampError) {
          console.warn('⚠️ Boostramp analysis failed, using scraped data only:', boostrampError.message);
        }
      }

      // Step 4: Generate recommendations
      const recommendations = this.generateRecommendations(scrapedData, boostrampData);

      // Step 5: Calculate overall score
      const score = this.calculateSEOScore(scrapedData, boostrampData);

      return {
        success: true,
        url: url,
        analysis: {
          ...scrapedData,
          boostramp: boostrampData,
          score: score
        },
        recommendations: recommendations,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Comprehensive analysis failed:', error.message);
      throw error;
    }
  }

  // Generate SEO recommendations based on analysis
  generateRecommendations(scrapedData, boostrampData) {
    const recommendations = [];

    // Title recommendations
    if (!scrapedData.title) {
      recommendations.push('Add a title tag to improve SEO and user experience');
    } else if (scrapedData.title.length < 30) {
      recommendations.push('Title tag is too short. Aim for 30-60 characters for better SEO');
    } else if (scrapedData.title.length > 60) {
      recommendations.push('Title tag is too long. Keep it under 60 characters to avoid truncation');
    }

    // Meta description recommendations
    if (!scrapedData.metaDescription) {
      recommendations.push('Add a meta description to improve click-through rates from search results');
    } else if (scrapedData.metaDescription.length < 120) {
      recommendations.push('Meta description is too short. Aim for 120-160 characters');
    } else if (scrapedData.metaDescription.length > 160) {
      recommendations.push('Meta description is too long. Keep it under 160 characters');
    }

    // Heading structure recommendations
    if (scrapedData.headings.h1 === 0) {
      recommendations.push('Add an H1 tag to improve page structure and SEO');
    } else if (scrapedData.headings.h1 > 1) {
      recommendations.push('Use only one H1 tag per page for better SEO structure');
    }

    // Image recommendations
    if (scrapedData.images.missingAlt > 0) {
      recommendations.push(`Add alt text to ${scrapedData.images.missingAlt} images for better accessibility and SEO`);
    }

    // Link recommendations
    if (scrapedData.links.external === 0) {
      recommendations.push('Consider adding external links to authoritative sources to improve credibility');
    }

    // Technical recommendations
    if (!scrapedData.canonical) {
      recommendations.push('Add canonical URL to prevent duplicate content issues');
    }

    if (!scrapedData.viewport) {
      recommendations.push('Add viewport meta tag for mobile responsiveness');
    }

    if (!scrapedData.language) {
      recommendations.push('Add language attribute to HTML tag for better accessibility');
    }

    return recommendations;
  }

  // Calculate overall SEO score
  calculateSEOScore(scrapedData, boostrampData) {
    let score = 0;
    let maxScore = 0;

    // Title (20 points)
    maxScore += 20;
    if (scrapedData.title) {
      score += 15;
      if (scrapedData.title.length >= 30 && scrapedData.title.length <= 60) {
        score += 5;
      }
    }

    // Meta description (15 points)
    maxScore += 15;
    if (scrapedData.metaDescription) {
      score += 10;
      if (scrapedData.metaDescription.length >= 120 && scrapedData.metaDescription.length <= 160) {
        score += 5;
      }
    }

    // Headings (15 points)
    maxScore += 15;
    if (scrapedData.headings.h1 === 1) {
      score += 10;
    }
    if (scrapedData.headings.h2 > 0) {
      score += 5;
    }

    // Images (10 points)
    maxScore += 10;
    if (scrapedData.images.total > 0) {
      const altTextRatio = (scrapedData.images.total - scrapedData.images.missingAlt) / scrapedData.images.total;
      score += Math.round(altTextRatio * 10);
    } else {
      score += 10; // No images means perfect score for this metric
    }

    // Technical SEO (20 points)
    maxScore += 20;
    if (scrapedData.canonical) score += 5;
    if (scrapedData.viewport) score += 5;
    if (scrapedData.language) score += 5;
    if (scrapedData.charset) score += 5;

    // Content structure (10 points)
    maxScore += 10;
    if (scrapedData.links.internal > 0) score += 5;
    if (scrapedData.links.external > 0) score += 5;

    // Boostramp bonus (10 points)
    maxScore += 10;
    if (boostrampData) {
      score += 10;
    }

    return Math.round((score / maxScore) * 100);
  }
}

module.exports = new BoostrampService();
