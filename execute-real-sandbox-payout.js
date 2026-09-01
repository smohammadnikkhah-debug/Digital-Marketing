const https = require('https');

function apiRequest(options, postData = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const parsed = body ? JSON.parse(body) : {};
          resolve({ statusCode: res.statusCode, headers: res.headers, data: parsed, rawBody: body });
        } catch (e) {
          resolve({ statusCode: res.statusCode, headers: res.headers, rawBody: body, error: e });
        }
      });
    });
    req.on('error', reject);
    if (postData) {
      req.write(typeof postData === 'string' ? postData : JSON.stringify(postData));
    }
    req.end();
  });
}

async function runRealSandboxPayout() {
  console.log('================================================================');
  console.log(' EXECUTING GENUINE PAYPAL SANDBOX PAYOUT TEST                   ');
  console.log(' Target Backend: https://mozarex.com                           ');
  console.log(' Target PayPal: https://api-m.sandbox.paypal.com               ');
  console.log('================================================================\n');

  const recipientEmail = 'sb-partner-james@personal.example.com';
  const adminToken = 'mock_token_admin';
  const jamesToken = 'mock_token_james';

  // 1. Configure Partner James recipient PayPal email on Mozarex
  console.log('1. Setting Partner James payout destination to: ' + recipientEmail);
  const accountRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/payout-account',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${jamesToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { paypalEmail: recipientEmail });

  console.log('   Status:', accountRes.statusCode, JSON.stringify(accountRes.data));

  // 1b. Create Admin Commission Adjustment to reach minimum payout threshold (100.00 AUD)
  console.log('\n1b. Adding qualifying commission adjustment for test partner...');
  const adjRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/admin/adjustments/create',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { partnerId: 'partner_james_123', amountMinor: 8000, currency: 'AUD', reason: 'Sandbox E2E test qualifying adjustment' });
  console.log('   Adjustment Status:', adjRes.statusCode, JSON.stringify(adjRes.data));

  // 2. Create Payout Batch for Partner James
  console.log('\n2. Creating internal Payout Batch on Mozarex...');
  const batchCreateRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/admin/payouts/create-batch',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { partnerId: 'partner_james_123', currency: 'AUD' });

  console.log('   Status:', batchCreateRes.statusCode, JSON.stringify(batchCreateRes.data));
  const internalPayoutId = batchCreateRes.data?.payout?.id || 'payout_test_real';

  // 3. Approve Payout Batch
  console.log('\n3. Approving Payout Batch #' + internalPayoutId + '...');
  const approveRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/admin/payouts/approve',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { payoutId: internalPayoutId });

  console.log('   Status:', approveRes.statusCode, JSON.stringify(approveRes.data));

  // 4. Send via PayPal (Real PayPal API invocation)
  console.log('\n4. Submitting Approved Payout to PayPal Sandbox via Mozarex...');
  const sendRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/admin/payouts/send-paypal',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { payoutId: internalPayoutId });

  console.log('   Status:', sendRes.statusCode);
  console.log('   Response Data:', JSON.stringify(sendRes.data, null, 2));

  const paypalBatchId = sendRes.data?.payout?.provider_batch_id;

  // 5. Query / Refresh Status from PayPal Sandbox
  if (paypalBatchId) {
    console.log('\n5. Querying PayPal Sandbox Batch Status for ID: ' + paypalBatchId + '...');
    const refreshRes = await apiRequest({
      hostname: 'mozarex.com',
      port: 443,
      path: '/api/aivekai/partners/admin/payouts/refresh-status',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${adminToken}`,
        'x-csrf-token': 'valid_csrf_token'
      }
    }, { payoutId: internalPayoutId });

    console.log('   Status:', refreshRes.statusCode);
    console.log('   PayPal Live Status Data:', JSON.stringify(refreshRes.data, null, 2));
  }

  // 6. Test Duplicate Submission Protection on Mozarex
  console.log('\n6. Testing Duplicate Submission Protection (Second Send Attempt)...');
  const duplicateSendRes = await apiRequest({
    hostname: 'mozarex.com',
    port: 443,
    path: '/api/aivekai/partners/admin/payouts/send-paypal',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${adminToken}`,
      'x-csrf-token': 'valid_csrf_token'
    }
  }, { payoutId: internalPayoutId });

  console.log('   Duplicate Send HTTP Status:', duplicateSendRes.statusCode);
  console.log('   Duplicate Send Response:', JSON.stringify(duplicateSendRes.data));

  return {
    accountSetup: accountRes.data,
    payoutCreation: batchCreateRes.data,
    payoutApproval: approveRes.data,
    payoutSubmission: sendRes.data,
    duplicatePrevention: duplicateSendRes.data
  };
}

if (require.main === module) {
  runRealSandboxPayout()
    .then(res => console.log('\nExecution completed.'))
    .catch(err => console.error('Execution Error:', err));
}
