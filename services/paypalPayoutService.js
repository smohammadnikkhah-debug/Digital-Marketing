const https = require('https');

/**
 * PayPal Payouts Integration Service for AivekAI Partner Program
 * Handles OAuth 2.0 client credential caching, payout submission, batch & item lookups,
 * webhook verification, and state reconciliation.
 */
class PaypalPayoutService {
  constructor() {
    this.clientId = process.env.PAYPAL_CLIENT_ID || 'mock_paypal_client_id';
    this.clientSecret = process.env.PAYPAL_CLIENT_SECRET || 'mock_paypal_client_secret';
    this.webhookId = process.env.PAYPAL_WEBHOOK_ID || 'mock_paypal_webhook_id';
    this.environment = (process.env.PAYPAL_ENVIRONMENT || 'sandbox').toLowerCase();

    // Base URL configuration
    this.baseUrl = this.environment === 'live'
      ? 'https://api-m.paypal.com'
      : 'https://api-m.sandbox.paypal.com';

    // Cached OAuth token
    this.cachedToken = null;
    this.tokenExpiresAt = 0;
  }

  /**
   * Helper HTTP request wrapper
   */
  async _request(options, postData = null) {
    if (this.clientId.startsWith('mock_')) {
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
   * Internal mock handler for local development & automated test suites
   */
  _handleMockRequest(options, postData) {
    const path = options.path;

    if (path.includes('/v1/oauth2/token')) {
      return Promise.resolve({
        statusCode: 200,
        data: {
          access_token: `mock_paypal_token_${Date.now()}`,
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
          links: [{ href: `${this.baseUrl}/v1/payments/payouts/${batchId}`, rel: 'self' }]
        }
      });
    }

    if (path.includes('/v1/payments/payouts/')) {
      const batchId = path.split('/').pop();
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
   * Obtain and cache OAuth 2.0 Access Token
   */
  async getAccessToken() {
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
      raw_response: response.data
    };
  }

  /**
   * Get PayPal Payout Batch Details
   */
  async getPayoutBatch(payoutBatchId) {
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
   * Explicitly separates pre-delivery failures vs. post-delivery returns vs. in-flight
   */
  normalizePayPalStatus(status) {
    if (!status) return 'submitted';
    const s = status.toUpperCase();

    // 1. Success (funds delivered)
    if (s === 'SUCCESS') {
      return 'paid';
    }

    // 2. Pre-delivery rejection (funds never left our balance)
    if (['DENIED', 'FAILED', 'BLOCKED'].includes(s)) {
      return 'failed';
    }

    // 3. Post-delivery return / reversal (funds returned after submission/delivery - requires manual accounting review)
    if (['RETURNED', 'REFUNDED', 'REVERSED'].includes(s)) {
      return 'reversed';
    }

    // 4. In-flight / pending delivery (funds held by PayPal, recipient pending claim)
    if (['PENDING', 'UNCLAIMED', 'PROCESSING', 'ONHOLD'].includes(s)) {
      return 'submitted';
    }

    return 'submitted';
  }

  /**
   * Verify PayPal Webhook Authenticity
   */
  async verifyWebhook({ headers, rawBody, webhookId }) {
    const actualWebhookId = webhookId || this.webhookId;
    if (!actualWebhookId) {
      return false;
    }

    if (this.clientId.startsWith('mock_')) {
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
