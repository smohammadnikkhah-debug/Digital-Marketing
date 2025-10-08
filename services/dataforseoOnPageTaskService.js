/**
 * DataForSEO OnPage Task Service - Full Website Crawl
 * Handles task-based website crawling that analyzes ALL pages
 */

const axios = require('axios');
const EnvironmentConfig = require('./environmentConfig');
const URLNormalizer = require('./urlNormalizer');

class DataForSEOOnPageTaskService {
  constructor() {
    const environmentConfig = new EnvironmentConfig();
    this.envConfig = environmentConfig.getDataForSEOConfig();
    this.baseUrl = this.envConfig.baseUrl || 'https://api.dataforseo.com/v3';
    this.username = this.envConfig.username;
    this.password = this.envConfig.password;
    
    if (this.username && this.password) {
      this.authHeader = Buffer.from(`${this.username}:${this.password}`).toString('base64');
      console.log('✅ DataForSEO OnPage Task Service initialized');
    } else {
      console.warn('⚠️ DataForSEO credentials not configured for OnPage Task Service');
    }
  }

  /**
   * Make authenticated request to DataForSEO API
   */
  async makeRequest(endpoint, data) {
    try {
      const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
      const cleanBaseUrl = this.baseUrl.endsWith('/') ? this.baseUrl.slice(0, -1) : this.baseUrl;
      const fullUrl = `${cleanBaseUrl}${cleanEndpoint}`;
      
      const response = await axios.post(fullUrl, data, {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Basic ${this.authHeader}`
        }
      });
      
      return response.data;
    } catch (error) {
      console.error(`❌ DataForSEO OnPage Task API error:`, {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data
      });
      return null;
    }
  }

  /**
   * Create a full website crawl task
   * This will analyze ALL pages on the domain
   */
  async createFullCrawlTask(url, options = {}) {
    try {
      console.log(`🚀 Creating full website crawl task for: ${url}`);
      
      // Normalize URL to domain
      const domain = URLNormalizer.normalizeDomainForStorage(url);
      const targetUrl = `https://${domain}`;
      
      const taskData = [{
        target: targetUrl,
        max_crawl_pages: options.maxPages || 100,  // Crawl up to 100 pages
        load_resources: true,
        enable_javascript: true,
        enable_browser_rendering: true,
        store_raw_html: false,  // Don't store full HTML (saves space)
        custom_js: "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        validate_micromarkup: true,
        checks_threshold: options.checksThreshold || 90,  // Run 90%+ of available checks
        disable_cookie_popup: true
      }];
      
      const response = await this.makeRequest('/on_page/task_post', taskData);
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.error('❌ Failed to create OnPage task');
        return null;
      }
      
      const task = response.tasks[0];
      
      if (task.status_code === 20000) {
        console.log('✅ OnPage crawl task created successfully:', {
          taskId: task.id,
          target: targetUrl,
          maxPages: options.maxPages || 100
        });
        
        return {
          success: true,
          taskId: task.id,
          target: targetUrl,
          status: 'created'
        };
      } else {
        console.error('❌ OnPage task creation failed:', {
          status_code: task.status_code,
          status_message: task.status_message
        });
        return null;
      }
    } catch (error) {
      console.error('❌ Error creating OnPage task:', error);
      return null;
    }
  }

  /**
   * Check the status of a crawl task
   */
  async checkTaskStatus(taskId) {
    try {
      const response = await this.makeRequest('/on_page/tasks_ready', []);
      
      if (!response || !response.tasks) {
        return null;
      }
      
      // Find our specific task
      const tasks = response.tasks[0]?.result || [];
      const task = tasks.find(t => t.id === taskId);
      
      if (task) {
        console.log(`📊 OnPage task ${taskId} status:`, {
          status: task.status_message,
          pagesFound: task.result_count
        });
        
        return {
          id: taskId,
          status: task.status_message,
          pagesFound: task.result_count,
          isComplete: task.status_message === 'Ok.'
        };
      }
      
      return null;
    } catch (error) {
      console.error('❌ Error checking task status:', error);
      return null;
    }
  }

  /**
   * Get results from a completed crawl task
   */
  async getTaskResults(taskId, limit = 100) {
    try {
      console.log(`📥 Getting results for OnPage task: ${taskId}`);
      
      const requestData = [{
        id: taskId,
        limit: limit,
        filters: [
          ["status_code", "=", 200]  // Only successful pages
        ],
        order_by: ["checks.sitemap,desc"]  // Prioritize important pages
      }];
      
      const response = await this.makeRequest('/on_page/pages', requestData);
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.error('❌ Failed to get OnPage results');
        return null;
      }
      
      const task = response.tasks[0];
      
      if (task.status_code !== 20000 || !task.result) {
        console.error('❌ OnPage results retrieval failed:', {
          status_code: task.status_code,
          status_message: task.status_message
        });
        return null;
      }
      
      const pages = task.result;
      
      console.log(`✅ Retrieved ${pages.length} pages from OnPage crawl`);
      
      return this.processOnPageResults(pages);
    } catch (error) {
      console.error('❌ Error getting OnPage results:', error);
      return null;
    }
  }

