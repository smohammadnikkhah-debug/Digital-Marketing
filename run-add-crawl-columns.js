/**
 * Add crawl task tracking columns to websites table
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const fs = require('fs');
const supabaseService = require('./services/supabaseService');

async function addCrawlColumns() {
  console.log('🔧 Adding crawl task tracking columns to websites table...\n');
  
  if (!supabaseService.isConfigured) {
    console.error('❌ Supabase not configured');
    process.exit(1);
  }
  
  try {
    // Read the SQL file
    const sql = fs.readFileSync('./add-crawl-task-columns.sql', 'utf8');
    
    console.log('📄 SQL to execute:');
    console.log(sql);
    console.log('\n');
    
    // Execute the SQL using Supabase's RPC or direct query
    // Note: Supabase JS client doesn't support ALTER TABLE directly
    // You need to run this SQL in the Supabase SQL Editor
    
    console.log('⚠️  IMPORTANT: You need to run this SQL in your Supabase SQL Editor');
    console.log('📍 Go to: https://supabase.com/dashboard/project/[your-project]/editor');
    console.log('\n');
    
    // Try to verify if columns exist
    const { data, error } = await supabaseService.supabase
      .from('websites')
      .select('id, analysis_task_id, analysis_status, analysis_started_at, analysis_completed_at')
      .limit(1);
    
    if (error) {
      console.log('❌ Columns do NOT exist yet. Error:', error.message);
      console.log('\n📋 Copy the SQL above and run it in Supabase SQL Editor\n');
    } else {
      console.log('✅ Columns already exist!');
      console.log('Sample data:', data);
    }
    
  } catch (error) {
    console.error('❌ Error:', error);
  }
}

addCrawlColumns().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

