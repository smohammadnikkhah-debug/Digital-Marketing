#!/usr/bin/env node

/**
 * Signup Flow Debug Guide
 * Help identify why signup flow is redirecting to plans instead of Stripe
 */

console.log('🔍 Signup Flow Debug Guide');
console.log('==========================\n');

console.log('📋 Expected Signup Flow:');
console.log('1. User visits mozarex.com');
console.log('2. User clicks "Get Started" or selects a plan');
console.log('3. User is redirected to Auth0 signup page');
console.log('4. User signs up with Auth0 (email/Google/etc.)');
console.log('5. Auth0 redirects back to /auth/callback with plan data in state parameter');
console.log('6. Server creates user in Supabase with customer_id');
console.log('7. Server creates Stripe Checkout session');
console.log('8. User is redirected to Stripe payment page');
console.log('9. After payment, user goes to onboarding');
console.log('10. After onboarding, user goes to dashboard');
console.log('');

console.log('❌ Current Issue:');
console.log('After step 6, user is redirected back to /plans instead of Stripe');
console.log('');

console.log('🔍 What to Check in DigitalOcean Logs:');
console.log('When you go through the signup flow, look for these logs:');
console.log('');

console.log('1. State Parameter:');
console.log('   📋 Plan data from state: {...}');
console.log('   📋 Plan data details: {signup: true, plan: "...", priceId: "...", billing: "..."}');
console.log('   ⚠️ If you see "No state parameter received" → Problem with Auth0 URL');
console.log('');

console.log('2. Routing Decision:');
console.log('   🔍 Routing decision logic: {');
console.log('     hasActiveSubscription: false,');
console.log('     planDataSignup: true,  ← Should be true');
console.log('     planDataPriceId: "price_...",  ← Should have value');
console.log('     hasSelectedPlan: false,');
console.log('     hasAnalyzedDomains: false');
console.log('   }');
console.log('');

console.log('3. Expected Log (if working):');
console.log('   💳 User selected plan during signup - creating Stripe checkout session');
console.log('   💳 Plan data: {plan: "...", priceId: "...", billing: "..."}');
console.log('   💳 Creating Stripe Checkout session for user');
console.log('   ✅ Stripe Checkout session created: ses_...');
console.log('');

console.log('4. If Broken, You\'ll See:');
console.log('   🆕 New user without plan - redirecting to plans page to select subscription');
console.log('   🆕 Reason: hasSelectedPlan = false');
console.log('');

console.log('💡 Test Instructions:');
console.log('1. Open a new incognito/private browser window');
console.log('2. Go to https://mozarex.com');
console.log('3. Click "Get Started" and select a plan (e.g., Professional Monthly)');
console.log('4. Sign up with a NEW email (or use Google Sign-In)');
console.log('5. Watch DigitalOcean logs during the callback');
console.log('6. Share the logs showing the "Plan data from state" and "Routing decision logic"');
console.log('');

console.log('🔍 Debug complete!');
