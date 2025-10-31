/**
 * Location Detection Utility
 * Detects location (country) and language from domain TLD
 */

function getLocationFromDomain(domain) {
  const domainLower = domain.toLowerCase();
  const domainParts = domainLower.split('.');
  
  // Comprehensive location map - check compound TLDs first, then single TLDs
  const locationMap = {
    // Australian domains (check compound first)
    'com.au': { name: 'Australia', language: 'en' },
    'net.au': { name: 'Australia', language: 'en' },
    'org.au': { name: 'Australia', language: 'en' },
    'edu.au': { name: 'Australia', language: 'en' },
    'gov.au': { name: 'Australia', language: 'en' },
    'au': { name: 'Australia', language: 'en' },
    
    // UK domains
    'co.uk': { name: 'United Kingdom', language: 'en' },
    'org.uk': { name: 'United Kingdom', language: 'en' },
    'uk': { name: 'United Kingdom', language: 'en' },
    
    // Canadian domains
    'ca': { name: 'Canada', language: 'en' },
    
    // German domains
    'de': { name: 'Germany', language: 'de' },
    
    // French domains
    'fr': { name: 'France', language: 'fr' },
    
    // Indian domains
    'in': { name: 'India', language: 'en' },
    'co.in': { name: 'India', language: 'en' },
    
    // New Zealand
    'nz': { name: 'New Zealand', language: 'en' },
    'co.nz': { name: 'New Zealand', language: 'en' },
    
    // Singapore
    'sg': { name: 'Singapore', language: 'en' },
    
    // Japan
    'jp': { name: 'Japan', language: 'ja' },
    'co.jp': { name: 'Japan', language: 'ja' },
    
    // South Korea
    'kr': { name: 'South Korea', language: 'ko' },
    'co.kr': { name: 'South Korea', language: 'ko' },
    
    // China
    'cn': { name: 'China', language: 'zh' },
    'com.cn': { name: 'China', language: 'zh' },
    
    // Brazil
    'br': { name: 'Brazil', language: 'pt' },
    'com.br': { name: 'Brazil', language: 'pt' },
    
    // Mexico
    'mx': { name: 'Mexico', language: 'es' },
    'com.mx': { name: 'Mexico', language: 'es' },
    
    // Spain
    'es': { name: 'Spain', language: 'es' },
    
    // Italy
    'it': { name: 'Italy', language: 'it' },
    
    // Netherlands
    'nl': { name: 'Netherlands', language: 'nl' },
    
    // Sweden
    'se': { name: 'Sweden', language: 'sv' },
    
    // Poland
    'pl': { name: 'Poland', language: 'pl' },
    
    // Default to United States for .com, .io, .net, .org (when no country TLD)
    'com': { name: 'United States', language: 'en' },
    'io': { name: 'United States', language: 'en' },
    'net': { name: 'United States', language: 'en' },
    'org': { name: 'United States', language: 'en' },
    'edu': { name: 'United States', language: 'en' }
  };
  
  // Check for compound TLDs FIRST (like .com.au, .co.uk, .co.nz)
  if (domainParts.length >= 3) {
    const compoundTld = domainParts.slice(-2).join('.');
    if (locationMap[compoundTld]) {
      console.log(`🌍 Detected location from compound TLD: ${compoundTld} → ${locationMap[compoundTld].name}`);
      return locationMap[compoundTld];
    }
  }
  
  // Then check single TLD
  const tld = domainParts[domainParts.length - 1];
  const location = locationMap[tld] || locationMap['com']; // Default to US if unknown
  console.log(`🌍 Detected location from TLD: ${tld} → ${location.name}`);
  return location;
}

module.exports = {
  getLocationFromDomain
};

