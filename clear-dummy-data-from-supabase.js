/**
 * Clear ALL cached analysis data from Supabase
 * This will force fresh DataForSEO API calls for all domains
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const { createClient } = require('@supabase/supabase-js');

async function clearAllCachedData() {
  console.log('🗑️ Clearing all cached analysis data from Supabase...\n');
  
  // Initialize Supabase client
  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  
  if (!supabaseUrl || !supabaseKey) {
    console.error('❌ Supabase credentials not found in environment');
    return;
  }
  
  const supabase = createClient(supabaseUrl, supabaseKey);
  
  try {
    // Get count of cached analyses
    const { count: totalCount, error: countError } = await supabase
      .from('seo_analyses')
      .select('*', { count: 'exact', head: true });
    
    if (countError) {
      console.error('❌ Error counting analyses:', countError);
      return;
    }
    
    console.log(`📊 Found ${totalCount} cached analyses`);
    
    if (totalCount === 0) {
      console.log('✅ No cached data to clear');
      return;
    }
    
    // Get all cached data to show what's being deleted
    const { data: analyses, error: fetchError } = await supabase
      .from('seo_analyses')
      .select(`
        id,
        website_id,
        created_at,
        analysis_type,
        websites (domain)
      `)
      .order('created_at', { ascending: false });
    
    if (!fetchError && analyses) {
      console.log('\n📋 Cached analyses to be deleted:');
      analyses.forEach((analysis, index) => {
        console.log(`   ${index + 1}. Domain: ${analysis.websites?.domain || 'Unknown'}`);
        console.log(`      Type: ${analysis.analysis_type}`);
        console.log(`      Created: ${new Date(analysis.created_at).toLocaleString()}`);
      });
    }
    
    console.log('\n🗑️ Deleting all cached analyses...');
    
    // Delete ALL cached analysis data
    const { error: deleteError } = await supabase
      .from('seo_analyses')
      .delete()
      .neq('id', '00000000-0000-0000-0000-000000000000'); // Delete all (using a condition that matches everything)
    
    if (deleteError) {
      console.error('❌ Error deleting cached analyses:', deleteError);
      return;
    }
    
    console.log('✅ Successfully cleared all cached analysis data!');
    console.log('\n📝 Next steps:');
    console.log('   1. Visit your Technical SEO page');
    console.log('   2. It will fetch fresh data from DataForSEO');
    console.log('   3. For mozarex.com, you should see "No data available" (expected)');
    console.log('   4. Test with semrush.com to see real data');
    
  } catch (error) {
    console.error('❌ Unexpected error:', error);
  }
}

// Run the script
clearAllCachedData().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

