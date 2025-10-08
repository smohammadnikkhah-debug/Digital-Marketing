/**
 * Environment-Aware DataForSEO Service
 * Automatically switches between Sandbox and Production based on environment configuration
 */

const axios = require('axios');
const EnvironmentConfig = require('./environmentConfig');
const URLNormalizer = require('./urlNormalizer');

class DataForSEOService {
  constructor() {
    const environmentConfig = new EnvironmentConfig();
    this.envConfig = environmentConfig.getDataForSEOConfig();
    this.baseUrl = this.envConfig.baseUrl || this.envConfig.baseURL;  // Support both baseUrl and baseURL
    this.username = this.envConfig.username;
    this.password = this.envConfig.password;
    this.environment = this.envConfig.environment;
    
    // Ensure baseUrl has a value
    if (!this.baseUrl) {
      this.baseUrl = 'https://api.dataforseo.com/v3';
      console.log('⚠️ DataForSEO baseUrl not configured, using default:', this.baseUrl);
    }
    
    console.log('🔍 DataForSEO Service Initialization:', {
      baseUrl: this.baseUrl,
      environment: this.environment,
      hasUsername: !!this.username,
      hasPassword: !!this.password
    });
    
    // Create Base64 encoded authorization header
    if (this.username && this.password) {
      this.authHeader = Buffer.from(`${this.username}:${this.password}`).toString('base64');
      console.log(`✅ DataForSEO API initialized successfully (${this.environment} mode)`);
      console.log(`   Base URL: ${this.baseUrl}`);
    } else {
      if (process.env.NODE_ENV === 'production') {
        console.log('⚠️ DataForSEO credentials not configured. Please set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD in DigitalOcean App Platform environment variables');
      } else {
        console.log('⚠️ DataForSEO credentials not configured. Please set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD');
      }
    }
  }

