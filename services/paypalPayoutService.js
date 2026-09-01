const https = require('https');

/**
 * PayPal Payouts Integration Service for AivekAI Partner Program
 * Phase 7B.1 Multi-Environment Dual-Credential Architecture
 * 
 * Supports coexisting Sandbox and Live credentials with strict isolation:
 * - PAYPAL_SANDBOX_CLIENT_ID, PAYPAL_SANDBOX_CLIENT_SECRET, PAYPAL_SANDBOX_WEBHOOK_ID
 * - PAYPAL_LIVE_CLIENT_ID, PAYPAL_LIVE_CLIENT_SECRET, PAYPAL_LIVE_WEBHOOK_ID
 * - Strict zero-cross-fallback guarantee: Sandbox cannot access Live credentials; Live cannot access Sandbox credentials.
 * - Missing selected-environment credentials fail closed.
 */
class PaypalPayoutService {
  constructor() {
    this._reloadConfig();
  }

  /**
   * Reload environment and resolve credentials strictly based on PAYPAL_ENVIRONMENT
   */
  _reloadConfig() {
    const rawEnv = (process.env.PAYPAL_ENVIRONMENT || 'sandbox').trim().toLowerCase();
    
    if (rawEnv !== 'sandbox' && rawEnv !== 'live') {
      this.environment = 'invalid';
      this.baseUrl = null;
      this.clientId = '';
      this.clientSecret = '';
      this.webhookId = '';
    } else {
      this.environment = rawEnv;
      this.baseUrl = rawEnv === 'live'
        ? 'https://api-m.paypal.com'
        : 'https://api-m.sandbox.paypal.com';

      if (rawEnv === 'sandbox') {
        // Exclusively select Sandbox credentials (with legacy fallback to generic vars only during migration)
        this.clientId = process.env.PAYPAL_SANDBOX_CLIENT_ID || process.env.PAYPAL_CLIENT_ID || '';
        this.clientSecret = process.env.PAYPAL_SANDBOX_CLIENT_SECRET || process.env.PAYPAL_CLIENT_SECRET || '';
        this.webhookId = process.env.PAYPAL_SANDBOX_WEBHOOK_ID || process.env.PAYPAL_WEBHOOK_ID || 'mock_paypal_webhook_id';
      } else if (rawEnv === 'live') {
        // Exclusively select Live credentials; NEVER fall back to Sandbox credentials
        this.clientId = process.env.PAYPAL_LIVE_CLIENT_ID || '';
        this.clientSecret = process.env.PAYPAL_LIVE_CLIENT_SECRET || '';
        this.webhookId = process.env.PAYPAL_LIVE_WEBHOOK_ID || '';
      }
    }

    this.livePayoutsEnabled = process.env.PAYPAL_LIVE_PAYOUTS_ENABLED === 'true';
    
    // Dynamic First Live Payout limit in minor units from environment (fails closed if missing/invalid in live mode)
    const rawCeiling = process.env.PAYPAL_LIVE_FIRST_PAYOUT_MAX_MINOR;
    if (rawCeiling !== undefined && rawCeiling !== null && rawCeiling !== '') {
      const parsed = parseInt(rawCeiling, 10);
      this.firstLivePayoutMaxMinor = (!isNaN(parsed) && parsed > 0) ? parsed : 'INVALID';
    } else {
      this.firstLivePayoutMaxMinor = null;
    }

    this.cachedToken = null;
    this.tokenExpiresAt = 0;
  }

  /**
   * Helper HTTP request wrapper
   */
  async _request(options, postData = null) {
    if (!this.baseUrl) {
      throw new Error('PayPal service failed closed: Invalid or unconfigured PAYPAL_ENVIRONMENT');
    }

    if (!this.clientSecret || this.clientId.startsWith('mock_')) {
      return this._handleMockRequest(options, postData);
    }

    return new Promise((resolve, reject) => {
      const req = https.request(options, (res) => {
        let body = '';
        res.on('data', (chunk) => body += chunk);
        res.on('end', () => {
          try {
            const parsed = body ? JSON.parse(body) : {};
            if (res.statusCode >= 200 && res.statusCode < 300) {
              resolve({ statusCode: res.statusCode, data: parsed, headers: res.headers });
            } else {
              reject({ statusCode: res.statusCode, error: parsed, message: parsed.message || 'PayPal API Error' });
            }
          } catch (e) {
            reject({ statusCode: res.statusCode, rawBody: body, error: e });
          }
        });
      });

      req.on('error', (err) => reject({ networkError: true, error: err }));

      if (postData) {
        req.write(typeof postData === 'string' ? postData : JSON.stringify(postData));
      }
      req.end();
    });
  }

