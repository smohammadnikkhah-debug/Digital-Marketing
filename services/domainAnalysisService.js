const axios = require('axios');
const cheerio = require('cheerio');
const dataforseoService = require('./dataforseoService');

class DomainAnalysisService {
  constructor() {
    this.maxPages = 10; // Reduced to prevent large payloads
    this.timeout = 30000; // 30 seconds timeout
  }

  async analyzeDomain(domain) {
    try {
      console.log(`🔍 Starting comprehensive domain analysis for: ${domain}`);
      
      // Normalize domain
      const normalizedDomain = this.normalizeDomain(domain);
      
      // Step 1: Discover all pages
      const pages = await this.discoverPages(normalizedDomain);
      console.log(`📄 Found ${pages.length} pages to analyze`);
      
      // Step 2: Analyze each page
      const pageAnalyses = await this.analyzePages(pages);
      
      // Step 3: Aggregate results
      const aggregatedResults = this.aggregateResults(pageAnalyses);
      
      // Step 4: Generate overall metrics
      const overallMetrics = this.generateOverallMetrics(aggregatedResults);
      
      console.log(`✅ Domain analysis completed for ${domain}`);
      
      return {
        success: true,
        data: {
          domain: normalizedDomain,
          totalPages: pages.length,
          analyzedPages: pageAnalyses.length,
          pages: pageAnalyses,
          aggregated: aggregatedResults,
          metrics: overallMetrics,
          timestamp: new Date().toISOString()
        }
      };
    } catch (error) {
      console.error('Domain analysis error:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  async discoverPages(domain) {
    try {
      const pages = new Set();
      const baseUrl = `https://${domain}`;
      
      // Start with homepage
      pages.add(baseUrl);
      
      // Try to get sitemap
      const sitemapPages = await this.getSitemapPages(baseUrl);
      sitemapPages.forEach(page => pages.add(page));
      
      // Crawl homepage for internal links
      const homepageLinks = await this.getInternalLinks(baseUrl, domain);
      homepageLinks.forEach(link => pages.add(link));
      
      // Convert Set to Array and limit
      const pageArray = Array.from(pages).slice(0, this.maxPages);
      
      return pageArray;
    } catch (error) {
      console.error('Page discovery error:', error);
      return [`https://${domain}`]; // Fallback to just homepage
    }
  }

  async getSitemapPages(baseUrl) {
    try {
      const sitemapUrls = [
        `${baseUrl}/sitemap.xml`,
        `${baseUrl}/sitemap_index.xml`,
        `${baseUrl}/robots.txt`
      ];
      
      const pages = new Set();
      
      for (const sitemapUrl of sitemapUrls) {
        try {
          const response = await axios.get(sitemapUrl, { timeout: 10000 });
          const $ = cheerio.load(response.data);
          
          // Extract URLs from sitemap
          $('loc').each((i, element) => {
            const url = $(element).text().trim();
            if (url && url.includes(baseUrl)) {
              pages.add(url);
            }
          });
          
          // Extract URLs from robots.txt
          if (sitemapUrl.includes('robots.txt')) {
            const robotsContent = response.data;
            const sitemapMatches = robotsContent.match(/Sitemap:\s*(.+)/gi);
            if (sitemapMatches) {
              for (const match of sitemapMatches) {
                const sitemapPath = match.replace(/Sitemap:\s*/i, '').trim();
                try {
                  const sitemapResponse = await axios.get(sitemapPath, { timeout: 10000 });
                  const sitemap$ = cheerio.load(sitemapResponse.data);
                  sitemap$('loc').each((i, element) => {
                    const url = sitemap$(element).text().trim();
                    if (url && url.includes(baseUrl)) {
                      pages.add(url);
                    }
                  });
                } catch (sitemapError) {
                  console.log(`Could not fetch sitemap: ${sitemapPath}`);
                }
              }
            }
          }
        } catch (error) {
          console.log(`Could not fetch: ${sitemapUrl}`);
        }
      }
      
      return Array.from(pages);
    } catch (error) {
      console.error('Sitemap discovery error:', error);
      return [];
    }
  }

  async getInternalLinks(url, domain) {
    try {
      const response = await axios.get(url, { 
        timeout: 10000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; MozarexBot/1.0)'
        }
      });
      
      const $ = cheerio.load(response.data);
      const links = new Set();
      
      // Find all internal links
      $('a[href]').each((i, element) => {
        const href = $(element).attr('href');
        if (href) {
          const absoluteUrl = this.resolveUrl(url, href);
          if (absoluteUrl && absoluteUrl.includes(domain)) {
            links.add(absoluteUrl);
          }
        }
      });
      
      return Array.from(links);
    } catch (error) {
      console.error('Internal links discovery error:', error);
      return [];
    }
  }

