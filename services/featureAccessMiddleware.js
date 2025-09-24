const subscriptionService = require('./subscriptionService');

/**
 * Middleware to check if user has access to specific features
 * This should be used on routes that require subscription features
 */

// Feature definitions
const FEATURES = {
    AI_CONTENT_GENERATION: 'ai_content_generation',
    SOCIAL_MEDIA_INTEGRATION: 'social_media_integration',
    WORDPRESS_INTEGRATION: 'wordpress_integration',
    ADVANCED_SEO_ANALYSIS: 'advanced_seo_analysis',
    COMPETITOR_ANALYSIS: 'competitor_analysis',
    UNLIMITED_CONTENT_CALENDAR: 'unlimited_content_calendar',
    PRIORITY_SUPPORT: 'priority_support',
    WHITE_LABEL: 'white_label',
    CUSTOM_INTEGRATIONS: 'custom_integrations'
};

/**
 * Create middleware function to check feature access
 * @param {string} feature - The feature to check access for
 * @param {object} options - Additional options
 * @returns {function} Express middleware function
 */
function requireFeature(feature, options = {}) {
    return async (req, res, next) => {
        try {
            // Get user ID from request (adjust based on your auth system)
            const userId = req.user?.id || req.query.user_id || req.body.user_id;
            
            if (!userId) {
                return res.status(401).json({
                    success: false,
                    error: 'User authentication required',
                    code: 'AUTH_REQUIRED'
                });
            }

            // Check if feature access is enabled
            if (!process.env.ENABLE_FEATURE_RESTRICTIONS || process.env.ENABLE_FEATURE_RESTRICTIONS === 'false') {
                // Feature restrictions disabled, allow access
                return next();
            }

            // Check feature access
            const hasAccess = await subscriptionService.checkFeatureAccess(userId, feature);
            
            if (!hasAccess) {
                // Get user's current subscription for better error message
                const subscription = await subscriptionService.getUserSubscription(userId);
                
                return res.status(403).json({
                    success: false,
                    error: 'Feature not available in your current plan',
                    code: 'FEATURE_RESTRICTED',
                    feature: feature,
                    currentPlan: subscription?.plan || 'none',
                    upgradeRequired: true,
                    upgradeUrl: '/subscription'
                });
            }

            // User has access, continue
            next();
        } catch (error) {
            console.error('❌ Error checking feature access:', error);
            
            // In case of error, you might want to allow access or deny it
            // For now, we'll deny access to be safe
            return res.status(500).json({
                success: false,
                error: 'Unable to verify feature access',
                code: 'ACCESS_CHECK_FAILED'
            });
        }
    };
}

/**
 * Middleware to check if user has any active subscription
 */
async function requireActiveSubscription(req, res, next) {
    try {
        const userId = req.user?.id || req.query.user_id || req.body.user_id;
        
        if (!userId) {
            return res.status(401).json({
                success: false,
                error: 'User authentication required',
                code: 'AUTH_REQUIRED'
            });
        }

        const subscription = await subscriptionService.getUserSubscription(userId);
        
        if (!subscription) {
            return res.status(403).json({
                success: false,
                error: 'Active subscription required',
                code: 'SUBSCRIPTION_REQUIRED',
                upgradeUrl: '/subscription'
            });
        }

        // Check if subscription is active or in trial
        if (!['active', 'trialing'].includes(subscription.status)) {
            return res.status(403).json({
                success: false,
                error: 'Active subscription required',
                code: 'SUBSCRIPTION_INACTIVE',
                currentStatus: subscription.status,
                upgradeUrl: '/subscription'
            });
        }

        // Check if trial has expired
        if (subscription.status === 'trialing' && subscription.trial_end) {
            const trialEnd = new Date(subscription.trial_end);
            if (trialEnd < new Date()) {
                return res.status(403).json({
                    success: false,
                    error: 'Trial period has expired',
                    code: 'TRIAL_EXPIRED',
                    upgradeUrl: '/subscription'
                });
            }
        }

        // Add subscription info to request for use in route handlers
        req.subscription = subscription;
        next();
    } catch (error) {
        console.error('❌ Error checking subscription status:', error);
        return res.status(500).json({
            success: false,
            error: 'Unable to verify subscription status',
            code: 'SUBSCRIPTION_CHECK_FAILED'
        });
    }
}

/**
 * Middleware to add subscription info to request without blocking
 */
async function addSubscriptionInfo(req, res, next) {
    try {
        const userId = req.user?.id || req.query.user_id || req.body.user_id;
        
        if (userId) {
            const subscription = await subscriptionService.getUserSubscription(userId);
            req.subscription = subscription;
        }
        
        next();
    } catch (error) {
        console.error('❌ Error adding subscription info:', error);
        // Don't block the request, just continue without subscription info
        next();
    }
}

/**
 * Helper function to check feature access in route handlers
 */
async function checkFeatureAccess(userId, feature) {
    try {
        return await subscriptionService.checkFeatureAccess(userId, feature);
    } catch (error) {
        console.error('❌ Error checking feature access:', error);
        return false;
    }
}

/**
 * Helper function to get user's subscription in route handlers
 */
async function getUserSubscription(userId) {
    try {
        return await subscriptionService.getUserSubscription(userId);
    } catch (error) {
        console.error('❌ Error getting user subscription:', error);
        return null;
    }
}

/**
 * Helper function to check if user is in trial
 */
function isUserInTrial(subscription) {
    if (!subscription) return false;
    
    if (subscription.status !== 'trialing') return false;
    
    if (subscription.trial_end) {
        const trialEnd = new Date(subscription.trial_end);
        return trialEnd > new Date();
    }
    
    return false;
}

/**
 * Helper function to check if user has unlimited access (Enterprise plan)
 */
function hasUnlimitedAccess(subscription) {
    if (!subscription) return false;
    
    return subscription.plan === 'enterprise' && subscription.status === 'active';
}

module.exports = {
    FEATURES,
    requireFeature,
    requireActiveSubscription,
    addSubscriptionInfo,
    checkFeatureAccess,
    getUserSubscription,
    isUserInTrial,
    hasUnlimitedAccess
};
