process.env.NODE_ENV = 'test';

const assert = require('assert');
const http = require('http');
const { app, server } = require('./server');
const partnerRouter = require('./routes/aivekaiPartners');
const partnerEmailService = require('./services/partnerEmailService');
const mockStore = partnerRouter.mockStore;
const rateLimitMap = partnerRouter.rateLimitMap;
const { runPasswordReset, validatePasswordStrength } = require('./reset-admin-password');

function makeRequest({ port, path, method = 'GET', headers = {}, body = null }) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port,
      path,
      method,
      headers
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = data ? JSON.parse(data) : {};
          resolve({ statusCode: res.statusCode, headers: res.headers, data: parsed, rawBody: data });
        } catch (e) {
          resolve({ statusCode: res.statusCode, headers: res.headers, rawBody: data, error: e });
        }
      });
    });
    req.on('error', reject);
    if (body) {
      req.write(typeof body === 'string' ? body : JSON.stringify(body));
    }
    req.end();
  });
}

async function runPasswordSecurityTests() {
  console.log('================================================================');
  console.log(' ADMIN PASSWORD MANAGEMENT & SECURE RESET TEST SUITE            ');
  console.log('================================================================\n');

  if (rateLimitMap) rateLimitMap.clear();
  partnerEmailService.resetState();

  let passed = 0;
  let failed = 0;

  async function test(name, fn) {
    try {
      if (rateLimitMap) rateLimitMap.clear();
      await fn();
      console.log(`✅ ${name}`);
      passed++;
    } catch (err) {
      console.error(`❌ ${name}: ${err.message}`);
      failed++;
    }
  }

  const TEST_PORT = 3008;
  await new Promise((resolve) => server.listen(TEST_PORT, resolve));

  try {
    // -------------------------------------------------------------------------
    // 1. FORGOT PASSWORD & RECOVERY LIFECYCLE TESTS
    // -------------------------------------------------------------------------

    // SEC-RESET-01: Unknown / Non-Admin Email returns generic message, no email sent
    await test('SEC-RESET-01: Unknown/non-admin email returns generic message without leaking account existence', async () => {
      partnerEmailService.resetState();
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/forgot-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: { email: 'nonexistent_user@example.com' }
      });

      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.message, "If an eligible administrator account exists for this email address, we've sent password reset instructions.");

      // No email should be sent for an unknown user
      const sentResetEmails = partnerEmailService.sentEmails.filter(e => e.type === 'admin_password_reset');
      assert.strictEqual(sentResetEmails.length, 0);
    });

    // SEC-RESET-02: Valid Admin Email returns generic message and dispatches security reset email
    let extractedResetToken = null;
    await test('SEC-RESET-02: Valid admin email returns generic response and dispatches security email with reset link', async () => {
      partnerEmailService.resetState();
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/forgot-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: { email: 'info@mozarex.com' }
      });

      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.message, "If an eligible administrator account exists for this email address, we've sent password reset instructions.");

      // Verify email was dispatched
      const sentResetEmails = partnerEmailService.sentEmails.filter(e => e.type === 'admin_password_reset');
      assert.strictEqual(sentResetEmails.length, 1);
      const email = sentResetEmails[0];
      assert.strictEqual(email.to, 'info@mozarex.com');
      assert.strictEqual(email.subject, 'Reset your AivekAI Admin password');
      assert.ok(email.text.includes('Reset your password by visiting this secure link:'));
      assert.ok(email.html.includes('Reset Password'));

      // Extract token from reset link
      const tokenMatch = email.text.match(/token=([a-f0-9]+)/i);
      assert.ok(tokenMatch && tokenMatch[1], 'Reset token should be present in email link');
      extractedResetToken = tokenMatch[1];
    });

    // Obtain an active admin session prior to password reset to verify session invalidation
    const preResetLogin = await makeRequest({
      port: TEST_PORT,
      path: '/api/aivekai/admin/login',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
      body: { username: 'aivekai_admin', password: 'ValidAdminPassword123!' }
    });
    assert.strictEqual(preResetLogin.statusCode, 200);
    const preResetAdminCookie = preResetLogin.headers['set-cookie']?.[0]?.split(';')[0];
    assert.ok(preResetAdminCookie);

    // Verify the pre-reset session works before reset
    const preCheck = await makeRequest({
      port: TEST_PORT,
      path: '/api/aivekai/admin/session',
      method: 'GET',
      headers: { 'Cookie': preResetAdminCookie }
    });
    assert.strictEqual(preCheck.data.authenticated, true);

    // SEC-RESET-03: Reset password with weak password or mismatched confirmation is rejected with 400
    await test('SEC-RESET-03: Reset password rejects weak password and mismatched confirmation with 400', async () => {
      // Mismatched confirmation
      const mismatchRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/reset-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          token: extractedResetToken,
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'MismatchPassword2026!#'
        }
      });
      assert.strictEqual(mismatchRes.statusCode, 400);
      assert.strictEqual(mismatchRes.data.message, 'New password and confirmation do not match.');

      // Weak password
      const weakRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/reset-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          token: extractedResetToken,
          newPassword: 'weak',
          confirmPassword: 'weak'
        }
      });
      assert.strictEqual(weakRes.statusCode, 400);
      assert.ok(weakRes.data.message.includes('10 characters'));
    });

    // SEC-RESET-04: Reset password with valid password succeeds
    await test('SEC-RESET-04: Reset password with valid parameters succeeds and returns redirect to login', async () => {
      // Small pause to guarantee timestamp distinction
      await new Promise(r => setTimeout(r, 50));

      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/reset-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          token: extractedResetToken,
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'BrandNewPass2026!#'
        }
      });

      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.message, 'Your password has been reset. Sign in with your new password.');
      assert.strictEqual(res.data.redirect_url, '/aivekai/admin/login?reset=success');

      // Check sanitized audit log
      const resetLog = mockStore.auditLogs.find(l => l.action === 'admin_password_reset' && l.status === 'success');
      assert.ok(resetLog);
      assert.strictEqual(resetLog.password, undefined);
      assert.strictEqual(resetLog.token, undefined);
    });

    // SEC-RESET-05: Old password is now rejected upon login attempt
    await test('SEC-RESET-05: Old password is rejected with generic 401 after password reset', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/login',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: { username: 'aivekai_admin', password: 'ValidAdminPassword123!' } // Old password
      });

      assert.strictEqual(res.statusCode, 401);
      assert.strictEqual(res.data.success, false);
      assert.strictEqual(res.data.message, 'Invalid username or password.');
    });

    // SEC-RESET-06: New password is accepted and successfully authenticates admin
    let postResetAdminCookie = null;
    await test('SEC-RESET-06: New password is accepted and successfully logs in admin', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/login',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: { username: 'aivekai_admin', password: 'BrandNewPass2026!#' } // New password
      });

      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.redirect_url, '/aivekai/admin/partners');
      postResetAdminCookie = res.headers['set-cookie']?.[0]?.split(';')[0];
      assert.ok(postResetAdminCookie);
    });

    // SEC-RESET-07: Old Admin sessions created prior to reset are persistently invalidated
    await test('SEC-RESET-07: Old Admin sessions created prior to password reset are revoked with 401', async () => {
      // 1. Check protected admin API endpoint with old pre-reset cookie
      const apiRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/applications',
        method: 'GET',
        headers: { 'Cookie': preResetAdminCookie }
      });
      assert.strictEqual(apiRes.statusCode, 401);
      assert.strictEqual(apiRes.data.error, 'session_invalidated');

      // 2. Check session status endpoint with old pre-reset cookie
      const sessionRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/session',
        method: 'GET',
        headers: { 'Cookie': preResetAdminCookie }
      });
      assert.strictEqual(sessionRes.data.authenticated, false);

      // 3. Verify new post-reset cookie works normally
      const newSessionRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/session',
        method: 'GET',
        headers: { 'Cookie': postResetAdminCookie }
      });
      assert.strictEqual(newSessionRes.data.authenticated, true);
    });

    // SEC-RESET-08: Reset token cannot be reused
    await test('SEC-RESET-08: Consumed reset token cannot be reused (rejected with 400)', async () => {
      const reuseRes = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/reset-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          token: extractedResetToken,
          newPassword: 'AnotherPassword2026!#',
          confirmPassword: 'AnotherPassword2026!#'
        }
      });

      assert.strictEqual(reuseRes.statusCode, 400);
      assert.strictEqual(reuseRes.data.message, 'Password reset link is invalid or has expired. Please request a new one.');
    });

    // -------------------------------------------------------------------------
    // 2. AUTHENTICATED CHANGE PASSWORD & PORTAL SECURITY TESTS
    // -------------------------------------------------------------------------

    // SEC-PW-01: Unauthenticated change password rejected with 401
    await test('SEC-PW-01: Unauthenticated request to change-password rejected with 401', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'BrandNewPass2026!#',
          newPassword: 'AnotherPass2026!#',
          confirmPassword: 'AnotherPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 401);
      assert.strictEqual(res.data.error, 'Admin authentication required');
    });

    // SEC-PW-02: Non-admin rejected with 403
    await test('SEC-PW-02: Non-admin (partner token) rejected with 403', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer mock_token_james',
          'x-csrf-token': 'valid_csrf_token'
        },
        body: {
          currentPassword: 'BrandNewPass2026!#',
          newPassword: 'AnotherPass2026!#',
          confirmPassword: 'AnotherPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 403);
      assert.strictEqual(res.data.error, 'Admin authorization required');
    });

    // SEC-PW-03: Wrong current password rejected with 401
    await test('SEC-PW-03: Wrong current password rejected with 401', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': postResetAdminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'IncorrectCurrentPass123!',
          newPassword: 'YetAnotherPass2026!#',
          confirmPassword: 'YetAnotherPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 401);
      assert.strictEqual(res.data.message, 'Current password verification failed.');
    });

    // SEC-PW-04: Valid self-service password change succeeds and updates session
    await test('SEC-PW-04: Valid self-service password change succeeds', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': postResetAdminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'BrandNewPass2026!#',
          newPassword: 'FinalAdminPassword2026!#',
          confirmPassword: 'FinalAdminPassword2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.message, 'Your administrator password has been updated successfully.');
    });

    // SEC-PW-05: Rate limiting blocks rapid password reset requests with 429
    await test('SEC-PW-05: Rate limiting blocks rapid forgot-password attempts with 429', async () => {
      let hit429 = false;
      for (let i = 0; i < 7; i++) {
        const res = await makeRequest({
          port: TEST_PORT,
          path: '/api/aivekai/admin/forgot-password',
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
          body: { email: 'info@mozarex.com' }
        });
        if (res.statusCode === 429) {
          hit429 = true;
          assert.strictEqual(res.data.error, 'too_many_attempts');
          break;
        }
      }
      assert.strictEqual(hit429, true);
    });

    // SEC-PW-06: CLI recovery script cannot elevate unauthorized accounts
    await test('SEC-PW-06: CLI recovery script cannot create or elevate arbitrary unauthorized accounts', async () => {
      await assert.rejects(
        async () => {
          await runPasswordReset('arbitrary_attacker@evil.com', {
            newPassword: 'HackedPassword2026!#',
            confirmPassword: 'HackedPassword2026!#',
            throwOnError: true
          });
        },
        (err) => {
          assert.ok(err.message.includes('No authorized') || err.message.includes('unauthorized') || err.message.includes('not found'));
          return true;
        }
      );
    });

    // SEC-PW-07: Zero plaintext passwords or reset tokens leaked in audit logs or mock store
    await test('SEC-PW-07: Zero plaintext passwords or reset tokens exist in audit logs', () => {
      for (const log of mockStore.auditLogs) {
        assert.strictEqual(log.password, undefined);
        assert.strictEqual(log.newPassword, undefined);
        assert.strictEqual(log.currentPassword, undefined);
        assert.strictEqual(log.password_hash, undefined);
        assert.strictEqual(log.token, undefined);
      }
      for (const admin of mockStore.adminUsers) {
        assert.strictEqual(admin.password, undefined);
        assert.strictEqual(admin.password_hash, undefined);
      }
    });

  } finally {
    server.close();
  }

  console.log(`\n================================================================`);
  console.log(` TEST SUMMARY: ${passed} passed, ${failed} failed`);
  console.log(`================================================================\n`);

  if (failed > 0) {
    process.exit(1);
  }
}

if (require.main === module) {
  runPasswordSecurityTests();
}

module.exports = runPasswordSecurityTests;