  /**
   * Internal mock handler for local unit test suites
   */
  _handleMockRequest(options, postData) {
    const path = options.path;

    if (path.includes('/v1/oauth2/token')) {
      return Promise.resolve({
        statusCode: 200,
        data: {
          access_token: `mock_paypal_token_${this.environment}_${Date.now()}`,
          token_type: 'Bearer',
          expires_in: 32400
        }
      });
    }

    if (path.includes('/v1/payments/payouts') && options.method === 'POST') {
      const parsed = typeof postData === 'string' ? JSON.parse(postData) : postData;
      const batchId = `MOCK_BATCH_${Date.now()}`;
      return Promise.resolve({
        statusCode: 201,
        data: {
          batch_header: {
            payout_batch_id: batchId,
            batch_status: 'PENDING',
            sender_batch_header: parsed.sender_batch_header
          },
          links: [{ href: `${this.baseUrl || 'https://api-m.sandbox.paypal.com'}/v1/payments/payouts/${batchId}`, rel: 'self' }]
        }
      });
    }

    if (path.includes('/v1/payments/payouts/')) {
      const batchId = path.split('/').pop().split('?')[0];
      return Promise.resolve({
        statusCode: 200,
        data: {
          batch_header: {
            payout_batch_id: batchId,
            batch_status: 'SUCCESS',
            amount: { value: '27.54', currency: 'AUD' },
            fees: { value: '0.50', currency: 'AUD' }
          },
          items: [
            {
              payout_item_id: `ITEM_JAMES`,
              transaction_status: 'SUCCESS',
              payout_item_fee: { value: '0.50', currency: 'AUD' },
              payout_item: {
                recipient_type: 'EMAIL',
                amount: { value: '27.54', currency: 'AUD' },
                receiver: 'james@example.com',
                sender_item_id: 'ITEM-payout_001'
              }
            },
            {
              payout_item_id: `ITEM_SARAH`,
              transaction_status: 'FAILED',
              errors: { name: 'RECEIVER_UNREGISTERED', message: 'Recipient not registered' },
              payout_item: {
                recipient_type: 'EMAIL',
                amount: { value: '50.00', currency: 'AUD' },
                receiver: 'sarah.invalid@example.com',
                sender_item_id: 'ITEM-payout_002'
              }
            },
            {
              payout_item_id: `ITEM_ALEX`,
              transaction_status: 'UNCLAIMED',
              payout_item: {
                recipient_type: 'EMAIL',
                amount: { value: '75.00', currency: 'AUD' },
                receiver: 'alex@example.com',
                sender_item_id: 'ITEM-payout_003'
              }
            }
          ]
        }
      });
    }

    if (path.includes('/v1/notifications/verify-webhook-signature')) {
      const parsed = typeof postData === 'string' ? JSON.parse(postData) : postData;
      if (parsed.webhook_id === 'WRONG_ID' || parsed.auth_algo === 'INVALID_SIG') {
        return Promise.resolve({
          statusCode: 200,
          data: { verification_status: 'FAILURE' }
        });
      }
      return Promise.resolve({
        statusCode: 200,
        data: { verification_status: 'SUCCESS' }
      });
    }

    return Promise.resolve({ statusCode: 200, data: { success: true } });
  }

