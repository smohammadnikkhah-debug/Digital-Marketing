#!/usr/bin/env node

/**
 * Debug script to validate DataForSEO API responses
 * This will help us understand the actual data structure we're receiving
 */

const axios = require('axios');

async function debugDataForSEOResponse() {
    console.log('🔍 Debugging DataForSEO API Response Structure...\n');

    // Test credentials (from environment)
    const username = process.env.DATAFORSEO_USERNAME;
    const password = process.env.DATAFORSEO_PASSWORD;
    const domain = localStorage.getItem('lastAnalyzedDomain') || 'mozarex.com';
    console.log('🌐 Testing API endpoints for domain:', domain);
    
    if (!username || !password) {
        console.error('❌ DataForSEO credentials not found in environment variables');
        return;
    }

    const authHeader = Buffer.from(`${username}:${password}`).toString('base64');
    const baseUrl = 'https://api.dataforseo.com/v3';

    // Test 1: Keywords For Site API
    console.log('📊 Testing Keywords For Site API...');
    try {
        const keywordsData = [{
            target: domain,
            location_name: 'United States',
            language_code: 'en',
            limit: 5
        }];

        const keywordsResponse = await axios.post(`${baseUrl}/dataforseo_labs/google/keywords_for_site/live`, keywordsData, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${authHeader}`
            }
        });

        console.log('✅ Keywords API Response Structure:');
        console.log('Status Code:', keywordsResponse.data.status_code);
        console.log('Tasks Count:', keywordsResponse.data.tasks?.length);
        
        if (keywordsResponse.data.tasks && keywordsResponse.data.tasks[0]) {
            const task = keywordsResponse.data.tasks[0];
            console.log('Task Status:', task.status_code, task.status_message);
            console.log('Result Count:', task.result?.length || 0);
            
            if (task.result && task.result[0]) {
                console.log('First Keyword Result Structure:');
                console.log(JSON.stringify(task.result[0], null, 2));
            }
        }
    } catch (error) {
        console.error('❌ Keywords API Error:', error.response?.data || error.message);
    }

    console.log('\n' + '='.repeat(50) + '\n');

    // Test 2: Competitors Domain API
    console.log('🏆 Testing Competitors Domain API...');
    try {
        const competitorData = [{
            target: domain,
            location_name: 'United States',
            language_code: 'en',
            limit: 5,
            filters: [["metrics.organic.count", ">", 10]]
        }];

        const competitorResponse = await axios.post(`${baseUrl}/dataforseo_labs/google/competitors_domain/live`, competitorData, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${authHeader}`
            }
        });

        console.log('✅ Competitors API Response Structure:');
        console.log('Status Code:', competitorResponse.data.status_code);
        console.log('Tasks Count:', competitorResponse.data.tasks?.length);
        
        if (competitorResponse.data.tasks && competitorResponse.data.tasks[0]) {
            const task = competitorResponse.data.tasks[0];
            console.log('Task Status:', task.status_code, task.status_message);
            console.log('Result Count:', task.result?.length || 0);
            
            if (task.result && task.result[0]) {
                console.log('First Competitor Result Structure:');
                console.log(JSON.stringify(task.result[0], null, 2));
            }
        }
    } catch (error) {
        console.error('❌ Competitors API Error:', error.response?.data || error.message);
    }

    console.log('\n' + '='.repeat(50) + '\n');

    // Test 3: On-Page Instant Pages API
    console.log('📄 Testing On-Page Instant Pages API...');
    try {
        const onPageData = [{
            url: domain,
            enable_javascript: true,
            enable_browser_rendering: true,
            disable_cookie_popup: true,
            load_resources: true,
            enable_xhr: true
        }];

        const onPageResponse = await axios.post(`${baseUrl}/on_page/instant_pages`, onPageData, {
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Basic ${authHeader}`
            }
        });

        console.log('✅ On-Page API Response Structure:');
        console.log('Status Code:', onPageResponse.data.status_code);
        console.log('Tasks Count:', onPageResponse.data.tasks?.length);
        
        if (onPageResponse.data.tasks && onPageResponse.data.tasks[0]) {
            const task = onPageResponse.data.tasks[0];
            console.log('Task Status:', task.status_code, task.status_message);
            console.log('Has Result:', !!task.result);
            
            if (task.result) {
                console.log('On-Page Result Keys:', Object.keys(task.result));
                if (task.result.items && task.result.items[0]) {
                    console.log('First Item Keys:', Object.keys(task.result.items[0]));
                }
            }
        }
    } catch (error) {
        console.error('❌ On-Page API Error:', error.response?.data || error.message);
    }

    console.log('\n🎯 Debug complete! Check the structures above to understand the data format.');
}

// Run the debug
debugDataForSEOResponse().catch(console.error);
