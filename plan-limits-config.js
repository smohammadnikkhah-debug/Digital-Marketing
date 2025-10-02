// Plan-based website limits configuration
// This file defines how many websites each plan can add to their dashboard

const PLAN_WEBSITE_LIMITS = {
  // Starter plan limits
  'price_1SB8IyBFUEdVmecWKH5suX6H': 1, // Starter Monthly
  'price_1S9k6kBFUEdVmecWiYNLbXia': 1, // Starter Yearly
  
  // Professional plan limits
  'price_1SB8gWBFUEdVmecWkHXlvki6': 5, // Professional Monthly
  'price_1S9kCwBFUEdVmecWP4DTGzBy': 5, // Professional Yearly
  
  // Legacy plan support
  'basic': 1,
  'pro': 5,
  'business': 10
};

// Default limit for unknown plans
const DEFAULT_WEBSITE_LIMIT = 1;

/**
 * Get the website limit for a given plan
 * @param {string} planId - The plan ID (Stripe price ID or legacy plan name)
 * @returns {number} - The maximum number of websites allowed
 */
function getWebsiteLimit(planId) {
  if (!planId) {
    return DEFAULT_WEBSITE_LIMIT;
  }
  
  return PLAN_WEBSITE_LIMITS[planId] || DEFAULT_WEBSITE_LIMIT;
}

/**
 * Check if a plan allows adding more websites
 * @param {string} planId - The plan ID
 * @param {number} currentWebsiteCount - Current number of websites
 * @returns {boolean} - True if more websites can be added
 */
function canAddMoreWebsites(planId, currentWebsiteCount) {
  const limit = getWebsiteLimit(planId);
  return currentWebsiteCount < limit;
}

module.exports = {
  PLAN_WEBSITE_LIMITS,
  DEFAULT_WEBSITE_LIMIT,
  getWebsiteLimit,
  canAddMoreWebsites
};