  async analyzePages(pages) {
    const analyses = [];
    const batchSize = 5; // Process 5 pages at a time
    
    for (let i = 0; i < pages.length; i += batchSize) {
      const batch = pages.slice(i, i + batchSize);
      const batchPromises = batch.map(page => this.analyzeSinglePage(page));
      
      try {
        const batchResults = await Promise.allSettled(batchPromises);
        batchResults.forEach((result, index) => {
          if (result.status === 'fulfilled' && result.value) {
            analyses.push(result.value);
          } else {
            console.log(`Failed to analyze: ${batch[index]}`);
          }
        });
      } catch (error) {
        console.error('Batch analysis error:', error);
      }
    }
    
    return analyses;
  }

  async analyzeSinglePage(url) {
    try {
      console.log(`📊 Analyzing: ${url}`);
      
      // Use DataForSEO for comprehensive analysis
      const dataforseoResult = await dataforseoService.getOnPageAnalysis(url);
      
      if (dataforseoResult && dataforseoResult.crawl_progress === 'finished' && dataforseoResult.items_count > 0) {
        return {
          url: url,
          analysis: dataforseoResult,
          source: 'dataforseo',
          timestamp: new Date().toISOString()
        };
      }
      
      // Check if DataForSEO detected restricted access
      if (dataforseoResult && dataforseoResult.restricted_access) {
        console.log(`🚫 Website ${url} has restricted access (robots.txt or security measures)`);
        // Try basic scraping as fallback
        const basicResult = await this.basicPageAnalysis(url);
        if (basicResult) {
          console.log(`✅ Basic analysis successful for ${url}`);
          return basicResult;
        } else {
          // Return informative analysis for restricted sites
          return {
            url: url,
            analysis: {
              title: 'Website Access Restricted',
              metaDescription: 'This website has restricted access via robots.txt or security measures',
              headings: { h1: 0, h2: 0, h3: 0 },
              h1Tags: [],
              h2Tags: [],
              h3Tags: [],
              images: { total: 0, missingAlt: 0 },
              links: { internal: 0, external: 0 },
              content: { wordCount: 0 },
              ssl: url.startsWith('https://'),
              mobileFriendly: true,
              technical: { 
                openGraph: {}, 
                schemaMarkup: [], 
                socialLinks: {},
                restricted_access: true,
                robots_txt_blocked: true
              },
              restricted_access: true,
              error_message: 'Website access restricted by robots.txt or security measures'
            },
            source: 'restricted',
            timestamp: new Date().toISOString()
          };
        }
      }
      
      // Fallback to basic scraping if DataForSEO can't crawl the site
      console.log(`⚠️ DataForSEO couldn't crawl ${url}, falling back to basic analysis`);
      const basicResult = await this.basicPageAnalysis(url);
      
      if (basicResult) {
        console.log(`✅ Basic analysis successful for ${url}`);
        return basicResult;
      } else {
        console.log(`❌ Both DataForSEO and basic analysis failed for ${url}`);
        // Return a minimal analysis structure to prevent errors
        return {
          url: url,
          analysis: {
            title: 'Analysis Unavailable',
            metaDescription: 'Website could not be analyzed due to access restrictions',
            headings: { h1: 0, h2: 0, h3: 0 },
            h1Tags: [],
            h2Tags: [],
            h3Tags: [],
            images: { total: 0, missingAlt: 0 },
            links: { internal: 0, external: 0 },
            content: { wordCount: 0 },
            ssl: true,
            mobileFriendly: true,
            technical: {
              openGraph: {},
              schemaMarkup: [],
              socialLinks: {}
            }
          },
          source: 'fallback',
          timestamp: new Date().toISOString()
        };
      }
    } catch (error) {
      console.error(`Error analyzing ${url}:`, error);
      return null;
    }
  }

