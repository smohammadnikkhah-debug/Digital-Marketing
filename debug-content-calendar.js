// Debug script to check what content exists
console.log('🔍 Debugging Content Calendar Data');

// Check localStorage
console.log('📱 localStorage data:');
console.log('- lastAnalyzedDomain:', localStorage.getItem('lastAnalyzedDomain'));
console.log('- analysisData:', localStorage.getItem('analysisData'));
console.log('- calendarData:', localStorage.getItem('calendarData'));

// Check if we can fetch from API
async function checkAPI() {
    try {
        const domain = localStorage.getItem('lastAnalyzedDomain') || 'mozarex.com';
        console.log('🌐 Testing API endpoints for domain:', domain);
        
        // Test month endpoint
        const year = new Date().getFullYear();
        const month = new Date().getMonth() + 1;
        console.log(`📅 Testing month endpoint: /api/content-calendar/${domain}/month/${year}/${month}`);
        
        const response = await fetch(`/api/content-calendar/${domain}/month/${year}/${month}`);
        const result = await response.json();
        console.log('📊 Month API response:', result);
        
        // Test specific date (September 18th)
        const testDate = '2024-09-18';
        console.log(`📅 Testing date endpoint: /api/content-calendar/${domain}/${testDate}`);
        
        const dateResponse = await fetch(`/api/content-calendar/${domain}/${testDate}`);
        const dateResult = await dateResponse.json();
        console.log('📊 Date API response:', dateResult);
        
        // Test check needs endpoint
        console.log('🔍 Testing check needs endpoint');
        const needsResponse = await fetch('/api/content-calendar/check-needs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ domain: domain })
        });
        const needsResult = await needsResponse.json();
        console.log('📊 Check needs response:', needsResult);
        
    } catch (error) {
        console.error('❌ API test error:', error);
    }
}

checkAPI();
