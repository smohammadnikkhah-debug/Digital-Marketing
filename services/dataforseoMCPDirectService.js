/**
 * DataForSEO MCP Direct Integration Service
 * Direct integration with MCP tools for DataForSEO analysis
 */

class DataForSEOMCPDirectService {
  constructor() {
    this.mcpTools = {
      // Keyword Analysis Tools
      keywordOverview: 'mcp_dfs_dataforseo_labs_google_keyword_overview',
      keywordSuggestions: 'mcp_dfs_dataforseo_labs_google_keyword_suggestions',
      keywordIdeas: 'mcp_dfs_dataforseo_labs_google_keyword_ideas',
      keywordDifficulty: 'mcp_dfs_dataforseo_labs_bulk_keyword_difficulty',
      searchVolume: 'mcp_dfs_keywords_data_google_ads_search_volume',
      
      // SERP Analysis Tools
      serpOrganic: 'mcp_dfs_serp_organic_live_advanced',
      
      // Domain Analysis Tools
      domainRank: 'mcp_dfs_dataforseo_labs_google_domain_rank_overview',
      domainIntersection: 'mcp_dfs_dataforseo_labs_google_domain_intersection',
      competitors: 'mcp_dfs_dataforseo_labs_google_competitors_domain',
      
      // Backlink Analysis Tools
      backlinks: 'mcp_dfs_backlinks_backlinks',
      backlinkSummary: 'mcp_dfs_backlinks_summary',
      backlinkAnchors: 'mcp_dfs_backlinks_anchors',
      backlinkCompetitors: 'mcp_dfs_backlinks_competitors',
      
      // On-Page Analysis Tools
      onPageContent: 'mcp_dfs_on_page_content_parsing',
      onPageLighthouse: 'mcp_dfs_on_page_lighthouse',
      onPageInstant: 'mcp_dfs_on_page_instant_pages',
      
      // Trends and Demographics
      googleTrends: 'mcp_dfs_keywords_data_google_trends_explore',
      trendsDemography: 'mcp_dfs_keywords_data_dataforseo_trends_demography',
      
      // Content Analysis
      contentAnalysis: 'mcp_dfs_content_analysis_search',
      contentSummary: 'mcp_dfs_content_analysis_summary',
      
      // Business Data
      businessListings: 'mcp_dfs_business_data_business_listings_search'
    };
  }

  /**
   * Check if MCP tools are available
   */
  isMCPSupported() {
    return typeof window !== 'undefined' && window.mcp && typeof window.mcp.callTool === 'function';
  }

  /**
   * Call MCP tool with error handling
   */
  async callMCPTool(toolName, params) {
    if (!this.isMCPSupported()) {
      throw new Error('MCP tools are not available in this environment');
    }

    try {
      const result = await window.mcp.callTool(toolName, params);
      return result;
    } catch (error) {
      console.error(`Error calling MCP tool ${toolName}:`, error);
      throw new Error(`MCP tool ${toolName} failed: ${error.message}`);
    }
  }

  /**
   * Get keyword overview using MCP
   */
  async getKeywordOverview(keywords, location = 'United States', language = 'en') {
    const params = {
      keywords: Array.isArray(keywords) ? keywords : [keywords],
      location_name: location,
      language_code: language
    };

    const result = await this.callMCPTool(this.mcpTools.keywordOverview, params);
    return this.processKeywordOverviewData(result);
  }

  /**
   * Get keyword suggestions using MCP
   */
  async getKeywordSuggestions(keyword, location = 'United States', language = 'en') {
    const params = {
      keyword: keyword,
      location_name: location,
      language_code: language,
      limit: 100
    };

    const result = await this.callMCPTool(this.mcpTools.keywordSuggestions, params);
    return this.processKeywordSuggestionsData(result);
  }

