const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

async function checkSubscriptionsTable() {
    try {
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_ANON_KEY
        );

        console.log('🔍 Checking subscriptions table schema...');

        // Try to get table info by attempting a simple query
        const { data, error } = await supabase
            .from('subscriptions')
            .select('*')
            .limit(1);

        if (error) {
            console.log('❌ Error querying subscriptions table:', error.message);
            
            if (error.code === 'PGRST204') {
                console.log('📋 The table exists but has different column names');
                console.log('📋 Expected columns: stripe_customer_id, stripe_subscription_id, etc.');
                console.log('📋 Actual table might have: customer_id, subscription_id, etc.');
            }
        } else {
            console.log('✅ Subscriptions table query successful');
            console.log('📋 Table columns:', data.length > 0 ? Object.keys(data[0]) : 'No data to inspect');
        }

        // Let's try to see what columns exist by attempting different column names
        console.log('\n🔍 Testing different column names...');
        
        const testColumns = [
            'customer_id',
            'stripe_customer_id', 
            'subscription_id',
            'stripe_subscription_id',
            'user_id',
            'plan_name',
            'status'
        ];

        for (const column of testColumns) {
            try {
                const { error: colError } = await supabase
                    .from('subscriptions')
                    .select(column)
                    .limit(1);
                
                if (!colError) {
                    console.log(`✅ Column '${column}' exists`);
                } else {
                    console.log(`❌ Column '${column}' does not exist`);
                }
            } catch (err) {
                console.log(`❌ Column '${column}' test failed:`, err.message);
            }
        }

    } catch (error) {
        console.error('❌ Unexpected error:', error);
    }
}

checkSubscriptionsTable();