  async basicPageAnalysis(url) {
    try {
      console.log(`🔍 Attempting basic analysis for: ${url}`);
      
      const response = await axios.get(url, { 
        timeout: 15000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
          'Accept-Language': 'en-US,en;q=0.5',
          'Accept-Encoding': 'gzip, deflate, br',
          'Connection': 'keep-alive',
          'Upgrade-Insecure-Requests': '1'
        },
        maxRedirects: 5
      });
      
      const $ = cheerio.load(response.data);
      
      // Extract basic SEO elements
      const title = $('title').text().trim();
      const metaDescription = $('meta[name="description"]').attr('content') || '';
      const h1Tags = $('h1').map((i, el) => $(el).text().trim()).get().slice(0, 10);
      const h2Tags = $('h2').map((i, el) => $(el).text().trim()).get().slice(0, 20);
      const h3Tags = $('h3').map((i, el) => $(el).text().trim()).get().slice(0, 30);
      
      // Count images without alt text
      const imagesWithoutAlt = $('img:not([alt])').length;
      const totalImages = $('img').length;
      
      // Count links
      const internalLinks = $('a[href*="' + this.extractDomain(url) + '"]').length;
      const externalLinks = $('a[href^="http"]:not([href*="' + this.extractDomain(url) + '"])').length;
      
      // Get content (limited to prevent large payloads)
      const content = $('body').text().replace(/\s+/g, ' ').trim().substring(0, 5000);
      const wordCount = content.split(' ').length;
      
      // Check SSL
      const hasSSL = url.startsWith('https://');
      
      return {
        url: url,
        analysis: {
          title: title,
          metaDescription: metaDescription,
          headings: {
            h1: h1Tags.length,
            h2: h2Tags.length,
            h3: h3Tags.length
          },
          h1Tags: h1Tags,
          h2Tags: h2Tags,
          h3Tags: h3Tags,
          images: {
            total: totalImages,
            missingAlt: imagesWithoutAlt
          },
          links: {
            internal: internalLinks,
            external: externalLinks
          },
          content: {
            wordCount: wordCount,
            fullContent: content.substring(0, 1000) // First 1000 chars
          },
          technical: {
            sslCertificate: hasSSL,
            language: $('html').attr('lang') || 'en'
          }
        },
        source: 'basic',
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      console.error(`Basic analysis error for ${url}:`, error);
      return null;
    }
  }

  aggregateResults(pageAnalyses) {
    // Ensure pageAnalyses is an array
    const validPageAnalyses = Array.isArray(pageAnalyses) ? pageAnalyses : [];
    
    const aggregated = {
      totalPages: validPageAnalyses.length,
      pagesWithTitle: 0,
      pagesWithMetaDescription: 0,
      pagesWithH1: 0,
      pagesWithH2: 0,
      totalH1Tags: 0,
      totalH2Tags: 0,
      totalH3Tags: 0,
      totalImages: 0,
      imagesWithoutAlt: 0,
      totalInternalLinks: 0,
      totalExternalLinks: 0,
      totalWordCount: 0,
      pagesWithSSL: 0,
      issues: [],
      recommendations: [],
      // Dashboard-specific fields
      fixedIssues: 0,
      healthyPages: 0,
      pagesWithIssues: 0,
      // Ensure technical data structure exists
      technical: {
        openGraph: {},
        schemaMarkup: [],
        socialLinks: {}
      }
    };

    validPageAnalyses.forEach(page => {
      if (!page || !page.analysis) return;
      
      const analysis = page.analysis;
      
      // Count pages with specific elements
      if (analysis.title) aggregated.pagesWithTitle++;
      if (analysis.metaDescription) aggregated.pagesWithMetaDescription++;
      if (analysis.headings?.h1 > 0) aggregated.pagesWithH1++;
      if (analysis.headings?.h2 > 0) aggregated.pagesWithH2++;
      
      // Sum up totals
      aggregated.totalH1Tags += analysis.headings?.h1 || 0;
      aggregated.totalH2Tags += analysis.headings?.h2 || 0;
      aggregated.totalH3Tags += analysis.headings?.h3 || 0;
      aggregated.totalImages += analysis.images?.total || 0;
      aggregated.imagesWithoutAlt += analysis.images?.missingAlt || 0;
      aggregated.totalInternalLinks += analysis.links?.internal || 0;
      aggregated.totalExternalLinks += analysis.links?.external || 0;
      aggregated.totalWordCount += analysis.content?.wordCount || 0;
      
      if (analysis.technical?.sslCertificate) aggregated.pagesWithSSL++;
      
      // Identify issues
      if (!analysis.title) {
        aggregated.issues.push({
          type: 'missing_title',
          page: page.url,
          severity: 'critical'
        });
      }
      
      if (!analysis.metaDescription) {
        aggregated.issues.push({
          type: 'missing_meta_description',
          page: page.url,
          severity: 'critical'
        });
      }
      
      if (analysis.headings?.h1 === 0) {
        aggregated.issues.push({
          type: 'missing_h1',
          page: page.url,
          severity: 'critical'
        });
      }
      
      if (analysis.images?.missingAlt > 0) {
        aggregated.issues.push({
          type: 'images_without_alt',
          page: page.url,
          count: analysis.images.missingAlt,
          severity: 'important'
        });
      }
      
      if (!analysis.technical?.sslCertificate) {
        aggregated.issues.push({
          type: 'no_ssl',
          page: page.url,
          severity: 'critical'
        });
      }
    });

    // Calculate dashboard-specific metrics
    const metrics = this.generateOverallMetrics(aggregated);
    aggregated.fixedIssues = metrics.fixedIssues;
    aggregated.healthyPages = metrics.healthyPages;
    aggregated.pagesWithIssues = metrics.pagesWithIssues;

    return aggregated;
  }

