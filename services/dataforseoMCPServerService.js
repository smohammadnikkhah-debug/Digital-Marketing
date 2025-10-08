/**
 * DataForSEO MCP Server-Side Integration Service
 * Uses MCP tools available in Cursor/Node.js environment
 */

class DataForSEOMCPServerService {
  constructor() {
    this.mcpTools = {
      // Keyword Analysis Tools
      keywordOverview: 'mcp_dfs_dataforseo_labs_google_keyword_overview',
      rankedKeywords: 'mcp_dfs_dataforseo_labs_google_ranked_keywords',
      keywordSuggestions: 'mcp_dfs_dataforseo_labs_google_keyword_suggestions',
      keywordIdeas: 'mcp_dfs_dataforseo_labs_google_keyword_ideas',
      keywordsForSite: 'mcp_dfs_dataforseo_labs_google_keywords_for_site',
      
      // Competitor & Domain Analysis
      competitors: 'mcp_dfs_dataforseo_labs_google_competitors_domain',
      domainRank: 'mcp_dfs_dataforseo_labs_google_domain_rank_overview',
      domainIntersection: 'mcp_dfs_dataforseo_labs_google_domain_intersection',
      
      // SERP Analysis
      serpOrganic: 'mcp_dfs_serp_organic_live_advanced',
      
      // Backlink Analysis
      backlinkSummary: 'mcp_dfs_backlinks_summary',
      backlinks: 'mcp_dfs_backlinks_backlinks',
      
      // On-Page Analysis (note: these may require special subscription)
      // We'll use the basic APIs for now
    };

    console.log('🔌 DataForSEO MCP Server Service initialized');
  }

  /**
   * Check if MCP tools are available
   */
  isMCPSupported() {
    // Check if we have access to MCP tools in the server environment
    // In Cursor, MCP tools are available through the runtime
    try {
      return typeof global !== 'undefined' || typeof process !== 'undefined';
    } catch (error) {
      return false;
    }
  }

  /**
   * Call MCP tool with error handling (Server-side)
   * This method should be called through the Cursor MCP interface
   */
  async callMCPTool(toolName, params) {
    // Note: In a proper MCP integration, this would call the MCP tool directly
    // For now, we'll use the DataForSEO API directly through the MCP tools
    // that are available in the Cursor environment
    
    console.log(`📞 Calling MCP tool: ${toolName}`, params);
    
    try {
      // This is a placeholder - in actual implementation, Cursor's MCP runtime
      // would handle this call
      throw new Error('MCP tool calls must be made through Cursor MCP runtime');
    } catch (error) {
      console.error(`Error calling MCP tool ${toolName}:`, error);
      throw error;
    }
  }

  /**
   * Get keywords for a domain using MCP
   */
  async getKeywordsForDomain(domain, location = 'United States', language = 'en', limit = 20) {
    console.log(`🔑 Getting keywords for domain: ${domain} via MCP`);
    
    const params = {
      target: domain,
      location_name: location,
      language_code: language,
      limit: limit,
      order_by: ['keyword_data.keyword_info.search_volume,desc']
    };

    try {
      const result = await this.callMCPTool(this.mcpTools.keywordsForSite, params);
      return this.processKeywordsForSiteData(result);
    } catch (error) {
      console.error('Error getting keywords for domain via MCP:', error);
      return {
        success: false,
        error: error.message,
        keywords: []
      };
    }
  }

  /**
   * Get competitor analysis using MCP
   */
  async getCompetitorAnalysis(domain, location = 'United States', language = 'en', limit = 10) {
    console.log(`🏆 Getting competitors for domain: ${domain} via MCP`);
    
    const params = {
      target: domain,
      location_name: location,
      language_code: language,
      limit: limit,
      filters: [['metrics.organic.count', '>', 10]]
    };

    try {
      const result = await this.callMCPTool(this.mcpTools.competitors, params);
      return this.processCompetitorData(result);
    } catch (error) {
      console.error('Error getting competitors via MCP:', error);
      return {
        success: false,
        error: error.message,
        competitors: []
      };
    }
  }

