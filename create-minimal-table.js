/**
 * Create minimal content_calendar table
 */

const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

async function createMinimalTable() {
    try {
        console.log('🚀 Creating minimal content_calendar table...');
        
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );
        
        // Create a very simple table
        const simpleTableSQL = `
            CREATE TABLE IF NOT EXISTS content_calendar (
                id SERIAL PRIMARY KEY,
                domain VARCHAR(255) NOT NULL,
                target_date DATE NOT NULL,
                platform VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        `;
        
        try {
            await supabase.rpc('sql', { query: simpleTableSQL });
            console.log('✅ Simple table created');
        } catch (error) {
            console.log('⚠️ Could not create via RPC:', error.message);
        }
        
        // Test with minimal data
        const testData = {
            domain: 'test.com',
            target_date: '2025-09-18',
            platform: 'twitter',
            content: 'Test content'
        };
        
        const { data, error } = await supabase
            .from('content_calendar')
            .insert(testData)
            .select();
        
        if (error) {
            console.error('❌ Error:', error);
        } else {
            console.log('✅ Test insert successful!');
            console.log('📝 Data:', data[0]);
            
            // Clean up
            await supabase
                .from('content_calendar')
                .delete()
                .eq('domain', 'test.com');
            
            console.log('🧹 Cleaned up');
        }
        
    } catch (error) {
        console.error('❌ Error:', error);
    }
}

createMinimalTable();
