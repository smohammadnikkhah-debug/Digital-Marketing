#!/usr/bin/env node

/**
 * Clear cache for a specific domain to force fresh DataForSEO analysis
 */

const supabaseService = require('./services/supabaseService');

async function clearCacheForDomain(domain) {
    console.log(`🗑️ Clearing cache for domain: ${domain}`);
    
    try {
        const supabase = require('./services/supabaseService');
        
        if (!supabase.isConfigured) {
            console.error('❌ Supabase not configured');
            return;
        }
        
        // Get website ID for this domain
        const { data: website, error: websiteError } = await supabase.supabase
            .from('websites')
            .select('id, customer_id')
            .eq('domain', domain)
            .order('created_at', { ascending: false })
            .limit(1);
            
        if (websiteError) {
            console.error('❌ Error finding website:', websiteError);
            return;
        }
        
        if (!website || website.length === 0) {
            console.error('❌ Website not found:', domain);
            return;
        }
        
        const websiteId = website[0].id;
        console.log(`📋 Found website ID: ${websiteId}`);
        
        // Delete all cached analyses for this website
        const { data: deletedAnalyses, error: deleteError } = await supabase.supabase
            .from('seo_analyses')
            .delete()
            .eq('website_id', websiteId);
            
        if (deleteError) {
            console.error('❌ Error deleting cached analyses:', deleteError);
            return;
        }
        
        console.log(`✅ Successfully cleared cache for ${domain}`);
        console.log(`🔄 Next analysis will fetch fresh data from DataForSEO APIs`);
        
    } catch (error) {
        console.error('❌ Error clearing cache:', error);
    }
}

// Get domain from command line argument
const domain = process.argv[2];

if (!domain) {
    console.error('❌ Please provide a domain as argument');
    console.log('Usage: node clear-cache-for-domain.js mozarex.com');
    process.exit(1);
}

clearCacheForDomain(domain);
