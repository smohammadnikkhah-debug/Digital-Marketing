const express = require('express');
const router = express.Router();
const supabaseService = require('../services/supabaseService');

// AI-powered keyword optimization endpoint
router.post('/optimize-keyword', async (req, res) => {
    try {
        const { keyword, aiScore, domain } = req.body;
        
        console.log(`🤖 AI optimizing keyword: ${keyword} for domain: ${domain}`);
        
        // Generate AI-powered recommendations based on keyword and score
        const recommendations = generateAIRecommendations(keyword, aiScore, domain);
        
        res.json(recommendations);
        
    } catch (error) {
        console.error('❌ Error in AI keyword optimization:', error);
        res.status(500).json({ 
            error: 'Failed to generate AI recommendations',
            message: error.message 
        });
    }
});

// Implement AI recommendation endpoint
router.post('/implement-recommendation', async (req, res) => {
    try {
        const { recommendationId, keyword, domain } = req.body;
        
        console.log(`🔧 Implementing AI recommendation: ${recommendationId} for keyword: ${keyword}`);
        
        // Simulate implementing the recommendation
        const result = await implementRecommendation(recommendationId, keyword, domain);
        
        res.json(result);
        
    } catch (error) {
        console.error('❌ Error implementing recommendation:', error);
        res.status(500).json({ 
            error: 'Failed to implement recommendation',
            message: error.message 
        });
    }
});

// Generate AI-powered recommendations
function generateAIRecommendations(keyword, aiScore, domain) {
    const recommendations = [];
    
    // Content optimization recommendations
    if (aiScore < 70) {
        recommendations.push({
            id: 'content-optimization',
            icon: '📝',
            title: 'Content Optimization',
            description: `Optimize your content for "${keyword}" by improving keyword density, adding related terms, and enhancing readability.`,
            priority: 'High',
            actionText: 'Optimize Content'
        });
    }
    
    // Technical SEO recommendations
    if (aiScore < 80) {
        recommendations.push({
            id: 'technical-seo',
            icon: '⚙️',
            title: 'Technical SEO',
            description: `Improve technical aspects like page speed, mobile optimization, and structured data for better rankings.`,
            priority: 'Medium',
            actionText: 'Fix Technical Issues'
        });
    }
    
    // Link building recommendations
    if (aiScore < 75) {
        recommendations.push({
            id: 'link-building',
            icon: '🔗',
            title: 'Link Building',
            description: `Build high-quality backlinks from relevant websites to improve domain authority and rankings.`,
            priority: 'Medium',
            actionText: 'Build Links'
        });
    }
    
    // Meta tags optimization
    if (aiScore < 85) {
        recommendations.push({
            id: 'meta-optimization',
            icon: '🏷️',
            title: 'Meta Tags Optimization',
            description: `Optimize title tags, meta descriptions, and header tags to better target "${keyword}".`,
            priority: 'High',
            actionText: 'Optimize Meta Tags'
        });
    }
    
    // User experience improvements
    if (aiScore < 90) {
        recommendations.push({
            id: 'user-experience',
            icon: '👥',
            title: 'User Experience',
            description: `Improve user experience with better navigation, faster loading times, and mobile-friendly design.`,
            priority: 'Low',
            actionText: 'Improve UX'
        });
    }
    
    // Schema markup
    if (aiScore < 80) {
        recommendations.push({
            id: 'schema-markup',
            icon: '📊',
            title: 'Schema Markup',
            description: `Add structured data markup to help search engines understand your content better.`,
            priority: 'Medium',
            actionText: 'Add Schema'
        });
    }
    
    return recommendations;
}