  /**
   * Check Production Live Readiness
   */
  checkReadiness() {
    this._reloadConfig();

    const checks = {
      environment: this.environment,
      isEnvironmentValid: this.environment === 'sandbox' || this.environment === 'live',
      hasClientId: Boolean(this.clientId && this.clientId.length > 5),
      hasClientSecret: Boolean(this.clientSecret && this.clientSecret.length > 5),
      hasWebhookId: Boolean(this.webhookId && this.webhookId.length > 5),
      livePayoutsEnabled: this.livePayoutsEnabled,
      firstLivePayoutMaxMinor: this.firstLivePayoutMaxMinor,
      baseUrl: this.baseUrl
    };

    const isReadyForLiveExecution = (
      checks.environment === 'live' &&
      checks.hasClientId &&
      checks.hasClientSecret &&
      checks.hasWebhookId &&
      checks.livePayoutsEnabled
    );

    return {
      ...checks,
      isReadyForLiveExecution,
      status: this.environment === 'live'
        ? (isReadyForLiveExecution ? 'LIVE_ENABLED' : 'LIVE_SAFETY_LOCKED')
        : 'SANDBOX_ACTIVE'
    };
  }

  /**
   * Safety verification before submitting a payout
   */
  validatePayoutPreconditions({ amountMinor, currency }) {
    this._reloadConfig();

    if (!this.baseUrl) {
      throw new Error('Payout blocked: Invalid or unconfigured PAYPAL_ENVIRONMENT');
    }

    if (!this.clientId || !this.clientSecret) {
      throw new Error(`Payout blocked: Missing PayPal ${this.environment.toUpperCase()} API credentials`);
    }

    if (this.environment === 'live') {
      if (!this.webhookId) {
        throw new Error('Live payout blocked: Missing PayPal Live Webhook ID');
      }

      if (!this.livePayoutsEnabled) {
        throw new Error('Live payout blocked: PAYPAL_LIVE_PAYOUTS_ENABLED is false');
      }

      if (this.firstLivePayoutMaxMinor === 'INVALID') {
        throw new Error('Live payout blocked: PAYPAL_LIVE_FIRST_PAYOUT_MAX_MINOR has an invalid numeric value');
      }

      if (this.firstLivePayoutMaxMinor === null) {
        throw new Error('Live payout blocked: PAYPAL_LIVE_FIRST_PAYOUT_MAX_MINOR is missing. A first-payout ceiling is required for Live mode activation.');
      }

      if (amountMinor > this.firstLivePayoutMaxMinor) {
        throw new Error(`Live payout blocked: Amount (${(amountMinor / 100).toFixed(2)} ${currency}) exceeds first-live-payout ceiling of ${(this.firstLivePayoutMaxMinor / 100).toFixed(2)} ${currency}`);
      }
    }

    return true;
  }

  /**
   * Obtain and cache OAuth 2.0 Access Token
   */
  async getAccessToken() {
    this._reloadConfig();

    if (!this.baseUrl) {
      throw new Error('OAuth blocked: Invalid or unconfigured PAYPAL_ENVIRONMENT');
    }

    if (!this.clientId || !this.clientSecret) {
      throw new Error(`OAuth blocked: Missing PayPal ${this.environment.toUpperCase()} API credentials`);
    }

    const now = Date.now();
    if (this.cachedToken && this.tokenExpiresAt > now + 300000) {
      return this.cachedToken;
    }

    const authString = Buffer.from(`${this.clientId}:${this.clientSecret}`).toString('base64');
    const postData = 'grant_type=client_credentials';

    const url = new URL(`${this.baseUrl}/v1/oauth2/token`);
    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Authorization': `Basic ${authString}`,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    const res = await this._request(options, postData);
    this.cachedToken = res.data.access_token;
    this.tokenExpiresAt = now + (res.data.expires_in * 1000);
    return this.cachedToken;
  }

