/**
 * Check Supabase database for sydcleaningservices.com.au analysis
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const { createClient } = require('@supabase/supabase-js');

async function checkAnalysisData() {
  console.log('🔍 Checking Supabase for sydcleaningservices.com.au analysis...\n');
  
  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  
  if (!supabaseUrl || !supabaseKey) {
    console.error('❌ Supabase credentials not found');
    return;
  }
  
  const supabase = createClient(supabaseUrl, supabaseKey);
  
  try {
    // Check 1: Find the website record
    console.log('📊 Step 1: Looking for website record...');
    const { data: websites, error: websiteError } = await supabase
      .from('websites')
      .select('*')
      .eq('domain', 'sydcleaningservices.com.au');
    
    if (websiteError) {
      console.error('❌ Error finding website:', websiteError);
      return;
    }
    
    if (!websites || websites.length === 0) {
      console.log('❌ No website record found for sydcleaningservices.com.au');
      console.log('\n💡 This means the website was not created in the database during onboarding');
      return;
    }
    
    console.log('✅ Found website record:');
    websites.forEach((website, index) => {
      console.log(`\n   Website #${index + 1}:`);
      console.log('   ID:', website.id);
      console.log('   Domain:', website.domain);
      console.log('   Customer ID:', website.customer_id);
      console.log('   Created:', new Date(website.created_at).toLocaleString());
      console.log('   Updated:', new Date(website.updated_at).toLocaleString());
    });
    
    // Check 2: Find analysis records for each website
    console.log('\n📊 Step 2: Looking for analysis records...');
    
    for (const website of websites) {
      const { data: analyses, error: analysisError } = await supabase
        .from('seo_analyses')
        .select('*')
        .eq('website_id', website.id)
        .order('created_at', { ascending: false });
      
      if (analysisError) {
        console.error('❌ Error finding analyses for website ID', website.id, ':', analysisError);
        continue;
      }
      
      if (!analyses || analyses.length === 0) {
        console.log(`\n❌ No analysis records found for website ID: ${website.id}`);
        console.log('   This means the analysis was NOT stored in Supabase');
        console.log('\n💡 Possible reasons:');
        console.log('   1. Analysis completed but storeAnalysis() failed');
        console.log('   2. Error during storage process');
        console.log('   3. Analysis API call succeeded but wasn\'t saved');
      } else {
        console.log(`\n✅ Found ${analyses.length} analysis record(s) for website ID: ${website.id}`);
        
        analyses.forEach((analysis, index) => {
          console.log(`\n   Analysis #${index + 1}:`);
          console.log('   ID:', analysis.id);
          console.log('   Type:', analysis.analysis_type);
          console.log('   Created:', new Date(analysis.created_at).toLocaleString());
          console.log('   Expires:', analysis.expires_at ? new Date(analysis.expires_at).toLocaleString() : 'Never');
          console.log('   Has Data:', !!analysis.analysis_data);
          
          if (analysis.analysis_data) {
            const data = analysis.analysis_data;
            console.log('   Data Summary:');
            console.log('     - Has keywords:', !!data.keywords);
            console.log('     - Keyword count:', data.keywords?.keywords?.length || data.keywords?.totalKeywords || 0);
            console.log('     - Has competitors:', !!data.competitors);
            console.log('     - Has onPage:', !!data.onPage);
            console.log('     - Score:', data.score);
          }
        });
      }
    }
    
    // Check 3: Find keywords records
    console.log('\n📊 Step 3: Looking for keyword records...');
    
    for (const website of websites) {
      const { data: keywords, error: keywordsError } = await supabase
        .from('keywords')
        .select('*')
        .eq('website_id', website.id);
      
      if (keywordsError) {
        console.error('❌ Error finding keywords:', keywordsError);
        continue;
      }
      
      if (!keywords || keywords.length === 0) {
        console.log(`\n❌ No keyword records found for website ID: ${website.id}`);
      } else {
        console.log(`\n✅ Found ${keywords.length} keyword records`);
        console.log('   Sample keywords:', keywords.slice(0, 5).map(k => k.keyword).join(', '));
      }
    }
    
  } catch (error) {
    console.error('❌ Unexpected error:', error);
  }
}

// Run the check
checkAnalysisData().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

