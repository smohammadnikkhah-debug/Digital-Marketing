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
        // Mimic real browser to avoid bot detection
        custom_js: "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        custom_user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        // Handle authentication/protection
        validate_micromarkup: true,
        disable_cookie_popup: true,
        // Allow subdomains and respect sitemap
        allow_subdomains: true,
        respect_sitemap: true
      }];
      
      const response = await this.makeRequest('/on_page/task_post', taskData);
      
      if (!response || !response.tasks || response.tasks.length === 0) {
        console.error('❌ Failed to create OnPage task');
        return null;
      }
      
      const task = response.tasks[0];
      
      // Status codes: 20000 = Ok (instant), 20100 = Task Created (background)
      if (task.status_code === 20000 || task.status_code === 20100) {
        console.log('✅ OnPage crawl task created successfully:', {
          taskId: task.id,
          statusCode: task.status_code,
          statusMessage: task.status_message,
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
   * First checks tasks_ready, then checks summary directly
   */
  async checkTaskStatus(taskId) {
    try {
      console.log(`📊 Checking status for task: ${taskId}`);
      
      // Method 1: Check if task is in the ready list
      const readyResponse = await this.makeRequest('/on_page/tasks_ready', []);
      
      if (readyResponse && readyResponse.tasks && readyResponse.tasks.length > 0) {
        const task = readyResponse.tasks[0];
        
        // Check if our task is in the ready list
        if (task.result && Array.isArray(task.result)) {
          const readyTask = task.result.find(t => t.id === taskId);
          
          if (readyTask) {
            console.log(`✅ OnPage task ${taskId} is READY (via tasks_ready):`, {
              resultCount: readyTask.result_count
            });
            
            return {
              id: taskId,
              statusCode: 20000,
              statusMessage: 'Task complete',
              pagesFound: readyTask.result_count || 0,
              isComplete: true,
              inProgress: false
            };
          }
        }
      }
      
      // Method 2: Check summary endpoint directly (more reliable)
      console.log(`📊 Checking summary endpoint directly for task: ${taskId}`);
      const summaryResponse = await this.makeRequest('/on_page/summary', [{
        id: taskId
      }]);
      
      if (summaryResponse && summaryResponse.tasks && summaryResponse.tasks.length > 0) {
        const task = summaryResponse.tasks[0];
        
        if (task.result && task.result.length > 0) {
          const summary = task.result[0];
          const isFinished = summary.crawl_progress === 'finished';
          const pagesCrawled = summary.crawl_status?.pages_crawled || 0;
          
          console.log(`📊 Task summary:`, {
            crawlProgress: summary.crawl_progress,
            pagesCrawled: pagesCrawled,
            pagesInQueue: summary.crawl_status?.pages_in_queue || 0,
            isFinished: isFinished
          });
          
          if (isFinished) {
            return {
              id: taskId,
              statusCode: 20000,
              statusMessage: 'Task complete',
              pagesFound: pagesCrawled,
              isComplete: true,
              inProgress: false
            };
          } else {
            return {
              id: taskId,
              statusCode: 20100,
              statusMessage: 'Task in progress',
              pagesFound: pagesCrawled,
              isComplete: false,
              inProgress: true
            };
          }
        }
      }
      
      // If we can't determine status, assume still processing
      console.log(`⏳ Task ${taskId} status unknown, assuming in progress`);
      return {
        id: taskId,
        statusCode: 20100,
        statusMessage: 'Task in progress',
        pagesFound: 0,
        isComplete: false,
        inProgress: true
      };
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
        limit: limit
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
      
      // Extract actual pages from result wrapper
      const resultWrapper = task.result[0];
      const pages = resultWrapper.items || [];
      
      console.log(`✅ Retrieved ${pages.length} pages from OnPage crawl`);
      console.log(`📊 Crawl summary: Total items: ${resultWrapper.total_items_count}, Items in this batch: ${resultWrapper.items_count}`);
      
      if (pages.length === 0) {
        console.warn('⚠️ No pages found in result - might need pagination or crawl was blocked');
        return null;
      }
      
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

    const calculatedScore = Math.round(averageScore);
    const allIssues = this.categorizeIssues(processedPages);
    const recommendations = this.generateRecommendationsFromIssues(allIssues, processedPages);
    
    return {
      // Dashboard expects these exact keys
      score: calculatedScore,
      totalPages: totalPages,
      healthyPages: healthyPages,
      pagesWithIssues: pagesWithIssues,
      averageScore: calculatedScore,
      totalIssues: totalErrors,
      recommendations: recommendations,
      
      // Full crawl data
      pages: processedPages,
      onPage: {
        pages: processedPages,
        score: calculatedScore,
        pageMetrics: {
          totalPages: totalPages,
          healthyPages: healthyPages,
          pagesWithIssues: pagesWithIssues,
          averageScore: calculatedScore,
          totalFixedIssues: 0,
          issuesByType: allIssues
        }
      },
      
      // Metadata
      timestamp: new Date().toISOString(),
      environment: 'prod',
      source: 'dataforseo_onpage_full_crawl'
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
   * Generate actionable recommendations from issues
   */
  generateRecommendationsFromIssues(issues, pages) {
    const recommendations = [];
    
    // Count issue types
    const seoIssueCount = issues.seo?.length || 0;
    const performanceIssueCount = issues.performance?.length || 0;
    const contentIssueCount = issues.content?.length || 0;
    
    // Generate top recommendations based on most common issues
    if (seoIssueCount > 0) {
      recommendations.push({
        category: 'SEO',
        priority: 'High',
        issue: `${seoIssueCount} pages have SEO issues`,
        solution: 'Fix missing H1 tags, meta descriptions, and image alt text',
        impact: 'Improves search engine rankings and visibility'
      });
    }
    
    if (performanceIssueCount > 0) {
      recommendations.push({
        category: 'Performance',
        priority: 'Medium',
        issue: `${performanceIssueCount} pages have performance issues`,
        solution: 'Optimize images, enable compression, reduce page load times',
        impact: 'Faster loading improves user experience and SEO'
      });
    }
    
    if (contentIssueCount > 0) {
      recommendations.push({
        category: 'Content',
        priority: 'Medium',
        issue: `${contentIssueCount} pages have content issues`,
        solution: 'Add more content, remove Lorem Ipsum, improve readability',
        impact: 'Better content increases engagement and rankings'
      });
    }
    
    // Check for broken links across all pages
    const brokenLinksCount = pages.reduce((sum, p) => sum + (p.links?.broken || 0), 0);
    if (brokenLinksCount > 0) {
      recommendations.push({
        category: 'Technical',
        priority: 'High',
        issue: `${brokenLinksCount} broken links found`,
        solution: 'Fix or remove all broken links (404 errors)',
        impact: 'Broken links hurt SEO and user experience'
      });
    }
    
    // Check for duplicate content
    const duplicatePages = pages.filter(p => p.checks?.duplicate_content).length;
    if (duplicatePages > 5) {
      recommendations.push({
        category: 'SEO',
        priority: 'High',
        issue: `${duplicatePages} pages have duplicate content`,
        solution: 'Add unique content or use canonical tags',
        impact: 'Duplicate content dilutes SEO value'
      });
    }
    
    return recommendations.slice(0, 5); // Top 5 recommendations
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
          // Check if crawl was blocked (0 pages found)
          if (results.totalPages === 0 || (results.pagesWithIssues === 0 && results.healthyPages === 0)) {
            console.warn(`⚠️ Crawl completed but found 0 pages - website is blocking the crawler`);
            
            // Store blocked status with helpful message
            const supabaseService = require('./supabaseService');
            const blockedMessage = 'Website is blocking DataForSEO crawler. Please whitelist the following IPs in your firewall or hosting control panel: 94.130.93.30, 168.119.141.170, 168.119.99.190-194, 68.183.60.34, 134.209.42.109, 68.183.60.80, 68.183.54.131, 68.183.49.222, 68.183.149.30, 68.183.157.22, 68.183.149.129';
            
            await supabaseService.updateAnalysisTaskStatus(websiteId, taskId, 'blocked', blockedMessage);
            
            console.log(`⚠️ Task marked as 'blocked' - user needs to whitelist DataForSEO IPs`);
            return { 
              success: false, 
              error: 'crawler_blocked',
              message: blockedMessage
            };
          }
          
          // Get domain from first page URL
          const domain = results.pages && results.pages[0] ? 
            new URL(results.pages[0].url).hostname.replace('www.', '') : 
            null;
          
          // Also fetch keywords and competitors for complete analysis
          if (domain) {
            console.log(`🔑 Fetching keywords and competitors for: ${domain}`);
            
            try {
              const dataforseoService = require('./dataforseoEnvironmentService');
              
              // Fetch keywords and competitors in parallel
              const [keywordsData, competitorsData] = await Promise.allSettled([
                dataforseoService.getKeywordsAnalysis(`https://${domain}`),
                dataforseoService.getCompetitorAnalysis(`https://${domain}`)
              ]);
              
              // Add to results
              if (keywordsData.status === 'fulfilled' && keywordsData.value) {
                results.keywords = keywordsData.value;
                console.log(`✅ Added ${keywordsData.value.totalKeywords || 0} keywords to analysis`);
              }
              
              if (competitorsData.status === 'fulfilled' && competitorsData.value) {
                results.competitors = competitorsData.value;
                console.log(`✅ Added ${competitorsData.value.totalCompetitors || 0} competitors to analysis`);
              }
            } catch (keywordError) {
              console.warn(`⚠️ Could not fetch keywords/competitors:`, keywordError.message);
            }
          }
          
          // Store successful results in Supabase
          const supabaseService = require('./supabaseService');
          await supabaseService.storeAnalysis(websiteId, results, 'full_crawl');
          
          // Update task status
          await supabaseService.updateAnalysisTaskStatus(websiteId, taskId, 'completed');
          
          console.log(`✅ Full website analysis complete and stored!`);
          console.log(`   Total pages analyzed: ${results.totalPages}`);
          console.log(`   Healthy pages: ${results.healthyPages}`);
          console.log(`   Pages with issues: ${results.pagesWithIssues}`);
          console.log(`   Average score: ${results.averageScore}`);
          console.log(`   Keywords: ${results.keywords?.totalKeywords || 0}`);
          console.log(`   Competitors: ${results.competitors?.totalCompetitors || 0}`);
          
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