// Implement recommendation (simulated)
async function implementRecommendation(recommendationId, keyword, domain) {
    // Simulate processing time
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    const results = {
        'content-optimization': {
            message: 'Content optimized successfully for better keyword targeting',
            impact: 'Expected 15-25% improvement in rankings within 2-4 weeks'
        },
        'technical-seo': {
            message: 'Technical SEO issues identified and fixed',
            impact: 'Page speed improved by 30%, mobile score increased to 95+'
        },
        'link-building': {
            message: 'Link building strategy implemented',
            impact: '5 high-quality backlinks identified and outreach initiated'
        },
        'meta-optimization': {
            message: 'Meta tags optimized for better search visibility',
            impact: 'Click-through rate expected to increase by 20-30%'
        },
        'user-experience': {
            message: 'User experience improvements implemented',
            impact: 'Bounce rate reduced by 15%, time on page increased by 25%'
        },
        'schema-markup': {
            message: 'Schema markup added to improve search understanding',
            impact: 'Rich snippets enabled, better search result appearance'
        }
    };
    
    return results[recommendationId] || {
        message: 'Recommendation implemented successfully',
        impact: 'Positive impact expected on search rankings'
    };
}

    // Endpoint to generate AI proposals for different sections
    router.post('/generate-proposals', async (req, res) => {
        const { domain, section } = req.body;
        console.log(`[AI Route] Received request to generate proposals for domain: ${domain}, section: ${section}`);

        // Simulate AI processing time
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Generate context-specific proposals based on section
        let proposals = [];
        
        switch (section) {
            case 'technical':
                proposals = [
                    { id: 'tech1', icon: '🔧', title: 'Fix Meta Tags', description: 'Optimize title tags and meta descriptions for better search visibility.', priority: 'High', actionText: 'Fix Meta Tags' },
                    { id: 'tech2', icon: '⚡', title: 'Improve Page Speed', description: 'Optimize images and reduce server response time for better user experience.', priority: 'High', actionText: 'Speed Optimization' },
                    { id: 'tech3', icon: '📱', title: 'Mobile Optimization', description: 'Ensure your website is fully responsive and mobile-friendly.', priority: 'Medium', actionText: 'Mobile Fix' },
                    { id: 'tech4', icon: '🔗', title: 'Fix Broken Links', description: 'Identify and fix internal and external broken links.', priority: 'Medium', actionText: 'Fix Links' },
                    { id: 'tech5', icon: '🏷️', title: 'Schema Markup', description: 'Implement structured data markup for rich snippets.', priority: 'Low', actionText: 'Add Schema' }
                ];
                break;
            case 'keywords':
                proposals = [
                    { id: 'kw1', icon: '🎯', title: 'Keyword Optimization', description: 'Optimize content for high-value keywords with better search volume.', priority: 'High', actionText: 'Optimize Keywords' },
                    { id: 'kw2', icon: '📝', title: 'Content Enhancement', description: 'Improve content quality and relevance for target keywords.', priority: 'High', actionText: 'Enhance Content' },
                    { id: 'kw3', icon: '🔍', title: 'Long-tail Keywords', description: 'Target long-tail keywords for better conversion rates.', priority: 'Medium', actionText: 'Target Long-tail' },
                    { id: 'kw4', icon: '📊', title: 'Keyword Research', description: 'Discover new keyword opportunities in your niche.', priority: 'Medium', actionText: 'Research Keywords' }
                ];
                break;
            case 'competitors':
                proposals = [
                    { id: 'comp1', icon: '🎯', title: 'Competitor Analysis', description: 'Analyze competitor strategies and identify opportunities.', priority: 'High', actionText: 'Analyze Competitors' },
                    { id: 'comp2', icon: '📈', title: 'Market Positioning', description: 'Improve your market positioning against competitors.', priority: 'High', actionText: 'Position Better' },
                    { id: 'comp3', icon: '🔍', title: 'Gap Analysis', description: 'Identify content and keyword gaps compared to competitors.', priority: 'Medium', actionText: 'Find Gaps' },
                    { id: 'comp4', icon: '💡', title: 'Opportunity Discovery', description: 'Discover untapped market opportunities.', priority: 'Low', actionText: 'Find Opportunities' }
                ];
                break;
            case 'backlinks':
                proposals = [
                    { id: 'bl1', icon: '🔗', title: 'Link Building Strategy', description: 'Develop a comprehensive link building strategy.', priority: 'High', actionText: 'Build Links' },
                    { id: 'bl2', icon: '📝', title: 'Content Marketing', description: 'Create link-worthy content to attract natural backlinks.', priority: 'High', actionText: 'Create Content' },
                    { id: 'bl3', icon: '🤝', title: 'Outreach Campaign', description: 'Reach out to relevant websites for link opportunities.', priority: 'Medium', actionText: 'Start Outreach' },
                    { id: 'bl4', icon: '🏆', title: 'Authority Building', description: 'Build domain authority through quality backlinks.', priority: 'Medium', actionText: 'Build Authority' }
                ];
                break;
            default:
                proposals = [
                    { id: 'gen1', icon: '🎯', title: 'SEO Optimization', description: 'General SEO improvements for better search rankings.', priority: 'High', actionText: 'Optimize SEO' },
                    { id: 'gen2', icon: '📊', title: 'Performance Analysis', description: 'Analyze website performance and identify improvement areas.', priority: 'Medium', actionText: 'Analyze Performance' },
                    { id: 'gen3', icon: '🚀', title: 'Growth Strategy', description: 'Develop a comprehensive growth strategy for your website.', priority: 'Low', actionText: 'Plan Growth' }
                ];
        }

        res.json({
            success: true,
            proposals: proposals,
            domain: domain,
            section: section,
            generated_at: new Date().toISOString()
        });
    });

    // Blog recommendations endpoint
