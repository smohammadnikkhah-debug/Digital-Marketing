/**
 * Check DataForSEO task status directly
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const axios = require('axios');

async function checkTaskDirectly() {
  const username = process.env.DATAFORSEO_USERNAME;
  const password = process.env.DATAFORSEO_PASSWORD;
  const taskId = '10090558-1147-0216-0000-33b819001faa';
  
  if (!username || !password) {
    console.error('❌ DataForSEO credentials not found');
    return;
  }
  
  const authHeader = Buffer.from(`${username}:${password}`).toString('base64');
  const baseUrl = 'https://api.dataforseo.com/v3';
  
  console.log('🔍 Checking task status directly with DataForSEO...\n');
  console.log(`Task ID: ${taskId}\n`);
  
  try {
    // Check tasks_ready
    console.log('1️⃣ Checking /on_page/tasks_ready endpoint...');
    const readyResponse = await axios.post(`${baseUrl}/on_page/tasks_ready`, [], {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Basic ${authHeader}`
      }
    });
    
    console.log('Response:', JSON.stringify(readyResponse.data, null, 2));
    
    if (readyResponse.data.tasks && readyResponse.data.tasks[0] && readyResponse.data.tasks[0].result) {
      const tasks = readyResponse.data.tasks[0].result;
      console.log(`\n✅ Found ${tasks.length} ready tasks:`);
      tasks.forEach(task => {
        console.log(`  - Task ID: ${task.id}`);
        console.log(`    Pages: ${task.result_count}`);
        console.log(`    Status: ${task.status_message}`);
        
        if (task.id === taskId) {
          console.log('\n🎉 OUR TASK IS READY!');
        }
      });
    } else {
      console.log('⚠️ No ready tasks found');
    }
    
  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
  
  console.log('\n');
  
  // Try to get task results directly
  try {
    console.log('2️⃣ Trying to get results with /on_page/pages endpoint...');
    const pagesResponse = await axios.post(`${baseUrl}/on_page/pages`, [{
      id: taskId
    }], {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Basic ${authHeader}`
      }
    });
    
    console.log('Response:', JSON.stringify(pagesResponse.data, null, 2));
    
    if (pagesResponse.data.tasks && pagesResponse.data.tasks[0]) {
      const task = pagesResponse.data.tasks[0];
      console.log(`\nTask Status Code: ${task.status_code}`);
      console.log(`Task Status Message: ${task.status_message}`);
      
      if (task.result && task.result.length > 0) {
        console.log(`\n✅ Task HAS RESULTS! ${task.result.length} pages found`);
        console.log('\nFirst 3 pages:');
        task.result.slice(0, 3).forEach((page, i) => {
          console.log(`  ${i + 1}. ${page.url} (Score: ${page.onpage_score || 'N/A'})`);
        });
      } else {
        console.log('\n⚠️ Task exists but has no results yet');
      }
    }
  } catch (error) {
    console.error('❌ Error getting pages:', error.response?.data || error.message);
  }
  
  console.log('\n');
  
  // Check summary
  try {
    console.log('3️⃣ Trying to get summary with /on_page/summary endpoint...');
    const summaryResponse = await axios.post(`${baseUrl}/on_page/summary`, [{
      id: taskId
    }], {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Basic ${authHeader}`
      }
    });
    
    console.log('Response:', JSON.stringify(summaryResponse.data, null, 2));
  } catch (error) {
    console.error('❌ Error getting summary:', error.response?.data || error.message);
  }
}

checkTaskDirectly().then(() => {
  console.log('\n✨ Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