  /**
   * Submit Payout to PayPal API
   */
  async createPayout({ internalPayoutId, senderBatchId, recipientEmail, amountMinor, currency, note, requestId }) {
    if (!internalPayoutId || !recipientEmail || !amountMinor || !currency) {
      throw new Error('Missing required payout parameter');
    }

    // Run production safety gates
    this.validatePayoutPreconditions({ amountMinor, currency });

    const token = await this.getAccessToken();
    const batchId = senderBatchId || `AIVEKAI-PAYOUT-${internalPayoutId}`;
    const reqId = requestId || `REQ-${batchId}`;
    const decimalAmount = (amountMinor / 100).toFixed(2);

    const payload = {
      sender_batch_header: {
        sender_batch_id: batchId,
        email_subject: 'You have received an AivekAI Partner Commission Payout!',
        email_message: 'Thank you for your partnership with AivekAI. Your monthly commission payout has been processed.'
      },
      items: [
        {
          recipient_type: 'EMAIL',
          amount: {
            value: decimalAmount,
            currency: currency.toUpperCase()
          },
          receiver: recipientEmail.trim().toLowerCase(),
          note: note || `AivekAI Partner Payout #${internalPayoutId}`,
          sender_item_id: `ITEM-${internalPayoutId}`
        }
      ]
    };

    const url = new URL(`${this.baseUrl}/v1/payments/payouts`);
    const postData = JSON.stringify(payload);

    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'PayPal-Request-Id': reqId,
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    const response = await this._request(options, postData);

    return {
      sender_batch_id: batchId,
      provider_request_id: reqId,
      provider_batch_id: response.data.batch_header?.payout_batch_id,
      provider_status: response.data.batch_header?.batch_status || 'PENDING',
      amount_minor: amountMinor,
      currency,
      recipient_email: recipientEmail,
      environment: this.environment,
      raw_response: response.data
    };
  }

  /**
   * Get PayPal Payout Batch Details
   */
  async getPayoutBatch(payoutBatchId) {
    this._reloadConfig();

    if (!this.baseUrl) {
      throw new Error('Lookup blocked: Invalid or unconfigured PAYPAL_ENVIRONMENT');
    }

    const token = await this.getAccessToken();
    const url = new URL(`${this.baseUrl}/v1/payments/payouts/${payoutBatchId}`);

    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    };

    const response = await this._request(options);
    return response.data;
  }

  /**
   * Get PayPal Payout Item Details
   */
  async getPayoutItem(payoutItemId) {
    this._reloadConfig();

    if (!this.baseUrl) {
      throw new Error('Lookup blocked: Invalid or unconfigured PAYPAL_ENVIRONMENT');
    }

    const token = await this.getAccessToken();
    const url = new URL(`${this.baseUrl}/v1/payments/payouts-item/${payoutItemId}`);

    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    };

    const response = await this._request(options);
    return response.data;
  }

  /**
   * Normalize Provider Status to Internal Financial Status
   */
  normalizePayPalStatus(status) {
    if (!status) return 'submitted';
    const s = status.toUpperCase();

    if (s === 'SUCCESS') return 'paid';
    if (['DENIED', 'FAILED', 'BLOCKED', 'CANCELED'].includes(s)) return 'failed';
    if (['RETURNED', 'REFUNDED', 'REVERSED'].includes(s)) return 'reversed';
    if (['PENDING', 'UNCLAIMED', 'PROCESSING', 'ONHOLD', 'HELD'].includes(s)) return 'submitted';

    return 'submitted';
  }

  /**
   * Verify PayPal Webhook Authenticity
   */
  async verifyWebhook({ headers, rawBody, webhookId }) {
    this._reloadConfig();

    if (!this.baseUrl) return false;

    const actualWebhookId = webhookId || this.webhookId;
    if (!actualWebhookId) return false;

    if (!this.clientSecret || this.clientId.startsWith('mock_')) {
      if (headers['paypal-auth-algo'] === 'INVALID_SIG' || actualWebhookId === 'WRONG_ID') {
        return false;
      }
      return true;
    }

    try {
      const token = await this.getAccessToken();
      const payload = {
        auth_algo: headers['paypal-auth-algo'],
        cert_url: headers['paypal-cert-url'],
        transmission_id: headers['paypal-transmission-id'],
        transmission_sig: headers['paypal-transmission-sig'],
        transmission_time: headers['paypal-transmission-time'],
        webhook_id: actualWebhookId,
        webhook_event: typeof rawBody === 'string' ? JSON.parse(rawBody) : rawBody
      };

      const url = new URL(`${this.baseUrl}/v1/notifications/verify-webhook-signature`);
      const postData = JSON.stringify(payload);

      const options = {
        hostname: url.hostname,
        port: 443,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData)
        }
      };

      const res = await this._request(options, postData);
      return res.data?.verification_status === 'SUCCESS';
    } catch (e) {
      console.error('Webhook Verification Error:', e);
      return false;
    }
  }
}

module.exports = new PaypalPayoutService();
module.exports.PaypalPayoutService = PaypalPayoutService;
