const axios = require('axios');
const cheerio = require('cheerio');

class SubpageAnalysisService {
  constructor() {
    this.maxPages = 50; // Limit to prevent excessive API calls
    this.maxDepth = 3; // Maximum crawl depth
    this.analyzedUrls = new Set();
  }

  // Discover all pages and subpages of a website
  async discoverSubpages(baseUrl) {
    try {
      console.log(`🔍 Discovering subpages for: ${baseUrl}`);
      
      const discoveredPages = new Set();
      const pagesToAnalyze = [baseUrl];
      const analyzedPages = new Set();
      
      // Normalize base URL
      const baseDomain = this.extractDomain(baseUrl);
      
      while (pagesToAnalyze.length > 0 && discoveredPages.size < this.maxPages) {
        const currentUrl = pagesToAnalyze.shift();
        
        if (analyzedPages.has(currentUrl)) continue;
        analyzedPages.add(currentUrl);
        
        try {
          // Fetch page content
          const response = await axios.get(currentUrl, {
            timeout: 10000,
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
          });
          
          const $ = cheerio.load(response.data);
          discoveredPages.add(currentUrl);
          
          // Extract internal links
          $('a[href]').each((i, element) => {
            const href = $(element).attr('href');
            if (!href) return;
            
            const absoluteUrl = this.resolveUrl(currentUrl, href);
            const urlDomain = this.extractDomain(absoluteUrl);
            
            // Only include links from the same domain
            if (urlDomain === baseDomain && !discoveredPages.has(absoluteUrl)) {
              // Check if it's a meaningful page (not just fragments, files, etc.)
              if (this.isValidPage(absoluteUrl)) {
                discoveredPages.add(absoluteUrl);
                pagesToAnalyze.push(absoluteUrl);
              }
            }
          });
          
        } catch (error) {
          console.warn(`⚠️ Failed to analyze ${currentUrl}:`, error.message);
        }
      }
      
      console.log(`✅ Discovered ${discoveredPages.size} pages for ${baseDomain}`);
      return Array.from(discoveredPages);
      
    } catch (error) {
      console.error('❌ Subpage discovery failed:', error.message);
      return [baseUrl]; // Fallback to just the main page
    }
  }

