const express = require('express');
const router = express.Router();
const supabaseService = require('../services/supabaseService');

// Get real traffic data from Supabase (traffic trends from DataForSEO)
router.get('/traffic-data/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        const { months = '3' } = req.query;
        
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
        const analysisData = await supabaseService.getAnalysisData(domain, customerId);
        
        if (analysisData && analysisData.trafficTrends) {
            const trafficTrends = analysisData.trafficTrends;
            const requestedMonths = parseInt(months);
            
            console.log(`✅ Found traffic trends data:`, {
                months: trafficTrends.months?.length || 0,
                hasOrganic: !!trafficTrends.organic,
                hasPaid: !!trafficTrends.paid,
                hasSocial: !!trafficTrends.social
            });
            
            // Extract the requested number of months
            const organic = (trafficTrends.organic || []).slice(-requestedMonths);
            const paid = (trafficTrends.paid || []).slice(-requestedMonths);
            const social = (trafficTrends.social || []).slice(-requestedMonths);
            const monthsLabels = (trafficTrends.months || []).slice(-requestedMonths);
            
            // If we have less data than requested, pad with the last value
            while (organic.length < requestedMonths && organic.length > 0) {
                organic.unshift(organic[0]);
                paid.unshift(paid[0] || 0);
                social.unshift(social[0] || 0);
            }
            
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
                source: 'supabase',
                generated_at: new Date().toISOString()
            });
            return;
        }
        
        // Fallback: Generate mock data if no real data available
        console.log(`⚠️ No traffic trends data found for ${domain}, using mock data`);
        const dataPoints = parseInt(months);
        const trafficData = {
            organic: [],
            social: [],
            ads: [],
            referringDomains: [],
            positions: []
        };
        
        // Generate deterministic realistic-looking data (no random changes)
        for (let i = 0; i < dataPoints; i++) {
            // Organic traffic: trending upward with consistent variation
            const organicBase = 8000 + (i * 200);
            const organicVariation = Math.sin(i * 0.5) * 300; // Consistent wave pattern
            trafficData.organic.push(Math.floor(organicBase + organicVariation));
            
            // Social traffic: moderate growth with consistent pattern
            const socialBase = 500 + (i * 50);
            const socialVariation = Math.cos(i * 0.3) * 80; // Consistent variation
            trafficData.social.push(Math.floor(socialBase + socialVariation));
            
            // Ads traffic: variable but generally stable
            const adsBase = 1000 + (i * 30);
            const adsVariation = Math.sin(i * 0.8) * 150; // Consistent pattern
            trafficData.ads.push(Math.floor(adsBase + adsVariation));
            
            // Referring domains: gradual increase with small variations
            const domainsBase = 20 + (i * 2);
            const domainsVariation = Math.cos(i * 0.4) * 3; // Small consistent variation
            trafficData.referringDomains.push(Math.floor(domainsBase + domainsVariation));
            
            // Keyword positions: improving over time with small fluctuations
            const positionBase = 45 - (i * 2);
            const positionVariation = Math.sin(i * 0.6) * 4; // Small consistent variation
            trafficData.positions.push(Math.floor(positionBase + positionVariation));
        }
        
        res.json({
            success: true,
            domain: domain,
            months: months,
            data: trafficData,
            source: 'mock',
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
