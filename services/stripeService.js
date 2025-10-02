const Stripe = require('stripe');
const fs = require('fs');
const path = require('path');

class StripeService {
  constructor() {
    this.loadEnvironmentVariables();
    this.stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
    this.isTestMode = process.env.NODE_ENV === 'development';
  }

  // Load environment variables from .env
  loadEnvironmentVariables() {
    const envPath = path.join(__dirname, '..', '.env');
    if (fs.existsSync(envPath)) {
      const envContent = fs.readFileSync(envPath, 'utf8');
      const lines = envContent.split('\n');
      
      lines.forEach(line => {
        const trimmedLine = line.trim();
        if (trimmedLine && !trimmedLine.startsWith('#')) {
          const [key, ...valueParts] = trimmedLine.split('=');
          if (key && valueParts.length > 0) {
            const value = valueParts.join('=');
            process.env[key] = value;
          }
        }
      });
      console.log('✅ Loaded environment variables from .env');
    }
  }

  // Get all products with their prices
  async getProducts() {
    try {
      const products = await this.stripe.products.list({
        active: true,
        expand: ['data.default_price']
      });

      const productsWithPrices = await Promise.all(
        products.data.map(async (product) => {
          const prices = await this.stripe.prices.list({
            product: product.id,
            active: true
          });

          return {
            id: product.id,
            name: product.name,
            description: product.description,
            metadata: product.metadata,
            prices: prices.data.map(price => ({
              id: price.id,
              amount: price.unit_amount,
              currency: price.currency,
              interval: price.recurring?.interval,
              interval_count: price.recurring?.interval_count,
              type: price.type
            }))
          };
        })
      );

      return productsWithPrices;
    } catch (error) {
      console.error('Error fetching Stripe products:', error);
      throw error;
    }
  }

  // Get a specific product by ID
  async getProduct(productId) {
    try {
      const product = await this.stripe.products.retrieve(productId, {
        expand: ['default_price']
      });

      const prices = await this.stripe.prices.list({
        product: product.id,
        active: true
      });

      return {
        id: product.id,
        name: product.name,
        description: product.description,
        metadata: product.metadata,
        prices: prices.data.map(price => ({
          id: price.id,
          amount: price.unit_amount,
          currency: price.currency,
          interval: price.recurring?.interval,
          interval_count: price.recurring?.interval_count,
          type: price.type
        }))
      };
    } catch (error) {
      console.error('Error fetching Stripe product:', error);
      throw error;
    }
  }

  // Get products formatted for frontend display
  async getFormattedProducts() {
    try {
      // Get the 4 specific products by their price IDs from .env
      const priceIds = this.getPriceIdsFromEnv();
      
      const products = [];
      
      // Fetch each product by its price ID
      for (const [planType, priceId] of Object.entries(priceIds)) {
        try {
          const price = await this.stripe.prices.retrieve(priceId);
          const product = await this.stripe.products.retrieve(price.product);
          
          // Determine if this is yearly based on plan type name
          const isYearly = planType.toLowerCase().includes('yearly');
          const actualInterval = isYearly ? 'year' : price.recurring?.interval || 'month';
          
          console.log(`🔍 Processing ${planType}: ${product.name} - ${actualInterval} - ${this.formatPrice(price.unit_amount, price.currency)}`);
          console.log(`📋 Product metadata from Stripe:`, product.metadata);
          
          products.push({
            id: product.id,
            name: product.name,
            description: product.description,
            metadata: product.metadata,
            priceId: price.id,
            amount: price.unit_amount,
            currency: price.currency,
            interval: actualInterval,
            formatted: this.formatPrice(price.unit_amount, price.currency)
          });
        } catch (error) {
          console.error(`Error fetching ${planType} with price ID ${priceId}:`, error);
        }
      }
      
      // Group products by base name (Starter, Professional)
      const groupedProducts = {};
      
      products.forEach(product => {
        console.log(`📦 Processing product: ${product.name} (${product.interval})`);
        
        // Determine base name based on product name patterns
        let baseName;
        if (product.name.toLowerCase().includes('starter')) {
          baseName = 'Starter';
        } else if (product.name.toLowerCase().includes('professional')) {
          baseName = 'Professional';
        } else {
          baseName = product.name; // fallback
        }
        
        if (!groupedProducts[baseName]) {
          groupedProducts[baseName] = {
            name: baseName,
            description: product.description,
            metadata: product.metadata,
            monthly: null,
            yearly: null,
            features: this.parseFeatures(product.metadata),
            popular: product.metadata?.popular === 'true',
            badge: product.metadata?.badge
          };
        }
        
        if (product.interval === 'month') {
          groupedProducts[baseName].monthly = {
            priceId: product.priceId,
            amount: product.amount,
            currency: product.currency,
            formatted: product.formatted
          };
          console.log(`✅ Added monthly pricing for ${baseName}: ${product.formatted}`);
        } else if (product.interval === 'year') {
          groupedProducts[baseName].yearly = {
            priceId: product.priceId,
            amount: product.amount,
            currency: product.currency,
            formatted: product.formatted
          };
          console.log(`✅ Added yearly pricing for ${baseName}: ${product.formatted}`);
        }
      });
      
      // Calculate savings for yearly plans
      Object.values(groupedProducts).forEach(product => {
        if (product.monthly && product.yearly) {
          const monthlyYearlyTotal = product.monthly.amount * 12;
          const savings = Math.round((monthlyYearlyTotal - product.yearly.amount) / 100);
          product.yearly.savings = savings;
          console.log(`💰 ${product.name} savings: A$${savings} (Monthly: A$${product.monthly.amount/100} × 12 = A$${monthlyYearlyTotal/100}, Yearly: A$${product.yearly.amount/100})`);
        }
      });
      
      return Object.values(groupedProducts);
    } catch (error) {
      console.error('Error formatting Stripe products:', error);
      throw error;
    }
  }

