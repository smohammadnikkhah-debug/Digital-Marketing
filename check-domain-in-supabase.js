const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const supabaseService = require('./services/supabaseService');

async function checkDomainInSupabase() {
    console.log('🔍 Checking Supabase for domain data...\n');
    
    if (!supabaseService.isConfigured) {
        console.error('❌ Supabase not configured');
        return;
    }
    
    // Check what domain data exists for the user's websites
    try {
        const domainToCheck = process.argv[2] || 'shineline.com.au';
        
        console.log(`📊 Checking analysis data for: ${domainToCheck}\n`);
        
        // Get the website record
        const { data: website, error: websiteError } = await supabaseService.supabase
            .from('websites')
            .select('id, domain, customer_id')
            .eq('domain', domainToCheck)
            .single();
        
        if (websiteError || !website) {
            console.error(`❌ No website record found for: ${domainToCheck}`);
            console.error('Error:', websiteError);
            return;
        }
        
        console.log('✅ Website record found:');
        console.log('   ID:', website.id);
        console.log('   Domain:', website.domain);
        console.log('   Customer ID:', website.customer_id);
        console.log('');
        
        // Get the latest analysis
        const { data: analysis, error: analysisError } = await supabaseService.supabase
            .from('seo_analyses')
            .select('id, website_id, analysis_data, created_at')
            .eq('website_id', website.id)
            .order('created_at', { ascending: false })
            .limit(1)
            .single();
        
        if (analysisError || !analysis) {
            console.error(`❌ No analysis found for website ID: ${website.id}`);
            console.error('Error:', analysisError);
            return;
        }
        
        console.log('✅ Latest analysis found:');
        console.log('   Analysis ID:', analysis.id);
        console.log('   Created at:', analysis.created_at);
        console.log('   Stored domain in analysis_data:', analysis.analysis_data?.domain);
        console.log('   Score:', analysis.analysis_data?.score);
        console.log('   Total pages:', analysis.analysis_data?.totalPages);
        console.log('');
        
        if (analysis.analysis_data?.domain !== domainToCheck) {
            console.warn(`⚠️  DOMAIN MISMATCH DETECTED!`);
            console.warn(`   Requested: ${domainToCheck}`);
            console.warn(`   Stored:    ${analysis.analysis_data?.domain}`);
            console.warn(`   This is why the Technical SEO page shows the wrong domain!`);
            console.warn('');
            console.warn(`   Solution: The backend fix should override this, but let's verify...`);
        } else {
            console.log(`✅ Domain matches! The analysis data has the correct domain.`);
        }
        
    } catch (error) {
        console.error('❌ Error:', error);
    }
}

checkDomainInSupabase();



