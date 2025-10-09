/**
 * Check the status of the full website crawl task
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const onPageTaskService = require('./services/dataforseoOnPageTaskService');

async function checkTaskStatus() {
  console.log('🔍 Checking OnPage crawl task status...\n');
  
  // Get all ready tasks
  try {
    const response = await onPageTaskService.makeRequest('/on_page/tasks_ready', []);
    
    if (!response || !response.tasks) {
      console.log('❌ No response from tasks_ready endpoint');
      return;
    }
    
    const tasks = response.tasks[0]?.result || [];
    
    if (tasks.length === 0) {
      console.log('ℹ️ No tasks ready yet');
      console.log('\nThis could mean:');
      console.log('  1. Task is still in progress (crawling pages)');
      console.log('  2. Task completed and results were already retrieved');
      console.log('  3. No tasks have been created recently');
      return;
    }
    
    console.log(`✅ Found ${tasks.length} ready task(s):\n`);
    
    tasks.forEach((task, index) => {
      console.log(`Task #${index + 1}:`);
      console.log(`  ID: ${task.id}`);
      console.log(`  Status: ${task.status_message}`);
      console.log(`  Pages Found: ${task.result_count || 0}`);
      console.log(`  Created: ${task.time || 'N/A'}`);
      console.log('');
    });
    
    // If we have a task ID, we can get the results
    if (tasks.length > 0 && tasks[0].id) {
      const taskId = tasks[0].id;
      console.log(`\n📥 Getting results for task: ${taskId}...`);
      
      const results = await onPageTaskService.getTaskResults(taskId, 10);
      
      if (results) {
        console.log(`\n✅ Results Retrieved:`);
        console.log(`  Total Pages: ${results.totalPages}`);
        console.log(`  Healthy Pages: ${results.healthyPages}`);
        console.log(`  Pages with Issues: ${results.pagesWithIssues}`);
        console.log(`  Average Score: ${results.averageScore}`);
        console.log(`  Total Errors: ${results.totalErrors}`);
        console.log(`\n  Sample Pages:`);
        results.pages.slice(0, 5).forEach((page, i) => {
          console.log(`    ${i + 1}. ${page.url} (Score: ${page.onPageScore})`);
        });
      }
    }
    
  } catch (error) {
    console.error('❌ Error checking task status:', error);
  }
}

// Run the check
checkTaskStatus().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

