#!/usr/bin/env node

/**
 * DataForSEO Account Status Check
 * Help identify what API endpoints are available in your DataForSEO subscription
 */

console.log('🔍 DataForSEO Account Status');
console.log('============================\n');

console.log('📋 Analysis of Current Errors:');
console.log('');

console.log('1. On-Page API (/on_page/instant_pages):');
console.log('   Status: 402 Payment Required');
console.log('   Message: Your DataForSEO account needs credits or a paid plan');
console.log('   Cause: Insufficient credits in DataForSEO account');
console.log('');

console.log('2. DataForSEO Labs API (/dataforseo_labs/google/keyword_suggestions):');
console.log('   Status: 404 Not Found');
console.log('   Message: Endpoint not available');
console.log('   Cause: This endpoint requires DataForSEO Labs subscription');
console.log('');

console.log('💡 Solutions:');
console.log('');

console.log('Option 1: Add Credits to DataForSEO Account');
console.log('   1. Log in to your DataForSEO account');
console.log('   2. Go to Billing or Credits section');
console.log('   3. Add credits to your account');
console.log('   4. Try analysis again');
console.log('');

console.log('Option 2: Use Alternative API Endpoints');
console.log('   Use free or lower-cost DataForSEO endpoints:');
console.log('   - /serp/google/organic/live/advanced (SERP data)');
console.log('   - /keywords_data/google_ads/search_volume (Keyword data)');
console.log('   - /backlinks/backlinks (Backlink data)');
console.log('');

console.log('Option 3: Use Demo/Sandbox Mode');
console.log('   Set ENABLE_DEMO_DATA=true to use demo data for testing');
console.log('   Not recommended for production use');
console.log('');

console.log('📊 DataForSEO Pricing:');
console.log('   OnPage API: ~$0.001 - $0.002 per page');
console.log('   DataForSEO Labs: Requires separate subscription');
console.log('   SERP API: ~$0.002 - $0.01 per query');
console.log('   Backlinks API: ~$0.001 per request');
console.log('');

console.log('🎯 Recommended Action:');
console.log('1. Check your DataForSEO account balance');
console.log('2. Add $10-$20 credits for testing');
console.log('3. Re-run the analysis');
console.log('4. Monitor credit usage to optimize costs');
console.log('');

console.log('🔗 DataForSEO Account Links:');
console.log('   Login: https://app.dataforseo.com/');
console.log('   Billing: https://app.dataforseo.com/billing');
console.log('   API Docs: https://docs.dataforseo.com/');
console.log('');

console.log('🔍 Check complete!');
