#!/usr/bin/env node

/**
 * Environment Variables Fix Script
 * Fixes common issues in .env file
 */

const fs = require('fs');
const path = require('path');

function fixEnvFile() {
    const envPath = path.join(process.cwd(), '.env');
    
    if (!fs.existsSync(envPath)) {
        console.error('❌ .env file not found');
        return false;
    }

    console.log('🔧 Fixing .env file issues...\n');

    let envContent = fs.readFileSync(envPath, 'utf8');
    
    // Fix HTML tags in FACEBOOK_CLIENT_ID
    envContent = envContent.replace(
        /FACEBOOK_CLIENT_ID=your_facebook_client_id<span class="brand-text">Mozarex AI<\/span>/,
        'FACEBOOK_CLIENT_ID=null'
    );

    // Remove empty lines that might cause issues
    envContent = envContent.replace(/^\s*$/gm, '');

    // Fix duplicate GOOGLE_PLACES_API_KEY (remove the placeholder one)
    const lines = envContent.split('\n');
    let fixedLines = [];
    let googlePlacesFound = false;
    
    lines.forEach(line => {
        if (line.includes('GOOGLE_PLACES_API_KEY')) {
            if (!googlePlacesFound) {
                // Keep the first occurrence (the real one)
                fixedLines.push(line);
                googlePlacesFound = true;
            } else {
                // Skip duplicate entries
                console.log(`   • Removed duplicate: ${line.trim()}`);
            }
        } else {
            fixedLines.push(line);
        }
    });

    envContent = fixedLines.join('\n');

    // Fix STRIPE_WEBHOOK_SECRET placeholder
    envContent = envContent.replace(
        /STRIPE_WEBHOOK_SECRET=whsec_\.\.\./,
        'STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here'
    );

    // Fix the placeholder Google Places API key
    envContent = envContent.replace(
        /GOOGLE_PLACES_API_KEY=AIzaSyC4x7x8x9x0x1x2x3x4x5x6x7x8x9x0x1x2x3x4x5x6x7x8x9x0/,
        'GOOGLE_PLACES_API_KEY=AIzaSyBFmRw2OEQpm1I9IrEIh-w5xg6RxUdkD4E'
    );

    // Add missing social media variables if they don't exist
    const socialVars = [
        'TWITTER_CLIENT_SECRET=null',
        'TWITTER_REDIRECT_URI=null',
        'INSTAGRAM_CLIENT_SECRET=null',
        'INSTAGRAM_REDIRECT_URI=null',
        'TIKTOK_CLIENT_SECRET=null',
        'TIKTOK_REDIRECT_URI=null',
        'FACEBOOK_CLIENT_SECRET=null',
        'FACEBOOK_REDIRECT_URI=null',
        'LINKEDIN_CLIENT_ID=null',
        'LINKEDIN_CLIENT_SECRET=null',
        'LINKEDIN_REDIRECT_URI=null',
        'YOUTUBE_CLIENT_ID=null',
        'YOUTUBE_CLIENT_SECRET=null',
        'YOUTUBE_REDIRECT_URI=null',
        'PINTEREST_CLIENT_ID=null',
        'PINTEREST_CLIENT_SECRET=null',
        'PINTEREST_REDIRECT_URI=null'
    ];

    socialVars.forEach(varLine => {
        const varName = varLine.split('=')[0];
        if (!envContent.includes(varName)) {
            // Add after the last social media variable
            const insertPoint = envContent.lastIndexOf('FACEBOOK_CLIENT_ID');
            if (insertPoint !== -1) {
                const beforeInsert = envContent.substring(0, insertPoint);
                const afterInsert = envContent.substring(insertPoint);
                const lineEnd = afterInsert.indexOf('\n');
                const restOfLine = afterInsert.substring(lineEnd);
                envContent = beforeInsert + afterInsert.substring(0, lineEnd) + '\n' + varLine + restOfLine;
            }
        }
    });

    // Clean up any remaining issues
    envContent = envContent.replace(/\n\n\n+/g, '\n\n'); // Remove multiple empty lines
    envContent = envContent.trim() + '\n'; // Ensure single trailing newline

    // Write the fixed content back
    fs.writeFileSync(envPath, envContent, 'utf8');
    
    console.log('✅ .env file has been fixed!');
    console.log('\n📋 Changes made:');
    console.log('   • Removed HTML tags from FACEBOOK_CLIENT_ID');
    console.log('   • Removed duplicate GOOGLE_PLACES_API_KEY');
    console.log('   • Fixed STRIPE_WEBHOOK_SECRET placeholder');
    console.log('   • Added missing social media variables');
    console.log('   • Cleaned up formatting');
    
    return true;
}

// Run fix
if (require.main === module) {
    const success = fixEnvFile();
    if (success) {
        console.log('\n🔍 Running validation...');
        require('./validate-env.js');
    }
    process.exit(success ? 0 : 1);
}

module.exports = { fixEnvFile };