router.post('/blog-recommendations', async (req, res) => {
    try {
        const { domain, topic, keywords } = req.body;
        
        console.log('[AI] Generating blog recommendations for:', { domain, topic, keywords });
        
        // Generate AI recommendations based on competitor analysis and keyword research
        const recommendations = await generateBlogRecommendations(domain, topic, keywords);
        
        res.json({
            success: true,
            recommendations: recommendations
        });
        
    } catch (error) {
        console.error('[AI] Error generating blog recommendations:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to generate recommendations',
            message: error.message
        });
    }
});

// Apply recommendations to blog content
router.post('/apply-recommendations', async (req, res) => {
    try {
        const { blogContent, recommendations } = req.body;
        
        console.log('[AI] Applying recommendations to blog content');
        
        // Apply recommendations using AI
        const updatedContent = await applyRecommendationsToContent(blogContent, recommendations);
        
        res.json({
            success: true,
            updatedContent: updatedContent.content,
            newSeoScore: updatedContent.seoScore
        });
        
    } catch (error) {
        console.error('[AI] Error applying recommendations:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to apply recommendations',
            message: error.message
        });
    }
});

// Generate blog recommendations based on competitor analysis
async function generateBlogRecommendations(domain, topic, keywords) {
    // Mock recommendations based on competitor analysis
    // In real implementation, this would analyze competitor content and keyword data
    
    const recommendations = {
        contentStrategy: [
            {
                reason: "Based on competitor analysis and trending topics",
                text: "Focus on long-tail keywords with lower competition to capture more targeted traffic",
                impact: "Medium"
            },
            {
                reason: "Gap analysis from top competitors",
                text: "Create comprehensive guides that competitors are missing to establish thought leadership",
                impact: "High"
            }
        ],
        seoOptimization: [
            {
                reason: "Keyword density analysis",
                text: "Include primary keywords 3-5 times and secondary keywords 1-2 times naturally",
                impact: "High"
            },
            {
                reason: "Content structure optimization",
                text: "Use H2 and H3 headings with keywords to improve readability and SEO",
                impact: "Medium"
            }
        ],
        audienceEngagement: [
            {
                reason: "Based on competitor content performance",
                text: "Include interactive elements like lists, tables, and call-to-action buttons",
                impact: "Medium"
            },
            {
                reason: "User intent analysis",
                text: "Address common questions and pain points that your audience is searching for",
                impact: "High"
            }
        ]
    };
    
    return recommendations;
}

