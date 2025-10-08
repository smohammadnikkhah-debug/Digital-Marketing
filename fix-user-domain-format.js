/**
 * Fix user domain format in Auth0 to match website table format
 * This script normalizes all user domains to remove protocol and trailing slash
 */

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '.env') });
const Auth0Service = require('./services/auth0Service');
const URLNormalizer = require('./services/urlNormalizer');

async function fixUserDomainFormats() {
  console.log('🔧 Fixing user domain formats in Auth0...\n');
  
  const auth0Service = new Auth0Service();
  
  // Your user ID (from the logs)
  const userId = 'google-oauth2|111838027392074905757';
  const currentDomain = 'https://sydcleaningservices.com.au/';
  
  try {
    console.log('Current domain format:', currentDomain);
    
    // Normalize the domain
    const normalizedDomain = URLNormalizer.normalizeDomainForStorage(currentDomain);
    console.log('Normalized domain:', normalizedDomain);
    
    // Update in Auth0
    console.log('\n🔄 Updating Auth0 user domain...');
    const result = await auth0Service.updateUserDomain(userId, normalizedDomain);
    
    if (result) {
      console.log('✅ Successfully updated user domain in Auth0!');
      console.log('\n📝 Changes:');
      console.log(`   Before: ${currentDomain}`);
      console.log(`   After:  ${normalizedDomain}`);
      console.log('\n✨ User can now see their website data in dashboard!');
    } else {
      console.error('❌ Failed to update user domain');
    }
    
  } catch (error) {
    console.error('❌ Error fixing domain format:', error);
  }
}

// Run the fix
fixUserDomainFormats().then(() => {
  console.log('\n🎉 Done!');
  process.exit(0);
}).catch(error => {
  console.error('❌ Script failed:', error);
  process.exit(1);
});