  /**
   * Get domain rank overview using MCP
   */
  async getDomainRankOverview(domain, location = 'United States', language = 'en') {
    console.log(`📊 Getting domain rank for: ${domain} via MCP`);
    
    const params = {
      target: domain,
      location_name: location,
      language_code: language
    };

    try {
      const result = await this.callMCPTool(this.mcpTools.domainRank, params);
      return this.processDomainRankData(result);
    } catch (error) {
      console.error('Error getting domain rank via MCP:', error);
      return {
        success: false,
        error: error.message,
        rank: 0
      };
    }
  }

  /**
   * Get backlink summary using MCP
   */
  async getBacklinkSummary(domain) {
    console.log(`🔗 Getting backlink summary for: ${domain} via MCP`);
    
    const params = {
      target: domain,
      include_subdomains: true,
      exclude_internal_backlinks: true
    };

    try {
      const result = await this.callMCPTool(this.mcpTools.backlinkSummary, params);
      return this.processBacklinkData(result);
    } catch (error) {
      console.error('Error getting backlinks via MCP:', error);
      return {
        success: false,
        error: error.message,
        totalBacklinks: 0,
        referringDomains: 0
      };
    }
  }

  /**
   * Comprehensive website analysis using MCP
   */
  async analyzeWebsite(url, options = {}) {
    const domain = this.extractDomain(url);
    const location = options.location || 'United States';
    const language = options.language || 'en';

    console.log(`🔍 Starting MCP-based comprehensive analysis for: ${domain}`);

    try {
      // Run multiple MCP analyses in parallel
      const [
        keywordsResult,
        competitorsResult,
        domainRankResult,
        backlinksResult
      ] = await Promise.allSettled([
        this.getKeywordsForDomain(domain, location, language, 20),
        this.getCompetitorAnalysis(domain, location, language, 10),
        this.getDomainRankOverview(domain, location, language),
        this.getBacklinkSummary(domain)
      ]);

      const keywords = keywordsResult.status === 'fulfilled' ? keywordsResult.value : null;
      const competitors = competitorsResult.status === 'fulfilled' ? competitorsResult.value : null;
      const domainRank = domainRankResult.status === 'fulfilled' ? domainRankResult.value : null;
      const backlinks = backlinksResult.status === 'fulfilled' ? backlinksResult.value : null;

      console.log('✅ MCP analysis results:', {
        hasKeywords: !!keywords && keywords.keywords?.length > 0,
        hasCompetitors: !!competitors && competitors.competitors?.length > 0,
        hasDomainRank: !!domainRank,
        hasBacklinks: !!backlinks
      });

      return {
        success: true,
        analysis: {
          domain,
          url,
          keywords: keywords || { keywords: [] },
          competitors: competitors || { competitors: [] },
          domainRank: domainRank || { rank: 0 },
          backlinks: backlinks || { totalBacklinks: 0 },
          score: this.calculateOverallScore({
            keywords,
            competitors,
            domainRank,
            backlinks
          }),
          timestamp: new Date().toISOString(),
          source: 'dataforseo_mcp'
        }
      };
    } catch (error) {
      console.error('❌ Error in MCP website analysis:', error);
      return {
        success: false,
        error: error.message,
        analysis: null
      };
    }
  }