// Apply recommendations to blog content
async function applyRecommendationsToContent(blogContent, recommendations) {
    // Mock implementation - in real scenario, this would use AI to improve content
    let updatedContent = blogContent;
    let seoScore = 75; // Base score
    
    // Apply content strategy recommendations
    recommendations.forEach(rec => {
        if (rec.text.includes('long-tail keywords')) {
            seoScore += 5;
        }
        if (rec.text.includes('comprehensive guides')) {
            seoScore += 8;
        }
        if (rec.text.includes('keyword density')) {
            seoScore += 10;
        }
        if (rec.text.includes('headings')) {
            seoScore += 7;
        }
        if (rec.text.includes('interactive elements')) {
            seoScore += 5;
        }
        if (rec.text.includes('questions and pain points')) {
            seoScore += 8;
        }
    });
    
    // Ensure score doesn't exceed 100
    seoScore = Math.min(seoScore, 100);
    
    return {
        content: updatedContent,
        seoScore: seoScore
    };
}

// ==========================================
// AivekAI Secure Backend Routes & Middlewares
// ==========================================

// Initialize Supabase Client specifically for AivekAI (separating AivekAI from Digital Marketing dashboard database)
const { createClient } = require('@supabase/supabase-js');
const aivekaiSupabaseUrl = process.env.AIVEKAI_SUPABASE_URL || process.env.SUPABASE_URL;
const aivekaiSupabaseKey = process.env.AIVEKAI_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
const aivekaiSupabase = (aivekaiSupabaseUrl && aivekaiSupabaseKey) ? createClient(aivekaiSupabaseUrl, aivekaiSupabaseKey) : null;

const appEnv = process.env.APP_ENV || 'development';
console.log(`🤖 AivekAI Backend running in environment: ${appEnv.toUpperCase()}`);

const jwt = require('jsonwebtoken');
const sessionSecret = process.env.AIVEKAI_SESSION_SIGNING_SECRET || 'aivekai_dev_session_signing_secret_key_12345';

// Memory store for session creation abuse controls (IP & Installation ID rate limiting)
const sessionCreations = new Map();

// Helper to clean up expired/stale entries in the creations map
function cleanSessionCreations() {
    const now = Date.now();
    for (const [key, timestamps] of sessionCreations.entries()) {
        const fresh = timestamps.filter(t => t > now - 60 * 60 * 1000); // keep last 1 hour
        if (fresh.length === 0) {
            sessionCreations.delete(key);
        } else {
            sessionCreations.set(key, fresh);
        }
    }
}

// Endpoint to generate a signed anonymous session token
// POST /api/session/anonymous
router.post('/session/anonymous', (req, res) => {
    try {
        cleanSessionCreations();
        const clientIp = req.ip || req.headers['x-forwarded-for'] || 'unknown';
        const { installationId } = req.body;

        if (!installationId || typeof installationId !== 'string' || installationId.length < 10) {
            return res.status(400).json({ error: 'Valid installationId is required.' });
        }

        // Apply session creation abuse protections
        const ipKey = `ip:${clientIp}`;
        const instKey = `inst:${installationId}`;
        const now = Date.now();

        // 1. IP rate limit (max 10 sessions per hour)
        const ipTimestamps = sessionCreations.get(ipKey) || [];
        const recentIpCreations = ipTimestamps.filter(t => t > now - 60 * 60 * 1000);
        if (recentIpCreations.length >= 10) {
            console.warn(`[ABUSE] Session creation rate limit hit for IP: ${clientIp}`);
            return res.status(429).json({ error: 'Too many sessions created. Please try again later.' });
        }

        // 2. Installation ID rate limit (max 5 sessions per hour)
        const instTimestamps = sessionCreations.get(instKey) || [];
        const recentInstCreations = instTimestamps.filter(t => t > now - 60 * 60 * 1000);
        if (recentInstCreations.length >= 5) {
            console.warn(`[ABUSE] Session creation rate limit hit for Installation ID: ${installationId}`);
            return res.status(429).json({ error: 'Too many sessions created. Please try again later.' });
        }

        // Record creations
        recentIpCreations.push(now);
        sessionCreations.set(ipKey, recentIpCreations);
        recentInstCreations.push(now);
        sessionCreations.set(instKey, recentInstCreations);

        // Generate a random session ID
        const crypto = require('crypto');
        const sessionId = crypto.randomUUID();

        // Sign JWT token expiring in 7 days
        const token = jwt.sign(
            { sessionId, installationId },
            sessionSecret,
            { expiresIn: '7d' }
        );

        return res.json({ token });
    } catch (err) {
        console.error('[SESSION] Error generating anonymous session:', err);
        return res.status(500).json({ error: 'Failed to establish anonymous session.' });
    }
});