  /**
   * Get keyword ideas using MCP
   */
  async getKeywordIdeas(keywords, location = 'United States', language = 'en') {
    const params = {
      keywords: Array.isArray(keywords) ? keywords : [keywords],
      location_name: location,
      language_code: language,
      limit: 100
    };

    const result = await this.callMCPTool(this.mcpTools.keywordIdeas, params);
    return this.processKeywordIdeasData(result);
  }

  /**
   * Get keyword difficulty using MCP
   */
  async getKeywordDifficulty(keywords, location = 'United States', language = 'en') {
    const params = {
      keywords: Array.isArray(keywords) ? keywords : [keywords],
      location_name: location,
      language_code: language
    };

    const result = await this.callMCPTool(this.mcpTools.keywordDifficulty, params);
    return this.processKeywordDifficultyData(result);
  }

  /**
   * Get search volume using MCP
   */
  async getSearchVolume(keywords, location = 'United States', language = 'en') {
    const params = {
      keywords: Array.isArray(keywords) ? keywords : [keywords],
      location_name: location,
      language_code: language
    };

    const result = await this.callMCPTool(this.mcpTools.searchVolume, params);
    return this.processSearchVolumeData(result);
  }

  /**
   * Get SERP analysis using MCP
   */
  async getSerpAnalysis(keyword, location = 'United States', language = 'en', depth = 10) {
    const params = {
      keyword: keyword,
      location_name: location,
      language_code: language,
      depth: depth,
      device: 'desktop'
    };

    const result = await this.callMCPTool(this.mcpTools.serpOrganic, params);
    return this.processSerpData(result);
  }

  /**
   * Get domain rank overview using MCP
   */
  async getDomainRankOverview(target, location = 'United States', language = 'en') {
    const params = {
      target: target,
      location_name: location,
      language_code: language
    };

    const result = await this.callMCPTool(this.mcpTools.domainRank, params);
    return this.processDomainRankData(result);
  }

  /**
   * Get competitor analysis using MCP
   */
  async getCompetitorAnalysis(target, location = 'United States', language = 'en') {
    const params = {
      target: target,
      location_name: location,
      language_code: language,
      limit: 20
    };

    const result = await this.callMCPTool(this.mcpTools.competitors, params);
    return this.processCompetitorData(result);
  }

  /**
   * Get backlink analysis using MCP
   */
  async getBacklinkAnalysis(target) {
    const params = {
      target: target,
      include_subdomains: true,
      exclude_internal_backlinks: true
    };

    const result = await this.callMCPTool(this.mcpTools.backlinkSummary, params);
    return this.processBacklinkData(result);
  }

  /**
   * Get detailed backlinks using MCP
   */
  async getDetailedBacklinks(target, limit = 100) {
    const params = {
      target: target,
      limit: limit,
      order_by: ['rank,desc']
    };

    const result = await this.callMCPTool(this.mcpTools.backlinks, params);
    return this.processDetailedBacklinksData(result);
  }

  /**
   * Get on-page analysis using MCP
   */
  async getOnPageAnalysis(url) {
    const params = {
      url: url,
      enable_javascript: true,
      custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    };

    const result = await this.callMCPTool(this.mcpTools.onPageContent, params);
    return this.processOnPageData(result);
  }

  /**
   * Get Lighthouse analysis using MCP
   */
  async getLighthouseAnalysis(url) {
    const params = {
      url: url,
      enable_javascript: true
    };

    const result = await this.callMCPTool(this.mcpTools.onPageLighthouse, params);
    return this.processLighthouseData(result);
  }

  /**
   * Get Google Trends data using MCP
   */
  async getGoogleTrends(keywords, location = 'United States', language = 'en', timeRange = 'past_12_months') {
    const params = {
      keywords: Array.isArray(keywords) ? keywords : [keywords],
      location_name: location,
      language_code: language,
      time_range: timeRange,
      item_types: ['google_trends_graph']
    };

    const result = await this.callMCPTool(this.mcpTools.googleTrends, params);
    return this.processGoogleTrendsData(result);
  }

