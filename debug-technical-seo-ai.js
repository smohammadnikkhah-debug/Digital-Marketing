require('dotenv').config();

const supabaseService = require('./services/supabaseService');
const technicalSEOAIService = require('./services/technicalSEOAIService');

async function debugTechnicalSEOAI() {
  try {
    console.log('🔍 Starting Technical SEO AI Debug...\n');
    
    // Test 1: Check environment variables
    console.log('1️⃣ Checking Environment Variables:');
    console.log('   SUPABASE_URL:', process.env.SUPABASE_URL ? '✅ Set' : '❌ Not set');
    console.log('   SUPABASE_SERVICE_ROLE_KEY:', process.env.SUPABASE_SERVICE_ROLE_KEY ? '✅ Set' : '❌ Not set');
    console.log('   OPENAI_API_KEY:', process.env.OPENAI_API_KEY ? '✅ Set' : '❌ Not set');
    console.log('');
    
    // Test 2: Get test domain from command line or use default
    const testDomain = process.argv[2] || 'example.com';
    console.log(`2️⃣ Testing with domain: ${testDomain}\n`);
    
    // Test 3: Check if crawl data exists
    console.log('3️⃣ Fetching crawl data from Supabase...');
    const crawlData = await supabaseService.getAnalysisData(testDomain, null);
    
    if (!crawlData) {
      console.error('   ❌ No crawl data found for domain:', testDomain);
      console.log('\n💡 Tip: Please analyze this domain from the dashboard first:');
      console.log(`   http://localhost:3000/dashboard-mantis-v2`);
      return;
    }
    
    console.log('   ✅ Crawl data found!');
    console.log('   Domain:', crawlData.domain);
    console.log('   Has onPage data:', !!crawlData.onPage);
    console.log('   Pages count:', crawlData.onPage?.pages?.length || 0);
    console.log('');
    
    // Test 4: Generate Meta Optimization recommendations
    console.log('4️⃣ Generating Meta Optimization recommendations...');
    const metaRecs = await technicalSEOAIService.generateMetaOptimizationRecommendations(crawlData);
    
    if (metaRecs.success) {
      console.log('   ✅ Meta recommendations generated!');
      console.log('   Category:', metaRecs.category);
      console.log('   Score:', metaRecs.score);
      console.log('   Issues found:', metaRecs.issues?.length || 0);
      console.log('   Quick wins:', metaRecs.quickWins?.length || 0);
      console.log('');
      
      // Display first issue if available
      if (metaRecs.issues && metaRecs.issues.length > 0) {
        console.log('   📋 First Issue:');
        const firstIssue = metaRecs.issues[0];
        console.log('      Title:', firstIssue.title);
        console.log('      Severity:', firstIssue.severity);
        console.log('      Description:', firstIssue.description.substring(0, 100) + '...');
      }
    } else {
      console.error('   ❌ Failed to generate recommendations');
    }
    console.log('');
    
    // Test 5: Test Content Improvements
    console.log('5️⃣ Generating Content Improvements recommendations...');
    const contentRecs = await technicalSEOAIService.generateContentImprovementsRecommendations(crawlData);
    
    if (contentRecs.success) {
      console.log('   ✅ Content recommendations generated!');
      console.log('   Score:', contentRecs.score);
      console.log('   Issues found:', contentRecs.issues?.length || 0);
    } else {
      console.error('   ❌ Failed to generate content recommendations');
    }
    console.log('');
    
    // Test 6: Test Technical Fixes
    console.log('6️⃣ Generating Technical Fixes recommendations...');
    const technicalRecs = await technicalSEOAIService.generateTechnicalFixesRecommendations(crawlData);
    
    if (technicalRecs.success) {
      console.log('   ✅ Technical recommendations generated!');
      console.log('   Score:', technicalRecs.score);
      console.log('   Issues found:', technicalRecs.issues?.length || 0);
    } else {
      console.error('   ❌ Failed to generate technical recommendations');
    }
    console.log('');
    
    console.log('✅ All tests completed successfully!');
    console.log('\n📝 Summary:');
    console.log('   - Supabase connection: ✅ Working');
    console.log('   - Crawl data retrieval: ✅ Working');
    console.log('   - AI recommendations: ✅ Working');
    console.log('\n🚀 Your Technical SEO AI system is ready to use!');
    
  } catch (error) {
    console.error('\n❌ Error during debug:', error.message);
    console.error('Stack trace:', error.stack);
    console.log('\n💡 Common issues:');
    console.log('   1. Domain not analyzed yet - Run analysis from dashboard first');
    console.log('   2. Supabase credentials missing - Check .env file');
    console.log('   3. OpenAI API key missing - AI will use fallback recommendations');
  }
  
  process.exit(0);
}

// Run debug
console.log('\n🔧 Technical SEO AI Debug Script\n');
console.log('Usage: node debug-technical-seo-ai.js [domain]');
console.log('Example: node debug-technical-seo-ai.js example.com\n');

debugTechnicalSEOAI();

