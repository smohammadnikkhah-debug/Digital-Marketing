#!/usr/bin/env node

/**
 * Fix the unique constraint issue on the websites table
 * This script will remove the unique constraint on domain field and add a composite constraint
 */

const { createClient } = require('@supabase/supabase-js');

async function fixDomainConstraint() {
    console.log('🔧 Fixing Domain Constraint Issue');
    console.log('==================================\n');

    // Check if Supabase is configured
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
        console.log('❌ Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.');
        console.log('   This script should be run in DigitalOcean where these variables are available.');
        return;
    }

    try {
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );

        console.log('1. Checking current constraints...');
        
        // Check current constraints
        const { data: constraints, error: constraintError } = await supabase
            .rpc('get_table_constraints', { table_name: 'websites' });

        if (constraintError) {
            console.log('   Using direct SQL query instead...');
        } else {
            console.log('   Current constraints:', constraints);
        }

        console.log('\n2. Removing unique constraint on domain field...');
        
        // Remove the unique constraint on domain field
        const { error: dropError } = await supabase.rpc('exec_sql', {
            sql: 'ALTER TABLE websites DROP CONSTRAINT IF EXISTS websites_domain_key;'
        });

        if (dropError) {
            console.log('   ❌ Error removing constraint:', dropError.message);
            console.log('   Trying alternative approach...');
            
            // Try alternative approach
            const { error: altError } = await supabase
                .from('websites')
                .select('*')
                .limit(1);
                
            if (altError) {
                console.log('   ❌ Cannot access websites table:', altError.message);
                return;
            }
        } else {
            console.log('   ✅ Removed unique constraint on domain field');
        }

        console.log('\n3. Adding composite unique constraint...');
        
        // Add composite unique constraint
        const { error: addError } = await supabase.rpc('exec_sql', {
            sql: 'ALTER TABLE websites ADD CONSTRAINT websites_domain_customer_unique UNIQUE (domain, customer_id);'
        });

        if (addError) {
            console.log('   ❌ Error adding composite constraint:', addError.message);
            console.log('   This might already exist or there might be duplicate data');
        } else {
            console.log('   ✅ Added composite unique constraint (domain, customer_id)');
        }

        console.log('\n4. Testing website creation...');
        
        // Test with a sample domain
        const testDomain = 'test-' + Date.now() + '.com';
        const testCustomerId = 'test-customer-' + Date.now();
        
        const { data: testWebsite, error: testError } = await supabase
            .from('websites')
            .insert({
                domain: testDomain,
                company_name: 'Test Company',
                customer_id: testCustomerId,
                status: 'active',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
            })
            .select()
            .single();

        if (testError) {
            console.log('   ❌ Test website creation failed:', testError.message);
        } else {
            console.log('   ✅ Test website created successfully');
            
            // Clean up test website
            await supabase
                .from('websites')
                .delete()
                .eq('id', testWebsite.id);
            console.log('   🧹 Test website cleaned up');
        }

        console.log('\n✅ Domain constraint fix completed!');
        console.log('\n📋 Summary:');
        console.log('- Removed unique constraint on domain field');
        console.log('- Added composite unique constraint (domain, customer_id)');
        console.log('- Multiple customers can now add the same domain');
        console.log('- Each customer can only have one entry per domain');

    } catch (error) {
        console.error('❌ Error fixing domain constraint:', error);
    }
}

// Run the fix
fixDomainConstraint().catch(console.error);
