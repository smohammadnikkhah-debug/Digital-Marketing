#!/usr/bin/env node

/**
 * Environment Variables Validation Script
 * Checks for common issues in .env file
 */

const fs = require('fs');
const path = require('path');

function validateEnvFile() {
    const envPath = path.join(process.cwd(), '.env');
    
    if (!fs.existsSync(envPath)) {
        console.error('❌ .env file not found');
        return false;
    }

    const envContent = fs.readFileSync(envPath, 'utf8');
    const lines = envContent.split('\n');
    
    const issues = [];
    const warnings = [];
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
        'AUTH0_CLIENT_SECRET'
    ];

    console.log('🔍 Validating .env file...\n');

    // Check for malformed lines
    lines.forEach((line, index) => {
        const lineNum = index + 1;
        
        // Skip empty lines and comments
        if (!line.trim() || line.trim().startsWith('#')) {
            return;
        }

        // Check for HTML tags or malformed content
        if (line.includes('<') && line.includes('>')) {
            issues.push(`Line ${lineNum}: Contains HTML tags - "${line.trim()}"`);
        }

        // Check for missing equals sign
        if (!line.includes('=')) {
            issues.push(`Line ${lineNum}: Missing equals sign - "${line.trim()}"`);
        }

        // Check for empty values
        const [key, ...valueParts] = line.split('=');
        const value = valueParts.join('=').trim();
        
        if (key && !value) {
            warnings.push(`Line ${lineNum}: Empty value for ${key.trim()}`);
        }

        // Check for very long lines (potential concatenation issues)
        if (line.length > 200) {
            warnings.push(`Line ${lineNum}: Very long line (${line.length} chars) - potential concatenation issue`);
        }
    });

    // Check for required variables
    const envVars = {};
    lines.forEach(line => {
        if (line.includes('=') && !line.trim().startsWith('#')) {
            const [key, ...valueParts] = line.split('=');
            envVars[key.trim()] = valueParts.join('=').trim();
        }
    });

    requiredVars.forEach(varName => {
        if (!envVars[varName] || envVars[varName] === 'null' || envVars[varName] === '') {
            issues.push(`Missing or empty required variable: ${varName}`);
        }
    });

    // Check for duplicate keys
    const keys = [];
    lines.forEach((line, index) => {
        if (line.includes('=') && !line.trim().startsWith('#')) {
            const key = line.split('=')[0].trim();
            if (keys.includes(key)) {
                issues.push(`Duplicate key found: ${key}`);
            }
            keys.push(key);
        }
    });

    // Check for common issues
    if (envVars.STRIPE_WEBHOOK_SECRET === 'whsec_...') {
        issues.push('STRIPE_WEBHOOK_SECRET is not configured (still has placeholder value)');
    }

    if (envVars.GOOGLE_PLACES_API_KEY && envVars.GOOGLE_PLACES_API_KEY.includes('x')) {
        warnings.push('GOOGLE_PLACES_API_KEY appears to be a placeholder (contains x characters)');
    }

    // Report results
    if (issues.length === 0 && warnings.length === 0) {
        console.log('✅ .env file validation passed!');
        return true;
    }

    if (issues.length > 0) {
        console.log('❌ Issues found:');
        issues.forEach(issue => console.log(`   • ${issue}`));
    }

    if (warnings.length > 0) {
        console.log('\n⚠️  Warnings:');
        warnings.forEach(warning => console.log(`   • ${warning}`));
    }

    console.log('\n📋 Summary:');
    console.log(`   Issues: ${issues.length}`);
    console.log(`   Warnings: ${warnings.length}`);
    console.log(`   Total variables: ${Object.keys(envVars).length}`);

    return issues.length === 0;
}

// Run validation
if (require.main === module) {
    const isValid = validateEnvFile();
    process.exit(isValid ? 0 : 1);
}

module.exports = { validateEnvFile };

