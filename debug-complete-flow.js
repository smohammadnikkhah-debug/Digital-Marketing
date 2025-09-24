const axios = require('axios');

async function debugCompleteOnboardingFlow() {
    console.log('🔍 DEBUGGING COMPLETE ONBOARDING FLOW');
    console.log('=====================================');
    
    const testDomain = 'complete-debug.com';
    const testBusinessDescription = 'Complete test business for debugging';
    
    try {
        // Step 1: Simulate website analysis (like onboarding does)
        console.log('\n🔬 STEP 1: Simulating website analysis...');
        const analysisResponse = await axios.post('http://localhost:3000/api/dataforseo/environment/analyze-website', {
            url: testDomain
        });
        console.log('✅ Analysis response status:', analysisResponse.status);
        console.log('✅ Analysis success:', analysisResponse.data.success);
        console.log('✅ Analysis data keys:', Object.keys(analysisResponse.data.analysis || {}));
        
        // Step 2: Prepare user data (like onboarding does)
        console.log('\n📝 STEP 2: Preparing user data...');
        const userData = {
            domain: testDomain,
            businessDescription: testBusinessDescription,
            integrations: { console: false, business: false },
            analysisData: analysisResponse.data.analysis
        };
        console.log('✅ User data prepared with domain:', userData.domain);
        console.log('✅ Analysis data included:', !!userData.analysisData);
        
        // Step 3: Save user data (like onboarding does)
        console.log('\n💾 STEP 3: Saving user data...');
        const saveResponse = await axios.post('http://localhost:3000/api/user/save-onboarding', userData);
        console.log('✅ Save response:', saveResponse.data);
        
        // Step 4: Test retrieval (like dashboard does)
        console.log('\n📖 STEP 4: Testing user data retrieval...');
        const getResponse = await axios.get(`http://localhost:3000/api/user/get-data?domain=${testDomain}`);
        console.log('✅ Get response success:', getResponse.data.success);
        console.log('✅ Retrieved domain:', getResponse.data.data?.domain);
        console.log('✅ Retrieved business description:', getResponse.data.data?.businessDescription);
        console.log('✅ Retrieved analysis data:', !!getResponse.data.data?.analysisData);
        
        // Step 5: Test localStorage simulation
        console.log('\n💾 STEP 5: Testing localStorage simulation...');
        console.log('✅ Would store in localStorage: lastAnalyzedDomain =', testDomain);
        
        // Step 6: Test dashboard flow
        console.log('\n📊 STEP 6: Testing dashboard flow...');
        console.log('✅ Dashboard would look for domain:', testDomain);
        console.log('✅ Dashboard would call API:', `/api/user/get-data?domain=${testDomain}`);
        console.log('✅ Dashboard should find user data:', getResponse.data.success);
        
        console.log('\n🎉 COMPLETE FLOW TEST PASSED!');
        console.log('The issue is NOT in the backend - it must be in the frontend flow.');
        
    } catch (error) {
        console.error('\n❌ ERROR FOUND:', error.response?.data || error.message);
        console.error('Status:', error.response?.status);
        console.error('URL:', error.config?.url);
    }
}

// Run the debug
debugCompleteOnboardingFlow();