  /**
   * Make authenticated request to DataForSEO API
   */
  async makeRequest(endpoint, data) {
    try {
      // Ensure no double slashes in URL
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      const cleanBaseUrl = this.baseUrl.endsWith('/') ? this.baseUrl.slice(0, -1) : this.baseUrl;
      const fullUrl = `${cleanBaseUrl}${cleanEndpoint}`;
      
      console.log(`🔍 DataForSEO API Request (${this.environment}):`, {
        endpoint: fullUrl,
        dataLength: data.length,
        firstItem: data[0]
      });
      
      const response = await axios.post(fullUrl, data, {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Basic ${this.authHeader}`
        }
      });
      
      console.log(`✅ DataForSEO API Response (${this.environment}):`, {
        status: response.data.status_code,
        tasksCount: response.data.tasks?.length,
        firstTaskStatus: response.data.tasks?.[0]?.status_code,
        firstTaskMessage: response.data.tasks?.[0]?.status_message
      });
      
      return response.data;
    } catch (error) {
      const errorStatus = error.response?.status;
      const errorData = error.response?.data;
      
      // Handle 402 Payment Required error
      if (errorStatus === 402) {
        console.error(`💳 DataForSEO API error (${this.environment}): Payment Required`, {
          message: 'Your DataForSEO account needs credits or a paid plan',
          status: errorStatus,
          statusCode: errorData?.status_code,
          statusMessage: errorData?.status_message,
          tasksError: errorData?.tasks_error,
          endpoint: endpoint
        });
      } else {
        console.error(`❌ DataForSEO API error (${this.environment}):`, {
          message: error.message,
          status: errorStatus,
          data: errorData,
          endpoint: endpoint
        });
      }
      
      return null;
    }
  }

  /**
   * Get service status
   */
  getServiceStatus() {
    return {
      environment: this.environment,
      baseURL: this.baseUrl,
      isSandbox: this.envConfig.isSandbox,
      isProduction: this.envConfig.isProduction,
      configured: !!(this.username && this.password),
      message: `Using DataForSEO ${this.environment} API`,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Switch environment (runtime)
   */
  switchEnvironment(newEnvironment) {
    if (newEnvironment === 'sandbox') {
      environmentConfig.forceSandboxMode();
    } else if (newEnvironment === 'production') {
      environmentConfig.forceProductionMode();
    } else {
      throw new Error('Invalid environment. Must be "sandbox" or "production"');
    }
    
    // Reload configuration
    this.envConfig = environmentConfig.getDataForSEOConfig();
    this.baseUrl = this.envConfig.baseURL;
    
    console.log(`🔄 Switched to ${newEnvironment} environment`);
    console.log(`   New Base URL: ${this.baseUrl}`);
  }

  /**
   * Comprehensive SEO analysis using current environment
   */
  async analyzeWebsite(url) {
    try {
      console.log(`🔍 Starting comprehensive SEO analysis for: ${url} (${this.environment} mode)`);

      // Normalize URL to handle all possible formats (www, http, https, etc.)
      let processedUrl;
      try {
        processedUrl = URLNormalizer.normalizeForDataForSEO(url);
        console.log(`✅ Normalized URL for DataForSEO: ${processedUrl}`);
      } catch (error) {
        console.error(`❌ URL normalization failed: ${error.message}`);
        // Fallback to simple protocol addition
        processedUrl = url;
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
          processedUrl = `https://${url}`;
          console.log(`🔧 Added protocol to URL: ${processedUrl}`);
        }
      }

      // Check if DataForSEO is properly configured
      if (!this.username || !this.password) {
        return {
          success: false,
          error: 'DataForSEO API credentials not configured. Please set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD in environment configuration.',
          timestamp: new Date().toISOString()
        };
      }

      // Run multiple DataForSEO endpoints in parallel
      const [
        onPageData,
        backlinksData,
        keywordsData,
        competitorsData,
        serpData,
        trafficData
      ] = await Promise.allSettled([
        this.getBasicOnPageAnalysis(processedUrl),
        Promise.resolve({ status: 'fulfilled', value: null }), // Disabled backlinks (requires separate subscription)
        this.getKeywordsAnalysis(processedUrl),
        this.getCompetitorAnalysis(processedUrl), // ENABLED: Real competitor analysis
        this.getSERPAnalysis(processedUrl),
        this.getTrafficAnalysis(processedUrl)
      ]);

      // Check if we got any real data
      const hasOnPageData = onPageData.status === 'fulfilled' && onPageData.value !== null;
      const hasAnyData = [onPageData, backlinksData, keywordsData, competitorsData, serpData, trafficData]
        .some(result => result.status === 'fulfilled' && result.value !== null);

      if (!hasAnyData) {
        if (onPageData.status === 'fulfilled' && onPageData.value && onPageData.value.crawl_progress === 'finished' && onPageData.value.items_count === 0) {
          return {
            success: false,
            error: 'Website cannot be crawled by DataForSEO. This may be due to robots.txt restrictions, JavaScript requirements, or site blocking. Try a different website.',
            timestamp: new Date().toISOString()
          };
        }
        
        return {
          success: false,
          error: `No data available from DataForSEO ${this.environment} API. Please check your API credentials and account status.`,
          timestamp: new Date().toISOString()
        };
      }

      // Combine all data into comprehensive analysis
      const analysis = {
        url: url,
        timestamp: new Date().toISOString(),
        environment: this.environment,
        onPage: this.processOnPageData(onPageData.status === 'fulfilled' ? onPageData.value : null),
        backlinks: this.processBacklinksData(backlinksData.status === 'fulfilled' ? backlinksData.value : null),
        keywords: this.processKeywordsData(keywordsData.status === 'fulfilled' ? keywordsData.value : null),
        competitors: this.processCompetitorsData(competitorsData.status === 'fulfilled' ? competitorsData.value : null),
        serp: this.processSERPData(serpData.status === 'fulfilled' ? serpData.value : null),
        traffic: this.processTrafficData(trafficData.status === 'fulfilled' ? trafficData.value : null),
        recommendations: this.generateRecommendations(
          onPageData.status === 'fulfilled' ? onPageData.value : null,
          backlinksData.status === 'fulfilled' ? backlinksData.value : null,
          keywordsData.status === 'fulfilled' ? keywordsData.value : null
        ),
        score: this.calculateOverallScore(
          onPageData.status === 'fulfilled' ? onPageData.value : null,
          backlinksData.status === 'fulfilled' ? backlinksData.value : null,
          keywordsData.status === 'fulfilled' ? keywordsData.value : null,
          trafficData.status === 'fulfilled' ? trafficData.value : null
        )
      };

      return {
        success: true,
        analysis: analysis,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error(`❌ DataForSEO analysis failed (${this.environment}):`, error.message);
      return {
        success: false,
        error: `DataForSEO analysis failed: ${error.message}`,
        timestamp: new Date().toISOString()
      };
    }
  }

  // Basic On-Page SEO Analysis
  async getBasicOnPageAnalysis(url) {
    try {
      console.log(`📊 Getting basic on-page SEO analysis for: ${url} (${this.environment} mode)`);
      
      // Make real DataForSEO API call for on-page analysis
      // Note: OnPage Instant Pages API has specific parameters, removed invalid ones
      const onPageData = [{
        url: url,
        enable_javascript: true,
        enable_browser_rendering: true,
        disable_cookie_popup: true,
        load_resources: true,
        enable_xhr: true,
        custom_js: "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        // Removed accept_language - not supported by OnPage Instant Pages API
      }];
      
      const response = await this.makeRequest('/on_page/instant_pages', onPageData);
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.log(`⚠️ No on-page data available from DataForSEO for ${url}`);
        return null;
      }
      
      const task = response.tasks[0];
      if (task.status_code !== 20000 || !task.result || task.result.length === 0) {
        console.log(`⚠️ DataForSEO on-page analysis failed for ${url}:`, {
          status_code: task.status_code,
          status_message: task.status_message,
          error: task.error,
          result_count: task.result?.length || 0,
          path: task.path
        });
        return null;
      }
      
      const result = task.result[0];
      const domain = new URL(url).hostname.replace('www.', '');
      
      // Process real DataForSEO data
      const basicAnalysis = {
        domain: domain,
        url: url,
        title: result.title || '',
        metaDescription: result.meta_description || '',
        headings: {
          h1: result.h1 || [],
          h2: result.h2 || [],
          h3: result.h3 || []
        },
        images: {
          total: result.images ? result.images.length : 0,
          missingAlt: result.images ? result.images.filter(img => !img.alt).length : 0
        },
        links: {
          internal: result.internal_links_count || 0,
          external: result.external_links_count || 0
        },
        content: {
          wordCount: result.content ? result.content.split(' ').length : 0,
          text: result.content || ''
        },
        ssl: url.startsWith('https://'),
        mobileFriendly: result.mobile_friendly || false,
        technical: {
          canonical: result.canonical || url,
          robots: result.robots || '',
          viewport: result.viewport || '',
          charset: result.charset || '',
          language: result.language || 'en'
        },
        status: 'success',
        source: `dataforseo_onpage_${this.environment}`,
        environment: this.environment,
        timestamp: new Date().toISOString()
      };
      
      // Calculate real issues based on DataForSEO data
      const issues = [];
      let score = 100; // Start with perfect score
      
      // Check title length
      if (basicAnalysis.title.length > 60) {
        issues.push('Title tag is too long (over 60 characters)');
        score -= 10;
      }
      
      // Check meta description length
      if (basicAnalysis.metaDescription.length < 120 || basicAnalysis.metaDescription.length > 160) {
        issues.push('Meta description should be 120-160 characters');
        score -= 10;
      }
      
      // Check for H1 tags
      if (!basicAnalysis.headings.h1 || basicAnalysis.headings.h1.length === 0) {
        issues.push('Missing H1 tag');
        score -= 15;
      }
      
      // Check for missing alt text
      if (basicAnalysis.images.missingAlt > 0) {
        issues.push(`${basicAnalysis.images.missingAlt} images missing alt text`);
        score -= (basicAnalysis.images.missingAlt * 5);
      }
      
      // Check content length
      if (basicAnalysis.content.wordCount < 300) {
        issues.push('Content is too short (under 300 words)');
        score -= 10;
      }
      
      // Check SSL
      if (!basicAnalysis.ssl) {
        issues.push('Website not using HTTPS');
        score -= 20;
      }
      
      // Check mobile friendliness
      if (!basicAnalysis.mobileFriendly) {
        issues.push('Website not mobile-friendly');
        score -= 15;
      }
      
      // Ensure score doesn't go below 0
      score = Math.max(0, score);
      
      // Add calculated metrics to analysis
      basicAnalysis.score = score;
      basicAnalysis.issues = issues;
      basicAnalysis.issuesCount = issues.length;
      basicAnalysis.status = score >= 80 ? 'excellent' : score >= 60 ? 'good' : 'needs_improvement';
      
      console.log(`✅ Basic on-page analysis completed successfully (${this.environment})`);
      return basicAnalysis;
      
    } catch (error) {
      console.error(`Basic on-page analysis error (${this.environment}):`, error.message);
      return null;
    }
  }

