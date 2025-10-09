/**
 * Debug what data Mantis v2 is receiving
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const supabaseService = require('./services/supabaseService');

async function debugMantisData() {
  console.log('🔍 Debugging Mantis v2 data for shineline.com.au\n');
  
  const domain = 'shineline.com.au';
  
  try {
    // Get the analysis data the same way the API does
    const { data: website, error } = await supabaseService.supabase
      .from('websites')
      .select('id, domain')
      .eq('domain', domain)
      .single();
    
    if (error || !website) {
      console.error('❌ Website not found:', error);
      return;
    }
    
    console.log('✅ Website found:', website);
    
    // Get analysis data
    const analysisData = await supabaseService.getAnalysisData(domain, null);
    
    console.log('\n📊 Analysis Data Structure:');
    console.log(JSON.stringify(analysisData, null, 2));
    
    console.log('\n📋 Key Fields:');
    console.log('  score:', analysisData?.score);
    console.log('  averageScore:', analysisData?.averageScore);
    console.log('  totalPages:', analysisData?.totalPages);
    console.log('  totalIssues:', analysisData?.totalIssues);
    console.log('  healthyPages:', analysisData?.healthyPages);
    console.log('  pagesWithIssues:', analysisData?.pagesWithIssues);
    console.log('  recommendations.length:', analysisData?.recommendations?.length);
    console.log('  keywords:', analysisData?.keywords);
    console.log('  competitors:', analysisData?.competitors);
    console.log('  onPage:', analysisData?.onPage ? 'Present' : 'Missing');
    console.log('  pages.length:', analysisData?.pages?.length);
    
  } catch (error) {
    console.error('❌ Error:', error);
  }
}

debugMantisData().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

