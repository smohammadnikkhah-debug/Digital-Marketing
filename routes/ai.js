const express = require('express');
const router = express.Router();
const { createClient } = require('@supabase/supabase-js');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');

// ==============================================================================
// AivekAI Nutrition & AI Backend Service Endpoints
// ==============================================================================

// Initialize Supabase client
const aivekaiSupabaseUrl = process.env.AIVEKAI_SUPABASE_URL || process.env.SUPABASE_URL;
const aivekaiSupabaseKey = process.env.AIVEKAI_SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
const aivekaiSupabase = (aivekaiSupabaseUrl && aivekaiSupabaseKey) ? createClient(aivekaiSupabaseUrl, aivekaiSupabaseKey) : null;

const appEnv = process.env.APP_ENV || 'development';
const sessionSecret = process.env.AIVEKAI_SESSION_SIGNING_SECRET || 'aivekai_session_signing_secret_default';

// Memory store for session creation abuse controls (IP & Installation ID rate limiting)
const sessionCreations = new Map();

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
// POST /api/ai/session/anonymous
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

        recentIpCreations.push(now);
        sessionCreations.set(ipKey, recentIpCreations);
        recentInstCreations.push(now);
        sessionCreations.set(instKey, recentInstCreations);

        const sessionId = crypto.randomUUID();
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
        timestamps = timestamps.filter(t => t > oneDayAgo);
        
        const minuteCount = timestamps.filter(t => t > oneMinuteAgo).length;
        if (minuteCount >= limitPerMinute) {
            return res.status(429).json({
                error: 'AI analysis is temporarily unavailable. Please try again shortly.'
            });
        }

        if (timestamps.length >= limitPerDay) {
            return res.status(429).json({
                error: 'Daily limit reached. Please try again tomorrow.'
            });
        }

        timestamps.push(now);
        rateLimitMap.set(userId, timestamps);
        next();
    };
}

// Active request promise cache for deduplication
const activeRequests = new Map();

function getDeduplicationHash(userId, operation, input) {
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

            if (response.status === 401 || response.status === 403 || response.status === 400) {
                const errText = await response.text();
                throw new Error(`OpenAI Client Error: ${response.status} - ${errText}`);
            }

            if (attempt === maxRetries) {
                const errText = await response.text();
                throw new Error(`OpenAI failed after ${maxRetries} retries: ${response.status} - ${errText}`);
            }
        } catch (err) {
            if (attempt === maxRetries) throw err;
        }

        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2;
    }
}

// Log OpenAI usage metrics to usage_logs table in Supabase
async function logOpenAIUsage(userId, operation, isImage, response, duration, retryCount, duplicatesBlocked = 0) {
    try {
        if (!aivekaiSupabase) return;
        const usage = response.data?.usage || {};
        await aivekaiSupabase.from('usage_logs').insert({
            user_id: userId,
            operation,
            is_image: isImage,
            prompt_tokens: usage.prompt_tokens || 0,
            completion_tokens: usage.completion_tokens || 0,
            total_tokens: usage.total_tokens || 0,
            duration_ms: duration,
            retry_count: retryCount,
            duplicates_blocked: duplicatesBlocked,
            created_at: new Date().toISOString()
        });
    } catch (e) {
        console.warn('Failed to log OpenAI usage:', e.message);
    }
}