  /**
   * Process OnPage crawl results into structured data
   */
  processOnPageResults(pages) {
    const processedPages = pages.map(page => ({
      url: page.url,
      title: page.title,
      metaDescription: page.meta?.description || '',
      h1: page.meta?.h1 || [],
      h2: page.meta?.h2 || [],
      statusCode: page.status_code,
      loadTime: page.load_time,
      size: page.size,
      wordCount: page.word_count,
      images: {
        total: page.images || 0,
        brokenImages: page.checks?.broken_images || 0,
        imagesWithoutAlt: page.checks?.images_without_alt || 0
      },
      links: {
        internal: page.links_internal || 0,
        external: page.links_external || 0,
        broken: page.checks?.broken_links || 0
      },
      checks: page.checks || {},
      onPageScore: page.onpage_score || 0,
      errors: this.extractPageErrors(page.checks)
    }));

    // Calculate aggregate metrics
    const totalPages = processedPages.length;
    const healthyPages = processedPages.filter(p => p.onPageScore >= 80).length;
    const pagesWithIssues = processedPages.filter(p => p.onPageScore < 80).length;
    const averageScore = processedPages.reduce((sum, p) => sum + p.onPageScore, 0) / totalPages;
    const totalErrors = processedPages.reduce((sum, p) => sum + p.errors.length, 0);

    return {
      totalPages: totalPages,
      healthyPages: healthyPages,
      pagesWithIssues: pagesWithIssues,
      averageScore: Math.round(averageScore),
      totalErrors: totalErrors,
      pages: processedPages,
      summary: {
        crawlDate: new Date().toISOString(),
        pagesAnalyzed: totalPages,
        issues: this.categorizeIssues(processedPages)
      }
    };
  }

  /**
   * Extract errors from page checks
   */
  extractPageErrors(checks) {
    const errors = [];
    
    if (!checks) return errors;
    
    // Check for common SEO issues
    if (checks.no_content_encoding) errors.push({ type: 'performance', issue: 'No content encoding' });
    if (checks.high_loading_time) errors.push({ type: 'performance', issue: 'High loading time' });
    if (checks.is_redirect) errors.push({ type: 'redirect', issue: 'Page is a redirect' });
    if (checks.is_4xx_code) errors.push({ type: 'error', issue: '4xx error code' });
    if (checks.is_5xx_code) errors.push({ type: 'error', issue: '5xx error code' });
    if (checks.is_broken) errors.push({ type: 'error', issue: 'Broken page' });
    if (checks.is_www) errors.push({ type: 'technical', issue: 'WWW inconsistency' });
    if (checks.is_https) errors.push({ type: 'security', issue: 'HTTPS issue' });
    if (checks.is_http) errors.push({ type: 'security', issue: 'HTTP instead of HTTPS' });
    if (checks.no_h1_tag) errors.push({ type: 'seo', issue: 'Missing H1 tag' });
    if (checks.canonical) errors.push({ type: 'seo', issue: 'Canonical tag issue' });
    if (checks.no_image_alt) errors.push({ type: 'seo', issue: 'Images missing alt text' });
    if (checks.no_image_title) errors.push({ type: 'seo', issue: 'Images missing title' });
    if (checks.seo_friendly_url === false) errors.push({ type: 'seo', issue: 'URL not SEO-friendly' });
    if (checks.flash) errors.push({ type: 'technical', issue: 'Uses Flash' });
    if (checks.frame) errors.push({ type: 'technical', issue: 'Uses frames' });
    if (checks.lorem_ipsum) errors.push({ type: 'content', issue: 'Contains Lorem Ipsum' });
    if (checks.seo_friendly_url_characters_check === false) errors.push({ type: 'seo', issue: 'URL has non-SEO characters' });
    if (checks.seo_friendly_url_dynamic_check === false) errors.push({ type: 'seo', issue: 'URL is dynamic' });
    if (checks.seo_friendly_url_keywords_check === false) errors.push({ type: 'seo', issue: 'URL missing keywords' });
    if (checks.seo_friendly_url_relative_length_check === false) errors.push({ type: 'seo', issue: 'URL too long' });
    if (checks.small_page_size === false) errors.push({ type: 'performance', issue: 'Page size too large' });
    if (checks.recursive_canonical) errors.push({ type: 'seo', issue: 'Recursive canonical' });
    if (checks.canonical_chain) errors.push({ type: 'seo', issue: 'Canonical chain' });
    if (checks.canonical_to_redirect) errors.push({ type: 'seo', issue: 'Canonical points to redirect' });
    
    return errors;
  }

