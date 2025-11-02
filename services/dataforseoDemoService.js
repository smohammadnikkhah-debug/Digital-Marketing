/**
 * DataForSEO Demo Service
 * Provides demo data when API credits are not available
 */

class DataForSEODemoService {
  constructor() {
    this.isMCPSupported = typeof window !== 'undefined' && window.mcp && typeof window.mcp.callTool === 'function';
  }

  /**
   * Generate demo keyword overview data
   */
  generateDemoKeywordOverview(keywords) {
    const keywordsArray = Array.isArray(keywords) ? keywords : [keywords];
    
    return {
      keywords: keywordsArray.map(keyword => ({
        keyword: keyword,
        searchVolume: Math.floor(Math.random() * 100000) + 1000,
        competition: ['LOW', 'MEDIUM', 'HIGH'][Math.floor(Math.random() * 3)],
        cpc: Math.random() * 5 + 0.5,
        difficulty: Math.floor(Math.random() * 100) + 1
      })),
      summary: {
        totalKeywords: keywordsArray.length,
        avgSearchVolume: Math.floor(Math.random() * 50000) + 5000,
        avgCPC: Math.random() * 3 + 1,
        avgDifficulty: Math.floor(Math.random() * 50) + 25
      }
    };
  }

  /**
   * Generate demo SERP data
   */
  generateDemoSerpData(keyword) {
    const domains = ['google.com', 'microsoft.com', 'apple.com', 'amazon.com', 'facebook.com'];
    
    return {
      keyword: keyword,
      location: 'United States',
      language: 'en',
      totalResults: Math.floor(Math.random() * 1000000000) + 1000000,
      items: Array.from({ length: 10 }, (_, i) => ({
        position: i + 1,
        title: `${keyword} - ${domains[Math.floor(Math.random() * domains.length)]}`,
        url: `https://${domains[Math.floor(Math.random() * domains.length)]}/${keyword.replace(/\s+/g, '-')}`,
        description: `Learn about ${keyword} and discover the best solutions for your needs.`,
        domain: domains[Math.floor(Math.random() * domains.length)]
      })),
      relatedKeywords: [
        `${keyword} tools`,
        `${keyword} software`,
        `best ${keyword}`,
        `${keyword} guide`,
        `${keyword} tips`
      ]
    };
  }

  /**
   * Generate demo competitor data
   */
  generateDemoCompetitorData(target) {
    const competitors = [
      { domain: 'competitor1.com', rank: 85, organicTraffic: 150000, organicKeywords: 25000 },
      { domain: 'competitor2.com', rank: 92, organicTraffic: 98000, organicKeywords: 18000 },
      { domain: 'competitor3.com', rank: 78, organicTraffic: 210000, organicKeywords: 32000 },
      { domain: 'competitor4.com', rank: 88, organicTraffic: 120000, organicKeywords: 22000 },
      { domain: 'competitor5.com', rank: 95, organicTraffic: 75000, organicKeywords: 15000 }
    ];

    return {
      competitors: competitors,
      summary: {
        totalCompetitors: competitors.length,
        avgRank: Math.round(competitors.reduce((sum, c) => sum + c.rank, 0) / competitors.length),
        totalOrganicTraffic: competitors.reduce((sum, c) => sum + c.organicTraffic, 0),
        totalPaidTraffic: Math.floor(Math.random() * 50000) + 10000
      }
    };
  }

  /**
   * Generate demo backlink data
   */
  generateDemoBacklinkData(target) {
    return {
      target: target,
      totalBacklinks: Math.floor(Math.random() * 1000000) + 10000,
      referringDomains: Math.floor(Math.random() * 50000) + 1000,
      referringMainDomains: Math.floor(Math.random() * 10000) + 500,
      rank: Math.floor(Math.random() * 100) + 1,
      brokenBacklinks: Math.floor(Math.random() * 100) + 10,
      brokenPages: Math.floor(Math.random() * 50) + 5,
      referringNetworks: Math.floor(Math.random() * 1000) + 100,
      referringIps: Math.floor(Math.random() * 500) + 50
    };
  }

  /**
   * Generate demo on-page data
   */
  generateDemoOnPageData(url) {
    return {
      url: url,
      title: `Demo Page Title - ${new URL(url).hostname}`,
      description: 'This is a demo description for SEO analysis purposes.',
      headings: [
        { level: 1, text: 'Main Heading' },
        { level: 2, text: 'Sub Heading 1' },
        { level: 2, text: 'Sub Heading 2' },
        { level: 3, text: 'Sub Sub Heading' }
      ],
      images: Array.from({ length: 5 }, (_, i) => ({
        src: `https://example.com/image${i + 1}.jpg`,
        alt: `Demo image ${i + 1}`
      })),
      links: Array.from({ length: 10 }, (_, i) => ({
        url: `https://example.com/link${i + 1}`,
        text: `Demo link ${i + 1}`
      })),
      text: 'This is demo text content for SEO analysis. It contains multiple sentences and paragraphs to simulate real website content.',
      wordCount: Math.floor(Math.random() * 1000) + 500,
      loadTime: Math.floor(Math.random() * 3000) + 500,
      statusCode: 200
    };
  }

