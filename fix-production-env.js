#!/usr/bin/env node

/**
 * Production Environment Variables Fix Script
 * Fixes null values and prepares .env for production deployment
 */

const fs = require('fs');
const path = require('path');

function fixProductionEnv() {
    const envPath = path.join(process.cwd(), '.env');
    
    if (!fs.existsSync(envPath)) {
        console.error('❌ .env file not found');
        return false;
    }

    console.log('🔧 Fixing production environment variables...\n');

    let envContent = fs.readFileSync(envPath, 'utf8');
    
    // Fix null values for optional social media APIs
    const nullReplacements = {
        'FACEBOOK_CLIENT_ID=null': 'FACEBOOK_CLIENT_ID=',
        'FACEBOOK_CLIENT_SECRET=null': 'FACEBOOK_CLIENT_SECRET=',
        'FACEBOOK_REDIRECT_URI=null': 'FACEBOOK_REDIRECT_URI=',
        'TWITTER_CLIENT_ID=null': 'TWITTER_CLIENT_ID=',
        'TWITTER_CLIENT_SECRET=null': 'TWITTER_CLIENT_SECRET=',
        'INSTAGRAM_CLIENT_ID=null': 'INSTAGRAM_CLIENT_ID=',
        'INSTAGRAM_CLIENT_SECRET=null': 'INSTAGRAM_CLIENT_SECRET=',
        'TIKTOK_CLIENT_ID=null': 'TIKTOK_CLIENT_ID=',
        'TIKTOK_CLIENT_SECRET=null': 'TIKTOK_CLIENT_SECRET=',
        'LINKEDIN_CLIENT_ID=null': 'LINKEDIN_CLIENT_ID=',
        'LINKEDIN_CLIENT_SECRET=null': 'LINKEDIN_CLIENT_SECRET=',
        'LINKEDIN_REDIRECT_URI=null': 'LINKEDIN_REDIRECT_URI=',
        'YOUTUBE_CLIENT_ID=null': 'YOUTUBE_CLIENT_ID=',
        'YOUTUBE_CLIENT_SECRET=null': 'YOUTUBE_CLIENT_SECRET=',
        'YOUTUBE_REDIRECT_URI=null': 'YOUTUBE_REDIRECT_URI=',
        'PINTEREST_CLIENT_ID=null': 'PINTEREST_CLIENT_ID=',
        'PINTEREST_CLIENT_SECRET=null': 'PINTEREST_CLIENT_SECRET=',
        'PINTEREST_REDIRECT_URI=null': 'PINTEREST_REDIRECT_URI='
    };

    // Apply replacements
    for (const [oldValue, newValue] of Object.entries(nullReplacements)) {
        envContent = envContent.replace(new RegExp(oldValue, 'g'), newValue);
    }

    // Ensure NODE_ENV is set to production
    if (envContent.includes('NODE_ENV=development')) {
        envContent = envContent.replace('NODE_ENV=development', 'NODE_ENV=production');
    } else if (!envContent.includes('NODE_ENV=production')) {
        envContent = 'NODE_ENV=production\n' + envContent;
    }

    // Ensure PORT is set
    if (!envContent.includes('PORT=')) {
        envContent = envContent + '\nPORT=3000\n';
    }

    // Clean up any remaining formatting issues
    envContent = envContent.replace(/\n\n\n+/g, '\n\n'); // Remove multiple empty lines
    envContent = envContent.trim() + '\n'; // Ensure single trailing newline

    // Write the fixed content back
    fs.writeFileSync(envPath, envContent, 'utf8');

    console.log('✅ Fixed null values in .env file');
    console.log('✅ Set NODE_ENV to production');
    console.log('✅ Ensured PORT is set to 3000');
    console.log('✅ Cleaned up formatting\n');

    // Validate required variables
    const requiredVars = [
        'NODE_ENV',
        'DATAFORSEO_USERNAME',
        'DATAFORSEO_PASSWORD',
        'OPENAI_API_KEY',
        'SUPABASE_URL',
        'SUPABASE_ANON_KEY',
        'STRIPE_SECRET_KEY',
        'STRIPE_PUBLISHABLE_KEY',
        'AUTH0_DOMAIN',
        'AUTH0_CLIENT_ID',
        'AUTH0_CLIENT_SECRET',
        'AUTH0_SESSION_SECRET',
        'JWT_SECRET'
    ];

    console.log('🔍 Validating required environment variables...\n');

    const missingVars = [];
    const lines = envContent.split('\n');

    for (const varName of requiredVars) {
        const line = lines.find(line => line.startsWith(`${varName}=`));
        if (!line || line === `${varName}=` || line.includes('your_') || line.includes('null')) {
            missingVars.push(varName);
        }
    }

    if (missingVars.length > 0) {
        console.log('❌ Missing or invalid required environment variables:');
        missingVars.forEach(varName => {
            console.log(`   - ${varName}`);
        });
        console.log('\n📝 Please update these variables in your .env file with actual values.');
        console.log('   Refer to production.env.example for the expected format.\n');
        return false;
    }

    console.log('✅ All required environment variables are properly set');
    console.log('✅ .env file is ready for production deployment\n');

    return true;
}

// Run the fix
if (require.main === module) {
    const success = fixProductionEnv();
    process.exit(success ? 0 : 1);
}

module.exports = fixProductionEnv;

