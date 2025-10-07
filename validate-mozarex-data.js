#!/usr/bin/env node

/**
 * Validate mozarex.com data in Supabase
 * Check if data is from DataForSEO and properly stored
 */

const { createClient } = require('@supabase/supabase-js');

async function validateMozarexData() {
    console.log('🔍 Validating mozarex.com Data');
    console.log('===============================\n');

    // Check if Supabase is configured
    if (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
        console.log('❌ Supabase not configured. This script should be run where SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are available.');
        console.log('   Run this in DigitalOcean or set the environment variables locally.');
        return;
    }

    try {
        const supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );

        console.log('1. Checking websites table for mozarex.com...');
        
        // Get all mozarex.com entries
        const { data: websites, error: websiteError } = await supabase
            .from('websites')
            .select('*')
            .eq('domain', 'mozarex.com');

        if (websiteError) {
            console.log('   ❌ Error querying websites:', websiteError.message);
            return;
        }

        console.log(`   ✅ Found ${websites.length} website entry(ies) for mozarex.com`);
        
        if (websites.length === 0) {
            console.log('   ⚠️ No website entries found for mozarex.com');
            return;
        }

        websites.forEach((website, index) => {
            console.log(`\n   Website ${index + 1}:`);
            console.log(`      ID: ${website.id}`);
            console.log(`      Domain: ${website.domain}`);
            console.log(`      Customer ID: ${website.customer_id || 'null'}`);
            console.log(`      Company Name: ${website.company_name || 'null'}`);
            console.log(`      Created: ${website.created_at}`);
            console.log(`      Updated: ${website.updated_at}`);
        });

        console.log('\n2. Checking seo_analyses table for mozarex.com...');
        
        // Get all analyses for these websites
        for (const website of websites) {
            console.log(`\n   Checking analyses for website ID: ${website.id}`);
            
            const { data: analyses, error: analysisError } = await supabase
                .from('seo_analyses')
                .select('*')
                .eq('website_id', website.id)
                .order('created_at', { ascending: false });

            if (analysisError) {
                console.log('      ❌ Error querying analyses:', analysisError.message);
                continue;
            }

            console.log(`      ✅ Found ${analyses.length} analysis entry(ies)`);
            
            if (analyses.length === 0) {
                console.log('      ⚠️ No analysis data found for this website');
                continue;
            }

            analyses.forEach((analysis, index) => {
                console.log(`\n      Analysis ${index + 1}:`);
                console.log(`         ID: ${analysis.id}`);
                console.log(`         Created: ${analysis.created_at}`);
                console.log(`         Updated: ${analysis.updated_at}`);
                
                // Check the analysis data structure
                if (analysis.analysis_data) {
                    const data = analysis.analysis_data;
                    console.log(`         Data Type: ${typeof data}`);
                    
                    // Check for DataForSEO indicators
                    const hasDataForSEO = data.dataforseo || data.onPage || data.keywords || data.serp;
                    const hasDemoData = data.isDemo || data.isDemoData || data.demo === true;
                    const hasScore = data.score !== undefined;
                    
                    console.log(`         Has DataForSEO data: ${hasDataForSEO ? '✅ Yes' : '❌ No'}`);
                    console.log(`         Is Demo Data: ${hasDemoData ? '⚠️ Yes' : '✅ No'}`);
                    console.log(`         Has Score: ${hasScore ? `✅ Yes (${data.score}/100)` : '❌ No'}`);
                    
                    // Show key data points
                    if (data.onPage) {
                        console.log(`         On-Page Data: ✅ Yes`);
                        console.log(`            Title: ${data.onPage.title || 'N/A'}`);
                        console.log(`            Meta Description: ${data.onPage.meta_description ? 'Yes' : 'No'}`);
                    }
                    
                    if (data.keywords) {
                        console.log(`         Keywords Data: ✅ Yes`);
                        console.log(`            Keyword Count: ${Array.isArray(data.keywords) ? data.keywords.length : 'N/A'}`);
                    }
                    
                    if (data.healthyPages !== undefined) {
                        console.log(`         Page Metrics:`);
                        console.log(`            Healthy Pages: ${data.healthyPages}`);
                        console.log(`            Pages with Issues: ${data.pagesWithIssues}`);
                        console.log(`            Fixed Issues: ${data.fixedIssues}`);
                        console.log(`            Total Pages: ${data.totalPages || data.analyzedPages || 'N/A'}`);
                    }
                } else {
                    console.log('         ⚠️ No analysis_data found');
                }
            });
        }

        console.log('\n3. Summary:');
        console.log('===========');
        
        let hasRealData = false;
        let hasDemoData = false;
        let dataSource = 'Unknown';
        
        for (const website of websites) {
            const { data: analyses } = await supabase
                .from('seo_analyses')
                .select('analysis_data')
                .eq('website_id', website.id)
                .order('created_at', { ascending: false })
                .limit(1)
                .single();

            if (analyses && analyses.analysis_data) {
                const data = analyses.analysis_data;
                
                // Check data source
                if (data.dataforseo || data.onPage || data.keywords) {
                    hasRealData = true;
                    dataSource = 'DataForSEO';
                }
                
                if (data.isDemo || data.isDemoData || data.demo === true) {
                    hasDemoData = true;
                    dataSource = 'Demo/Test Data';
                }
            }
        }
        
        console.log(`✅ Website Entries: ${websites.length}`);
        console.log(`✅ Data Source: ${dataSource}`);
        console.log(`${hasRealData ? '✅' : '❌'} Has Real DataForSEO Data: ${hasRealData}`);
        console.log(`${hasDemoData ? '⚠️' : '✅'} Has Demo/Test Data: ${hasDemoData}`);
        
        if (hasDemoData) {
            console.log('\n⚠️ WARNING: Demo/test data detected!');
            console.log('   This data should be replaced with real DataForSEO data.');
        }
        
        if (!hasRealData) {
            console.log('\n❌ ISSUE: No real DataForSEO data found!');
            console.log('   The data might be coming from:');
            console.log('   1. Demo/test data');
            console.log('   2. Cached data from a previous analysis');
            console.log('   3. Scraped data (not from DataForSEO API)');
            console.log('\n   To fix: Trigger a fresh analysis from DataForSEO');
        }

    } catch (error) {
        console.error('❌ Validation failed:', error);
    }

    console.log('\n🔍 Validation complete!');
}

// Run the validation
validateMozarexData().catch(console.error);