  /**
   * Generate demo domain rank data
   */
  generateDemoDomainRankData(target) {
    return {
      target: target,
      rank: Math.floor(Math.random() * 100) + 1,
      organicTraffic: Math.floor(Math.random() * 1000000) + 10000,
      organicKeywords: Math.floor(Math.random() * 100000) + 1000,
      organicVisibility: Math.random() * 100,
      paidTraffic: Math.floor(Math.random() * 100000) + 1000,
      paidKeywords: Math.floor(Math.random() * 10000) + 100,
      paidVisibility: Math.random() * 50,
      totalTraffic: Math.floor(Math.random() * 1100000) + 11000
    };
  }

  /**
   * Get keyword overview (demo or MCP)
   */
  async getKeywordOverview(keywords, location = 'United States', language = 'en') {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_dataforseo_labs_google_keyword_overview', {
          keywords: Array.isArray(keywords) ? keywords : [keywords],
          location_name: location,
          language_code: language
        });
        return this.processKeywordOverviewData(result);
      } catch (error) {
        console.warn('MCP keyword overview failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoKeywordOverview(keywords);
  }

  /**
   * Get SERP analysis (demo or MCP)
   */
  async getSerpAnalysis(keyword, location = 'United States', language = 'en', depth = 10) {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_serp_organic_live_advanced', {
          keyword: keyword,
          location_name: location,
          language_code: language,
          depth: depth,
          device: 'desktop'
        });
        return this.processSerpData(result);
      } catch (error) {
        console.warn('MCP SERP analysis failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoSerpData(keyword);
  }

  /**
   * Get competitor analysis (demo or MCP)
   */
  async getCompetitorAnalysis(target, location = 'United States', language = 'en') {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_dataforseo_labs_google_competitors_domain', {
          target: target,
          location_name: location,
          language_code: language,
          limit: 20
        });
        return this.processCompetitorData(result);
      } catch (error) {
        console.warn('MCP competitor analysis failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoCompetitorData(target);
  }

  /**
   * Get backlink analysis (demo or MCP)
   */
  async getBacklinkAnalysis(target) {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_backlinks_summary', {
          target: target,
          include_subdomains: true,
          exclude_internal_backlinks: true
        });
        return this.processBacklinkData(result);
      } catch (error) {
        console.warn('MCP backlink analysis failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoBacklinkData(target);
  }

  /**
   * Get on-page analysis (demo or MCP)
   */
  async getOnPageAnalysis(url) {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_on_page_content_parsing', {
          url: url,
          enable_javascript: true,
          custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        });
        return this.processOnPageData(result);
      } catch (error) {
        console.warn('MCP on-page analysis failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoOnPageData(url);
  }

  /**
   * Get domain rank overview (demo or MCP)
   */
  async getDomainRankOverview(target, location = 'United States', language = 'en') {
    if (this.isMCPSupported) {
      try {
        const result = await window.mcp.callTool('mcp_dfs_dataforseo_labs_google_domain_rank_overview', {
          target: target,
          location_name: location,
          language_code: language
        });
        return this.processDomainRankData(result);
      } catch (error) {
        console.warn('MCP domain rank analysis failed, using demo data:', error.message);
      }
    }

    // Return demo data
    return this.generateDemoDomainRankData(target);
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
        timestamp: new Date().toISOString(),
        dataSource: this.isMCPSupported ? 'MCP + Demo Fallback' : 'Demo Data'
      };
    } catch (error) {
      console.error('Error in comprehensive website analysis:', error);
      throw error;
    }
  }

  /**
   * Process keyword overview data (for MCP results)
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
   * Process SERP data (for MCP results)
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
   * Process competitor data (for MCP results)
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
   * Process backlink data (for MCP results)
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
   * Process on-page data (for MCP results)
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
   * Process domain rank data (for MCP results)
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
   * Get service status
   */
  getServiceStatus() {
    return {
      mcpSupported: this.isMCPSupported,
      serviceMode: this.isMCPSupported ? 'MCP + Demo Fallback' : 'Demo Data Only',
      message: this.isMCPSupported 
        ? 'MCP tools available with demo data fallback' 
        : 'Using demo data for testing (MCP not available)',
      note: 'This service provides demo data when MCP tools are not available or API credits are insufficient'
    };
  }
}

module.exports = new DataForSEODemoService();







