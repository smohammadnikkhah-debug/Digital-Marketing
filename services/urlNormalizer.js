/**
 * URL Normalization Utility
 * Handles all possible URL formats and normalizes them for consistent processing
 */

class URLNormalizer {
  /**
   * Normalize a URL to ensure it has the correct format
   * Handles: www.domain.com, domain.com, https://domain.com, http://domain.com, etc.
   * @param {string} url - The URL to normalize
   * @param {object} options - Normalization options
   * @returns {object} - Normalized URL data
   */
  static normalize(url, options = {}) {
    const {
      addProtocol = true,        // Add https:// if no protocol
      removeWWW = false,          // Remove www. prefix
      forceHTTPS = true,          // Force HTTPS protocol
      toLowerCase = true,         // Convert to lowercase
      removePath = false,         // Remove path and query params
      removeTrailingSlash = true  // Remove trailing slash
    } = options;

    try {
      if (!url || typeof url !== 'string') {
        throw new Error('Invalid URL: URL must be a non-empty string');
      }

      let normalizedUrl = url.trim();

      // Convert to lowercase if requested
      if (toLowerCase) {
        normalizedUrl = normalizedUrl.toLowerCase();
      }

      // Add protocol if missing
      if (!normalizedUrl.match(/^https?:\/\//i)) {
        if (addProtocol) {
          normalizedUrl = `https://${normalizedUrl}`;
        } else {
          throw new Error('Invalid URL: Missing protocol (http:// or https://)');
        }
      }

      // Force HTTPS if requested
      if (forceHTTPS && normalizedUrl.startsWith('http://')) {
        normalizedUrl = normalizedUrl.replace('http://', 'https://');
      }

      // Parse the URL
      const urlObj = new URL(normalizedUrl);

      // Remove www if requested
      if (removeWWW && urlObj.hostname.startsWith('www.')) {
        urlObj.hostname = urlObj.hostname.substring(4);
      }

      // Remove path if requested (keep only domain)
      if (removePath) {
        urlObj.pathname = '/';
        urlObj.search = '';
        urlObj.hash = '';
      }

      // Get the final URL
      let finalUrl = urlObj.toString();

      // Remove trailing slash if requested
      if (removeTrailingSlash && finalUrl.endsWith('/') && urlObj.pathname === '/') {
        finalUrl = finalUrl.slice(0, -1);
      }

      // Extract domain information
      const domain = urlObj.hostname.replace(/^www\./, '');
      const domainWithWWW = urlObj.hostname;

      return {
        url: finalUrl,
        originalUrl: url,
        protocol: urlObj.protocol.replace(':', ''),
        hostname: urlObj.hostname,
        domain: domain,
        domainWithWWW: domainWithWWW,
        path: urlObj.pathname,
        search: urlObj.search,
        hash: urlObj.hash,
        port: urlObj.port,
        isValid: true
      };

    } catch (error) {
      console.error('URL normalization error:', error.message);
      return {
        url: null,
        originalUrl: url,
        error: error.message,
        isValid: false
      };
    }
  }

  /**
   * Normalize URL for DataForSEO API
   * DataForSEO requires specific format: https://domain.com (without trailing slash for root domain)
   * @param {string} url - The URL to normalize
   * @returns {string} - Normalized URL for DataForSEO
   */
  static normalizeForDataForSEO(url) {
    const normalized = this.normalize(url, {
      addProtocol: true,
      removeWWW: false,  // Keep www if present
      forceHTTPS: true,
      toLowerCase: true,
      removePath: false,  // Keep full URL with path
      removeTrailingSlash: true  // Remove trailing slash - DataForSEO doesn't like it
    });

    if (!normalized.isValid) {
      throw new Error(`Invalid URL for DataForSEO: ${normalized.error}`);
    }

    return normalized.url;
  }

  /**
   * Normalize URL for domain storage
   * Store domain without protocol and www for consistency
   * @param {string} url - The URL to normalize
   * @returns {string} - Domain without protocol or www
   */
  static normalizeDomainForStorage(url) {
    const normalized = this.normalize(url, {
      addProtocol: true,
      removeWWW: true,   // Remove www for storage
      forceHTTPS: true,
      toLowerCase: true,
      removePath: true,  // Remove path for storage
      removeTrailingSlash: true
    });

    if (!normalized.isValid) {
      throw new Error(`Invalid URL for storage: ${normalized.error}`);
    }

    // Return just the domain without protocol
    return normalized.domain;
  }

  /**
   * Get all possible URL variations for a domain
   * Useful for checking if a domain exists in different formats
   * @param {string} url - The URL or domain
   * @returns {array} - Array of URL variations
   */
  static getVariations(url) {
    try {
      const normalized = this.normalize(url, { addProtocol: true });
      
      if (!normalized.isValid) {
        return [];
      }

      const domain = normalized.domain;
      
      return [
        domain,                    // domain.com
        `www.${domain}`,          // www.domain.com
        `http://${domain}`,       // http://domain.com
        `https://${domain}`,      // https://domain.com
        `http://www.${domain}`,   // http://www.domain.com
        `https://www.${domain}`,  // https://www.domain.com
      ];
    } catch (error) {
      console.error('Error getting URL variations:', error.message);
      return [];
    }
  }

  /**
   * Validate if a URL is valid
   * @param {string} url - The URL to validate
   * @returns {boolean} - True if valid, false otherwise
   */
  static isValid(url) {
    const normalized = this.normalize(url);
    return normalized.isValid;
  }

  /**
   * Test URL normalization with examples
   */
  static test() {
    const testUrls = [
      'mozarex.com',
      'www.mozarex.com',
      'https://mozarex.com',
      'http://mozarex.com',
      'https://www.mozarex.com',
      'http://www.mozarex.com',
      'MOZAREX.COM',
      'mozarex.com/',
      'mozarex.com/page',
      'https://mozarex.com/page?query=test'
    ];

    console.log('🔍 URL Normalization Test');
    console.log('=========================\n');

    testUrls.forEach(url => {
      console.log(`Input: ${url}`);
      
      const normalized = this.normalize(url);
      console.log(`  Normalized: ${normalized.url}`);
      console.log(`  Domain: ${normalized.domain}`);
      
      const dataForSEO = this.normalizeForDataForSEO(url);
      console.log(`  For DataForSEO: ${dataForSEO}`);
      
      const storage = this.normalizeDomainForStorage(url);
      console.log(`  For Storage: ${storage}`);
      console.log('');
    });
  }
}

module.exports = URLNormalizer;
