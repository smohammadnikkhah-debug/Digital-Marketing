require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY);

async function addCompanyColumn() {
    try {
        console.log('🔧 Adding company column to users table...');
        
        // Add the company column
        const { data, error } = await supabase.rpc('exec_sql', {
            sql: 'ALTER TABLE public.users ADD COLUMN company TEXT;'
        });
        
        if (error) {
            console.log('❌ Error adding company column:', error);
            
            // If the column already exists, that's okay
            if (error.message && error.message.includes('already exists')) {
                console.log('✅ Company column already exists');
                return;
            }
            
            // Try alternative approach - direct SQL execution
            console.log('🔄 Trying alternative approach...');
            const { data: altData, error: altError } = await supabase
                .from('users')
                .select('company')
                .limit(1);
                
            if (altError && altError.message.includes('company')) {
                console.log('❌ Company column does not exist and cannot be added via RPC');
                console.log('📝 Please run this SQL manually in your Supabase dashboard:');
                console.log('ALTER TABLE public.users ADD COLUMN company TEXT;');
                return;
            } else {
                console.log('✅ Company column exists or was added successfully');
            }
        } else {
            console.log('✅ Company column added successfully');
        }
        
        // Verify the column was added
        console.log('🔍 Verifying company column...');
        const { data: testData, error: testError } = await supabase
            .from('users')
            .select('id, company')
            .limit(1);
            
        if (testError) {
            console.log('❌ Error verifying company column:', testError);
        } else {
            console.log('✅ Company column verified successfully');
            console.log('Sample data:', testData);
        }
        
    } catch (error) {
        console.error('❌ Error:', error);
    }
}

addCompanyColumn();












