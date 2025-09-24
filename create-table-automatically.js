/**
 * Automatically create content_calendar table in Supabase
 * This script will create the table with the correct structure
 */

const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

async function createTableAutomatically() {
    try {
        console.log('🚀 Creating content_calendar table automatically...');
        
        if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
            throw new Error('Missing Supabase environment variables');
        }
        
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );
        
        // First, try to drop the existing table if it exists
        console.log('🗑️ Dropping existing table if it exists...');
        try {
            await supabase.rpc('sql', { 
                query: 'DROP TABLE IF EXISTS content_calendar CASCADE;' 
            });
            console.log('✅ Existing table dropped');
        } catch (error) {
            console.log('⚠️ Could not drop table (might not exist):', error.message);
        }
        
        // Create the table with basic columns
        console.log('📊 Creating new table...');
        const createTableSQL = `
            CREATE TABLE content_calendar (
                id SERIAL PRIMARY KEY,
                domain VARCHAR(255) NOT NULL,
                target_date DATE NOT NULL,
                platform VARCHAR(50) NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                description TEXT,
                hashtags TEXT[],
                seo_keywords TEXT[],
                status VARCHAR(50) DEFAULT 'planned',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                
                -- Ensure unique content per domain per date per platform
                UNIQUE(domain, target_date, platform)
            );
        `;
        
        try {
            await supabase.rpc('sql', { query: createTableSQL });
            console.log('✅ Table created successfully!');
        } catch (error) {
            console.log('⚠️ Could not create table via RPC:', error.message);
            console.log('💡 Please create the table manually using the SQL script');
            return;
        }
        
        // Create indexes
        console.log('📈 Creating indexes...');
        const indexes = [
            'CREATE INDEX idx_content_calendar_domain ON content_calendar(domain);',
            'CREATE INDEX idx_content_calendar_date ON content_calendar(target_date);',
            'CREATE INDEX idx_content_calendar_domain_date ON content_calendar(domain, target_date);',
            'CREATE INDEX idx_content_calendar_status ON content_calendar(status);'
        ];
        
        for (const indexSQL of indexes) {
            try {
                await supabase.rpc('sql', { query: indexSQL });
                console.log('✅ Index created');
            } catch (error) {
                console.log('⚠️ Could not create index:', error.message);
            }
        }
        
        // Test the table
        console.log('\n🧪 Testing the new table...');
        
        const testData = {
            domain: 'test.com',
            target_date: '2025-09-18',
            platform: 'twitter',
            content: 'This is a test post for content calendar',
            title: 'Test Post',
            description: 'Test description',
            hashtags: ['#test', '#content'],
            seo_keywords: ['test', 'content'],
            status: 'planned'
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
        
        console.log('\n🎉 Content Calendar table created successfully!');
        console.log('💡 Next steps:');
        console.log('   1. Restart your server');
        console.log('   2. Visit the content calendar page');
        console.log('   3. Content will be automatically generated and stored');
        
    } catch (error) {
        console.error('❌ Creation failed:', error);
        console.log('\n💡 Manual creation required:');
        console.log('   1. Go to Supabase Dashboard > SQL Editor');
        console.log('   2. Copy and paste the contents of create-simple-content-calendar-table.sql');
        console.log('   3. Run the SQL');
        console.log('   4. Then restart your server');
    }
}

// Run the creation
createTableAutomatically();