  // Keywords Analysis
  async getKeywordsAnalysis(url) {
    try {
      console.log(`🔑 Getting keywords analysis for: ${url} (${this.environment} mode)`);
      
      const domain = new URL(url).hostname.replace('www.', '');
      
      // Try Keywords For Site API first (better for domain analysis)
      console.log(`🔑 Trying Keywords For Site API for domain: ${domain}`);
      const keywordsForSiteData = [{
        target: domain,
        location_name: 'United States',
        language_code: 'en',
        limit: 20
      }];
      
      let response = await this.makeRequest('dataforseo_labs/google/keywords_for_site/live', keywordsForSiteData);
      
      // Log the full response structure for debugging
      console.log(`🔍 Keywords For Site API Response:`, JSON.stringify(response, null, 2));
      
      // If Keywords For Site fails, try Keyword Suggestions as fallback
      if (!response || !response.tasks || response.tasks[0]?.status_code !== 20000) {
        console.log(`🔑 Keywords For Site not available, trying Keyword Suggestions...`);
        
        const keywordSuggestionsData = [{
          keyword: domain,
          location_name: 'United States',
          language_code: 'en',
          limit: 20
        }];
        
        response = await this.makeRequest('dataforseo_labs/google/keyword_suggestions/live', keywordSuggestionsData);
        console.log(`🔍 Keyword Suggestions API Response:`, JSON.stringify(response, null, 2));
      }
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.log(`⚠️ No keyword data available from DataForSEO for ${domain}`);
        return null;
      }
      
      const task = response.tasks[0];
      console.log(`🔍 Keywords Task Details:`, {
        status_code: task.status_code,
        status_message: task.status_message,
        has_result: !!task.result,
        result_length: task.result?.length || 0,
        result_structure: task.result ? Object.keys(task.result[0] || {}) : [],
        full_result: JSON.stringify(task.result, null, 2)
      });
      
      if (task.status_code !== 20000 || !task.result || task.result.length === 0) {
        console.log(`⚠️ DataForSEO keyword analysis failed for ${domain}:`, {
          status_code: task.status_code,
          status_message: task.status_message,
          error: task.error,
          result_count: task.result?.length || 0,
          path: task.path
        });
        return null;
      }
      
      const result = task.result[0];
      console.log(`🔍 Keywords Result Structure:`, JSON.stringify(result, null, 2));
      
      // Handle different possible result structures
      let keywords = [];
      if (result.items && Array.isArray(result.items)) {
        keywords = result.items.map(item => ({
          keyword: item.keyword,
          searchVolume: item.search_volume || 0,
          cpc: item.cpc || 0,
          competition: item.competition_level || 'Unknown',
          difficulty: item.keyword_difficulty || 0
        }));
      } else if (result.keywords && Array.isArray(result.keywords)) {
        keywords = result.keywords.map(item => ({
          keyword: item.keyword,
          searchVolume: item.search_volume || 0,
          cpc: item.cpc || 0,
          competition: item.competition_level || 'Unknown',
          difficulty: item.keyword_difficulty || 0
        }));
      } else if (Array.isArray(result)) {
        keywords = result.map(item => ({
          keyword: item.keyword,
          searchVolume: item.search_volume || 0,
          cpc: item.cpc || 0,
          competition: item.competition_level || 'Unknown',
          difficulty: item.keyword_difficulty || 0
        }));
      }
      
      console.log(`✅ Generated keyword suggestions successfully (${this.environment})`);
      return {
        totalKeywords: keywords.length,
        keywords: keywords,
        status: 'success',
        source: `dataforseo_keywords_${this.environment}`,
        message: `Keyword suggestions from DataForSEO API (${this.environment} mode).`,
        environment: this.environment
      };
      
    } catch (error) {
      console.error(`Keywords analysis error (${this.environment}):`, error.message);
      return {
        status: 'error',
        message: 'Keywords analysis failed',
        totalKeywords: 0,
        keywords: [],
        environment: this.environment
      };
    }
  }

  // SERP Analysis
  async getSERPAnalysis(url) {
    try {
      console.log(`🔍 Getting SERP analysis for: ${url} (${this.environment} mode)`);
      
      console.log(`ℹ️ SERP analysis requires DataForSEO Labs subscription (${this.environment} mode)`);
      return {
        status: 'requires_upgrade',
        message: `SERP analysis requires DataForSEO Labs subscription (${this.environment} mode)`,
        data: {
          serp_results: [],
          total_results: 0
        },
        environment: this.environment
      };
    } catch (error) {
      console.error(`SERP analysis error (${this.environment}):`, error.message);
      return null;
    }
  }

  // Traffic Analysis
  async getTrafficAnalysis(url) {
    try {
      console.log(`📊 Getting traffic analysis for: ${url} (${this.environment} mode)`);
      
      console.log(`ℹ️ Traffic analysis requires DataForSEO Labs subscription (${this.environment} mode)`);
      return {
        status: 'requires_upgrade',
        message: `Traffic analysis requires DataForSEO Labs subscription (${this.environment} mode)`,
        data: {
          estimated_traffic: 0,
          organic_traffic: 0,
          paid_traffic: 0
        },
        environment: this.environment
      };
    } catch (error) {
      console.error(`Traffic analysis error (${this.environment}):`, error.message);
      return null;
    }
  }

  // Competitor Analysis using DataForSEO Labs
  async getCompetitorAnalysis(url) {
    try {
      console.log(`🏆 Getting competitor analysis for: ${url} (${this.environment} mode)`);
      
      const domain = new URL(url).hostname.replace('www.', '');
      
      // Use DataForSEO Labs Competitors Domain API
      const competitorData = [{
        target: domain,
        location_name: 'United States',
        language_code: 'en',
        limit: 10,
        filters: [["metrics.organic.count", ">", 10]]  // Only competitors with 10+ keywords
      }];
      
      const response = await this.makeRequest('dataforseo_labs/google/competitors_domain/live', competitorData);
      
      // Log the full response structure for debugging
      console.log(`🔍 Competitors Domain API Response:`, JSON.stringify(response, null, 2));
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.log(`ℹ️ Competitor analysis requires DataForSEO Labs subscription (${this.environment} mode)`);
        return null;
      }
      
      const task = response.tasks[0];
      console.log(`🔍 Competitors Task Details:`, {
        status_code: task.status_code,
        status_message: task.status_message,
        has_result: !!task.result,
        result_length: task.result?.length || 0,
        result_structure: task.result ? Object.keys(task.result[0] || {}) : [],
        full_result: JSON.stringify(task.result, null, 2)
      });
      
      if (task.status_code !== 20000 || !task.result || task.result.length === 0) {
        console.log(`ℹ️ Competitor analysis not available:`, {
          status_code: task.status_code,
          status_message: task.status_message,
          note: 'Requires DataForSEO Labs subscription'
        });
        return null;
      }
      
      const result = task.result[0];
      console.log(`🔍 Competitors Result Structure:`, JSON.stringify(result, null, 2));
      
      // Handle different possible result structures
      let competitors = [];
      if (result.items && Array.isArray(result.items)) {
        competitors = result.items.map(item => ({
          domain: item.domain || item.target,
          avgPosition: item.avg_position || 0,
          sumPosition: item.sum_position || 0,
          intersections: item.intersections || 0,
          fullDomainMetrics: item.full_domain_metrics || {},
          metrics: item.metrics || {}
        })).slice(0, 5);
      } else if (result.competitors && Array.isArray(result.competitors)) {
        competitors = result.competitors.map(item => ({
          domain: item.domain || item.target,
          avgPosition: item.avg_position || 0,
          sumPosition: item.sum_position || 0,
          intersections: item.intersections || 0,
          fullDomainMetrics: item.full_domain_metrics || {},
          metrics: item.metrics || {}
        })).slice(0, 5);
      } else if (Array.isArray(result)) {
        competitors = result.map(item => ({
          domain: item.domain || item.target,
          avgPosition: item.avg_position || 0,
          sumPosition: item.sum_position || 0,
          intersections: item.intersections || 0,
          fullDomainMetrics: item.full_domain_metrics || {},
          metrics: item.metrics || {}
        })).slice(0, 5);
      }
      
      console.log(`✅ Competitor analysis completed: ${competitors.length} competitors found (${this.environment})`);
      return {
        totalCompetitors: competitors.length,
        competitors: competitors,
        status: 'success',
        source: `dataforseo_competitors_${this.environment}`,
        environment: this.environment
      };
      
    } catch (error) {
      console.error(`Competitor analysis error (${this.environment}):`, error.message);
      return null;
    }
  }

  // This method is no longer needed as we use real DataForSEO API calls
  // Removed generateDomainPages method to eliminate fake data generation

  // Process data methods (keeping existing logic)
  processOnPageData(onPageData) {
    if (!onPageData) return null;
    return {
      ...onPageData,
      environment: this.environment
    };
  }

  processBacklinksData(backlinksData) {
    if (!backlinksData) return null;
    return {
      ...backlinksData,
      environment: this.environment
    };
  }

  processKeywordsData(keywordsData) {
    if (!keywordsData) return null;
    return {
      ...keywordsData,
      environment: this.environment
    };
  }

  processCompetitorsData(competitorsData) {
    if (!competitorsData) return null;
    return {
      ...competitorsData,
      environment: this.environment
    };
  }

  processSERPData(serpData) {
    if (!serpData) return null;
    return {
      ...serpData,
      environment: this.environment
    };
  }

  processTrafficData(trafficData) {
    if (!trafficData) return null;
    return {
      ...trafficData,
      environment: this.environment
    };
  }

  // Generate Recommendations
  generateRecommendations(onPageData, backlinksData, keywordsData) {
    const recommendations = [];
    
    // Add environment-specific recommendations
    recommendations.push({
      category: 'Environment',
      priority: 'Info',
      issue: `Running in ${this.environment} mode`,
      solution: `Currently using DataForSEO ${this.environment} API`,
      impact: this.environment === 'sandbox' ? 'Free testing environment' : 'Production environment with real data'
    });

    // Add comprehensive recommendations based on data
    if (onPageData) {
      if (!onPageData.title) {
        recommendations.push({
          category: 'On-Page SEO',
          priority: 'High',
          issue: 'Missing page title',
          solution: 'Add a compelling title tag (50-60 characters) with primary keyword',
          impact: 'Critical for SEO and user experience'
        });
      }
      
      if (!onPageData.metaDescription) {
        recommendations.push({
          category: 'On-Page SEO',
          priority: 'High',
          issue: 'Missing meta description',
          solution: 'Add a descriptive meta description (150-160 characters)',
          impact: 'Affects click-through rates from search results'
        });
      }
      
      if (onPageData.headings?.h1 === 0) {
        recommendations.push({
          category: 'On-Page SEO',
          priority: 'High',
          issue: 'Missing H1 tag',
          solution: 'Add a single H1 tag with your primary keyword',
          impact: 'Essential for page structure and SEO'
        });
      }
      
      if (onPageData.headings?.h2 === 0) {
        recommendations.push({
          category: 'On-Page SEO',
          priority: 'Medium',
          issue: 'Missing H2 tags',
          solution: 'Add H2 tags to structure your content',
          impact: 'Improves content organization and SEO'
        });
      }
      
      if (onPageData.content?.wordCount < 300) {
        recommendations.push({
          category: 'Content',
          priority: 'Medium',
          issue: 'Low content word count',
          solution: 'Increase content to at least 300 words',
          impact: 'More content provides better SEO value'
        });
      }
      
      if (onPageData.images?.missingAlt > 0) {
        recommendations.push({
          category: 'Accessibility',
          priority: 'Medium',
          issue: `${onPageData.images.missingAlt} images missing alt text`,
          solution: 'Add descriptive alt text to all images',
          impact: 'Improves accessibility and SEO'
        });
      }
      
      if (!onPageData.ssl) {
        recommendations.push({
          category: 'Security',
          priority: 'High',
          issue: 'No SSL certificate',
          solution: 'Install SSL certificate (HTTPS)',
          impact: 'Critical for security and SEO ranking'
        });
      }
      
      if (!onPageData.mobileFriendly) {
        recommendations.push({
          category: 'Mobile',
          priority: 'High',
          issue: 'Not mobile friendly',
          solution: 'Implement responsive design',
          impact: 'Essential for mobile search rankings'
        });
      }
    }

    // Add keyword-based recommendations
    if (keywordsData && keywordsData.keywords) {
      const highDifficultyKeywords = keywordsData.keywords.filter(k => k.difficulty > 70);
      if (highDifficultyKeywords.length > 0) {
        recommendations.push({
          category: 'Keywords',
          priority: 'Medium',
          issue: `${highDifficultyKeywords.length} high-difficulty keywords`,
          solution: 'Focus on long-tail keywords with lower competition',
          impact: 'Easier to rank for less competitive terms'
        });
      }
    }

    return recommendations;
  }

  // Calculate Overall SEO Score
  calculateOverallScore(onPageData, backlinksData, keywordsData, trafficData) {
    let score = 0;
    let maxScore = 0;

    // Base score for environment
    maxScore += 20;
    score += this.environment === 'production' ? 20 : 15; // Production gets full points, sandbox gets most

    // On-Page Score (40 points)
    maxScore += 40;
    if (onPageData) {
      if (onPageData.title) score += 10;
      if (onPageData.metaDescription) score += 10;
      if (onPageData.h1Tags && onPageData.h1Tags.length > 0) score += 10;
      if (onPageData.ssl) score += 5;
      if (onPageData.mobileFriendly) score += 5;
    }

    // Keywords Score (20 points)
    maxScore += 20;
    if (keywordsData && keywordsData.keywords && keywordsData.keywords.length > 0) {
      score += Math.min(20, keywordsData.keywords.length * 2);
    }

    // Traffic Score (20 points)
    maxScore += 20;
    if (trafficData && trafficData.estimated_traffic > 0) {
      score += Math.min(20, Math.floor(trafficData.estimated_traffic / 1000));
    }

    return Math.round((score / maxScore) * 100);
  }
}

module.exports = new DataForSEOService();