// Middleware to verify signed anonymous session tokens
async function verifyAivekAIAnonymousSession(req, res, next) {
    try {
        const authHeader = req.headers.authorization;
        if (!authHeader || !authHeader.startsWith('Bearer ')) {
            return res.status(401).json({ error: 'Your session has expired. Please sign in again.' });
        }
        const token = authHeader.substring(7).trim();
        if (!token) {
            return res.status(401).json({ error: 'Your session has expired. Please sign in again.' });
        }

        // Verify token signature and expiration
        const decoded = jwt.verify(token, sessionSecret);
        if (!decoded.sessionId || !decoded.installationId) {
            return res.status(401).json({ error: 'Your session has expired. Please sign in again.' });
        }

        req.user = { 
            sessionId: decoded.sessionId, 
            installationId: decoded.installationId 
        };
        next();
    } catch (err) {
        console.warn('[AUTH] Token verification failed:', err.message);
        return res.status(401).json({ error: 'Your session has expired. Please sign in again.' });
    }
}

// In-memory rate limiting map
const rateLimitMap = new Map();

function aiRateLimiter(limitPerMinute = 10, limitPerDay = 100) {
    return (req, res, next) => {
        const userId = req.user.sessionId;
        const now = Date.now();
        const oneMinuteAgo = now - 60 * 1000;
        const oneDayAgo = now - 24 * 60 * 60 * 1000;

        if (!rateLimitMap.has(userId)) {
            rateLimitMap.set(userId, []);
        }

        let timestamps = rateLimitMap.get(userId);
        
        // Clean up timestamps older than 24 hours
        timestamps = timestamps.filter(t => t > oneDayAgo);
        
        // Check 1-minute limit
        const minuteCount = timestamps.filter(t => t > oneMinuteAgo).length;
        if (minuteCount >= limitPerMinute) {
            console.warn(`[RATE_LIMIT] User ${userId} exceeded minute limit: ${minuteCount}/${limitPerMinute}`);
            return res.status(429).json({
                error: 'AI analysis is temporarily unavailable. Please try again shortly.'
            });
        }

        // Check daily limit
        if (timestamps.length >= limitPerDay) {
            console.warn(`[RATE_LIMIT] User ${userId} exceeded daily limit: ${timestamps.length}/${limitPerDay}`);
            return res.status(429).json({
                error: 'Daily limit reached. Please try again tomorrow.'
            });
        }

        // Add current timestamp
        timestamps.push(now);
        rateLimitMap.set(userId, timestamps);
        next();
    };
}

// Active request promise cache for deduplication
const activeRequests = new Map();

function getDeduplicationHash(userId, operation, input) {
    const crypto = require('crypto');
    const normalizedInput = typeof input === 'string' ? input.trim().toLowerCase() : JSON.stringify(input);
    return crypto.createHash('md5').update(`${userId}:${operation}:${normalizedInput}`).digest('hex');
}

