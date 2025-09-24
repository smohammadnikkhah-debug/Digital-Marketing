/**
 * DataForSEO Sandbox Service
 * Provides free testing access to DataForSEO APIs using Sandbox mode
 * Based on: https://dataforseo.com/help-center/dataforseo-sandbox-best-practices
 */

const axios = require('axios');

class DataForSEOSandboxService {
  constructor() {
    this.baseURL = 'https://sandbox.dataforseo.com/v3';
    this.username = process.env.DATAFORSEO_USERNAME || 'mohammad.nikkhah@mozarex.com';
    this.password = process.env.DATAFORSEO_PASSWORD || '5fa07e54063b133c';
    this.sandboxMode = true; // Enable sandbox mode for free testing
    
    // Create axios instance with authentication
    this.api = axios.create({
      baseURL: this.baseURL,
      auth: {
        username: this.username,
        password: this.password
      },
      headers: {
        'Content-Type': 'application/json'
      }
    });
  }

  /**
   * Get keyword overview using Sandbox API (Google Ads API for free testing)
   */
  async getKeywordOverview(keywords, location = 'United States', language = 'en') {
    try {
      const tasks = keywords.map(keyword => ({
        keyword: keyword,
        location_name: location,
        language_code: language,
        device: 'desktop',
        os: 'windows'
      }));

      const response = await this.api.post('/keywords_data/google_ads/search_volume/live', [{
        tasks: tasks
      }]);

      return this.processKeywordOverviewData(response.data);
    } catch (error) {
      console.error('Sandbox Keyword Overview error:', error.response?.data || error.message);
      return { error: 'Failed to get keyword overview from Sandbox API' };
    }
  }

  /**
   * Get SERP analysis using Sandbox API
   */
  async getSerpAnalysis(keyword, location = 'United States', language = 'en', depth = 10) {
    try {
      const response = await this.api.post('/serp/google/organic/live/advanced', [{
        keyword: keyword,
        location_name: location,
        language_code: language,
        depth: depth,
        device: 'desktop',
        os: 'windows'
      }]);

      return this.processSerpData(response.data);
    } catch (error) {
      console.error('Sandbox SERP Analysis error:', error.response?.data || error.message);
      return { error: 'Failed to get SERP analysis from Sandbox API' };
    }
  }

  /**
   * Get competitor analysis using Sandbox API
   */
  async getCompetitorAnalysis(target, location = 'United States', language = 'en') {
    try {
      const response = await this.api.post('/dataforseo_labs/google/competitors_domain/live', [{
        target: target,
        location_name: location,
        language_code: language,
        limit: 20,
        exclude_top_domains: true
      }]);

      return this.processCompetitorData(response.data);
    } catch (error) {
      console.error('Sandbox Competitor Analysis error:', error.response?.data || error.message);
      return { error: 'Failed to get competitor analysis from Sandbox API' };
    }
  }

  /**
   * Get backlink analysis using Sandbox API
   */
  async getBacklinkAnalysis(target) {
    try {
      const response = await this.api.post('/backlinks/summary/live', [{
        target: target,
        include_subdomains: true,
        exclude_internal_backlinks: true
      }]);

      return this.processBacklinkData(response.data);
    } catch (error) {
      console.error('Sandbox Backlink Analysis error:', error.response?.data || error.message);
      return { error: 'Failed to get backlink analysis from Sandbox API' };
    }
  }

  /**
   * Get on-page analysis using Sandbox API
   */
  async getOnPageAnalysis(url) {
    try {
      const response = await this.api.post('/on_page/content_parsing/live', [{
        url: url,
        enable_javascript: true,
        custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }]);

      return this.processOnPageData(response.data);
    } catch (error) {
      console.error('Sandbox On-Page Analysis error:', error.response?.data || error.message);
      return { error: 'Failed to get on-page analysis from Sandbox API' };
    }
  }

  /**
   * Get domain rank overview using Sandbox API
   */
  async getDomainRankOverview(target, location = 'United States', language = 'en') {
    try {
      const response = await this.api.post('/dataforseo_labs/google/domain_rank_overview/live', [{
        target: target,
        location_name: location,
        language_code: language
      }]);

      return this.processDomainRankData(response.data);
    } catch (error) {
      console.error('Sandbox Domain Rank error:', error.response?.data || error.message);
      return { error: 'Failed to get domain rank overview from Sandbox API' };
    }
  }

  /**
   * Get keyword suggestions using Sandbox API
   */
  async getKeywordSuggestions(keyword, location = 'United States', language = 'en') {
    try {
      const response = await this.api.post('/dataforseo_labs/google/keyword_suggestions/live', [{
        keyword: keyword,
        location_name: location,
        language_code: language,
        limit: 100
      }]);

      return this.processKeywordSuggestionsData(response.data);
    } catch (error) {
      console.error('Sandbox Keyword Suggestions error:', error.response?.data || error.message);
      return { error: 'Failed to get keyword suggestions from Sandbox API' };
    }
  }

  /**
   * Get keyword ideas using Sandbox API
   */
  async getKeywordIdeas(keywords, location = 'United States', language = 'en') {
    try {
      const tasks = keywords.map(keyword => ({
        keyword: keyword,
        location_name: location,
        language_code: language,
        limit: 100
      }));

      const response = await this.api.post('/dataforseo_labs/google/keyword_ideas/live', [{
        tasks: tasks
      }]);

      return this.processKeywordIdeasData(response.data);
    } catch (error) {
      console.error('Sandbox Keyword Ideas error:', error.response?.data || error.message);
      return { error: 'Failed to get keyword ideas from Sandbox API' };
    }
  }

  /**
   * Comprehensive website analysis using Sandbox API
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
        timestamp: new Date().toISOString(),
        dataSource: 'DataForSEO Sandbox API'
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
        difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0,
        intent: item.search_intent_info?.main_intent || 'N/A'
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
   * Process keyword suggestions data
   */
  processKeywordSuggestionsData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword suggestions data available' };
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
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0)),
        avgDifficulty: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.keyword_difficulty || 0))
      }
    };
  }

  /**
   * Process keyword ideas data
   */
  processKeywordIdeasData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword ideas data available' };
    }

    const results = data.tasks[0].result;
    return {
      ideas: results.map(item => ({
        keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
        searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
        competition: item.keyword_data?.keyword_info?.competition_level || 'N/A',
        cpc: item.keyword_data?.keyword_info?.cpc || 0,
        difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0
      })),
      summary: {
        totalIdeas: results.length,
        avgSearchVolume: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.search_volume || 0)),
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0)),
        avgDifficulty: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.keyword_difficulty || 0))
      }
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
   * Get service status
   */
  getServiceStatus() {
    return {
      sandboxMode: this.sandboxMode,
      apiConfigured: !!(this.username && this.password),
      serviceMode: 'DataForSEO Sandbox API',
      message: 'Using DataForSEO Sandbox API for free testing',
      note: 'Sandbox provides free access to DataForSEO APIs with sample data',
      baseURL: this.baseURL,
      documentation: 'https://docs.dataforseo.com/v3/appendix/sandbox/',
      validation: '✅ Correctly configured to use sandbox.dataforseo.com/v3'
    };
  }
}

module.exports = new DataForSEOSandboxService();
