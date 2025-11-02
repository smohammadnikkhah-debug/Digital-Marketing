const axios = require('axios');

async function debugOnboardingFlow() {
    console.log('🔍 DEBUGGING ONBOARDING FLOW');
    console.log('================================');
    
    const testDomain = 'debug-test.com';
    const testBusinessDescription = 'Test business for debugging';
    
    try {
        // Step 1: Test user data save
        console.log('\n📝 STEP 1: Testing user data save...');
        const saveData = {
            domain: testDomain,
            businessDescription: testBusinessDescription,
            integrations: { console: false, business: false },
            analysisData: { test: 'data' }
        };
        
        const saveResponse = await axios.post('http://localhost:3000/api/user/save-onboarding', saveData);
        console.log('✅ Save response:', saveResponse.data);
        
        // Step 2: Test user data retrieval
        console.log('\n📖 STEP 2: Testing user data retrieval...');
        const getResponse = await axios.get(`http://localhost:3000/api/user/get-data?domain=${testDomain}`);
        console.log('✅ Get response:', getResponse.data);
        
        // Step 3: Test analysis data save
        console.log('\n🔬 STEP 3: Testing analysis data save...');
        const analysisData = {
            domain: testDomain,
            analysis: {
                onPage: { title: 'Test Title', description: 'Test Description' },
                keywords: [{ keyword: 'test', volume: 1000 }],
                competitors: [{ domain: 'competitor.com', rank: 1 }],
                backlinks: [{ domain: 'backlink.com', count: 50 }]
            }
        };
        
        const analysisResponse = await axios.post(`http://localhost:3000/api/supabase/analysis/${testDomain}`, analysisData);
        console.log('✅ Analysis save response:', analysisResponse.data);
        
        // Step 4: Test analysis data retrieval
        console.log('\n📊 STEP 4: Testing analysis data retrieval...');
        const getAnalysisResponse = await axios.get(`http://localhost:3000/api/supabase/analysis/${testDomain}`);
        console.log('✅ Analysis get response:', getAnalysisResponse.data);
        
        // Step 5: Test Supabase status
        console.log('\n🗄️ STEP 5: Testing Supabase connection...');
        const supabaseResponse = await axios.get('http://localhost:3000/api/supabase/status');
        console.log('✅ Supabase status:', supabaseResponse.data);
        
        console.log('\n🎉 ALL TESTS PASSED! The backend is working correctly.');
        
    } catch (error) {
        console.error('\n❌ ERROR FOUND:', error.response?.data || error.message);
        console.error('Status:', error.response?.status);
        console.error('URL:', error.config?.url);
    }
}

// Run the debug
debugOnboardingFlow();







