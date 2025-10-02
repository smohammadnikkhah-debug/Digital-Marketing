const express = require('express');
const router = express.Router();
const stripeService = require('../services/stripeService');

// Get all products for pricing page
router.get('/products', async (req, res) => {
  try {
    const products = await stripeService.getFormattedProducts();
    res.json({ success: true, products });
  } catch (error) {
    console.error('Error fetching products:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to fetch products',
      details: error.message 
    });
  }
});

// Get a specific product
router.get('/products/:productId', async (req, res) => {
  try {
    const product = await stripeService.getProduct(req.params.productId);
    res.json({ success: true, product });
  } catch (error) {
    console.error('Error fetching product:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to fetch product',
      details: error.message 
    });
  }
});

// Create checkout session
router.post('/create-checkout-session', async (req, res) => {
  try {
    const { priceId, successUrl, cancelUrl, customerEmail, trialPeriodDays } = req.body;
    
    if (!priceId) {
      return res.status(400).json({
        success: false,
        error: 'Price ID is required'
      });
    }

    const session = await stripeService.createCheckoutSession(
      priceId,
      successUrl || `${req.protocol}://${req.get('host')}/dashboard-mantis-v2`,
      cancelUrl || `${req.protocol}://${req.get('host')}/plans`,
      customerEmail,
      trialPeriodDays
    );

    res.json({ success: true, sessionId: session.id, url: session.url });
  } catch (error) {
    console.error('Error creating checkout session:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to create checkout session',
      details: error.message 
    });
  }
});

// Get price details
router.get('/prices/:priceId', async (req, res) => {
  try {
    const price = await stripeService.getPrice(req.params.priceId);
    res.json({ success: true, price });
  } catch (error) {
    console.error('Error fetching price:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to fetch price',
      details: error.message 
    });
  }
});

// Stripe webhook handler
router.post('/webhook', express.raw({type: 'application/json'}), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;

  try {
    event = stripeService.verifyWebhookSignature(req.body, sig, webhookSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  // Handle the event
  try {
    switch (event.type) {
      case 'checkout.session.completed':
        await stripeService.handleCheckoutSessionCompleted(event.data.object);
        break;
      case 'customer.subscription.created':
        await stripeService.handleSubscriptionCreated(event.data.object);
        break;
      case 'customer.subscription.updated':
        await stripeService.handleSubscriptionUpdated(event.data.object);
        break;
      case 'customer.subscription.deleted':
        await stripeService.handleSubscriptionDeleted(event.data.object);
        break;
      case 'invoice.payment_succeeded':
        await stripeService.handlePaymentSucceeded(event.data.object);
        break;
      case 'invoice.payment_failed':
        await stripeService.handlePaymentFailed(event.data.object);
        break;
      default:
        console.log(`Unhandled event type ${event.type}`);
    }

    res.json({ received: true });
  } catch (error) {
    console.error('Error handling webhook:', error);
    res.status(500).json({ error: 'Webhook handler failed' });
  }
});

module.exports = router;
