/**
 * Manually update a completed task status and retrieve results
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const onPageTaskService = require('./services/dataforseoOnPageTaskService');
const supabaseService = require('./services/supabaseService');

async function updateCompletedTask() {
  const taskId = '10090908-1147-0216-0000-e37e8549e027';
  const websiteId = 'c1ac68de-9e4b-4cf1-9c6e-551a7261c29d';
  
  console.log('🔄 Manually updating completed task...\n');
  console.log(`Task ID: ${taskId}`);
  console.log(`Website ID: ${websiteId}\n`);
  
  try {
    // Check if task is complete
    const status = await onPageTaskService.checkTaskStatus(taskId);
    
    if (!status) {
      console.error('❌ Could not get task status');
      return;
    }
    
    console.log('📊 Task Status:', status);
    
    if (status.isComplete) {
      console.log('\n✅ Task is complete! Retrieving results...\n');
      
      // Get results
      const results = await onPageTaskService.getTaskResults(taskId, 100);
      
      if (results) {
        console.log('✅ Results retrieved:');
        console.log(`   Total Pages: ${results.totalPages}`);
        console.log(`   Healthy Pages: ${results.healthyPages}`);
        console.log(`   Pages with Issues: ${results.pagesWithIssues}`);
        console.log(`   Average Score: ${results.averageScore}`);
        console.log(`   Total Issues: ${results.totalIssues}`);
        
        // Store in Supabase
        console.log('\n💾 Storing analysis in Supabase...');
        await supabaseService.storeAnalysis(websiteId, results, 'full_crawl');
        
        // Update task status
        console.log('💾 Updating task status to completed...');
        await supabaseService.updateAnalysisTaskStatus(websiteId, taskId, 'completed');
        
        console.log('\n✅ SUCCESS! Analysis stored and status updated');
        console.log('🔄 Refresh your dashboard to see the results!\n');
      } else {
        console.error('❌ Failed to retrieve results');
      }
    } else {
      console.log('\n⏳ Task is still in progress');
      console.log(`   Pages found so far: ${status.pagesFound || 0}`);
    }
    
  } catch (error) {
    console.error('❌ Error:', error);
  }
}

updateCompletedTask().then(() => {
  console.log('✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

