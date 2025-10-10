const DataForSEOService = require('./services/dataforseoEnvironmentService');

async function testTrafficAPIs() {
    console.log('🧪 Testing DataForSEO Traffic APIs\n');
    
    const service = new DataForSEOService();
    const domain = 'shineline.com.au';
    
    if (!service.username || !service.password) {
        console.error('❌ DataForSEO credentials not configured');
        return;
    }
    
    console.log('✅ DataForSEO configured:', {
        username: service.username,
        environment: service.environment,
        baseUrl: service.baseUrl
    });
    
    console.log('\n' + '='.repeat(60));
    console.log('TEST 1: Traffic Trends (Last 3 Months)');
    console.log('='.repeat(60));
    
    try {
        const trends = await service.getTrafficTrends(`https://${domain}`, 3);
        
        if (trends) {
            console.log('✅ Traffic Trends Result:');
            console.log(JSON.stringify(trends, null, 2));
            console.log('\nData Summary:');
            console.log('   Months:', trends.months);
            console.log('   Organic:', trends.organic);
            console.log('   Paid:', trends.paid);
            console.log('   Social:', trends.social);
        } else {
            console.log('❌ Traffic Trends returned null');
            console.log('   This might mean:');
            console.log('   - Domain not in DataForSEO database yet');
            console.log('   - Insufficient Labs credits');
            console.log('   - API returned error');
        }
    } catch (error) {
        console.error('❌ Error testing traffic trends:', error.message);
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('TEST 2: Traffic by Country (Top 5)');
    console.log('='.repeat(60));
    
    try {
        const countries = await service.getTrafficByCountry(`https://${domain}`);
        
        if (countries && countries.length > 0) {
            console.log('✅ Country Traffic Result:');
            console.log(JSON.stringify(countries, null, 2));
            console.log('\nCountries Summary:');
            countries.forEach((c, i) => {
                console.log(`   ${i + 1}. ${c.name} (${c.code}): ${c.traffic.toLocaleString()} visits/month`);
            });
        } else {
            console.log('❌ Country Traffic returned null or empty');
            console.log('   This might mean:');
            console.log('   - Domain not in DataForSEO database yet');
            console.log('   - Insufficient Labs credits');
            console.log('   - API returned error');
        }
    } catch (error) {
        console.error('❌ Error testing country traffic:', error.message);
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('TEST 3: Domain Rank Overview (Traffic Metrics)');
    console.log('='.repeat(60));
    
    try {
        const traffic = await service.getTrafficAnalysis(`https://${domain}`);
        
        if (traffic) {
            console.log('✅ Traffic Analysis Result:');
            console.log(JSON.stringify(traffic, null, 2));
            console.log('\nTraffic Summary:');
            console.log('   Organic ETV:', traffic.organic?.etv || 0);
            console.log('   Paid ETV:', traffic.paid?.etv || 0);
            console.log('   Total Estimated Traffic:', traffic.estimatedTraffic || 0);
        } else {
            console.log('❌ Traffic Analysis returned null');
            console.log('   This might mean:');
            console.log('   - Domain not in DataForSEO database yet');
            console.log('   - Insufficient Labs credits');
            console.log('   - API returned error');
        }
    } catch (error) {
        console.error('❌ Error testing traffic analysis:', error.message);
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('TESTING COMPLETE');
    console.log('='.repeat(60));
}

testTrafficAPIs().catch(console.error);