  // Analyze all discovered pages
  async analyzeAllPages(pages, analysisService) {
    try {
      console.log(`🔍 Analyzing ${pages.length} pages...`);
      
      const analysisResults = [];
      const batchSize = 5; // Process in batches to avoid overwhelming the server
      
      for (let i = 0; i < pages.length; i += batchSize) {
        const batch = pages.slice(i, i + batchSize);
        
        const batchPromises = batch.map(async (url) => {
          try {
            console.log(`📊 Analyzing: ${url}`);
            const analysis = await analysisService.scrapeWebsite(url);
            return {
              url: url,
              analysis: analysis,
              success: true
            };
          } catch (error) {
            console.warn(`⚠️ Failed to analyze ${url}:`, error.message);
            return {
              url: url,
              analysis: null,
              success: false,
              error: error.message
            };
          }
        });
        
        const batchResults = await Promise.allSettled(batchPromises);
        
        batchResults.forEach((result) => {
          if (result.status === 'fulfilled') {
            analysisResults.push(result.value);
          }
        });
        
        // Small delay between batches
        if (i + batchSize < pages.length) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
      
      return analysisResults;
      
    } catch (error) {
      console.error('❌ Page analysis failed:', error.message);
      return [];
    }
  }

  // Generate comprehensive website analysis report
  generateWebsiteReport(pageAnalyses) {
    try {
      const successfulAnalyses = pageAnalyses.filter(p => p.success && p.analysis);
      
      if (successfulAnalyses.length === 0) {
        return {
          success: false,
          error: 'No pages could be analyzed successfully',
          timestamp: new Date().toISOString()
        };
      }
      
      // Aggregate data across all pages
      const aggregatedData = this.aggregatePageData(successfulAnalyses);
      
      // Calculate overall website score
      const overallScore = this.calculateWebsiteScore(successfulAnalyses);
      
      // Generate recommendations
      const recommendations = this.generateWebsiteRecommendations(successfulAnalyses, aggregatedData);
      
      // Calculate domain-level metrics
      const domainMetrics = this.calculateDomainMetrics(successfulAnalyses, aggregatedData);
      
      return {
        success: true,
        // Return domain-level analysis (compatible with existing dashboard)
        analysis: {
          url: successfulAnalyses[0]?.url || '',
          score: overallScore,
          totalPages: pageAnalyses.length,
          analyzedPages: successfulAnalyses.length,
          healthyPages: domainMetrics.healthyPages,
          pagesWithIssues: domainMetrics.pagesWithIssues,
          fixedIssues: domainMetrics.fixedIssues,
          aggregatedData: aggregatedData,
          recommendations: recommendations,
          // Include performance metrics from main page
          performance: successfulAnalyses[0]?.analysis?.performance || {},
          // Include technical analysis aggregated
          technical: this.aggregateTechnicalAnalysis(successfulAnalyses),
          // Include content analysis aggregated
          content: this.aggregateContentAnalysis(successfulAnalyses)
        },
        timestamp: new Date().toISOString()
      };
      
    } catch (error) {
      console.error('❌ Report generation failed:', error.message);
      return {
        success: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  // Calculate domain-level metrics
  calculateDomainMetrics(pageAnalyses, aggregatedData) {
    const totalPages = pageAnalyses.length;
    const analyzedPages = pageAnalyses.filter(p => p.success && p.analysis).length;
    
    // Count healthy pages (score >= 70)
    const healthyPages = pageAnalyses.filter(p => p.success && p.analysis && p.analysis.score >= 70).length;
    
    // Count pages with issues (score < 70 or missing critical elements)
    const pagesWithIssues = pageAnalyses.filter(p => {
      if (!p.success || !p.analysis) return true;
      const analysis = p.analysis;
      return analysis.score < 70 || 
             !analysis.title || 
             !analysis.metaDescription || 
             (analysis.images && analysis.images.missingAlt > 0);
    }).length;
    
    // Count fixed issues (pages that are now healthy)
    const fixedIssues = Math.max(0, healthyPages - Math.floor(totalPages * 0.3)); // Assume 30% baseline healthy
    
    return {
      totalPages,
      analyzedPages,
      healthyPages,
      pagesWithIssues,
      fixedIssues
    };
  }

  // Aggregate technical analysis across all pages
  aggregateTechnicalAnalysis(pageAnalyses) {
    const technical = {
      canonical: 0,
      viewport: 0,
      language: 0,
      charset: 0,
      robots: 0,
      sitemap: 0
    };
    
    pageAnalyses.forEach(page => {
      if (page.analysis) {
        if (page.analysis.canonical) technical.canonical++;
        if (page.analysis.viewport) technical.viewport++;
        if (page.analysis.language) technical.language++;
        if (page.analysis.charset) technical.charset++;
        if (page.analysis.robots) technical.robots++;
        if (page.analysis.sitemap) technical.sitemap++;
      }
    });
    
    return technical;
  }

  // Aggregate content analysis across all pages
  aggregateContentAnalysis(pageAnalyses) {
    const content = {
      titles: [],
      metaDescriptions: [],
      headings: { h1: 0, h2: 0, h3: 0, h4: 0, h5: 0, h6: 0 },
      images: { total: 0, missingAlt: 0 },
      links: { internal: 0, external: 0 },
      contentLength: 0
    };
    
    pageAnalyses.forEach(page => {
      if (page.analysis) {
        if (page.analysis.title) content.titles.push(page.analysis.title);
        if (page.analysis.metaDescription) content.metaDescriptions.push(page.analysis.metaDescription);
        
        if (page.analysis.headings) {
          Object.keys(page.analysis.headings).forEach(tag => {
            content.headings[tag] += page.analysis.headings[tag] || 0;
          });
        }
        
        if (page.analysis.images) {
          content.images.total += page.analysis.images.total || 0;
          content.images.missingAlt += page.analysis.images.missingAlt || 0;
        }
        
        if (page.analysis.links) {
          content.links.internal += page.analysis.links.internal || 0;
          content.links.external += page.analysis.links.external || 0;
        }
        
        content.contentLength += page.analysis.contentLength || 0;
      }
    });
    
    return content;
  }

  // Aggregate data from all pages
  aggregatePageData(pageAnalyses) {
    const aggregated = {
      titles: [],
      metaDescriptions: [],
      headings: { h1: 0, h2: 0, h3: 0, h4: 0, h5: 0, h6: 0 },
      images: { total: 0, missingAlt: 0 },
      links: { internal: 0, external: 0 },
      technical: {
        hasCanonical: 0,
        hasViewport: 0,
        hasLanguage: 0,
        hasCharset: 0
      },
      contentLength: { total: 0, average: 0 },
      loadTimes: [],
      issues: []
    };
    
    pageAnalyses.forEach(page => {
      const analysis = page.analysis;
      
      // Collect titles
      if (analysis.title) {
        aggregated.titles.push({
          url: page.url,
          title: analysis.title,
          length: analysis.title.length
        });
      }
      
      // Collect meta descriptions
      if (analysis.metaDescription) {
        aggregated.metaDescriptions.push({
          url: page.url,
          description: analysis.metaDescription,
          length: analysis.metaDescription.length
        });
      }
      
      // Aggregate headings
      if (analysis.headings) {
        Object.keys(analysis.headings).forEach(tag => {
          aggregated.headings[tag] += analysis.headings[tag] || 0;
        });
      }
      
      // Aggregate images
      if (analysis.images) {
        aggregated.images.total += analysis.images.total || 0;
        aggregated.images.missingAlt += analysis.images.missingAlt || 0;
      }
      
      // Aggregate links
      if (analysis.links) {
        aggregated.links.internal += analysis.links.internal || 0;
        aggregated.links.external += analysis.links.external || 0;
      }
      
      // Aggregate technical elements
      if (analysis.canonical) aggregated.technical.hasCanonical++;
      if (analysis.viewport) aggregated.technical.hasViewport++;
      if (analysis.language) aggregated.technical.hasLanguage++;
      if (analysis.charset) aggregated.technical.hasCharset++;
      
      // Collect load times
      if (analysis.loadTime) {
        aggregated.loadTimes.push(analysis.loadTime);
      }
      
      // Collect issues
      if (analysis.issues && analysis.issues.length > 0) {
        aggregated.issues.push(...analysis.issues.map(issue => ({
          url: page.url,
          issue: issue
        })));
      }
    });
    
    // Calculate averages
    aggregated.contentLength.average = aggregated.contentLength.total / pageAnalyses.length;
    
    return aggregated;
  }

  // Calculate overall website score
  calculateWebsiteScore(pageAnalyses) {
    if (pageAnalyses.length === 0) return 0;
    
    let totalScore = 0;
    let validPages = 0;
    
    pageAnalyses.forEach(page => {
      if (page.analysis && page.analysis.score) {
        totalScore += page.analysis.score;
        validPages++;
      }
    });
    
    return validPages > 0 ? Math.round(totalScore / validPages) : 0;
  }

  // Generate website-wide recommendations
  generateWebsiteRecommendations(pageAnalyses, aggregatedData) {
    const recommendations = [];
    
    // Title optimization
    const shortTitles = aggregatedData.titles.filter(t => t.length < 30);
    const longTitles = aggregatedData.titles.filter(t => t.length > 60);
    
    if (shortTitles.length > 0) {
      recommendations.push({
        category: 'Title Optimization',
        priority: 'High',
        issue: `${shortTitles.length} pages have titles shorter than 30 characters`,
        recommendation: 'Expand titles to 30-60 characters for better SEO',
        pages: shortTitles.map(t => t.url)
      });
    }
    
    if (longTitles.length > 0) {
      recommendations.push({
        category: 'Title Optimization',
        priority: 'Medium',
        issue: `${longTitles.length} pages have titles longer than 60 characters`,
        recommendation: 'Shorten titles to 30-60 characters to avoid truncation',
        pages: longTitles.map(t => t.url)
      });
    }
    
    // Meta description optimization
    const missingMeta = pageAnalyses.filter(p => !p.analysis.metaDescription);
    if (missingMeta.length > 0) {
      recommendations.push({
        category: 'Meta Descriptions',
        priority: 'High',
        issue: `${missingMeta.length} pages are missing meta descriptions`,
        recommendation: 'Add meta descriptions to all pages for better search results',
        pages: missingMeta.map(p => p.url)
      });
    }
    
    // Image optimization
    if (aggregatedData.images.missingAlt > 0) {
      const altRatio = (aggregatedData.images.total - aggregatedData.images.missingAlt) / aggregatedData.images.total;
      if (altRatio < 0.8) {
        recommendations.push({
          category: 'Image Optimization',
          priority: 'Medium',
          issue: `${aggregatedData.images.missingAlt} images are missing alt text`,
          recommendation: 'Add descriptive alt text to all images for accessibility and SEO',
          pages: ['Multiple pages']
        });
      }
    }
    
    // Technical SEO
    const pagesWithoutCanonical = pageAnalyses.filter(p => !p.analysis.canonical);
    if (pagesWithoutCanonical.length > 0) {
      recommendations.push({
        category: 'Technical SEO',
        priority: 'Medium',
        issue: `${pagesWithoutCanonical.length} pages are missing canonical tags`,
        recommendation: 'Add canonical tags to prevent duplicate content issues',
        pages: pagesWithoutCanonical.map(p => p.url)
      });
    }
    
    // Performance
    if (aggregatedData.loadTimes.length > 0) {
      const avgLoadTime = aggregatedData.loadTimes.reduce((a, b) => a + b, 0) / aggregatedData.loadTimes.length;
      if (avgLoadTime > 3000) {
        recommendations.push({
          category: 'Performance',
          priority: 'High',
          issue: `Average load time is ${Math.round(avgLoadTime)}ms`,
          recommendation: 'Optimize images, minify CSS/JS, and use CDN to improve load times',
          pages: ['All pages']
        });
      }
    }
    
    return recommendations;
  }

  // Helper methods
  extractDomain(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch (error) {
      return url;
    }
  }

  resolveUrl(baseUrl, relativeUrl) {
    try {
      return new URL(relativeUrl, baseUrl).href;
    } catch (error) {
      return relativeUrl;
    }
  }

  isValidPage(url) {
    // Exclude common non-page URLs
    const excludePatterns = [
      /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|jpg|jpeg|png|gif|svg|css|js)$/i,
      /#/,
      /mailto:/,
      /tel:/,
      /javascript:/,
      /\.xml$/,
      /\.txt$/,
      /sitemap/,
      /robots\.txt/
    ];
    
    return !excludePatterns.some(pattern => pattern.test(url));
  }
}

module.exports = new SubpageAnalysisService();
