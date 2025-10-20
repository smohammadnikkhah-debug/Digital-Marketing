const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
require('dotenv').config();

async function createContentMemoryTable() {
    console.log('📊 Creating content_memory table in Supabase...');
    
    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;
    
    if (!supabaseUrl || !supabaseKey) {
        console.error('❌ Missing Supabase credentials in .env file');
        process.exit(1);
    }
    
    const supabase = createClient(supabaseUrl, supabaseKey);
    
    try {
        // Read the SQL file
        const sql = fs.readFileSync('./create-content-memory-table.sql', 'utf8');
        
        console.log('📄 SQL file loaded');
        console.log('🔧 Executing SQL commands...');
        
        // Execute the SQL (note: Supabase client doesn't support raw SQL directly)
        // So we'll use the REST API
        const response = await fetch(`${supabaseUrl}/rest/v1/rpc/exec_sql`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'apikey': supabaseKey,
                'Authorization': `Bearer ${supabaseKey}`
            },
            body: JSON.stringify({ query: sql })
        });
        
        if (!response.ok) {
            // If REST API doesn't work, try alternative approach
            console.log('⚠️ Direct SQL execution not available');
            console.log('📋 Please run the SQL manually in Supabase SQL Editor:');
            console.log('');
            console.log('1. Go to: https://supabase.com/dashboard/project/_/sql/new');
            console.log('2. Copy and paste the contents of create-content-memory-table.sql');
            console.log('3. Click "Run" to execute');
            console.log('');
            console.log('SQL Preview:');
            console.log('─'.repeat(60));
            console.log(sql);
            console.log('─'.repeat(60));
            return;
        }
        
        console.log('✅ Content memory table created successfully!');
        
        // Verify the table exists
        const { data, error } = await supabase
            .from('content_memory')
            .select('*')
            .limit(1);
        
        if (error) {
            console.error('❌ Error verifying table:', error.message);
        } else {
            console.log('✅ Table verified and ready to use!');
        }
        
    } catch (error) {
        console.error('❌ Error creating table:', error.message);
        console.log('');
        console.log('📋 Manual Setup Instructions:');
        console.log('1. Go to Supabase Dashboard → SQL Editor');
        console.log('2. Run the contents of: create-content-memory-table.sql');
        console.log('');
    }
}

createContentMemoryTable();

