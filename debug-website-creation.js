#!/usr/bin/env node

/**
 * Debug script to check website creation during onboarding
 * This will help us understand why websites aren't showing up in the dashboard
 */

const supabaseService = require('./services/supabaseService');
const auth0Service = require('./services/auth0Service');

async function debugWebsiteCreation() {
    console.log('🔍 Debugging Website Creation Process');
    console.log('=====================================\n');

    try {
        // Check if Supabase is configured
        console.log('1. Checking Supabase configuration...');
        const supabase = new supabaseService();
        console.log(`   Supabase configured: ${supabase.isConfigured ? '✅ Yes' : '❌ No'}`);
        
        if (!supabase.isConfigured) {
            console.log('❌ Supabase not configured. Check environment variables.');
            return;
        }

        // Check if we can connect to Supabase
        console.log('\n2. Testing Supabase connection...');
        try {
            const { data, error } = await supabase.supabase
                .from('websites')
                .select('count')
                .limit(1);
            
            if (error) {
                console.log(`   ❌ Supabase connection error: ${error.message}`);
                return;
            } else {
                console.log('   ✅ Supabase connection successful');
            }
        } catch (error) {
            console.log(`   ❌ Supabase connection failed: ${error.message}`);
            return;
        }

        // Check websites table structure
        console.log('\n3. Checking websites table...');
        try {
            const { data, error } = await supabase.supabase
                .from('websites')
                .select('*')
                .limit(5);
            
            if (error) {
                console.log(`   ❌ Error querying websites table: ${error.message}`);
            } else {
                console.log(`   ✅ Websites table accessible`);
                console.log(`   📊 Found ${data.length} websites in database`);
                
                if (data.length > 0) {
                    console.log('   📋 Sample website data:');
                    data.forEach((website, index) => {
                        console.log(`      ${index + 1}. Domain: ${website.domain}`);
                        console.log(`         Customer ID: ${website.customer_id || 'null'}`);
                        console.log(`         Company: ${website.company_name || 'null'}`);
                        console.log(`         Created: ${website.created_at || 'null'}`);
                    });
                }
            }
        } catch (error) {
            console.log(`   ❌ Error checking websites table: ${error.message}`);
        }

        // Check users table
        console.log('\n4. Checking users table...');
        try {
            const auth0 = new auth0Service();
            const users = await auth0.getAllUsers();
            
            if (users && users.length > 0) {
                console.log(`   ✅ Users table accessible`);
                console.log(`   📊 Found ${users.length} users in database`);
                
                console.log('   📋 Sample user data:');
                users.slice(0, 3).forEach((user, index) => {
                    console.log(`      ${index + 1}. Email: ${user.email}`);
                    console.log(`         Customer ID: ${user.customer_id || 'null'}`);
                    console.log(`         Domain: ${user.domain || 'null'}`);
                    console.log(`         Created: ${user.created_at || 'null'}`);
                });
            } else {
                console.log('   ⚠️ No users found in database');
            }
        } catch (error) {
            console.log(`   ❌ Error checking users table: ${error.message}`);
        }

        // Test website creation
        console.log('\n5. Testing website creation...');
        try {
            const testDomain = 'test-debug-' + Date.now() + '.com';
            const testCustomerId = 'test-customer-' + Date.now();
            
            console.log(`   Creating test website: ${testDomain}`);
            console.log(`   With customer ID: ${testCustomerId}`);
            
            const website = await supabase.createOrGetWebsite(testDomain, 'Test Company', testCustomerId);
            
            if (website && !website.error) {
                console.log('   ✅ Test website created successfully');
                console.log(`   📋 Website ID: ${website.id}`);
                console.log(`   📋 Domain: ${website.domain}`);
                console.log(`   📋 Customer ID: ${website.customer_id}`);
                
                // Clean up test website
                console.log('   🧹 Cleaning up test website...');
                await supabase.supabase
                    .from('websites')
                    .delete()
                    .eq('id', website.id);
                console.log('   ✅ Test website cleaned up');
            } else {
                console.log(`   ❌ Test website creation failed: ${website?.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.log(`   ❌ Error testing website creation: ${error.message}`);
        }

        // Check recent website creation attempts
        console.log('\n6. Checking recent website creation attempts...');
        try {
            const { data, error } = await supabase.supabase
                .from('websites')
                .select('*')
                .order('created_at', { ascending: false })
                .limit(10);
            
            if (error) {
                console.log(`   ❌ Error querying recent websites: ${error.message}`);
            } else {
                console.log(`   📊 Recent websites (last 10):`);
                if (data.length === 0) {
                    console.log('   ⚠️ No websites found in database');
                } else {
                    data.forEach((website, index) => {
                        console.log(`      ${index + 1}. ${website.domain} (Customer: ${website.customer_id || 'null'}) - ${website.created_at}`);
                    });
                }
            }
        } catch (error) {
            console.log(`   ❌ Error checking recent websites: ${error.message}`);
        }

    } catch (error) {
        console.error('❌ Debug script failed:', error);
    }

    console.log('\n🔍 Debug complete!');
}

// Run the debug script
debugWebsiteCreation().catch(console.error);
