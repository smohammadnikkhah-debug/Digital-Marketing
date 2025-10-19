const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

async function createSubscriptionsTable() {
    try {
        // Initialize Supabase client
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_ANON_KEY
        );

        console.log('🔧 Creating subscriptions table...');

        // SQL to create the subscriptions table
        const createTableSQL = `
            CREATE TABLE IF NOT EXISTS public.subscriptions (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id TEXT NOT NULL,
                stripe_customer_id TEXT NOT NULL,
                stripe_subscription_id TEXT NOT NULL UNIQUE,
                stripe_price_id TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                billing_cycle TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'yearly')),
                status TEXT NOT NULL DEFAULT 'trialing',
                trial_start TIMESTAMP WITH TIME ZONE,
                trial_end TIMESTAMP WITH TIME ZONE,
                current_period_start TIMESTAMP WITH TIME ZONE,
                current_period_end TIMESTAMP WITH TIME ZONE,
                cancel_at_period_end BOOLEAN DEFAULT FALSE,
                canceled_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        `;

        // Execute the SQL
        const { data, error } = await supabase.rpc('exec_sql', { sql: createTableSQL });
        
        if (error) {
            console.error('❌ Error creating table:', error);
            return;
        }

        console.log('✅ Subscriptions table created successfully!');

        // Create indexes
        const createIndexesSQL = `
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer_id ON public.subscriptions(stripe_customer_id);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription_id ON public.subscriptions(stripe_subscription_id);
            CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON public.subscriptions(status);
        `;

        const { error: indexError } = await supabase.rpc('exec_sql', { sql: createIndexesSQL });
        
        if (indexError) {
            console.error('❌ Error creating indexes:', indexError);
        } else {
            console.log('✅ Indexes created successfully!');
        }

        // Enable RLS
        const enableRLSSQL = `ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;`;
        const { error: rlsError } = await supabase.rpc('exec_sql', { sql: enableRLSSQL });
        
        if (rlsError) {
            console.error('❌ Error enabling RLS:', rlsError);
        } else {
            console.log('✅ RLS enabled successfully!');
        }

        console.log('🎉 Database setup completed!');

    } catch (error) {
        console.error('❌ Unexpected error:', error);
    }
}

// Run the function
createSubscriptionsTable();



