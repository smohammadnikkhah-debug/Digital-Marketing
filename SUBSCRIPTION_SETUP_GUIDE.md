# Subscription System Setup Guide

This guide will help you set up the complete subscription system with Stripe integration, SendGrid email notifications, and feature restrictions.

## 🎯 Overview

The subscription system includes:
- **3 Tiers**: Starter ($49.90), Professional ($99.90), Enterprise (Contact Us)
- **7-Day Free Trial** on all paid plans
- **Monthly & Yearly Billing** with 35% discount for yearly plans
- **Feature Restrictions** based on subscription tier
- **Email Notifications** for trial, renewal, and cancellation
- **Stripe Integration** for secure payments

## 📋 Prerequisites

1. **Stripe Account** - [Create one here](https://stripe.com)
2. **SendGrid Account** - [Create one here](https://sendgrid.com)
3. **Supabase Project** - [Create one here](https://supabase.com)

## 🛠️ Setup Instructions

### 1. Stripe Configuration

#### Create Stripe Products and Prices

1. **Login to Stripe Dashboard**
2. **Go to Products** → Create the following products:

**Starter Plan:**
- Name: `Mozarex Starter`
- Description: `Perfect for small businesses getting started with SEO`
- Create prices:
  - Monthly: $49.90/month
  - Yearly: $389.34/year (35% discount)

**Professional Plan:**
- Name: `Mozarex Professional`
- Description: `Advanced features for growing businesses`
- Create prices:
  - Monthly: $99.90/month
  - Yearly: $779.22/year (35% discount)

3. **Copy the Price IDs** - You'll need these for environment variables

#### Get Stripe Keys

1. **Go to Developers** → **API Keys**
2. **Copy your keys:**
   - Publishable key (starts with `pk_`)
   - Secret key (starts with `sk_`)

#### Setup Webhooks

1. **Go to Developers** → **Webhooks**
2. **Add endpoint:** `https://yourdomain.com/api/subscription/webhook`
3. **Select events:**
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `customer.subscription.trial_will_end`
4. **Copy the webhook signing secret** (starts with `whsec_`)

### 2. SendGrid Configuration

#### Create SendGrid Templates

1. **Login to SendGrid Dashboard**
2. **Go to Email API** → **Dynamic Templates**
3. **Create the following templates:**

**Trial Welcome Template:**
- Name: `Mozarex Trial Welcome`
- Template ID: Copy this (starts with `d-`)

**Trial Ending Template:**
- Name: `Mozarex Trial Ending`
- Template ID: Copy this (starts with `d-`)

**Cancellation Template:**
- Name: `Mozarex Cancellation`
- Template ID: Copy this (starts with `d-`)

#### Get SendGrid API Key

1. **Go to Settings** → **API Keys**
2. **Create API Key** with full access
3. **Copy the API key** (starts with `SG.`)

### 3. Database Setup

#### Run the Subscription Schema

```bash
# Connect to your Supabase database and run:
psql -h your-db-host -U postgres -d postgres -f database/subscription_schema.sql
```

Or copy the SQL from `database/subscription_schema.sql` and run it in your Supabase SQL editor.

### 4. Environment Variables

Add these to your `.env` file:

```env
# Stripe Configuration
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Stripe Price IDs
STRIPE_STARTER_MONTHLY_PRICE_ID=price_your_starter_monthly_price_id
STRIPE_STARTER_YEARLY_PRICE_ID=price_your_starter_yearly_price_id
STRIPE_PROFESSIONAL_MONTHLY_PRICE_ID=price_your_professional_monthly_price_id
STRIPE_PROFESSIONAL_YEARLY_PRICE_ID=price_your_professional_yearly_price_id

# SendGrid Configuration
SENDGRID_API_KEY=SG.your_sendgrid_api_key
SENDGRID_FROM_EMAIL=noreply@mozarex.com
SENDGRID_TEST_EMAIL=test@mozarex.com

# SendGrid Template IDs
SENDGRID_TRIAL_WELCOME_TEMPLATE_ID=d_your_trial_welcome_template_id
SENDGRID_TRIAL_ENDING_TEMPLATE_ID=d_your_trial_ending_template_id
SENDGRID_CANCELLATION_TEMPLATE_ID=d_your_cancellation_template_id

# Subscription Settings
TRIAL_DURATION_DAYS=7
YEARLY_DISCOUNT_PERCENTAGE=35
ENABLE_FEATURE_RESTRICTIONS=true
ENABLE_TRIAL_SYSTEM=true
ENABLE_EMAIL_NOTIFICATIONS=true

# Existing Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

### 5. Update Frontend

#### Update Subscription Page

1. **Open `frontend/subscription.html`**
2. **Update Stripe publishable key:**
   ```javascript
   stripe = Stripe('pk_test_your_stripe_publishable_key');
   ```

### 6. Test the System

#### Test Stripe Integration

```bash
# Test subscription plans endpoint
curl http://localhost:3000/api/subscription/plans

# Test trial creation (replace with actual data)
curl -X POST http://localhost:3000/api/subscription/trial/start \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "name": "Test User",
    "plan": "professional",
    "billingCycle": "monthly"
  }'
```

#### Test Email Templates

```bash
# Test email configuration
curl -X POST http://localhost:3000/api/subscription/test-email \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com"
  }'
```

## 🎨 Customization

### Modify Pricing

Edit `services/subscriptionService.js`:

```javascript
const SUBSCRIPTION_PLANS = {
    starter: {
        monthly: {
            price: 4990, // $49.90 in cents
        },
        yearly: {
            price: 38934, // $49.90 * 12 * 0.65 = $389.34 in cents
        }
    },
    // ... other plans
};
```

### Add New Features

1. **Add feature to `FEATURES` object** in `services/featureAccessMiddleware.js`
2. **Update plan restrictions** in `services/subscriptionService.js`
3. **Apply middleware** to protected routes

### Customize Email Templates

Edit the templates in `services/emailTemplates.js` or create dynamic templates in SendGrid.

## 🔒 Security Considerations

1. **Environment Variables**: Never commit `.env` files to version control
2. **Webhook Verification**: Always verify Stripe webhooks using the signing secret
3. **API Keys**: Rotate keys regularly and use least privilege access
4. **HTTPS**: Ensure all endpoints use HTTPS in production

## 🚀 Deployment

### Production Checklist

- [ ] Update Stripe keys to live keys
- [ ] Update webhook URL to production domain
- [ ] Set up SSL certificate
- [ ] Configure SendGrid domain authentication
- [ ] Test all payment flows
- [ ] Monitor webhook delivery
- [ ] Set up error logging

### Environment Variables for Production

```env
# Production Stripe Keys
STRIPE_SECRET_KEY=sk_live_your_live_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=pk_live_your_live_stripe_publishable_key

# Production SendGrid
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# Production Settings
ENABLE_FEATURE_RESTRICTIONS=true
```

## 📊 Monitoring

### Key Metrics to Track

1. **Trial Conversion Rate**
2. **Monthly Recurring Revenue (MRR)**
3. **Churn Rate**
4. **Feature Usage by Plan**
5. **Email Delivery Rates**

### Stripe Dashboard

Monitor these in your Stripe dashboard:
- Revenue trends
- Failed payments
- Customer lifetime value
- Subscription metrics

## 🆘 Troubleshooting

### Common Issues

**1. Stripe Webhook Not Working**
- Check webhook URL is accessible
- Verify webhook signing secret
- Check webhook event types

**2. Email Not Sending**
- Verify SendGrid API key
- Check template IDs
- Verify sender email is authenticated

**3. Feature Restrictions Not Working**
- Check `ENABLE_FEATURE_RESTRICTIONS=true`
- Verify user subscription status
- Check feature names match exactly

**4. Database Connection Issues**
- Verify Supabase credentials
- Check database schema is applied
- Ensure proper permissions

### Debug Mode

Enable debug logging:

```env
DEBUG_SUBSCRIPTION=true
DEBUG_EMAIL=true
DEBUG_STRIPE=true
```

## 📞 Support

For issues with this subscription system:
1. Check the troubleshooting section above
2. Review server logs for error messages
3. Test individual components (Stripe, SendGrid, Database)
4. Contact support if issues persist

## 🔄 Updates

To update the subscription system:
1. Backup your database
2. Test changes in development
3. Update environment variables
4. Deploy to production
5. Monitor for issues

---

**Note**: This system is designed to be flexible and customizable. Feel free to modify the plans, features, and email templates to match your specific needs.
