// Plan-based limits configuration
// This file defines limits for websites and content generation per plan

const PLAN_WEBSITE_LIMITS = {
  // Starter plan limits
  'price_1SB8IyBFUEdVmecWKH5suX6H': 1, // Starter Monthly
  'price_1S9k6kBFUEdVmecWiYNLbXia': 1, // Starter Yearly
  
  // Professional plan limits
  'price_1SB8gWBFUEdVmecWkHXlvki6': 3, // Professional Monthly
  'price_1S9kCwBFUEdVmecWP4DTGzBy': 3, // Professional Yearly
  
  // Legacy plan support
  'basic': 1,
  'pro': 3,
  'professional': 3,
  'business': 10
};

// Content generation limits per plan (blogs and social posts per month)
// ONLY using Stripe Price IDs - no legacy plans
const PLAN_CONTENT_LIMITS = {
  // Starter Plans - 4 content pieces per month (weekly)
  'price_1SB8IyBFUEdVmecWKH5suX6H': { // Starter Monthly
    blogs: 4,      // 4 blogs per month (once per week)
    socialPosts: 4 // 4 social posts per month (once per week)
  },
  'price_1S9k6kBFUEdVmecWiYNLbXia': { // Starter Yearly
    blogs: 4,      // 4 blogs per month (once per week)
    socialPosts: 4 // 4 social posts per month (once per week)
  },
  
  // Professional Plans - 30 content pieces per month (daily)
  'price_1SB8gWBFUEdVmecWkHXlvki6': { // Professional Monthly
    blogs: 30,      // 30 blogs per month (daily)
    socialPosts: 30 // 30 social posts per month (daily)
  },
  'price_1S9kCwBFUEdVmecWP4DTGzBy': { // Professional Yearly
    blogs: 30,      // 30 blogs per month (daily)
    socialPosts: 30 // 30 social posts per month (daily)
  }
};

// Default limits for users without a valid plan (free tier)
const DEFAULT_WEBSITE_LIMIT = 1;
const DEFAULT_CONTENT_LIMITS = {
  blogs: 2,        // Free tier: 2 blogs per month
  socialPosts: 2   // Free tier: 2 social posts per month
};

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

/**
 * Get content generation limits for a given plan
 * @param {string} planId - The plan ID (Stripe price ID or legacy plan name)
 * @returns {object} - Object with blogs and socialPosts limits
 */
function getContentLimits(planId) {
  if (!planId) {
    return DEFAULT_CONTENT_LIMITS;
  }
  
  return PLAN_CONTENT_LIMITS[planId] || DEFAULT_CONTENT_LIMITS;
}

/**
 * Check if a plan allows generating more blogs
 * @param {string} planId - The plan ID
 * @param {number} currentBlogCount - Current number of blogs this month
 * @returns {boolean} - True if more blogs can be generated
 */
function canGenerateMoreBlogs(planId, currentBlogCount) {
  const limits = getContentLimits(planId);
  return currentBlogCount < limits.blogs;
}

/**
 * Check if a plan allows generating more social posts
 * @param {string} planId - The plan ID
 * @param {number} currentSocialCount - Current number of social posts this month
 * @returns {boolean} - True if more social posts can be generated
 */
function canGenerateMoreSocialPosts(planId, currentSocialCount) {
  const limits = getContentLimits(planId);
  return currentSocialCount < limits.socialPosts;
}

module.exports = {
  PLAN_WEBSITE_LIMITS,
  PLAN_CONTENT_LIMITS,
  DEFAULT_WEBSITE_LIMIT,
  DEFAULT_CONTENT_LIMITS,
  getWebsiteLimit,
  canAddMoreWebsites,
  getContentLimits,
  canGenerateMoreBlogs,
  canGenerateMoreSocialPosts
};
