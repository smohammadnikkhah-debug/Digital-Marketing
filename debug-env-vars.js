#!/usr/bin/env node

/**
 * Environment Variables Debug Script
 * Helps debug environment variable configuration in DigitalOcean App Platform
 */

console.log('🔍 Environment Variables Debug Report');
console.log('=====================================\n');

// Check Node environment
console.log(`📋 Node Environment: ${process.env.NODE_ENV || 'not set'}`);
console.log(`📋 Port: ${process.env.PORT || 'not set'}\n`);

// Check DataForSEO configuration
console.log('🔍 DataForSEO Configuration:');
console.log(`   DATAFORSEO_ENVIRONMENT: ${process.env.DATAFORSEO_ENVIRONMENT || 'not set'}`);
console.log(`   DATAFORSEO_BASE_URL: ${process.env.DATAFORSEO_BASE_URL || 'not set'}`);
console.log(`   DATAFORSEO_USERNAME: ${process.env.DATAFORSEO_USERNAME ? '✅ Set' : '❌ Not set'}`);
console.log(`   DATAFORSEO_PASSWORD: ${process.env.DATAFORSEO_PASSWORD ? '✅ Set' : '❌ Not set'}\n`);

// Check OpenAI configuration
console.log('🔍 OpenAI Configuration:');
console.log(`   OPENAI_API_KEY: ${process.env.OPENAI_API_KEY ? '✅ Set' : '❌ Not set'}\n`);

// Check Supabase configuration
console.log('🔍 Supabase Configuration:');
console.log(`   SUPABASE_URL: ${process.env.SUPABASE_URL ? '✅ Set' : '❌ Not set'}`);
console.log(`   SUPABASE_ANON_KEY: ${process.env.SUPABASE_ANON_KEY ? '✅ Set' : '❌ Not set'}`);
console.log(`   SUPABASE_SERVICE_ROLE_KEY: ${process.env.SUPABASE_SERVICE_ROLE_KEY ? '✅ Set' : '❌ Not set'}\n`);

// Check Stripe configuration
console.log('🔍 Stripe Configuration:');
console.log(`   STRIPE_SECRET_KEY: ${process.env.STRIPE_SECRET_KEY ? '✅ Set' : '❌ Not set'}`);
console.log(`   STRIPE_PUBLISHABLE_KEY: ${process.env.STRIPE_PUBLISHABLE_KEY ? '✅ Set' : '❌ Not set'}\n`);

// Check Auth0 configuration
console.log('🔍 Auth0 Configuration:');
console.log(`   AUTH0_DOMAIN: ${process.env.AUTH0_DOMAIN || 'not set'}`);
console.log(`   AUTH0_CLIENT_ID: ${process.env.AUTH0_CLIENT_ID ? '✅ Set' : '❌ Not set'}`);
console.log(`   AUTH0_CLIENT_SECRET: ${process.env.AUTH0_CLIENT_SECRET ? '✅ Set' : '❌ Not set'}`);
console.log(`   AUTH0_CALLBACK_URL: ${process.env.AUTH0_CALLBACK_URL || 'not set'}`);
console.log(`   AUTH0_LOGOUT_URL: ${process.env.AUTH0_LOGOUT_URL || 'not set'}`);
console.log(`   AUTH0_SESSION_SECRET: ${process.env.AUTH0_SESSION_SECRET ? '✅ Set' : '❌ Not set'}\n`);

// Check JWT configuration
console.log('🔍 JWT Configuration:');
console.log(`   JWT_SECRET: ${process.env.JWT_SECRET ? '✅ Set' : '❌ Not set'}\n`);

// Check optional features
console.log('🔍 Optional Features:');
console.log(`   ENABLE_SANDBOX_MODE: ${process.env.ENABLE_SANDBOX_MODE || 'false'}`);
console.log(`   ENABLE_DEMO_DATA: ${process.env.ENABLE_DEMO_DATA || 'false'}`);
console.log(`   ENABLE_MOCK_RESPONSES: ${process.env.ENABLE_MOCK_RESPONSES || 'false'}`);
console.log(`   ENABLE_SOCIAL_CONNECTIONS: ${process.env.ENABLE_SOCIAL_CONNECTIONS || 'false'}\n`);

// Summary
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

console.log('📊 Summary:');
if (missingVars.length === 0) {
    console.log('✅ All critical environment variables are configured!');
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