// OpenAI API call with backoff retries
async function callOpenAIWithRetry(url, headers, body, maxRetries = 3) {
    let delay = 1000;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(body)
            });

            if (response.status === 200) {
                return {
                    statusCode: 200,
                    data: await response.json(),
                    headers: response.headers,
                    retryCount: attempt
                };
            }

            console.warn(`[OPENAI] Attempt ${attempt} failed with status: ${response.status}`);
            
            // Do not retry 401, 403, or client validation errors
            if (response.status === 401 || response.status === 403 || response.status === 400) {
                const errText = await response.text();
                throw new Error(`OpenAI Client Error: ${response.status} - ${errText}`);
            }

            if (attempt === maxRetries) {
                const errText = await response.text();
                throw new Error(`OpenAI failed after ${maxRetries} retries: ${response.status} - ${errText}`);
            }

        } catch (err) {
            console.error(`[OPENAI] Attempt ${attempt} error:`, err.message);
            if (attempt === maxRetries) {
                throw err;
            }
        }

        console.log(`[OPENAI] Waiting ${delay}ms before retry...`);
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2;
    }
}

// Log OpenAI usage metrics to usage_logs table in Supabase
async function logOpenAIUsage(userId, operation, isImage, response, duration, retryCount, duplicatesBlocked = 0) {
    try {
        const usage = response.data.usage || {};
        const inputTokens = usage.prompt_tokens || 0;
        const outputTokens = usage.completion_tokens || 0;
        const totalTokens = usage.total_tokens || 0;
        
        const estimatedCost = (inputTokens * 0.150 / 1000000) + (outputTokens * 0.600 / 1000000);

        const logData = {
            user_id: userId,
            action_type: 'openai_request',
            timestamp: new Date().toISOString(),
            details: {
                environment: appEnv,
                operation: operation,
                is_image: isImage,
                model: response.data.model || 'gpt-4o-mini',
                response_code: response.statusCode,
                duration_ms: duration,
                retry_count: retryCount,
                input_tokens: inputTokens,
                output_tokens: outputTokens,
                total_tokens: totalTokens,
                estimated_cost: estimatedCost,
                duplicates_blocked: duplicatesBlocked,
                request_id: response.headers.get('x-request-id') || response.headers.get('apiproxy-request-id') || ''
            }
        };

        await aivekaiSupabase
            .from('usage_logs')
            .insert(logData);

        console.log(`[LOG] AI Usage logged for user ${userId}. Cost: $${estimatedCost.toFixed(6)}, Tokens: ${totalTokens}`);
    } catch (err) {
        console.error('[LOG] Error saving usage log:', err.message);
    }
}

// Route: Chat completions (analyzes food/exercise text or photos)
router.post('/chat', verifyAivekAIAnonymousSession, aiRateLimiter(10, 100), async (req, res) => {
    const userId = req.user.sessionId;
    const { messages, input, isImage } = req.body;
    
    const inputForHash = input || (messages && messages.length > 0 ? messages[messages.length - 1].content : '');
    const dedupeHash = getDeduplicationHash(userId, 'chat', inputForHash);

    if (activeRequests.has(dedupeHash)) {
        console.log(`[DEDUPE] Reusing active request for user ${userId}`);
        try {
            const cachedResult = await activeRequests.get(dedupeHash);
            return res.json(cachedResult);
        } catch (err) {}
    }

    const requestPromise = (async () => {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OPENAI_KEY_NOT_CONFIGURED');
        }

        const startTime = Date.now();
        const openaiUrl = 'https://api.openai.com/v1/chat/completions';
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        };

        const body = {
            model: 'gpt-4o-mini',
            messages: messages,
            response_format: { type: 'json_object' }
        };

        const response = await callOpenAIWithRetry(openaiUrl, headers, body);
        const duration = Date.now() - startTime;

        logOpenAIUsage(userId, 'chat', !!isImage, response, duration, response.retryCount);

        return response.data;
    })();

    activeRequests.set(dedupeHash, requestPromise);

    try {
        const result = await requestPromise;
        res.json(result);
    } catch (err) {
        console.error('[CHAT] Error in OpenAI backend call:', err.message);
        if (err.message === 'OPENAI_KEY_NOT_CONFIGURED') {
            return res.status(503).json({ error: 'AI analysis is temporarily unavailable. Please try again shortly.' });
        }
        res.status(500).json({ error: 'We couldn\'t connect right now. Please check your connection and try again.' });
    } finally {
        setTimeout(() => activeRequests.delete(dedupeHash), 5000);
    }
});

