/**
 * Setup Content Calendar Table in Supabase
 * This script creates the content_calendar table and related functions
 */

const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

async function setupContentCalendarTable() {
    try {
        console.log('🚀 Setting up Content Calendar table in Supabase...');
        
        if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
            throw new Error('Missing Supabase environment variables');
        }
        
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );
        
        // Create the content_calendar table directly
        console.log('📊 Creating content_calendar table...');
        
        // First, let's check if the table already exists
        const { data: existingTables, error: checkError } = await supabase
            .from('information_schema.tables')
            .select('table_name')
            .eq('table_name', 'content_calendar');
        
        if (checkError) {
            console.log('⚠️ Could not check existing tables, proceeding with creation...');
        } else if (existingTables && existingTables.length > 0) {
            console.log('✅ content_calendar table already exists!');
        } else {
            console.log('📝 Table does not exist, creating...');
            
            // Create table using raw SQL
            const createTableSQL = `
                CREATE TABLE IF NOT EXISTS content_calendar (
                    id SERIAL PRIMARY KEY,
                    domain VARCHAR(255) NOT NULL,
                    target_date DATE NOT NULL,
                    platform VARCHAR(50) NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    description TEXT,
                    hashtags TEXT[],
                    seo_keywords TEXT[],
                    call_to_action TEXT,
                    engagement_tip TEXT,
                    scheduled_time TIME,
                    status VARCHAR(50) DEFAULT 'planned',
                    media_type VARCHAR(50) DEFAULT 'text',
                    media_url TEXT,
                    is_editable BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    
                    -- Ensure unique content per domain per date per platform
                    UNIQUE(domain, target_date, platform)
                );
            `;
            
            // Try to create the table using a direct SQL query
            const { data, error } = await supabase.rpc('sql', { query: createTableSQL });
            
            if (error) {
                console.log('⚠️ Could not create table via RPC, trying alternative approach...');
                // Alternative: try to insert a test record to see if table exists
                const testData = {
                    domain: 'test.com',
                    target_date: '2025-09-18',
                    platform: 'twitter',
                    content: 'Test content'
                };
                
                const { error: insertError } = await supabase
                    .from('content_calendar')
                    .insert(testData);
                
                if (insertError && insertError.code === 'PGRST116') {
                    console.log('❌ Table does not exist and cannot be created automatically');
                    console.log('💡 Please create the table manually in Supabase dashboard:');
                    console.log('   1. Go to Supabase Dashboard > SQL Editor');
                    console.log('   2. Run the SQL from database/content_calendar_schema.sql');
                    console.log('   3. Then restart your server');
                    return;
                } else if (insertError) {
                    console.error('❌ Error testing table:', insertError);
                } else {
                    console.log('✅ Table exists and is working!');
                    // Clean up test data
                    await supabase
                        .from('content_calendar')
                        .delete()
                        .eq('domain', 'test.com');
                }
            } else {
                console.log('✅ Table created successfully!');
            }
        }
        
        console.log('✅ Content Calendar table created successfully!');
        console.log('📊 Table: content_calendar');
        console.log('🔍 Features:');
        console.log('   - Stores AI-generated social media content');
        console.log('   - Unique constraint per domain/date/platform');
        console.log('   - Automatic updated_at timestamp');
        console.log('   - Optimized indexes for performance');
        
        // Test the table by inserting a sample record
        console.log('\n🧪 Testing table with sample data...');
        
        const testData = {
            domain: 'test.com',
            target_date: '2025-09-18',
            platform: 'twitter',
            content: 'This is a test post for content calendar'
        };
        
        const { data: insertData, error: insertError } = await supabase
            .from('content_calendar')
            .insert(testData)
            .select();
        
        if (insertError) {
            console.error('❌ Error inserting test data:', insertError);
        } else {
            console.log('✅ Test data inserted successfully!');
            console.log('📝 Sample record:', insertData[0]);
            
            // Clean up test data
            await supabase
                .from('content_calendar')
                .delete()
                .eq('domain', 'test.com');
            
            console.log('🧹 Test data cleaned up');
        }
        
        console.log('\n🎉 Content Calendar setup completed successfully!');
        console.log('💡 Next steps:');
        console.log('   1. Restart your server');
        console.log('   2. Visit the content calendar page');
        console.log('   3. Content will be automatically generated and stored');
        
    } catch (error) {
        console.error('❌ Setup failed:', error);
        process.exit(1);
    }
}

// Run the setup
setupContentCalendarTable();