  /**
   * Get content analysis using MCP
   */
  async getContentAnalysis(keyword, pageType = null) {
    const params = {
      keyword: keyword,
      limit: 100
    };

    if (pageType) {
      params.page_type = [pageType];
    }

    const result = await this.callMCPTool(this.mcpTools.contentAnalysis, params);
    return this.processContentAnalysisData(result);
  }

  /**
   * Get business listings using MCP
   */
  async getBusinessListings(categories = [], location = null) {
    const params = {
      limit: 100
    };

    if (categories.length > 0) {
      params.categories = categories;
    }

    if (location) {
      params.location_coordinate = location;
    }

    const result = await this.callMCPTool(this.mcpTools.businessListings, params);
    return this.processBusinessListingsData(result);
  }

  /**
   * Comprehensive website analysis using multiple MCP tools
   */
  async analyzeWebsite(url, options = {}) {
    const domain = this.extractDomain(url);
    const location = options.location || 'United States';
    const language = options.language || 'en';

    try {
      // Run multiple analyses in parallel
      const [
        onPageData,
        lighthouseData,
        backlinkData,
        domainRankData,
        competitorData
      ] = await Promise.allSettled([
        this.getOnPageAnalysis(url),
        this.getLighthouseAnalysis(url),
        this.getBacklinkAnalysis(domain),
        this.getDomainRankOverview(domain, location, language),
        this.getCompetitorAnalysis(domain, location, language)
      ]);

      return {
        url,
        domain,
        analysis: {
          onPage: onPageData.status === 'fulfilled' ? onPageData.value : { error: onPageData.reason?.message },
          lighthouse: lighthouseData.status === 'fulfilled' ? lighthouseData.value : { error: lighthouseData.reason?.message },
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
   * Process keyword ideas data
   */
  processKeywordIdeasData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword ideas available' };
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
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0))
      }
    };
  }

  /**
   * Process keyword difficulty data
   */
  processKeywordDifficultyData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No keyword difficulty data available' };
    }

    const results = data.tasks[0].result;
    return {
      keywords: results.map(item => ({
        keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
        difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0,
        searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
        competition: item.keyword_data?.keyword_info?.competition_level || 'N/A'
      })),
      summary: {
        totalKeywords: results.length,
        avgDifficulty: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.keyword_difficulty || 0)),
        avgSearchVolume: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.search_volume || 0))
      }
    };
  }

  /**
   * Process search volume data
   */
  processSearchVolumeData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No search volume data available' };
    }

    const results = data.tasks[0].result;
    return {
      keywords: results.map(item => ({
        keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
        searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
        competition: item.keyword_data?.keyword_info?.competition_level || 'N/A',
        cpc: item.keyword_data?.keyword_info?.cpc || 0
      })),
      summary: {
        totalKeywords: results.length,
        avgSearchVolume: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.search_volume || 0)),
        avgCPC: this.calculateAverage(results.map(r => r.keyword_data?.keyword_info?.cpc || 0))
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
   * Process detailed backlinks data
   */
  processDetailedBacklinksData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No detailed backlinks data available' };
    }

    const results = data.tasks[0].result;
    return {
      backlinks: results.map(backlink => ({
        url: backlink.url_from,
        domain: backlink.domain_from,
        anchor: backlink.anchor,
        rank: backlink.rank,
        pageRank: backlink.page_from_rank,
        domainRank: backlink.domain_from_rank,
        dofollow: backlink.dofollow,
        firstSeen: backlink.first_seen,
        lastSeen: backlink.last_seen
      })),
      summary: {
        totalBacklinks: results.length,
        avgRank: this.calculateAverage(results.map(r => r.rank || 0)),
        avgPageRank: this.calculateAverage(results.map(r => r.page_from_rank || 0)),
        avgDomainRank: this.calculateAverage(results.map(r => r.domain_from_rank || 0))
      }
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
   * Process Lighthouse data
   */
  processLighthouseData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No Lighthouse data available' };
    }

    const result = data.tasks[0].result[0];
    return {
      url: result.url,
      performance: result.lighthouse?.performance || 0,
      accessibility: result.lighthouse?.accessibility || 0,
      bestPractices: result.lighthouse?.best_practices || 0,
      seo: result.lighthouse?.seo || 0,
      firstContentfulPaint: result.lighthouse?.first_contentful_paint || 0,
      largestContentfulPaint: result.lighthouse?.largest_contentful_paint || 0,
      cumulativeLayoutShift: result.lighthouse?.cumulative_layout_shift || 0,
      speedIndex: result.lighthouse?.speed_index || 0
    };
  }

  /**
   * Process Google Trends data
   */
  processGoogleTrendsData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No Google Trends data available' };
    }

    const results = data.tasks[0].result[0];
    return {
      keywords: results.keywords,
      location: results.location_name,
      language: results.language_code,
      timeRange: results.time_range,
      trends: results.google_trends_graph?.map(item => ({
        date: item.date,
        values: item.values
      })) || []
    };
  }

  /**
   * Process content analysis data
   */
  processContentAnalysisData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No content analysis data available' };
    }

    const results = data.tasks[0].result;
    return {
      citations: results.map(item => ({
        url: item.url,
        title: item.title,
        description: item.description,
        domain: item.domain,
        sentiment: item.content_info?.sentiment_connotations || {},
        connotation: item.content_info?.connotation_types || {}
      })),
      summary: {
        totalCitations: results.length,
        avgSentiment: this.calculateAverage(results.map(r => r.content_info?.sentiment_connotations?.positive || 0))
      }
    };
  }

  /**
   * Process business listings data
   */
  processBusinessListingsData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      return { error: 'No business listings data available' };
    }

    const results = data.tasks[0].result;
    return {
      listings: results.map(listing => ({
        title: listing.title,
        description: listing.description,
        address: listing.address,
        phone: listing.phone,
        website: listing.website,
        rating: listing.rating?.value || 0,
        reviews: listing.rating?.votes_count || 0,
        categories: listing.categories || []
      })),
      summary: {
        totalListings: results.length,
        avgRating: this.calculateAverage(results.map(r => r.rating?.value || 0))
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
   * Get available MCP tools
   */
  getAvailableTools() {
    return Object.keys(this.mcpTools).map(key => ({
      name: key,
      tool: this.mcpTools[key],
      description: this.getToolDescription(key)
    }));
  }

  /**
   * Get tool description
   */
  getToolDescription(toolName) {
    const descriptions = {
      keywordOverview: 'Get comprehensive keyword data including search volume, competition, CPC, and difficulty',
      keywordSuggestions: 'Discover keyword suggestions and related search terms',
      keywordIdeas: 'Get keyword ideas based on seed keywords',
      keywordDifficulty: 'Analyze keyword difficulty scores',
      searchVolume: 'Get search volume data for keywords',
      serpOrganic: 'Analyze search engine results pages',
      domainRank: 'Get domain ranking and traffic data',
      domainIntersection: 'Find keywords that domains rank for',
      competitors: 'Analyze competitor domains and their performance',
      backlinks: 'Get detailed backlink information',
      backlinkSummary: 'Get backlink summary statistics',
      backlinkAnchors: 'Analyze anchor text distribution',
      backlinkCompetitors: 'Find backlink competitors',
      onPageContent: 'Analyze on-page content and structure',
      onPageLighthouse: 'Get Lighthouse performance metrics',
      onPageInstant: 'Get instant page analysis',
      googleTrends: 'Get Google Trends data',
      trendsDemography: 'Get demographic trends data',
      contentAnalysis: 'Analyze content citations and sentiment',
      contentSummary: 'Get content analysis summary',
      businessListings: 'Search business listings'
    };

    return descriptions[toolName] || 'MCP tool for DataForSEO analysis';
  }
}

module.exports = new DataForSEOMCPDirectService();


