#!/usr/bin/env node

/**
 * Complete Environment Variables Fix Script
 * Fixes all remaining issues in .env file
 */

const fs = require('fs');
const path = require('path');

function completeFixEnvFile() {
    const envPath = path.join(process.cwd(), '.env');
    
    if (!fs.existsSync(envPath)) {
        console.error('❌ .env file not found');
        return false;
    }

    console.log('🔧 Applying complete .env file fixes...\n');

    let envContent = fs.readFileSync(envPath, 'utf8');
    
    // Fix the concatenated AUTH0_SESSION_SECRET and JWT_SECRET
    envContent = envContent.replace(
        /AUTH0_SESSION_SECRET=([^J]+)JWT_SECRET=(.+)/,
        'AUTH0_SESSION_SECRET=$1\nJWT_SECRET=$2'
    );

    // Remove any empty lines at the end
    envContent = envContent.replace(/\n+$/, '\n');

    // Clean up any remaining formatting issues
    envContent = envContent.replace(/\n\n\n+/g, '\n\n'); // Remove multiple empty lines
    
    // Ensure proper line endings
    envContent = envContent.trim() + '\n';

    // Write the fixed content back
    fs.writeFileSync(envPath, envContent, 'utf8');
    
    console.log('✅ Complete .env file fixes applied!');
    console.log('\n📋 Changes made:');
    console.log('   • Separated concatenated AUTH0_SESSION_SECRET and JWT_SECRET');
    console.log('   • Removed empty lines');
    console.log('   • Cleaned up formatting');
    
    return true;
}

// Run fix
if (require.main === module) {
    const success = completeFixEnvFile();
    if (success) {
        console.log('\n🔍 Running final validation...');
        require('./validate-env.js');
    }
    process.exit(success ? 0 : 1);
}

module.exports = { completeFixEnvFile };

