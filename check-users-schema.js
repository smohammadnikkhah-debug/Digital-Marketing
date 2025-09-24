require('dotenv').config({ path: '.env' });
const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY);

async function checkUsersSchema() {
  try {
    console.log('🔍 Checking users table schema...');
    
    // Get a sample user to see the columns
    const { data: users, error } = await supabase
      .from('users')
      .select('*')
      .limit(1);

    if (error) {
      console.error('❌ Error fetching users:', error);
      return;
    }

    if (users && users.length > 0) {
      console.log('✅ Users table columns:');
      console.log(Object.keys(users[0]));
      
      // Check if password_hash exists
      if (users[0].password_hash) {
        console.log('✅ password_hash column exists');
      } else {
        console.log('❌ password_hash column does not exist');
        console.log('📝 Need to add password_hash column to users table');
      }
    } else {
      console.log('ℹ️ No users found in database');
    }

  } catch (error) {
    console.error('❌ Error:', error);
  }
}

checkUsersSchema();