/**
 * DataForSEO Hybrid Service
 * Supports both MCP integration and direct API calls
 */

const axios = require('axios');

class DataForSEOHybridService {
  constructor() {
    this.baseUrl = 'https://api.dataforseo.com/v3';
    this.username = process.env.DATAFORSEO_USERNAME || 'mohammad.nikkhah@mozarex.com';
    this.password = process.env.DATAFORSEO_PASSWORD || '5fa07e54063b133c';
    this.auth = Buffer.from(`${this.username}:${this.password}`).toString('base64');
    
    // Check if we're in an MCP environment
    this.isMCPSupported = typeof window !== 'undefined' && window.mcp && typeof window.mcp.callTool === 'function';
  }

  /**
   * Make a direct API call to DataForSEO
   */
  async makeAPICall(endpoint, data) {
    try {
      const response = await axios.post(`${this.baseUrl}${endpoint}`, data, {
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        timeout: 30000
      });

      return response.data;
    } catch (error) {
      console.error(`DataForSEO API Error (${endpoint}):`, error.response?.data || error.message);
      throw new Error(`DataForSEO API call failed: ${error.response?.data?.message || error.message}`);
    }
  }

  /**
   * Call MCP tool if available, otherwise fall back to direct API
   */
  async callToolOrAPI(toolName, mcpParams, apiEndpoint, apiData) {
    if (this.isMCPSupported) {
      try {
        return await window.mcp.callTool(toolName, mcpParams);
      } catch (error) {
        console.warn(`MCP tool ${toolName} failed, falling back to direct API:`, error.message);
      }
    }

    // Fall back to direct API call
    return await this.makeAPICall(apiEndpoint, apiData);
  }

