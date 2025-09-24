/**
 * DataForSEO MCP Service
 * Integrates with DataForSEO MCP tools for comprehensive SEO analysis
 */

class DataForSEOMCPService {
  constructor() {
    this.baseUrl = 'https://api.dataforseo.com/v3';
    this.username = process.env.DATAFORSEO_USERNAME || 'your_dataforseo_login';
    this.password = process.env.DATAFORSEO_PASSWORD || 'your_dataforseo_password';
    this.auth = Buffer.from(`${this.username}:${this.password}`).toString('base64');
  }

  /**
   * Get keyword overview data using MCP tools
   */
  async getKeywordOverview(keywords, location = 'United States', language = 'en') {
    try {
      // This would be called via MCP tools in the actual implementation
      const response = await fetch(`${this.baseUrl}/dataforseo_labs/google/keyword_overview/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          keywords: Array.isArray(keywords) ? keywords : [keywords],
          location_name: location,
          language_code: language
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processKeywordOverviewData(data);
    } catch (error) {
      console.error('Error getting keyword overview:', error);
      throw error;
    }
  }

  /**
   * Get SERP analysis using MCP tools
   */
  async getSerpAnalysis(keyword, location = 'United States', language = 'en', depth = 10) {
    try {
      const response = await fetch(`${this.baseUrl}/serp/google/organic/live/advanced`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          keyword: keyword,
          location_name: location,
          language_code: language,
          depth: depth,
          device: 'desktop'
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processSerpData(data);
    } catch (error) {
      console.error('Error getting SERP analysis:', error);
      throw error;
    }
  }

  /**
   * Get competitor analysis using MCP tools
   */
  async getCompetitorAnalysis(target, location = 'United States', language = 'en') {
    try {
      const response = await fetch(`${this.baseUrl}/dataforseo_labs/google/competitors_domain/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          target: target,
          location_name: location,
          language_code: language,
          limit: 20
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processCompetitorData(data);
    } catch (error) {
      console.error('Error getting competitor analysis:', error);
      throw error;
    }
  }

  /**
   * Get backlink analysis using MCP tools
   */
  async getBacklinkAnalysis(target) {
    try {
      const response = await fetch(`${this.baseUrl}/backlinks/summary/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          target: target,
          include_subdomains: true,
          exclude_internal_backlinks: true
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processBacklinkData(data);
    } catch (error) {
      console.error('Error getting backlink analysis:', error);
      throw error;
    }
  }

  /**
   * Get on-page analysis using MCP tools
   */
  async getOnPageAnalysis(url) {
    try {
      const response = await fetch(`${this.baseUrl}/on_page/content_parsing/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          url: url,
          enable_javascript: true,
          custom_user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processOnPageData(data);
    } catch (error) {
      console.error('Error getting on-page analysis:', error);
      throw error;
    }
  }

  /**
   * Get keyword suggestions using MCP tools
   */
  async getKeywordSuggestions(keyword, location = 'United States', language = 'en') {
    try {
      const response = await fetch(`${this.baseUrl}/dataforseo_labs/google/keyword_suggestions/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          keyword: keyword,
          location_name: location,
          language_code: language,
          limit: 100
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processKeywordSuggestionsData(data);
    } catch (error) {
      console.error('Error getting keyword suggestions:', error);
      throw error;
    }
  }

  /**
   * Get domain rank overview using MCP tools
   */
  async getDomainRankOverview(target, location = 'United States', language = 'en') {
    try {
      const response = await fetch(`${this.baseUrl}/dataforseo_labs/google/domain_rank_overview/live`, {
        method: 'POST',
        headers: {
          'Authorization': `Basic ${this.auth}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify([{
          target: target,
          location_name: location,
          language_code: language
        }])
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return this.processDomainRankData(data);
    } catch (error) {
      console.error('Error getting domain rank overview:', error);
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
   * Comprehensive website analysis using multiple MCP tools
   */
  async analyzeWebsite(url, options = {}) {
    try {
      const domain = this.extractDomain(url);
      const location = options.location || 'United States';
      const language = options.language || 'en';

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
}

module.exports = new DataForSEOMCPService();


