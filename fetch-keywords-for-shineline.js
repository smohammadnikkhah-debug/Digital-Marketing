/**
 * Fetch keywords and competitors for shineline.com.au and update analysis
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const supabaseService = require('./services/supabaseService');
const dataforseoService = require('./services/dataforseoEnvironmentService');

async function fetchKeywordsForShineline() {
  const domain = 'shineline.com.au';
  const websiteId = 'c1ac68de-9e4b-4cf1-9c6e-551a7261c29d';
  
  console.log('🔑 Fetching keywords and competitors for:', domain);
  
  try {
    // Get existing analysis
    const existingAnalysis = await supabaseService.getAnalysisData(domain, null);
    
    if (!existingAnalysis) {
      console.error('❌ No existing analysis found');
      return;
    }
    
    console.log('✅ Found existing analysis:', {
      score: existingAnalysis.score,
      totalPages: existingAnalysis.totalPages,
      hasKeywords: !!existingAnalysis.keywords,
      hasCompetitors: !!existingAnalysis.competitors
    });
    
    // Fetch keywords and competitors
    console.log('\n🔑 Fetching fresh keywords and competitors from DataForSEO...');
    
    const [keywordsResult, competitorsResult] = await Promise.allSettled([
      dataforseoService.getKeywordsAnalysis(`https://${domain}`),
      dataforseoService.getCompetitorAnalysis(`https://${domain}`)
    ]);
    
    console.log('\n📊 Keywords Result:', {
      status: keywordsResult.status,
      hasValue: !!keywordsResult.value,
      totalKeywords: keywordsResult.value?.totalKeywords || 0
    });
    
    console.log('📊 Competitors Result:', {
      status: competitorsResult.status,
      hasValue: !!competitorsResult.value,
      totalCompetitors: competitorsResult.value?.totalCompetitors || 0
    });
    
    // Update analysis with new data
    const updatedAnalysis = {
      ...existingAnalysis,
      keywords: keywordsResult.status === 'fulfilled' && keywordsResult.value ? keywordsResult.value : existingAnalysis.keywords,
      competitors: competitorsResult.status === 'fulfilled' && competitorsResult.value ? competitorsResult.value : existingAnalysis.competitors
    };
    
    console.log('\n💾 Storing updated analysis with keywords and competitors...');
    await supabaseService.storeAnalysis(websiteId, updatedAnalysis, 'full_crawl');
    
    console.log('✅ SUCCESS! Analysis updated with:');
    console.log('   Keywords:', updatedAnalysis.keywords?.totalKeywords || 0);
    console.log('   Competitors:', updatedAnalysis.competitors?.totalCompetitors || 0);
    console.log('\n🔄 Refresh your dashboard to see the keywords and competitors!');
    
  } catch (error) {
    console.error('❌ Error:', error);
  }
}

fetchKeywordsForShineline().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

