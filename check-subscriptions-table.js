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

        // Test connection first
        const { data: testData, error: testError } = await supabase
            .from('campaigns')
            .select('count')
            .limit(1);

        if (testError) {
            console.error('❌ Database connection error:', testError);
            return;
        }

        console.log('✅ Database connection successful');

        // Since we can't execute raw SQL with the client, let's try to insert a test record
        // to see if the table exists, and if not, we'll need to create it manually in Supabase dashboard
        
        const { data, error } = await supabase
            .from('subscriptions')
            .select('id')
            .limit(1);

        if (error && error.code === 'PGRST205') {
            console.log('📋 Table does not exist. Please create it manually in Supabase dashboard.');
            console.log('📋 Use the SQL from create-subscriptions-table.sql file');
            console.log('📋 Or run this SQL in your Supabase SQL editor:');
            console.log(`
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

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer_id ON public.subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription_id ON public.subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON public.subscriptions(status);

ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
            `);
        } else if (error) {
            console.error('❌ Error checking table:', error);
        } else {
            console.log('✅ Subscriptions table already exists!');
        }

    } catch (error) {
        console.error('❌ Unexpected error:', error);
    }
}

// Run the function
createSubscriptionsTable();




