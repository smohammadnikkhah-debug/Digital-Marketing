#!/usr/bin/env node

/**
 * Final Environment Variables Fix Script
 * Fixes the concatenated AUTH0_SESSION_SECRET and JWT_SECRET issue
 */

const fs = require('fs');
const path = require('path');

function finalFixEnvFile() {
    const envPath = path.join(process.cwd(), '.env');
    
    if (!fs.existsSync(envPath)) {
        console.error('❌ .env file not found');
        return false;
    }

    console.log('🔧 Applying final .env file fixes...\n');

    let envContent = fs.readFileSync(envPath, 'utf8');
    
    // Fix the concatenated AUTH0_SESSION_SECRET and JWT_SECRET
    envContent = envContent.replace(
        /AUTH0_SESSION_SECRET=([^J]+)JWT_SECRET=(.+)/,
        'AUTH0_SESSION_SECRET=$1\nJWT_SECRET=$2'
    );

    // Clean up any remaining formatting issues
    envContent = envContent.replace(/\n\n\n+/g, '\n\n'); // Remove multiple empty lines
    envContent = envContent.trim() + '\n'; // Ensure single trailing newline

    // Write the fixed content back
    fs.writeFileSync(envPath, envContent, 'utf8');
    
    console.log('✅ Final .env file fixes applied!');
    console.log('\n📋 Changes made:');
    console.log('   • Separated concatenated AUTH0_SESSION_SECRET and JWT_SECRET');
    console.log('   • Cleaned up formatting');
    
    return true;
}

// Run fix
if (require.main === module) {
    const success = finalFixEnvFile();
    if (success) {
        console.log('\n🔍 Running final validation...');
        require('./validate-env.js');
    }
    process.exit(success ? 0 : 1);
}

module.exports = { finalFixEnvFile };