  generateOverallMetrics(aggregated) {
    const totalPages = aggregated.totalPages;
    
    return {
      overallScore: this.calculateOverallScore(aggregated),
      fixedIssues: this.countFixedIssues(aggregated),
      healthyPages: this.countHealthyPages(aggregated),
      pagesWithIssues: this.countPagesWithIssues(aggregated),
      criticalIssues: aggregated.issues.filter(issue => issue.severity === 'critical').length,
      importantIssues: aggregated.issues.filter(issue => issue.severity === 'important').length,
      suggestions: aggregated.issues.filter(issue => issue.severity === 'suggestion').length,
      averageWordCount: Math.round(aggregated.totalWordCount / totalPages),
      sslCoverage: Math.round((aggregated.pagesWithSSL / totalPages) * 100),
      titleCoverage: Math.round((aggregated.pagesWithTitle / totalPages) * 100),
      metaDescriptionCoverage: Math.round((aggregated.pagesWithMetaDescription / totalPages) * 100),
      h1Coverage: Math.round((aggregated.pagesWithH1 / totalPages) * 100),
      h2Coverage: Math.round((aggregated.pagesWithH2 / totalPages) * 100)
    };
  }

  calculateOverallScore(aggregated) {
    let score = 100;
    const totalPages = aggregated.totalPages;
    
    // Deduct points based on coverage
    score -= ((totalPages - aggregated.pagesWithTitle) / totalPages) * 20;
    score -= ((totalPages - aggregated.pagesWithMetaDescription) / totalPages) * 15;
    score -= ((totalPages - aggregated.pagesWithH1) / totalPages) * 10;
    score -= ((totalPages - aggregated.pagesWithH2) / totalPages) * 10;
    score -= ((totalPages - aggregated.pagesWithSSL) / totalPages) * 20;
    
    // Deduct points for issues
    score -= aggregated.criticalIssues * 5;
    score -= aggregated.importantIssues * 2;
    
    return Math.max(0, Math.round(score));
  }

  countFixedIssues(aggregated) {
    // Count issues that are not present (i.e., fixed)
    return aggregated.totalPages - aggregated.issues.length;
  }

  countHealthyPages(aggregated) {
    // Count pages with no critical issues
    const pagesWithCriticalIssues = new Set(
      aggregated.issues
        .filter(issue => issue.severity === 'critical')
        .map(issue => issue.page)
    );
    
    return aggregated.totalPages - pagesWithCriticalIssues.size;
  }

  countPagesWithIssues(aggregated) {
    // Count pages with any issues
    const pagesWithIssues = new Set(
      aggregated.issues.map(issue => issue.page)
    );
    
    return pagesWithIssues.size;
  }

  normalizeDomain(domain) {
    // Remove protocol and www
    return domain
      .replace(/^https?:\/\//, '')
      .replace(/^www\./, '')
      .replace(/\/$/, '');
  }

  extractDomain(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch (error) {
      return '';
    }
  }

  resolveUrl(baseUrl, relativeUrl) {
    try {
      return new URL(relativeUrl, baseUrl).href;
    } catch (error) {
      return null;
    }
  }
}

module.exports = new DomainAnalysisService();
