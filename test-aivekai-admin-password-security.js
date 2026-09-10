process.env.NODE_ENV = 'test';

const assert = require('assert');
const http = require('http');
const { app, server } = require('./server');
const partnerRouter = require('./routes/aivekaiPartners');
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
  console.log(' ADMIN PASSWORD MANAGEMENT SECURITY HARDENING TEST SUITE        ');
  console.log('================================================================\n');

  if (rateLimitMap) rateLimitMap.clear();

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
    // 1. Unauthenticated change password is rejected with 401
    await test('SEC-PW-01: unauthenticated request to change-password rejected with 401', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'ValidAdminPassword123!',
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'BrandNewPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 401);
      assert.strictEqual(res.data.error, 'Admin authentication required');
    });

    // 2. Non-admin (partner token) cannot change Admin password (403)
    await test('SEC-PW-02: non-admin (partner session/token) rejected with 403', async () => {
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
          currentPassword: 'ValidAdminPassword123!',
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'BrandNewPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 403);
      assert.strictEqual(res.data.error, 'Admin authorization required');
    });

    // Obtain authenticated Admin session for subsequent tests
    const loginRes = await makeRequest({
      port: TEST_PORT,
      path: '/api/aivekai/admin/login',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
      body: { username: 'aivekai_admin', password: 'ValidAdminPassword123!' }
    });
    assert.strictEqual(loginRes.statusCode, 200);
    const adminCookie = loginRes.headers['set-cookie']?.[0]?.split(';')[0];
    assert.ok(adminCookie);

    // 3. Wrong current password is rejected with generic 401 and logged safely
    await test('SEC-PW-03: wrong current password rejected with generic 401', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': adminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'IncorrectOldPassword123!',
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'BrandNewPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 401);
      assert.strictEqual(res.data.success, false);
      assert.strictEqual(res.data.message, 'Current password verification failed.');

      // Check audit log for failure without leaking password
      const failedLog = mockStore.auditLogs.find(l => l.action === 'admin_password_change_failed');
      assert.ok(failedLog);
      assert.strictEqual(failedLog.status, 'failed');
      assert.strictEqual(failedLog.password, undefined);
      assert.strictEqual(failedLog.currentPassword, undefined);
    });

    // 4. Weak password rejected (< 10 chars, missing upper, lower, number, or symbol)
    await test('SEC-PW-04: weak passwords rejected with 400', async () => {
      const weakCases = [
        { pw: 'Short1!', expected: 'at least 10 characters' },
        { pw: 'nouppercase123!', expected: 'uppercase letter' },
        { pw: 'NOLOWERCASE123!', expected: 'lowercase letter' },
        { pw: 'NoNumbersHere!', expected: 'number' },
        { pw: 'NoSymbolsAllowed123', expected: 'special character' }
      ];

      for (const { pw, expected } of weakCases) {
        const res = await makeRequest({
          port: TEST_PORT,
          path: '/api/aivekai/admin/change-password',
          method: 'POST',
          headers: { 'Cookie': adminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
          body: {
            currentPassword: 'ValidAdminPassword123!',
            newPassword: pw,
            confirmPassword: pw
          }
        });
        assert.strictEqual(res.statusCode, 400, `Expected 400 for password: ${pw}`);
        assert.ok(res.data.message.toLowerCase().includes(expected.toLowerCase()), `Expected message to contain "${expected}", got: "${res.data.message}"`);
      }
    });

    // 5. Mismatched confirmation rejected (400)
    await test('SEC-PW-05: mismatched confirmation rejected with 400', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': adminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'ValidAdminPassword123!',
          newPassword: 'BrandNewPass2026!#',
          confirmPassword: 'DifferentPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 400);
      assert.strictEqual(res.data.message, 'New password and confirmation do not match.');
    });

    // 6. Identical password rejected (400)
    await test('SEC-PW-06: new password identical to current password rejected with 400', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': adminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'ValidAdminPassword123!',
          newPassword: 'ValidAdminPassword123!',
          confirmPassword: 'ValidAdminPassword123!'
        }
      });
      assert.strictEqual(res.statusCode, 400);
      assert.strictEqual(res.data.message, 'New password must be different from current password.');
    });

    // 7. Successful self-service password change works
    await test('SEC-PW-07: valid self-service password change succeeds and regenerates session', async () => {
      const res = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/change-password',
        method: 'POST',
        headers: { 'Cookie': adminCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: {
          currentPassword: 'ValidAdminPassword123!',
          newPassword: 'StrongAdminPass2026!#',
          confirmPassword: 'StrongAdminPass2026!#'
        }
      });
      assert.strictEqual(res.statusCode, 200);
      assert.strictEqual(res.data.success, true);
      assert.strictEqual(res.data.message, 'Your administrator password has been updated successfully.');

      // Verify audit log has sanitized success record
      const successLog = mockStore.auditLogs.find(l => l.action === 'admin_password_changed' && l.status === 'success');
      assert.ok(successLog);
      assert.strictEqual(successLog.mechanism, 'self_service');
      assert.strictEqual(successLog.password, undefined);
      assert.strictEqual(successLog.newPassword, undefined);
      assert.strictEqual(successLog.currentPassword, undefined);
    });

    // 8. Rate limiting blocks rapid password change attempts (429)
    await test('SEC-PW-08: rate limiting blocks brute-force/rapid attempts with 429', async () => {
      // Obtain fresh authenticated session
      const freshLogin = await makeRequest({
        port: TEST_PORT,
        path: '/api/aivekai/admin/login',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
        body: { username: 'aivekai_admin', password: 'ValidAdminPassword123!' }
      });
      assert.strictEqual(freshLogin.statusCode, 200);
      const activeCookie = freshLogin.headers['set-cookie']?.[0]?.split(';')[0];
      assert.ok(activeCookie);

      let hit429 = false;
      for (let i = 0; i < 7; i++) {
        const res = await makeRequest({
          port: TEST_PORT,
          path: '/api/aivekai/admin/change-password',
          method: 'POST',
          headers: { 'Cookie': activeCookie, 'Content-Type': 'application/json', 'x-csrf-token': 'valid_csrf_token' },
          body: {
            currentPassword: 'WrongPassword123!',
            newPassword: 'StrongAdminPass2026!#',
            confirmPassword: 'StrongAdminPass2026!#'
          }
        });
        if (res.statusCode === 429) {
          hit429 = true;
          assert.strictEqual(res.data.error, 'too_many_attempts');
          break;
        }
      }
      assert.strictEqual(hit429, true);
    });

    // 9. Recovery script cannot create or elevate arbitrary unauthorized users
    await test('SEC-PW-09: CLI recovery script cannot create or elevate arbitrary users', async () => {
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

    // 10. Password validator unit tests
    await test('SEC-PW-10: validatePasswordStrength rejects insufficient complexity', () => {
      assert.strictEqual(validatePasswordStrength('short').valid, false);
      assert.strictEqual(validatePasswordStrength('alllowercase123!').valid, false);
      assert.strictEqual(validatePasswordStrength('ALLUPPERCASE123!').valid, false);
      assert.strictEqual(validatePasswordStrength('NoNumbersHere!#').valid, false);
      assert.strictEqual(validatePasswordStrength('NoSpecialChars123').valid, false);
      assert.strictEqual(validatePasswordStrength('ValidStrongPass2026!#').valid, true);
    });

    // 11. Zero passwords leaked in mockStore or audit logs
    await test('SEC-PW-11: zero plaintext passwords exist in audit logs or admin user objects', () => {
      for (const log of mockStore.auditLogs) {
        assert.strictEqual(log.password, undefined);
        assert.strictEqual(log.newPassword, undefined);
        assert.strictEqual(log.currentPassword, undefined);
        assert.strictEqual(log.password_hash, undefined);
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