  /**
   * Get keyword overview
   */
  async getKeywordOverview(keywords, location = 'United States', language = 'en') {
    const keywordsArray = Array.isArray(keywords) ? keywords : [keywords];
    
    const mcpParams = {
      keywords: keywordsArray,
      location_name: location,
      language_code: language
    };

    const apiData = [{
      keywords: keywordsArray,
      location_name: location,
      language_code: language
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_dataforseo_labs_google_keyword_overview',
      mcpParams,
      '/dataforseo_labs/google/keyword_overview/live',
      apiData
    );

    return this.processKeywordOverviewData(result);
  }

  /**
   * Get SERP analysis
   */
  async getSerpAnalysis(keyword, location = 'United States', language = 'en', depth = 10) {
    const mcpParams = {
      keyword: keyword,
      location_name: location,
      language_code: language,
      depth: depth,
      device: 'desktop'
    };

    const apiData = [{
      keyword: keyword,
      location_name: location,
      language_code: language,
      depth: depth,
      device: 'desktop'
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_serp_organic_live_advanced',
      mcpParams,
      '/serp/google/organic/live/advanced',
      apiData
    );

    return this.processSerpData(result);
  }

  /**
   * Get competitor analysis
   */
  async getCompetitorAnalysis(target, location = 'United States', language = 'en') {
    const mcpParams = {
      target: target,
      location_name: location,
      language_code: language,
      limit: 20
    };

    const apiData = [{
      target: target,
      location_name: location,
      language_code: language,
      limit: 20
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_dataforseo_labs_google_competitors_domain',
      mcpParams,
      '/dataforseo_labs/google/competitors_domain/live',
      apiData
    );

    return this.processCompetitorData(result);
  }

  /**
   * Get backlink analysis
   */
  async getBacklinkAnalysis(target) {
    const mcpParams = {
      target: target,
      include_subdomains: true,
      exclude_internal_backlinks: true
    };

    const apiData = [{
      target: target,
      include_subdomains: true,
      exclude_internal_backlinks: true
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_backlinks_summary',
      mcpParams,
      '/backlinks/summary/live',
      apiData
    );

    return this.processBacklinkData(result);
  }

  /**
   * Get on-page analysis
   */
  async getOnPageAnalysis(url) {
    const mcpParams = {
      url: url,
      enable_javascript: true,
      custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    };

    const apiData = [{
      url: url,
      enable_javascript: true,
      custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_on_page_content_parsing',
      mcpParams,
      '/on_page/content_parsing/live',
      apiData
    );

    return this.processOnPageData(result);
  }

  /**
   * Get keyword suggestions
   */
  async getKeywordSuggestions(keyword, location = 'United States', language = 'en') {
    const mcpParams = {
      keyword: keyword,
      location_name: location,
      language_code: language,
      limit: 100
    };

    const apiData = [{
      keyword: keyword,
      location_name: location,
      language_code: language,
      limit: 100
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_dataforseo_labs_google_keyword_suggestions',
      mcpParams,
      '/dataforseo_labs/google/keyword_suggestions/live',
      apiData
    );

    return this.processKeywordSuggestionsData(result);
  }

  /**
   * Get domain rank overview
   */
  async getDomainRankOverview(target, location = 'United States', language = 'en') {
    const mcpParams = {
      target: target,
      location_name: location,
      language_code: language
    };

    const apiData = [{
      target: target,
      location_name: location,
      language_code: language
    }];

    const result = await this.callToolOrAPI(
      'mcp_dfs_dataforseo_labs_google_domain_rank_overview',
      mcpParams,
      '/dataforseo_labs/google/domain_rank_overview/live',
      apiData
    );

    return this.processDomainRankData(result);
  }

  /**
   * Comprehensive website analysis
   */
  async analyzeWebsite(url, options = {}) {
    const domain = this.extractDomain(url);
    const location = options.location || 'United States';
    const language = options.language || 'en';

    try {
      // Run multiple analyses in parallel
      const [
        onPageData,
        backlinkData,
        domainRankData,
        competitorData
      ] = await Promise.allSettled([
        this.getOnPageAnalysis(url),
        this.getBacklinkAnalysis(domain),
        this.getDomainRankOverview(domain, location, language),
        this.getCompetitorAnalysis(domain, location, language)
      ]);

      return {
        url,
        domain,
        analysis: {
          onPage: onPageData.status === 'fulfilled' ? onPageData.value : { error: onPageData.reason?.message },
          backlinks: backlinkData.status === 'fulfilled' ? backlinkData.value : { error: backlinkData.reason?.message },
          domainRank: domainRankData.status === 'fulfilled' ? domainRankData.value : { error: domainRankData.reason?.message },
          competitors: competitorData.status === 'fulfilled' ? competitorData.value : { error: competitorData.reason?.message }
        },
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error in comprehensive website analysis:', error);
      throw error;
    }
  }

  /**
   * Process keyword overview data
   */
  processKeywordOverviewData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword data available' };
    }

    const results = data.tasks[0].result;
    return {
      keywords: results.map(item => ({
        keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
        searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
        competition: item.keyword_data?.keyword_info?.competition_level || 'N/A',
        cpc: item.keyword_data?.keyword_info?.cpc || 0,
        difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0
      })),
      summary: {
        totalKeywords: results.length,
        avgSearchVolume: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.search_volume || 0)),
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0)),
        avgDifficulty: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.keyword_difficulty || 0))
      }
    };
  }

  /**
   * Process SERP data
   */
  processSerpData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No SERP data available' };
    }

    const results = data.tasks[0].result[0];
    return {
      keyword: results.keyword,
      location: results.location_name,
      language: results.language_code,
      totalResults: results.total_count,
      items: results.items?.map(item => ({
        position: item.rank_group,
        title: item.title,
        url: item.url,
        description: item.description,
        domain: this.extractDomain(item.url)
      })) || [],
      relatedKeywords: results.related_searches?.map(item => item.keyword) || []
    };
  }

  /**
   * Process competitor data
   */
  processCompetitorData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No competitor data available' };
    }

    const results = data.tasks[0].result;
    return {
      competitors: results.map(competitor => ({
        domain: competitor.target,
        rank: competitor.rank,
        organicTraffic: competitor.metrics?.organic?.etv || 0,
        organicKeywords: competitor.metrics?.organic?.count || 0,
        paidTraffic: competitor.metrics?.paid?.etv || 0,
        paidKeywords: competitor.metrics?.paid?.count || 0,
        visibility: competitor.metrics?.organic?.visibility || 0
      })),
      summary: {
        totalCompetitors: results.length,
        avgRank: this.calculateAverage(results.map(r => r.rank || 0)),
        totalOrganicTraffic: results.reduce((sum, r) => sum + (r.metrics?.organic?.etv || 0), 0),
        totalPaidTraffic: results.reduce((sum, r) => sum + (r.metrics?.paid?.etv || 0), 0)
      }
    };
  }

  /**
   * Process backlink data
   */
  processBacklinkData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No backlink data available' };
    }

    const result = data.tasks[0].result[0];
    return {
      target: result.target,
      totalBacklinks: result.backlinks || 0,
      referringDomains: result.referring_domains || 0,
      referringMainDomains: result.referring_main_domains || 0,
      rank: result.rank || 0,
      brokenBacklinks: result.broken_backlinks || 0,
      brokenPages: result.broken_pages || 0,
      referringNetworks: result.referring_networks || 0,
      referringIps: result.referring_ips || 0
    };
  }

  /**
   * Process on-page data
   */
  processOnPageData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No on-page data available' };
    }

    const result = data.tasks[0].result[0];
    return {
      url: result.url,
      title: result.title,
      description: result.description,
      headings: result.headings || [],
      images: result.images || [],
      links: result.links || [],
      text: result.text || '',
      wordCount: result.text?.split(' ').length || 0,
      loadTime: result.load_time || 0,
      statusCode: result.status_code || 0
    };
  }

  /**
   * Process keyword suggestions data
   */
  processKeywordSuggestionsData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword suggestions available' };
    }

    const results = data.tasks[0].result;
    return {
      suggestions: results.map(item => ({
        keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
        searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
        competition: item.keyword_data?.keyword_info?.competition_level || 'N/A',
        cpc: item.keyword_data?.keyword_info?.cpc || 0,
        difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0
      })),
      summary: {
        totalSuggestions: results.length,
        avgSearchVolume: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.search_volume || 0)),
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0))
      }
    };
  }

  /**
   * Process domain rank data
   */
  processDomainRankData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No domain rank data available' };
    }

    const result = data.tasks[0].result[0];
    return {
      target: result.target,
      rank: result.rank,
      organicTraffic: result.metrics?.organic?.etv || 0,
      organicKeywords: result.metrics?.organic?.count || 0,
      organicVisibility: result.metrics?.organic?.visibility || 0,
      paidTraffic: result.metrics?.paid?.etv || 0,
      paidKeywords: result.metrics?.paid?.count || 0,
      paidVisibility: result.metrics?.paid?.visibility || 0,
      totalTraffic: (result.metrics?.organic?.etv || 0) + (result.metrics?.paid?.etv || 0)
    };
  }

  /**
   * Calculate average from array of numbers
   */
  calculateAverage(numbers) {
    const validNumbers = numbers.filter(n => typeof n === 'number' && !isNaN(n));
    if (validNumbers.length === 0) return 0;
    return validNumbers.reduce((sum, num) => sum + num, 0) / validNumbers.length;
  }

  /**
   * Extract domain from URL
   */
  extractDomain(url) {
    try {
      return new URL(url).hostname;
    } catch (error) {
      return url;
    }
  }

  /**
   * Check service status
   */
  getServiceStatus() {
    return {
      mcpSupported: this.isMCPSupported,
      apiConfigured: !!(this.username && this.password),
      serviceMode: this.isMCPSupported ? 'MCP + API Fallback' : 'Direct API',
      message: this.isMCPSupported 
        ? 'MCP tools available with API fallback' 
        : 'Using direct DataForSEO API calls'
    };
  }
}

module.exports = new DataForSEOHybridService();