  /**
   * Categorize issues by type
   */
  categorizeIssues(pages) {
    const categories = {
      seo: [],
      performance: [],
      security: [],
      technical: [],
      content: []
    };

    pages.forEach(page => {
      page.errors.forEach(error => {
        if (!categories[error.type]) categories[error.type] = [];
        categories[error.type].push({
          page: page.url,
          issue: error.issue
        });
      });
    });

    return categories;
  }

  /**
   * Start full website analysis with background processing
   */
  async startFullWebsiteAnalysis(url, websiteId, options = {}) {
    try {
      console.log(`🚀 Starting FULL website analysis for: ${url}`);
      
      // Create the crawl task
      const taskResult = await this.createFullCrawlTask(url, options);
      
      if (!taskResult || !taskResult.success) {
        return {
          success: false,
          error: 'Failed to create crawl task'
        };
      }
      
      // Store task info in database for tracking
      const supabaseService = require('./supabaseService');
      await supabaseService.storeAnalysisTask(websiteId, {
        taskId: taskResult.taskId,
        target: taskResult.target,
        status: 'in_progress',
        startedAt: new Date().toISOString(),
        estimatedDuration: '5-30 minutes'
      });
      
      console.log(`✅ Full website crawl started - Task ID: ${taskResult.taskId}`);
      console.log(`   This will analyze ALL pages on ${url}`);
      console.log(`   Estimated time: 5-30 minutes`);
      console.log(`   Check status with: checkTaskStatus('${taskResult.taskId}')`);
      
      return {
        success: true,
        taskId: taskResult.taskId,
        status: 'in_progress',
        message: 'Full website crawl started. This will analyze all pages and may take 5-30 minutes.'
      };
    } catch (error) {
      console.error('❌ Error starting full website analysis:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Poll task until complete and store results
   */
  async pollAndStoreResults(taskId, websiteId, maxAttempts = 60) {
    console.log(`🔄 Starting to poll task ${taskId} (max ${maxAttempts} attempts, 30s interval)`);
    
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      console.log(`   Attempt ${attempt}/${maxAttempts} - Checking task status...`);
      
      const status = await this.checkTaskStatus(taskId);
      
      if (!status) {
        console.log('   ⚠️ Could not get task status, will retry...');
        await this.sleep(30000); // Wait 30 seconds
        continue;
      }
      
      if (status.isComplete) {
        console.log(`✅ Task ${taskId} complete! Getting results...`);
        
        // Get all crawl results
        const results = await this.getTaskResults(taskId, 100);
        
        if (results) {
          // Store in Supabase
          const supabaseService = require('./supabaseService');
          await supabaseService.storeAnalysis(websiteId, results, 'full_crawl');
          
          // Update task status
          await supabaseService.updateAnalysisTaskStatus(websiteId, taskId, 'completed');
          
          console.log(`✅ Full website analysis complete and stored!`);
          console.log(`   Total pages analyzed: ${results.totalPages}`);
          console.log(`   Healthy pages: ${results.healthyPages}`);
          console.log(`   Pages with issues: ${results.pagesWithIssues}`);
          
          return {
            success: true,
            results: results
          };
        } else {
          console.error('❌ Failed to get task results');
          return { success: false, error: 'Failed to retrieve results' };
        }
      }
      
      console.log(`   Task still in progress... (${status.pagesFound || 0} pages found so far)`);
      
      // Wait 30 seconds before next check
      await this.sleep(30000);
    }
    
    console.error(`❌ Task ${taskId} did not complete within ${maxAttempts * 30 / 60} minutes`);
    return {
      success: false,
      error: 'Task timed out'
    };
  }

  /**
   * Sleep helper
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

module.exports = new DataForSEOOnPageTaskService();

