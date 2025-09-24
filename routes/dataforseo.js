const express = require('express');
const router = express.Router();

// Mock DataForSEO traffic data endpoint
// TODO: Replace with real DataForSEO API integration
// Real implementation would use:
// - DataForSEO Labs API for historical traffic data
// - DataForSEO OnPage API for current metrics
// - DataForSEO Backlinks API for referring domains
router.get('/traffic-data/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        const { months = '3' } = req.query;
        
        console.log(`[DataForSEO] Fetching traffic data for domain: ${domain}, months: ${months}`);
        
        // Generate mock traffic data based on the requested months
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