  // Get price IDs from environment variables
  getPriceIdsFromEnv() {
    console.log(`🔧 Using production Stripe price IDs from .env`);
    
    const priceIds = {
      'Starter Monthly': process.env.STRIPE_STARTER_MONTHLY_PRICE_ID,
      'Starter Yearly': process.env.STRIPE_STARTER_YEARLY_PRICE_ID,
      'Professional Monthly': process.env.STRIPE_PROFESSIONAL_MONTHLY_PRICE_ID,
      'Professional Yearly': process.env.STRIPE_PROFESSIONAL_YEARLY_PRICE_ID
    };
    
    console.log('📋 Price IDs from env:', priceIds);
    
    return priceIds;
  }

  // Format price for display
  formatPrice(amount, currency = 'usd') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase()
    }).format(amount / 100);
  }

  // Parse features from metadata
  parseFeatures(metadata) {
    console.log(`🔍 Raw metadata received:`, metadata);
    
    const features = [];
    
    // Try different metadata formats for features
    if (metadata.features) {
      console.log(`✅ Found 'features' field:`, metadata.features);
      // If features is a string, split by comma or newline
      if (typeof metadata.features === 'string') {
        features.push(...metadata.features.split(/[,\n]/).map(f => f.trim()).filter(f => f));
      } else if (Array.isArray(metadata.features)) {
        features.push(...metadata.features);
      }
    }
    
    // Try numbered features (feature_1, feature_2, etc.) - case insensitive
    let i = 1;
    while (metadata[`feature_${i}`] || metadata[`Feature_${i}`]) {
      const feature = metadata[`feature_${i}`] || metadata[`Feature_${i}`];
      console.log(`✅ Found feature_${i}:`, feature);
      features.push(feature);
      i++;
    }
    
    // Try other common feature field names
    const featureFields = ['feature_list', 'plan_features', 'includes', 'benefits'];
    for (const field of featureFields) {
      if (metadata[field]) {
        console.log(`✅ Found '${field}' field:`, metadata[field]);
        if (typeof metadata[field] === 'string') {
          features.push(...metadata[field].split(/[,\n]/).map(f => f.trim()).filter(f => f));
        } else if (Array.isArray(metadata[field])) {
          features.push(...metadata[field]);
        }
      }
    }
    
    // Remove duplicates and empty strings
    const uniqueFeatures = [...new Set(features.filter(f => f && f.trim()))];
    
    console.log(`📋 Parsed features from metadata:`, uniqueFeatures);
    
    return uniqueFeatures;
  }

  // Create checkout session with 7-day free trial
  async createCheckoutSession(priceId, successUrl, cancelUrl, customerEmail = null, trialPeriodDays = 7) {
    try {
      const sessionParams = {
        payment_method_types: ['card'],
        line_items: [
          {
            price: priceId,
            quantity: 1,
          },
        ],
        mode: 'subscription',
        success_url: successUrl,
        cancel_url: cancelUrl,
        allow_promotion_codes: true,
        // Custom branding to match website colors
        custom_text: {
          submit: {
            message: 'Start your 7-day free trial with no commitment. Cancel anytime during the trial period.'
          }
        },
        // Add metadata for tracking
        metadata: {
          source: 'trial_signup',
          trial_days: trialPeriodDays.toString()
        }
      };

      // Add trial period only if specified
      if (trialPeriodDays && trialPeriodDays > 0) {
        sessionParams.subscription_data = {
          trial_period_days: trialPeriodDays,
        };
      }

      if (customerEmail) {
        sessionParams.customer_email = customerEmail;
      }

      const session = await this.stripe.checkout.sessions.create(sessionParams);
      return session;
    } catch (error) {
      console.error('Error creating checkout session:', error);
      throw error;
    }
  }

  // Get price by ID
  async getPrice(priceId) {
    try {
      const price = await this.stripe.prices.retrieve(priceId);
      return price;
    } catch (error) {
      console.error('Error fetching price:', error);
      throw error;
    }
  }

  // Verify webhook signature
  verifyWebhookSignature(payload, sig, secret) {
    try {
      return this.stripe.webhooks.constructEvent(payload, sig, secret);
    } catch (error) {
      console.error('Webhook signature verification failed:', error);
      throw error;
    }
  }

  // Handle checkout session completed
  async handleCheckoutSessionCompleted(session) {
    try {
      console.log('✅ Checkout session completed:', session.id);
      
      // Get subscription details
      const subscription = await this.stripe.subscriptions.retrieve(session.subscription);
      
      // Update customer record with subscription info
      await this.updateCustomerSubscription(session.customer_email, subscription);
      
    } catch (error) {
      console.error('Error handling checkout session completed:', error);
    }
  }

  // Handle subscription created
  async handleSubscriptionCreated(subscription) {
    try {
      console.log('✅ Subscription created:', subscription.id);
      
      // Get customer email from subscription
      const customer = await this.stripe.customers.retrieve(subscription.customer);
      
      // Update customer record
      await this.updateCustomerSubscription(customer.email, subscription);
      
    } catch (error) {
      console.error('Error handling subscription created:', error);
    }
  }

  // Handle subscription updated
  async handleSubscriptionUpdated(subscription) {
    try {
      console.log('✅ Subscription updated:', subscription.id);
      
      // Get customer email from subscription
      const customer = await this.stripe.customers.retrieve(subscription.customer);
      
      // Update customer record
      await this.updateCustomerSubscription(customer.email, subscription);
      
    } catch (error) {
      console.error('Error handling subscription updated:', error);
    }
  }

  // Handle subscription deleted
  async handleSubscriptionDeleted(subscription) {
    try {
      console.log('✅ Subscription deleted:', subscription.id);
      
      // Get customer email from subscription
      const customer = await this.stripe.customers.retrieve(subscription.customer);
      
      // Update customer record to remove subscription
      await this.updateCustomerSubscription(customer.email, null);
      
    } catch (error) {
      console.error('Error handling subscription deleted:', error);
    }
  }

  // Handle payment succeeded
  async handlePaymentSucceeded(invoice) {
    try {
      console.log('✅ Payment succeeded:', invoice.id);
      
      // Get subscription details
      const subscription = await this.stripe.subscriptions.retrieve(invoice.subscription);
      const customer = await this.stripe.customers.retrieve(subscription.customer);
      
      // Update customer record
      await this.updateCustomerSubscription(customer.email, subscription);
      
    } catch (error) {
      console.error('Error handling payment succeeded:', error);
    }
  }

  // Handle payment failed
  async handlePaymentFailed(invoice) {
    try {
      console.log('❌ Payment failed:', invoice.id);
      
      // Get subscription details
      const subscription = await this.stripe.subscriptions.retrieve(invoice.subscription);
      const customer = await this.stripe.customers.retrieve(subscription.customer);
      
      // Log payment failure (could send email notification here)
      console.log(`Payment failed for customer: ${customer.email}, subscription: ${subscription.id}`);
      
    } catch (error) {
      console.error('Error handling payment failed:', error);
    }
  }

  // Update customer subscription in database
  async updateCustomerSubscription(email, subscription) {
    try {
      const { createClient } = require('@supabase/supabase-js');
      const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);
      
      if (!email) {
        console.error('No email provided for subscription update');
        return;
      }

      // Find customer by email
      const { data: customer, error: findError } = await supabase
        .from('customers')
        .select('*')
        .eq('contact_email', email)
        .single();

      if (findError || !customer) {
        console.error('Customer not found for email:', email);
        return;
      }

      // Update customer record
      const updateData = {
        updated_at: new Date().toISOString()
      };

      if (subscription) {
        // Get price details to determine plan
        const price = await this.stripe.prices.retrieve(subscription.items.data[0].price.id);
        const product = await this.stripe.products.retrieve(price.product);
        
        updateData.plan_id = product.name;
        updateData.stripe_subscription_id = subscription.id;
        updateData.stripe_customer_id = subscription.customer;
        updateData.subscription_status = subscription.status;
        updateData.trial_end = subscription.trial_end ? new Date(subscription.trial_end * 1000).toISOString() : null;
        updateData.current_period_end = new Date(subscription.current_period_end * 1000).toISOString();
        
        // Mark trial as used if subscription has trial period
        if (subscription.trial_end) {
          updateData.trial_used = true;
        }
      } else {
        // Subscription cancelled
        updateData.plan_id = 'cancelled';
        updateData.subscription_status = 'cancelled';
        updateData.stripe_subscription_id = null;
      }

      const { error: updateError } = await supabase
        .from('customers')
        .update(updateData)
        .eq('id', customer.id);

      if (updateError) {
        console.error('Error updating customer subscription:', updateError);
      } else {
        console.log('✅ Customer subscription updated successfully');
      }

    } catch (error) {
      console.error('Error updating customer subscription:', error);
    }
  }
}

module.exports = new StripeService();