// Generic AI execution helper with deduplication
async function executeAIOperation(req, res, operation, isImage, inputData, promptBuilder) {
    const userId = req.user.sessionId;
    const dedupeKey = getDeduplicationHash(userId, operation, inputData);

    if (activeRequests.has(dedupeKey)) {
        const inFlight = activeRequests.get(dedupeKey);
        inFlight.duplicatesBlocked = (inFlight.duplicatesBlocked || 0) + 1;
        try {
            const result = await inFlight.promise;
            return res.json(result);
        } catch (err) {
            return res.status(500).json({ error: 'AI analysis failed. Please try again.' });
        }
    }

    const openAiApiKey = process.env.OPENAI_API_KEY;
    if (!openAiApiKey) {
        return res.status(500).json({ error: 'AI service is currently unconfigured.' });
    }

    const startTime = Date.now();
    const payload = promptBuilder(inputData);

    const promise = (async () => {
        const response = await callOpenAIWithRetry(
            'https://api.openai.com/v1/chat/completions',
            {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${openAiApiKey}`
            },
            payload
        );

        const duration = Date.now() - startTime;
        const inFlightRef = activeRequests.get(dedupeKey);
        const dupes = inFlightRef ? inFlightRef.duplicatesBlocked || 0 : 0;

        await logOpenAIUsage(userId, operation, isImage, response, duration, response.retryCount, dupes);

        const contentStr = response.data.choices[0].message.content.trim();
        return JSON.parse(contentStr.replace(/```json\n?|\n?```/g, ''));
    })();

    activeRequests.set(dedupeKey, { promise, duplicatesBlocked: 0 });

    try {
        const parsed = await promise;
        res.json(parsed);
    } catch (err) {
        console.error(`[AI] Error in ${operation}:`, err.message);
        res.status(500).json({ error: 'Failed to process AI analysis. Please try again.' });
    } finally {
        activeRequests.delete(dedupeKey);
    }
}

// 1. Analyze Nutrition Label
// POST /api/ai/analyze-nutrition-label
router.post('/analyze-nutrition-label', verifyAivekAIAnonymousSession, aiRateLimiter(10, 50), (req, res) => {
    const { imageBase64 } = req.body;
    if (!imageBase64) {
        return res.status(400).json({ error: 'imageBase64 is required.' });
    }

    executeAIOperation(req, res, 'analyze_nutrition_label', true, imageBase64.substring(0, 100), () => ({
        model: 'gpt-4o',
        messages: [
            {
                role: 'system',
                content: 'You are a professional nutritionist AI. Analyze the nutrition facts label in the image and extract accurate nutritional data. Return ONLY valid JSON format.'
            },
            {
                role: 'user',
                content: [
                    { type: 'text', text: 'Extract: foodName, servingSize, calories, protein, carbs, fat, fiber, sugar, sodium.' },
                    { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${imageBase64}` } }
                ]
            }
        ],
        temperature: 0.1,
        response_format: { type: 'json_object' }
    }));
});

// 2. Analyze Food Plate
// POST /api/ai/analyze-food
router.post('/analyze-food', verifyAivekAIAnonymousSession, aiRateLimiter(10, 50), (req, res) => {
    const { imageBase64 } = req.body;
    if (!imageBase64) {
        return res.status(400).json({ error: 'imageBase64 is required.' });
    }

    executeAIOperation(req, res, 'analyze_food_plate', true, imageBase64.substring(0, 100), () => ({
        model: 'gpt-4o',
        messages: [
            {
                role: 'system',
                content: 'You are a professional dietitian AI. Estimate food items and nutritional breakdown from this meal image. Return ONLY valid JSON.'
            },
            {
                role: 'user',
                content: [
                    { type: 'text', text: 'Estimate: mealName, items (array of {name, portion, calories, protein, carbs, fat}), totalCalories, totalProtein, totalCarbs, totalFat, confidenceScore.' },
                    { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${imageBase64}` } }
                ]
            }
        ],
        temperature: 0.2,
        response_format: { type: 'json_object' }
    }));
});

// 3. Calculate Personalized Macros
// POST /api/ai/calculate-macros
router.post('/calculate-macros', verifyAivekAIAnonymousSession, aiRateLimiter(20, 100), (req, res) => {
    const { age, gender, heightCm, weightKg, activityLevel, primaryGoal } = req.body;
    if (!age || !gender || !heightCm || !weightKg || !primaryGoal) {
        return res.status(400).json({ error: 'Missing required user biometrics.' });
    }

    const inputData = { age, gender, heightCm, weightKg, activityLevel, primaryGoal };

    executeAIOperation(req, res, 'calculate_macros', false, inputData, () => ({
        model: 'gpt-4o-mini',
        messages: [
            {
                role: 'system',
                content: 'Calculate scientifically sound BMR, TDEE, target calories, and macro breakdown (protein/carb/fat percentages and grams) based on user biometrics and primary goal. Return ONLY valid JSON.'
            },
            {
                role: 'user',
                content: JSON.stringify(inputData)
            }
        ],
        temperature: 0.1,
        response_format: { type: 'json_object' }
    }));
});

module.exports = router;
