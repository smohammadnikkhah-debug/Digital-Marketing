const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const supabaseService = require('./services/supabaseService');

async function fixDomainInSupabaseData() {
    console.log('🔧 Fixing domain field in Supabase analysis data...\n');
    
    if (!supabaseService.isConfigured) {
        console.error('❌ Supabase not configured');
        return;
    }
    
    try {
        const domainToFix = process.argv[2] || 'shineline.com.au';
        
        console.log(`📊 Fixing analysis data for: ${domainToFix}\n`);
        
        // Get the website record
        const { data: website, error: websiteError } = await supabaseService.supabase
            .from('websites')
            .select('id, domain')
            .eq('domain', domainToFix)
            .single();
        
        if (websiteError || !website) {
            console.error(`❌ No website record found for: ${domainToFix}`);
            return;
        }
        
        console.log('✅ Website record found:', website.domain);
        console.log('');
        
        // Get ALL analyses for this website
        const { data: analyses, error: analysesError } = await supabaseService.supabase
            .from('seo_analyses')
            .select('id, analysis_data')
            .eq('website_id', website.id);
        
        if (analysesError || !analyses || analyses.length === 0) {
            console.error(`❌ No analyses found for website: ${domainToFix}`);
            return;
        }
        
        console.log(`✅ Found ${analyses.length} analysis records to fix\n`);
        
        // Fix each analysis
        let fixed = 0;
        for (const analysis of analyses) {
            const analysisData = analysis.analysis_data;
            
            if (analysisData && (!analysisData.domain || analysisData.domain !== domainToFix)) {
                console.log(`🔧 Fixing analysis ${analysis.id}...`);
                console.log(`   Old domain: ${analysisData.domain || 'undefined'}`);
                console.log(`   New domain: ${domainToFix}`);
                
                // Update the domain field
                analysisData.domain = domainToFix;
                
                // Save back to Supabase
                const { error: updateError } = await supabaseService.supabase
                    .from('seo_analyses')
                    .update({ analysis_data: analysisData })
                    .eq('id', analysis.id);
                
                if (updateError) {
                    console.error(`   ❌ Error updating analysis ${analysis.id}:`, updateError);
                } else {
                    console.log(`   ✅ Fixed!`);
                    fixed++;
                }
                console.log('');
            }
        }
        
        console.log(`\n✅ Fixed ${fixed} out of ${analyses.length} analysis records`);
        console.log(`\n🎉 Domain field is now correct for ${domainToFix}!`);
        
    } catch (error) {
        console.error('❌ Error:', error);
    }
}

fixDomainInSupabaseData();








