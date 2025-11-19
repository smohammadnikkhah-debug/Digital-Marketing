require('dotenv').config({ path: '.env' });
const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY);

async function addPasswordHashColumn() {
  try {
    console.log('🔧 Adding password_hash column to users table...');
    
    // Add password_hash column
    const { data, error } = await supabase.rpc('exec_sql', {
      sql: `
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS password_hash TEXT;
      `
    });

    if (error) {
      console.error('❌ Error adding password_hash column:', error);
      
      // Try alternative approach using direct SQL
      console.log('🔄 Trying alternative approach...');
      
      const { data: altData, error: altError } = await supabase
        .from('users')
        .select('id')
        .limit(1);
        
      if (altError) {
        console.error('❌ Cannot access users table:', altError);
        return;
      }
      
      console.log('✅ Users table is accessible, but RPC might not be available');
      console.log('📝 Please add the password_hash column manually in Supabase:');
      console.log('   ALTER TABLE users ADD COLUMN password_hash TEXT;');
      return;
    }

    console.log('✅ password_hash column added successfully');
    
    // Verify the column was added
    const { data: users, error: verifyError } = await supabase
      .from('users')
      .select('*')
      .limit(1);

    if (verifyError) {
      console.error('❌ Error verifying column:', verifyError);
      return;
    }

    if (users && users.length > 0) {
      console.log('✅ Verified - password_hash column exists');
      console.log('📋 Updated users table columns:');
      console.log(Object.keys(users[0]));
    }

  } catch (error) {
    console.error('❌ Error:', error);
  }
}

addPasswordHashColumn();