// Route: Personalized wellness recommendations
router.post('/recommendation', verifyAivekAIAnonymousSession, aiRateLimiter(10, 100), async (req, res) => {
    const userId = req.user.sessionId;
    const { messages } = req.body;

    const dedupeHash = getDeduplicationHash(userId, 'recommendation', messages);

    if (activeRequests.has(dedupeHash)) {
        try {
            const cachedResult = await activeRequests.get(dedupeHash);
            return res.json(cachedResult);
        } catch (err) {}
    }

    const requestPromise = (async () => {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OPENAI_KEY_NOT_CONFIGURED');
        }

        const startTime = Date.now();
        const openaiUrl = 'https://api.openai.com/v1/chat/completions';
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        };

        const body = {
            model: 'gpt-4o-mini',
            messages: messages,
            response_format: { type: 'json_object' }
        };

        const response = await callOpenAIWithRetry(openaiUrl, headers, body);
        const duration = Date.now() - startTime;

        logOpenAIUsage(userId, 'recommendation', false, response, duration, response.retryCount);

        return response.data;
    })();

    activeRequests.set(dedupeHash, requestPromise);

    try {
        const result = await requestPromise;
        res.json(result);
    } catch (err) {
        console.error('[RECOMMENDATION] Error in OpenAI backend call:', err.message);
        if (err.message === 'OPENAI_KEY_NOT_CONFIGURED') {
            return res.status(503).json({ error: 'AI analysis is temporarily unavailable. Please try again shortly.' });
        }
        res.status(500).json({ error: 'We couldn\'t connect right now. Please check your connection and try again.' });
    } finally {
        setTimeout(() => activeRequests.delete(dedupeHash), 5000);
    }
});

// Route: Text and image content moderation
router.post('/moderate', verifyAivekAIAnonymousSession, aiRateLimiter(10, 100), async (req, res) => {
    const userId = req.user.sessionId;
    const { type, text, messages } = req.body;

    const dedupeHash = getDeduplicationHash(userId, 'moderate', req.body);

    if (activeRequests.has(dedupeHash)) {
        try {
            const cachedResult = await activeRequests.get(dedupeHash);
            return res.json(cachedResult);
        } catch (err) {}
    }

    const requestPromise = (async () => {
        if (!process.env.OPENAI_API_KEY) {
            throw new Error('OPENAI_KEY_NOT_CONFIGURED');
        }

        const startTime = Date.now();
        let openaiUrl = 'https://api.openai.com/v1/chat/completions';
        let body = {};

        if (type === 'moderations') {
            openaiUrl = 'https://api.openai.com/v1/moderations';
            body = { input: text };
        } else {
            body = {
                model: 'gpt-4o-mini',
                messages: messages,
                response_format: { type: 'json_object' }
            };
        }

        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        };

        const response = await callOpenAIWithRetry(openaiUrl, headers, body);
        const duration = Date.now() - startTime;

        logOpenAIUsage(userId, 'moderate_' + type, false, response, duration, response.retryCount);

        return response.data;
    })();

    activeRequests.set(dedupeHash, requestPromise);

    try {
        const result = await requestPromise;
        res.json(result);
    } catch (err) {
        console.error('[MODERATE] Error in OpenAI backend call:', err.message);
        if (err.message === 'OPENAI_KEY_NOT_CONFIGURED') {
            return res.status(503).json({ error: 'AI analysis is temporarily unavailable. Please try again shortly.' });
        }
        res.status(500).json({ error: 'We couldn\'t connect right now. Please check your connection and try again.' });
    } finally {
        setTimeout(() => activeRequests.delete(dedupeHash), 5000);
    }
});

module.exports = router;
