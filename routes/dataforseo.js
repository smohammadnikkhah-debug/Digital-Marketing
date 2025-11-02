const express = require('express');
const router = express.Router();
const supabaseService = require('../services/supabaseService');

// Get real traffic data from Supabase (traffic trends from DataForSEO)
router.get('/traffic-data/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        const { months = '3' } = req.query;
        const requestedMonths = parseInt(months);
        
        console.log(`[DataForSEO] Fetching REAL traffic data for domain: ${domain}, months: ${months}`);
        
        // Get customer ID from request (if authenticated)
        let customerId = null;
        try {
            // Use the same method as server.js uses
            const sessionService = require('../services/sessionService');
            const token = sessionService.extractToken(req);
            if (token) {
                const decoded = sessionService.verifyToken(token);
                const auth0Service = require('../services/auth0Service');
                const user = await auth0Service.getUserById(decoded.userId);
                if (user && user.customer_id) {
                    customerId = user.customer_id;
                    console.log(`👤 Customer ID found: ${customerId}`);
                }
            }
        } catch (authError) {
            console.log('⚠️ Could not get customer ID (not authenticated):', authError.message);
        }
        
        if (!customerId) {
            console.log('⚠️ No customer ID, will try to fetch analysis without customer filter');
        }
        
        // Get analysis data from Supabase (contains traffic trends)
        let analysisData = await supabaseService.getAnalysisData(domain, customerId);
        
        // Check if we have cached data and if it has enough months
        const hasSufficientCachedData = analysisData && 
                                        analysisData.trafficTrends && 
                                        analysisData.trafficTrends.months && 
                                        analysisData.trafficTrends.months.length >= requestedMonths;
        
        // If we need more data than cached OR no cached data, fetch fresh data
        if (!hasSufficientCachedData && requestedMonths > 3) {
            console.log(`🔄 Cached data insufficient for ${requestedMonths} months, fetching fresh data...`);
            try {
                const dataforseoService = require('../services/dataforseoEnvironmentService');
                const fullUrl = domain.startsWith('http') ? domain : `https://${domain}`;
                const freshTrends = await dataforseoService.getTrafficTrends(fullUrl, requestedMonths);
                
                if (freshTrends) {
                    console.log(`✅ Fresh traffic data fetched for ${requestedMonths} months`);
                    // Update analysis data with fresh trends
                    if (!analysisData) analysisData = {};
                    analysisData.trafficTrends = freshTrends;
                }
            } catch (fetchError) {
                console.error('⚠️ Error fetching fresh traffic data:', fetchError.message);
            }
        }
        
        if (analysisData && analysisData.trafficTrends) {
            const trafficTrends = analysisData.trafficTrends;
            
            console.log(`✅ Using traffic trends data:`, {
                cachedMonths: trafficTrends.months?.length || 0,
                requestedMonths: requestedMonths,
                hasOrganic: !!trafficTrends.organic,
                hasPaid: !!trafficTrends.paid,
                hasSocial: !!trafficTrends.social
            });
            
            // Extract the requested number of months (take the last N months)
            const organic = (trafficTrends.organic || []).slice(-requestedMonths);
            const paid = (trafficTrends.paid || []).slice(-requestedMonths);
            const social = (trafficTrends.social || []).slice(-requestedMonths);
            const monthsLabels = (trafficTrends.months || []).slice(-requestedMonths);
            
            const trafficData = {
                organic: organic.length > 0 ? organic : [],
                social: social.length > 0 ? social : [],
                ads: paid.length > 0 ? paid : [],
                referringDomains: [], // Not stored in trafficTrends
                positions: [] // Not stored in trafficTrends
            };
            
            res.json({
                success: true,
                domain: domain,
                months: months,
                data: trafficData,
                monthsLabels: monthsLabels.length > 0 ? monthsLabels : [],
                source: hasSufficientCachedData ? 'supabase-cache' : 'dataforseo-fresh',
                generated_at: new Date().toISOString()
            });
            return;
        }
        
        // No real data available - return empty arrays (NO MOCK DATA)
        console.log(`⚠️ No traffic trends data found for ${domain} - returning empty data`);
        console.log('💡 User needs to run fresh analysis to get DataForSEO data');
        
        res.json({
            success: false,
            domain: domain,
            months: months,
            data: {
                organic: [],
                social: [],
                ads: [],
                referringDomains: [],
                positions: []
            },
            source: 'no-data',
            message: 'No traffic data available. Please run a fresh analysis.',
            generated_at: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('[DataForSEO] Error fetching traffic data:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch traffic data',
            message: error.message
        });
    }
});

// Historical keyword data endpoint
router.get('/historical-data/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        
        console.log(`[DataForSEO] Fetching historical data for domain: ${domain}`);
        
        // Mock historical data
        const historicalData = {
            metrics: {
                estimatedTraffic: 12450,
                totalKeywords: 85,
                averagePosition: 28,
                seoIssues: 3
            },
            chartData: {
                traffic: {
                    months: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                    values: [8500, 9200, 10800, 11200, 11800, 12450]
                },
                positions: {
                    months: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                    values: [45, 42, 38, 35, 32, 28]
                }
            },
            rankedKeywords: [
                {
                    keyword_data: {
                        keyword_info: {
                            keyword: 'mozarex',
                            search_volume: 12000,
                            competition_level: 'MEDIUM'
                        }
                    },
                    ranked_serp_element: {
                        serp_item: {
                            rank_group: 33
                        }
                    }
                },
                {
                    keyword_data: {
                        keyword_info: {
                            keyword: 'mozarex services',
                            search_volume: 6000,
                            competition_level: 'HIGH'
                        }
                    },
                    ranked_serp_element: {
                        serp_item: {
                            rank_group: 35
                        }
                    }
                }
            ],
            competitors: [
                { domain: 'competitor1.com', rank: 1, traffic: 45000, keywords: 1250 },
                { domain: 'competitor2.com', rank: 2, traffic: 38000, keywords: 980 },
                { domain: 'competitor3.com', rank: 3, traffic: 32000, keywords: 850 }
            ]
        };
        
        res.json({
            success: true,
            domain: domain,
            data: historicalData,
            generated_at: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('[DataForSEO] Error fetching historical data:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to fetch historical data',
            message: error.message
        });
    }
});

module.exports = router;
