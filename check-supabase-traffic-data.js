const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });

const SupabaseService = require('./services/supabaseService');

async function checkSupabaseTrafficData() {
    console.log('🔍 Checking Supabase for traffic data...\n');
    
    const supabaseService = new SupabaseService();
    
    if (!supabaseService.isConfigured) {
        console.error('❌ Supabase not configured');
        return;
    }
    
    const domain = process.argv[2] || 'shineline.com.au';
    
    console.log(`📊 Checking data for domain: ${domain}\n`);
    
    // Get website record
    const { data: website, error: websiteError } = await supabaseService.supabase
        .from('websites')
        .select('*')
        .eq('domain', domain)
        .single();
    
    if (websiteError || !website) {
        console.error(`❌ Website not found: ${domain}`, websiteError);
        return;
    }
    
    console.log(`✅ Website found:`, {
        id: website.id,
        domain: website.domain,
        created_at: website.created_at
    });
    
    // Get latest analysis
    const { data: analyses, error: analysisError } = await supabaseService.supabase
        .from('seo_analyses')
        .select('*')
        .eq('website_id', website.id)
        .gt('expires_at', new Date().toISOString())
        .order('created_at', { ascending: false })
        .limit(1);
    
    if (analysisError) {
        console.error('❌ Error fetching analyses:', analysisError);
        return;
    }
    
    if (!analyses || analyses.length === 0) {
        console.log('❌ No valid analysis found (cache expired or never created)');
        return;
    }
    
    const analysis = analyses[0];
    const data = analysis.analysis_data;
    
    console.log('\n' + '='.repeat(60));
    console.log('ANALYSIS DATA STRUCTURE:');
    console.log('='.repeat(60));
    
    console.log('\n✅ Top-level keys:', Object.keys(data));
    
    console.log('\n📊 Data Summary:');
    console.log('   Score:', data.score || 'N/A');
    console.log('   Total Pages:', data.totalPages || 'N/A');
    console.log('   Total Issues:', data.totalIssues || 'N/A');
    
    console.log('\n🔑 Keywords:');
    if (data.keywords) {
        console.log('   Has keywords:', !!data.keywords);
        console.log('   Total Keywords:', data.keywords.totalKeywords || 0);
        console.log('   Keywords Array Length:', data.keywords.keywords?.length || 0);
        if (data.keywords.keywords && data.keywords.keywords.length > 0) {
            console.log('   First Keyword:', data.keywords.keywords[0]);
        }
    } else {
        console.log('   ❌ No keywords data');
    }
    
    console.log('\n🏆 Competitors:');
    if (data.competitors) {
        console.log('   Has competitors:', !!data.competitors);
        console.log('   Total Competitors:', data.competitors.totalCompetitors || 0);
        console.log('   Competitors Array Length:', data.competitors.competitors?.length || 0);
        if (data.competitors.competitors && data.competitors.competitors.length > 0) {
            console.log('   First Competitor:', data.competitors.competitors[0]);
        }
    } else {
        console.log('   ❌ No competitors data');
    }
    
    console.log('\n📈 Traffic Trends:');
    if (data.trafficTrends) {
        console.log('   Has trafficTrends:', !!data.trafficTrends);
        console.log('   Months:', data.trafficTrends.months);
        console.log('   Organic:', data.trafficTrends.organic);
        console.log('   Paid:', data.trafficTrends.paid);
        console.log('   Social:', data.trafficTrends.social);
    } else {
        console.log('   ❌ No trafficTrends data');
    }
    
    console.log('\n🌍 Traffic by Country:');
    if (data.trafficByCountry) {
        console.log('   Has trafficByCountry:', !!data.trafficByCountry);
        console.log('   Countries Count:', data.trafficByCountry.length || 0);
        if (data.trafficByCountry.length > 0) {
            console.log('   Countries:');
            data.trafficByCountry.forEach((c, i) => {
                console.log(`      ${i + 1}. ${c.name} (${c.code}): ${c.traffic} visits`);
            });
        }
    } else {
        console.log('   ❌ No trafficByCountry data');
    }
    
    console.log('\n💾 Cache Info:');
    console.log('   Created:', analysis.created_at);
    console.log('   Expires:', analysis.expires_at);
    console.log('   Cache Valid:', new Date(analysis.expires_at) > new Date());
    
    console.log('\n' + '='.repeat(60));
    console.log('RECOMMENDATION:');
    console.log('='.repeat(60));
    
    const missingData = [];
    if (!data.keywords || data.keywords.totalKeywords === 0) missingData.push('Keywords');
    if (!data.competitors || data.competitors.totalCompetitors === 0) missingData.push('Competitors');
    if (!data.trafficTrends) missingData.push('Traffic Trends');
    if (!data.trafficByCountry || data.trafficByCountry.length === 0) missingData.push('Country Data');
    
    if (missingData.length > 0) {
        console.log(`\n❌ Missing data: ${missingData.join(', ')}`);
        console.log('\n🔧 SOLUTION:');
        console.log('   1. Click "Full Crawl" button in dashboard');
        console.log('   2. Wait 15-30 seconds for smart fetch');
        console.log('   3. Data will be added to Supabase');
        console.log('   4. Cached for 7 days - no more API calls needed!');
    } else {
        console.log('\n✅ All data present in Supabase!');
        console.log('   Dashboard should load from cache without API calls.');
    }
}

checkSupabaseTrafficData().catch(console.error);

