#!/usr/bin/env node

/**
 * Comprehensive Environment Variables Debug Script for DigitalOcean
 * This script will help us understand exactly what's happening in the DigitalOcean environment
 */

console.log('🔍 DigitalOcean Environment Variables Debug Report');
console.log('==================================================\n');

// Check Node environment
console.log(`📋 Node Environment: ${process.env.NODE_ENV || 'not set'}`);
console.log(`📋 Port: ${process.env.PORT || 'not set'}`);
console.log(`📋 Working Directory: ${process.cwd()}`);
console.log(`📋 Process Platform: ${process.platform}`);
console.log(`📋 Node Version: ${process.version}\n`);

// Check if we're in DigitalOcean
const isDigitalOcean = process.env.DIGITALOCEAN_APP_ID || process.env.DO_APP_ID;
console.log(`🌊 DigitalOcean Environment: ${isDigitalOcean ? '✅ Detected' : '❌ Not detected'}`);
if (isDigitalOcean) {
    console.log(`   App ID: ${process.env.DIGITALOCEAN_APP_ID || process.env.DO_APP_ID || 'not set'}`);
}

// Check DataForSEO configuration
console.log('\n🔍 DataForSEO Configuration:');
console.log(`   DATAFORSEO_ENVIRONMENT: ${process.env.DATAFORSEO_ENVIRONMENT || 'not set'}`);
console.log(`   DATAFORSEO_BASE_URL: ${process.env.DATAFORSEO_BASE_URL || 'not set'}`);
console.log(`   DATAFORSEO_USERNAME: ${process.env.DATAFORSEO_USERNAME ? '✅ Set (' + process.env.DATAFORSEO_USERNAME + ')' : '❌ Not set'}`);
console.log(`   DATAFORSEO_PASSWORD: ${process.env.DATAFORSEO_PASSWORD ? '✅ Set (' + process.env.DATAFORSEO_PASSWORD.substring(0, 4) + '...)' : '❌ Not set'}\n`);

// Check OpenAI configuration
console.log('🔍 OpenAI Configuration:');
console.log(`   OPENAI_API_KEY: ${process.env.OPENAI_API_KEY ? '✅ Set (' + process.env.OPENAI_API_KEY.substring(0, 10) + '...)' : '❌ Not set'}\n`);

// Check Supabase configuration
console.log('🔍 Supabase Configuration:');
console.log(`   SUPABASE_URL: ${process.env.SUPABASE_URL ? '✅ Set' : '❌ Not set'}`);
console.log(`   SUPABASE_ANON_KEY: ${process.env.SUPABASE_ANON_KEY ? '✅ Set' : '❌ Not set'}`);
console.log(`   SUPABASE_SERVICE_ROLE_KEY: ${process.env.SUPABASE_SERVICE_ROLE_KEY ? '✅ Set' : '❌ Not set'}\n`);

// Check Auth0 configuration
console.log('🔍 Auth0 Configuration:');
console.log(`   AUTH0_DOMAIN: ${process.env.AUTH0_DOMAIN || 'not set'}`);
console.log(`   AUTH0_CLIENT_ID: ${process.env.AUTH0_CLIENT_ID ? '✅ Set' : '❌ Not set'}`);
console.log(`   AUTH0_CLIENT_SECRET: ${process.env.AUTH0_CLIENT_SECRET ? '✅ Set' : '❌ Not set'}`);
console.log(`   AUTH0_SESSION_SECRET: ${process.env.AUTH0_SESSION_SECRET ? '✅ Set' : '❌ Not set'}\n`);

// Check all environment variables that start with specific prefixes
console.log('🔍 All Environment Variables (filtered):');
const envVars = Object.keys(process.env).sort();
const relevantVars = envVars.filter(key => 
    key.includes('DATAFORSEO') || 
    key.includes('OPENAI') || 
    key.includes('SUPABASE') || 
    key.includes('AUTH0') || 
    key.includes('STRIPE') ||
    key.includes('JWT') ||
    key.includes('ENABLE_') ||
    key.includes('NODE_ENV') ||
    key.includes('PORT')
);

relevantVars.forEach(key => {
    const value = process.env[key];
    if (value && value.length > 20) {
        console.log(`   ${key}: ${value.substring(0, 20)}...`);
    } else {
        console.log(`   ${key}: ${value || 'not set'}`);
    }
});

// Test the environmentConfig service
console.log('\n🔍 Testing EnvironmentConfig Service:');
try {
    const EnvironmentConfig = require('./services/environmentConfig');
    const envConfig = new EnvironmentConfig();
    
    console.log('   EnvironmentConfig loaded successfully');
    console.log(`   Current environment: ${envConfig.currentEnvironment}`);
    
    const dataforseoConfig = envConfig.getDataForSEOConfig();
    console.log(`   DataForSEO config:`, {
        environment: dataforseoConfig.environment,
        baseURL: dataforseoConfig.baseUrl,
        username: dataforseoConfig.username ? 'set' : 'not set',
        password: dataforseoConfig.password ? 'set' : 'not set'
    });
    
    const validation = envConfig.validateConfig();
    console.log(`   Validation errors: ${validation.errors.length}`);
    console.log(`   Validation warnings: ${validation.warnings.length}`);
    
    if (validation.errors.length > 0) {
        console.log('   Errors:');
        validation.errors.forEach(error => console.log(`     - ${error}`));
    }
    
} catch (error) {
    console.log(`   ❌ Error loading EnvironmentConfig: ${error.message}`);
}

// Check if .env file exists
console.log('\n🔍 File System Check:');
const fs = require('fs');
const path = require('path');

const envPath = path.join(process.cwd(), '.env');
console.log(`   .env file path: ${envPath}`);
console.log(`   .env file exists: ${fs.existsSync(envPath) ? '✅ Yes' : '❌ No'}`);

if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    const lines = envContent.split('\n').filter(line => line.trim() && !line.startsWith('#'));
    console.log(`   .env file lines: ${lines.length}`);
    console.log(`   .env file size: ${envContent.length} bytes`);
}

console.log('\n📊 Summary:');
const criticalVars = [
    'DATAFORSEO_USERNAME',
    'DATAFORSEO_PASSWORD',
    'OPENAI_API_KEY',
    'SUPABASE_URL',
    'SUPABASE_ANON_KEY',
    'SUPABASE_SERVICE_ROLE_KEY',
    'STRIPE_SECRET_KEY',
    'STRIPE_PUBLISHABLE_KEY',
    'AUTH0_DOMAIN',
    'AUTH0_CLIENT_ID',
    'AUTH0_CLIENT_SECRET',
    'AUTH0_SESSION_SECRET',
    'JWT_SECRET'
];

const missingVars = criticalVars.filter(varName => !process.env[varName]);

if (missingVars.length === 0) {
    console.log('✅ All critical environment variables are configured!');
    console.log('💡 If you\'re still seeing errors, the issue might be:');
    console.log('   1. DigitalOcean app needs to be redeployed');
    console.log('   2. Environment variables are set but not propagated to the running app');
    console.log('   3. There might be a caching issue in DigitalOcean');
} else {
    console.log(`❌ Missing ${missingVars.length} critical environment variables:`);
    missingVars.forEach(varName => {
        console.log(`   - ${varName}`);
    });
    console.log('\n💡 To fix this in DigitalOcean App Platform:');
    console.log('   1. Go to your app in DigitalOcean App Platform');
    console.log('   2. Navigate to Settings → App-Level Settings');
    console.log('   3. Add the missing environment variables in the Environment Variables section');
    console.log('   4. Redeploy your app');
}

console.log('\n🔍 Debug complete!');
