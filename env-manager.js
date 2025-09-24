#!/usr/bin/env node

/**
 * Environment Management Script
 * Easy switching between development and production environments
 */

const fs = require('fs');
const path = require('path');

class EnvironmentManager {
  constructor() {
    this.projectRoot = path.join(__dirname);
    this.envFiles = {
      development: 'env.development',
      production: 'env.production'
    };
  }

  /**
   * Switch to development environment
   */
  switchToDevelopment() {
    console.log('🔄 Switching to development environment...');
    this.copyEnvFile('development');
    console.log('✅ Switched to development environment (Sandbox mode)');
    console.log('   - Using DataForSEO Sandbox API');
    console.log('   - Debug logs enabled');
    console.log('   - Demo data available');
  }

  /**
   * Switch to production environment
   */
  switchToProduction() {
    console.log('🔄 Switching to production environment...');
    this.copyEnvFile('production');
    console.log('✅ Switched to production environment (Production API)');
    console.log('   - Using DataForSEO Production API');
    console.log('   - Debug logs disabled');
    console.log('   - Real data only');
  }

  /**
   * Copy environment file to .env
   */
  copyEnvFile(environment) {
    const sourceFile = path.join(this.projectRoot, this.envFiles[environment]);
    const targetFile = path.join(this.projectRoot, '.env');

    if (!fs.existsSync(sourceFile)) {
      console.error(`❌ Environment file not found: ${sourceFile}`);
      process.exit(1);
    }

    try {
      fs.copyFileSync(sourceFile, targetFile);
      console.log(`📄 Copied ${this.envFiles[environment]} to .env`);
    } catch (error) {
      console.error(`❌ Failed to copy environment file: ${error.message}`);
      process.exit(1);
    }
  }

  /**
   * Show current environment status
   */
  showStatus() {
    const envFile = path.join(this.projectRoot, '.env');
    
    if (!fs.existsSync(envFile)) {
      console.log('❌ No .env file found');
      return;
    }

    const envContent = fs.readFileSync(envFile, 'utf8');
    const lines = envContent.split('\n');
    
    console.log('\n🔧 Current Environment Configuration:');
    console.log('=====================================');
    
    for (const line of lines) {
      const trimmedLine = line.trim();
      if (trimmedLine && !trimmedLine.startsWith('#')) {
        const [key, ...valueParts] = trimmedLine.split('=');
        if (key && valueParts.length > 0) {
          const value = valueParts.join('=').trim();
          if (key === 'DATAFORSEO_PASSWORD') {
            console.log(`   ${key}: ${'*'.repeat(value.length)}`);
          } else {
            console.log(`   ${key}: ${value}`);
          }
        }
      }
    }
    console.log('=====================================\n');
  }

  /**
   * Show available environments
   */
  showAvailable() {
    console.log('\n📋 Available Environments:');
    console.log('==========================');
    
    for (const [env, file] of Object.entries(this.envFiles)) {
      const filePath = path.join(this.projectRoot, file);
      const exists = fs.existsSync(filePath);
      console.log(`   ${env}: ${file} ${exists ? '✅' : '❌'}`);
    }
    console.log('==========================\n');
  }

  /**
   * Show help
   */
  showHelp() {
    console.log('\n🚀 Environment Management Script');
    console.log('=================================');
    console.log('Usage: node env-manager.js <command>');
    console.log('');
    console.log('Commands:');
    console.log('  dev, development    Switch to development environment (Sandbox)');
    console.log('  prod, production    Switch to production environment (Production API)');
    console.log('  status              Show current environment status');
    console.log('  list                Show available environments');
    console.log('  help                Show this help message');
    console.log('');
    console.log('Examples:');
    console.log('  node env-manager.js dev');
    console.log('  node env-manager.js production');
    console.log('  node env-manager.js status');
    console.log('=================================\n');
  }
}

// Main execution
function main() {
  const manager = new EnvironmentManager();
  const command = process.argv[2];

  switch (command) {
    case 'dev':
    case 'development':
      manager.switchToDevelopment();
      break;
    case 'prod':
    case 'production':
      manager.switchToProduction();
      break;
    case 'status':
      manager.showStatus();
      break;
    case 'list':
      manager.showAvailable();
      break;
    case 'help':
    case '--help':
    case '-h':
      manager.showHelp();
      break;
    default:
      console.log('❌ Unknown command. Use "help" to see available commands.');
      manager.showHelp();
      process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = EnvironmentManager;




