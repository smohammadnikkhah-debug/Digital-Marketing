const { createClient } = require('@supabase/supabase-js');

// Load environment variables
require('dotenv').config();

const supabase = createClient(
    process.env.SUPABASE_URL,
    process.env.SUPABASE_SERVICE_ROLE_KEY
);

async function createMissingTables() {
    try {
        console.log('🔧 Creating missing database tables...');
        
        // Create company_services table
        console.log('📝 Creating company_services table...');
        const { error: servicesError } = await supabase
            .from('company_services')
            .select('*')
            .limit(1);
            
        if (servicesError && servicesError.code === 'PGRST205') {
            // Table doesn't exist, create it using raw SQL
            console.log('Creating company_services table...');
            const { error: createError } = await supabase.rpc('exec', {
                sql: `
                    CREATE TABLE company_services (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id TEXT NOT NULL REFERENCES users(id),
                        domain TEXT NOT NULL,
                        service_name TEXT NOT NULL,
                        service_description TEXT,
                        target_keywords TEXT[],
                        content_themes TEXT[],
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                `
            });
            
            if (createError) {
                console.log('⚠️ Could not create company_services table:', createError.message);
                console.log('📋 Please create this table manually in Supabase dashboard:');
                console.log(`
CREATE TABLE company_services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    service_name TEXT NOT NULL,
    service_description TEXT,
    target_keywords TEXT[],
    content_themes TEXT[],
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
                `);
            } else {
                console.log('✅ company_services table created');
            }
        } else {
            console.log('✅ company_services table already exists');
        }
        
        // Create content_calendar_entries table
        console.log('📝 Creating content_calendar_entries table...');
        const { error: contentError } = await supabase
            .from('content_calendar_entries')
            .select('*')
            .limit(1);
            
        if (contentError && contentError.code === 'PGRST205') {
            console.log('Creating content_calendar_entries table...');
            const { error: createError } = await supabase.rpc('exec', {
                sql: `
                    CREATE TABLE content_calendar_entries (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id TEXT NOT NULL REFERENCES users(id),
                        domain TEXT NOT NULL,
                        target_date DATE NOT NULL,
                        platform TEXT NOT NULL CHECK (platform IN ('twitter', 'facebook', 'instagram', 'tiktok')),
                        content TEXT NOT NULL,
                        engagement_tip TEXT,
                        scheduled_time TIME,
                        status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'published', 'rejected')),
                        approved_by TEXT,
                        approved_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        UNIQUE(user_id, domain, target_date, platform)
                    );
                `
            });
            
            if (createError) {
                console.log('⚠️ Could not create content_calendar_entries table:', createError.message);
                console.log('📋 Please create this table manually in Supabase dashboard:');
                console.log(`
CREATE TABLE content_calendar_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    target_date DATE NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('twitter', 'facebook', 'instagram', 'tiktok')),
    content TEXT NOT NULL,
    engagement_tip TEXT,
    scheduled_time TIME,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'scheduled', 'published', 'rejected')),
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, domain, target_date, platform)
);
                `);
            } else {
                console.log('✅ content_calendar_entries table created');
            }
        } else {
            console.log('✅ content_calendar_entries table already exists');
        }
        
        // Create content_generation_logs table
        console.log('📝 Creating content_generation_logs table...');
        const { error: logsError } = await supabase
            .from('content_generation_logs')
            .select('*')
            .limit(1);
            
        if (logsError && logsError.code === 'PGRST205') {
            console.log('Creating content_generation_logs table...');
            const { error: createError } = await supabase.rpc('exec', {
                sql: `
                    CREATE TABLE content_generation_logs (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id TEXT NOT NULL REFERENCES users(id),
                        domain TEXT NOT NULL,
                        generation_date DATE NOT NULL,
                        days_generated INTEGER NOT NULL,
                        services_used TEXT[],
                        ai_model TEXT,
                        tokens_used INTEGER,
                        generation_time_ms INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    );
                `
            });
            
            if (createError) {
                console.log('⚠️ Could not create content_generation_logs table:', createError.message);
                console.log('📋 Please create this table manually in Supabase dashboard:');
                console.log(`
CREATE TABLE content_generation_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES users(id),
    domain TEXT NOT NULL,
    generation_date DATE NOT NULL,
    days_generated INTEGER NOT NULL,
    services_used TEXT[],
    ai_model TEXT,
    tokens_used INTEGER,
    generation_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
                `);
            } else {
                console.log('✅ content_generation_logs table created');
            }
        } else {
            console.log('✅ content_generation_logs table already exists');
        }
        
        // Insert sample company services
        console.log('📝 Inserting sample company services...');
        const { error: insertError } = await supabase
            .from('company_services')
            .upsert([
                {
                    user_id: 'mozarex-user',
                    domain: 'mozarex.com',
                    service_name: 'SEO Optimization',
                    service_description: 'Professional SEO services to improve website rankings and organic traffic',
                    target_keywords: ['SEO', 'search engine optimization', 'organic traffic', 'keyword research'],
                    content_themes: ['SEO tips', 'ranking improvements', 'organic growth', 'search visibility']
                },
                {
                    user_id: 'mozarex-user',
                    domain: 'mozarex.com',
                    service_name: 'Digital Marketing',
                    service_description: 'Comprehensive digital marketing strategies for business growth',
                    target_keywords: ['digital marketing', 'online advertising', 'social media marketing', 'PPC'],
                    content_themes: ['marketing strategies', 'advertising tips', 'social media', 'campaign optimization']
                },
                {
                    user_id: 'mozarex-user',
                    domain: 'mozarex.com',
                    service_name: 'Website Development',
                    service_description: 'Custom website development and optimization services',
                    target_keywords: ['website development', 'web design', 'responsive design', 'user experience'],
                    content_themes: ['web development', 'design trends', 'user experience', 'website optimization']
                },
                {
                    user_id: 'mozarex-user',
                    domain: 'mozarex.com',
                    service_name: 'Content Marketing',
                    service_description: 'Strategic content creation and marketing to engage audiences',
                    target_keywords: ['content marketing', 'content strategy', 'blog writing', 'content creation'],
                    content_themes: ['content strategy', 'writing tips', 'content planning', 'audience engagement']
                }
            ], { onConflict: 'user_id,domain,service_name' });
        
        if (insertError) {
            console.log('⚠️ Sample services insertion:', insertError.message);
        } else {
            console.log('✅ Sample company services inserted');
        }
        
        console.log('🎉 Database setup completed!');
        
        // Test the tables
        console.log('🧪 Testing tables...');
        
        const { data: services, error: testError } = await supabase
            .from('company_services')
            .select('*')
            .eq('user_id', 'mozarex-user')
            .eq('domain', 'mozarex.com');
            
        if (testError) {
            console.log('❌ Table test failed:', testError.message);
        } else {
            console.log(`✅ Found ${services.length} company services`);
            services.forEach(service => {
                console.log(`  - ${service.service_name}: ${service.service_description}`);
            });
        }
        
    } catch (error) {
        console.error('❌ Database setup failed:', error);
    }
}

// Run the setup
createMissingTables();