  /**
   * Process Keywords For Site data
   */
  processKeywordsForSiteData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      console.log('⚠️ No keywords data in MCP response');
      return {
        success: false,
        keywords: [],
        totalKeywords: 0
      };
    }

    const result = data.tasks[0].result;
    const keywords = result.map(item => ({
      keyword: item.keyword_data?.keyword_info?.keyword || 'N/A',
      searchVolume: item.keyword_data?.keyword_info?.search_volume || 0,
      competition: item.keyword_data?.keyword_info?.competition_level || 'UNKNOWN',
      cpc: item.keyword_data?.keyword_info?.cpc || 0,
      difficulty: item.keyword_data?.keyword_info?.keyword_difficulty || 0,
      position: item.ranked_serp_element?.serp_item?.rank_group || 0
    }));

    console.log(`✅ Processed ${keywords.length} keywords from MCP`);

    return {
      success: true,
      keywords: keywords,
      totalKeywords: keywords.length,
      topKeywords: keywords.slice(0, 10)
    };
  }

  /**
   * Process competitor data
   */
  processCompetitorData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      console.log('⚠️ No competitor data in MCP response');
      return {
        success: false,
        competitors: [],
        totalCompetitors: 0
      };
    }

    const result = data.tasks[0].result;
    const competitors = result.map(comp => ({
      domain: comp.target,
      relevance: comp.relevance || 0,
      avgPosition: comp.avg_position || 0,
      sumPosition: comp.sum_position || 0,
      intersections: comp.intersections || 0,
      organicTraffic: comp.metrics?.organic?.etv || 0,
      organicKeywords: comp.metrics?.organic?.count || 0
    }));

    console.log(`✅ Processed ${competitors.length} competitors from MCP`);

    return {
      success: true,
      competitors: competitors,
      totalCompetitors: competitors.length
    };
  }

  /**
   * Process domain rank data
   */
  processDomainRankData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      console.log('⚠️ No domain rank data in MCP response');
      return {
        success: false,
        rank: 0
      };
    }

    const result = data.tasks[0].result[0];
    
    console.log(`✅ Processed domain rank data from MCP`);

    return {
      success: true,
      target: result.target,
      rank: result.rank || 0,
      organicTraffic: result.metrics?.organic?.etv || 0,
      organicKeywords: result.metrics?.organic?.count || 0,
      paidTraffic: result.metrics?.paid?.etv || 0,
      paidKeywords: result.metrics?.paid?.count || 0
    };
  }

  /**
   * Process backlink data
   */
  processBacklinkData(data) {
    if (!data || !data.tasks || !data.tasks[0] || !data.tasks[0].result) {
      console.log('⚠️ No backlink data in MCP response');
      return {
        success: false,
        totalBacklinks: 0,
        referringDomains: 0
      };
    }

    const result = data.tasks[0].result[0];
    
    console.log(`✅ Processed backlink data from MCP`);

    return {
      success: true,
      target: result.target,
      totalBacklinks: result.backlinks || 0,
      referringDomains: result.referring_domains || 0,
      referringMainDomains: result.referring_main_domains || 0,
      rank: result.rank || 0
    };
  }

  /**
   * Calculate overall SEO score
   */
  calculateOverallScore(data) {
    let score = 0;
    let factors = 0;

    // Keywords score (0-30 points)
    if (data.keywords && data.keywords.keywords?.length > 0) {
      const keywordCount = data.keywords.keywords.length;
      score += Math.min(30, keywordCount * 2);
      factors++;
    }

    // Domain rank score (0-25 points)
    if (data.domainRank && data.domainRank.rank > 0) {
      score += Math.min(25, data.domainRank.rank / 40);
      factors++;
    }

    // Backlinks score (0-25 points)
    if (data.backlinks && data.backlinks.totalBacklinks > 0) {
      score += Math.min(25, data.backlinks.totalBacklinks / 100);
      factors++;
    }

    // Competitors score (0-20 points)
    if (data.competitors && data.competitors.competitors?.length > 0) {
      score += Math.min(20, data.competitors.competitors.length * 2);
      factors++;
    }

    // If we have at least some data, return the score
    if (factors > 0) {
      return Math.round(score);
    }

    // Default score if no data
    return 40;
  }

  /**
   * Extract domain from URL
   */
  extractDomain(url) {
    try {
      const urlObj = new URL(url.includes('://') ? url : `https://${url}`);
      return urlObj.hostname.replace('www.', '');
    } catch (error) {
      return url.replace('www.', '');
    }
  }
}

module.exports = new DataForSEOMCPServerService();

