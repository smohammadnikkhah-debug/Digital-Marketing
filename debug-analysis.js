#!/usr/bin/env node

/**
 * Debug script to help identify the website creation issue
 * Based on the console logs, the issue is that customer websites API returns empty array
 */

console.log('🔍 Website Creation Debug Analysis');
console.log('==================================\n');

console.log('📋 Based on your console logs:');
console.log('✅ User authentication: Working');
console.log('✅ User data loading: Working');
console.log('✅ User has domain: mozarex.com');
console.log('❌ Customer websites API: Returns empty array');
console.log('');

console.log('🔍 Possible Issues:');
console.log('1. Website not created in Supabase during onboarding');
console.log('2. Website created but without proper customer_id');
console.log('3. Authentication token not being passed to save-onboarding API');
console.log('4. Supabase configuration issue in DigitalOcean');
console.log('');

console.log('🛠️ Debug Steps:');
console.log('1. Check DigitalOcean app logs for save-onboarding API calls');
console.log('2. Verify Supabase environment variables in DigitalOcean');
console.log('3. Test website creation manually');
console.log('4. Check if customer_id is being retrieved correctly');
console.log('');

console.log('📊 Expected Flow:');
console.log('1. User completes onboarding → calls /api/user/save-onboarding');
console.log('2. Server extracts JWT token → gets user ID');
console.log('3. Server gets user from database → retrieves customer_id');
console.log('4. Server calls supabaseService.createOrGetWebsite(domain, business, customer_id)');
console.log('5. Website created in Supabase with customer_id');
console.log('6. Dashboard calls /api/supabase/customer-websites → returns website');
console.log('');

console.log('❌ Current Issue:');
console.log('Step 6 is failing - no websites returned for customer_id');
console.log('');

console.log('🔍 Next Steps:');
console.log('1. Check DigitalOcean logs for save-onboarding API calls');
console.log('2. Look for authentication token extraction logs');
console.log('3. Check if customer_id is being retrieved');
console.log('4. Verify website creation in Supabase');
console.log('');

console.log('💡 Quick Test:');
console.log('Try adding a website through onboarding again and check:');
console.log('- Browser console logs (should show detailed onboarding logs)');
console.log('- DigitalOcean app logs (should show server-side logs)');
console.log('- Look for "🔍 Save onboarding:" messages');
console.log('');

console.log('🔍 Debug complete!');
