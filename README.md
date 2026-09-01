# Mozarex Platform & AivekAI Backend

Web platform and backend services for Mozarex apps, including the AivekAI Partner Program, Creator Portal, and Nutrition AI services.

---

## 🚀 Key Features

* **AivekAI Marketing & Apps**: Public marketing pages for AivekAI, Puratryx, and StopTimetryx.
* **AivekAI Partner Program**:
  * Public Partner landing page and Creator application form.
  * Partner Dashboard (multi-currency balances, referral links, commission history).
  * Automated Creator Payout settings with PayPal account configuration.
* **Admin Partner Management**:
  * Creator application review & approval.
  * Commission ledger inspection & manual adjustments.
  * PayPal Payout batch management (approval, execution via PayPal Payouts API, status reconciliation).
* **AivekAI Nutrition & AI Backend**:
  * Anonymous signed session tokens with abuse prevention.
  * OpenAI GPT-4o vision nutrition label and food plate image analysis.
  * Scientific macro and biometric calculations with server-side usage telemetry.

---

## 🛠️ Environment Configuration

Copy `.env.example` to `.env` and configure:

```env
NODE_ENV=development
PORT=3000
SESSION_SECRET=your_session_secret

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

OPENAI_API_KEY=your_openai_api_key
AIVEKAI_SESSION_SIGNING_SECRET=your_signing_secret

PAYPAL_ENVIRONMENT=sandbox
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_WEBHOOK_ID=your_paypal_webhook_id
```

---

## 🧪 Testing

Run all automated test suites:

```bash
npm test
```