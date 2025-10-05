const express = require('express');
const router = express.Router();
const subscriptionService = require('../services/subscriptionService');
const Auth0Service = require('../services/auth0Service');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY, {
    timeout: 30000, // 30 seconds timeout
    maxNetworkRetries: 3, // Retry up to 3 times
    apiVersion: '2023-10-16'
});

// Initialize Auth0 service
const auth0Service = new Auth0Service();

// Get Stripe publishable key
router.get('/stripe-key', (req, res) => {
    try {
        const publishableKey = process.env.STRIPE_PUBLISHABLE_KEY || 'pk_test_...';
        res.json({
            success: true,
            publishableKey: publishableKey
        });
    } catch (error) {
        console.error('❌ Error getting Stripe key:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get Stripe key'
        });
    }
});

// Get Google Places API key
router.get('/google-places-key', (req, res) => {
    try {
        const apiKey = process.env.GOOGLE_PLACES_API_KEY;
        
        if (!apiKey) {
            return res.status(500).json({
                success: false,
                error: 'Google Places API key not configured'
            });
        }
        
        res.json({
            success: true,
            apiKey: apiKey
        });
    } catch (error) {
        console.error('❌ Error getting Google Places key:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to get Google Places key'
        });
    }
});

// Get subscription plans
router.get('/plans', async (req, res) => {
    try {
        const plans = subscriptionService.getPlans();
        const trialConfig = subscriptionService.getTrialConfig();
        
        // Format plans with pricing
        const formattedPlans = {};
        Object.keys(plans).forEach(planKey => {
            const plan = plans[planKey];
            formattedPlans[planKey] = {
                name: plan.name,
                description: plan.description,
                monthly: {
                    ...plan.monthly,
                    pricing: subscriptionService.getPlanPricing(planKey, 'monthly')
                },
                yearly: {
                    ...plan.yearly,
                    pricing: subscriptionService.getPlanPricing(planKey, 'yearly')
                }
            };
        });

        res.json({
            success: true,
            plans: formattedPlans,
            trial: trialConfig
        });
    } catch (error) {
        console.error('❌ Error getting subscription plans:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get subscription plans'
        });
    }
});

// Create setup intent for payment method collection
router.post('/setup-intent', async (req, res) => {
    try {
        console.log('🔧 Creating setup intent...');
        
        // Create setup intent without customer (customer will be created during trial start)
        const setupIntent = await stripe.setupIntents.create({
            payment_method_types: ['card'],
            usage: 'off_session'
        });

        console.log('✅ Setup intent created:', setupIntent.id);
        res.json({
            success: true,
            client_secret: setupIntent.client_secret
        });
    } catch (error) {
        console.error('❌ Error creating setup intent:', error);
        
        // Provide more specific error messages
        let errorMessage = 'Failed to create setup intent';
        if (error.type === 'StripeConnectionError') {
            errorMessage = 'Network connection error. Please check your internet connection and try again.';
        } else if (error.type === 'StripeAPIError') {
            errorMessage = `Stripe API error: ${error.message}`;
        } else if (error.message) {
            errorMessage = error.message;
        }
        
        res.status(500).json({
            success: false,
            error: errorMessage,
            details: process.env.NODE_ENV === 'development' ? error.message : undefined
        });
    }
});

// Create customer and start trial
router.post('/trial/start', async (req, res) => {
    try {
        const { email, name, plan, billingCycle, paymentMethodId } = req.body;
        
        if (!email || !name || !plan || !billingCycle || !paymentMethodId) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields: email, name, plan, billingCycle, paymentMethodId'
            });
        }

        // Check if plan exists
        const plans = subscriptionService.getPlans();
        if (!plans[plan]) {
            return res.status(400).json({
                success: false,
                error: 'Invalid plan selected'
            });
        }

        const planDetails = plans[plan][billingCycle];
        console.log('🔍 Debug - Plan details:', {
            plan,
            billingCycle,
            planDetails,
            priceId: planDetails?.priceId
        });
        
        if (!planDetails || !planDetails.priceId) {
            return res.status(400).json({
                success: false,
                error: 'Plan not available for selected billing cycle'
            });
        }

        // Create new customer
        const customer = await subscriptionService.createCustomer(email, name);
        
        // Attach payment method to customer
        await stripe.paymentMethods.attach(paymentMethodId, {
            customer: customer.id,
        });
        
        // Set as default payment method
        await stripe.customers.update(customer.id, {
            invoice_settings: {
                default_payment_method: paymentMethodId,
            },
        });
        
        // Create subscription with trial
        const subscription = await subscriptionService.createSubscriptionWithTrial(
            customer.id,
            planDetails.priceId,
            subscriptionService.getTrialConfig().durationDays
        );

                    // Use provided user ID or create trial user account
                    let userId = req.body.userId;
                    if (!userId) {
                        const trialUser = await auth0Service.createTrialUserAccount(email, name, customer.id);
                        userId = trialUser?.id || 'temp_user_id';
                    }
                    
                    // Save to database with user ID
                    const subscriptionData = {
                        ...subscription,
                        metadata: {
                            user_id: userId,
                            plan: plan,
                            billing_cycle: billingCycle
                        }
                    };

        await subscriptionService.saveSubscriptionToDatabase(subscriptionData);

        // Send welcome email
        await subscriptionService.sendTrialWelcomeEmail(email, name);

        res.json({
            success: true,
            subscription: {
                id: subscription.id,
                status: subscription.status,
                trial_end: subscription.trial_end,
                client_secret: subscription.latest_invoice?.payment_intent?.client_secret || null
            },
            redirect_url: '/login?trial=success&email=' + encodeURIComponent(email)
        });
    } catch (error) {
        console.error('❌ Error starting trial:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to start trial'
        });
    }
});

// Create subscription (after trial or direct purchase)
router.post('/create', async (req, res) => {
    try {
        const { email, name, plan, billingCycle, paymentMethodId } = req.body;
        
        if (!email || !name || !plan || !billingCycle || !paymentMethodId) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }

        // Check if plan exists
        const plans = subscriptionService.getPlans();
        if (!plans[plan]) {
            return res.status(400).json({
                success: false,
                error: 'Invalid plan selected'
            });
        }

        const planDetails = plans[plan][billingCycle];
        if (!planDetails || !planDetails.priceId) {
            return res.status(400).json({
                success: false,
                error: 'Plan not available for selected billing cycle'
            });
        }

        // Create Stripe customer
        const customer = await subscriptionService.createCustomer(email, name);
        
        // Attach payment method to customer
        await stripe.paymentMethods.attach(paymentMethodId, {
            customer: customer.id,
        });

        // Set as default payment method
        await stripe.customers.update(customer.id, {
            invoice_settings: {
                default_payment_method: paymentMethodId,
            },
        });

        // Create subscription
        const subscription = await subscriptionService.createSubscription(
            customer.id,
            planDetails.priceId
        );

        // Save to database
        const subscriptionData = {
            ...subscription,
            metadata: {
                user_id: req.user?.id || 'temp_user_id',
                plan: plan,
                billing_cycle: billingCycle
            }
        };

        await subscriptionService.saveSubscriptionToDatabase(subscriptionData);

        res.json({
            success: true,
            subscription: {
                id: subscription.id,
                status: subscription.status,
                client_secret: subscription.latest_invoice.payment_intent.client_secret
            }
        });
    } catch (error) {
        console.error('❌ Error creating subscription:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to create subscription'
        });
    }
});

// Get user's current subscription
router.get('/current', async (req, res) => {
    try {
        // Try to get user from JWT token
        const sessionService = require('../services/sessionService');
        const token = sessionService.extractToken(req);
        
        let userId = req.query.user_id;
        
        if (!userId && token) {
            const decoded = sessionService.verifyToken(token);
            if (decoded) {
                userId = decoded.userId;
            }
        }
        
        // If no user ID provided, return no subscription (user not logged in)
        if (!userId) {
            return res.json({
                success: true,
                subscription: null,
                message: 'No user authenticated'
            });
        }

        console.log('🔍 Getting subscription for user:', userId);

        // Get user to get customer_id
        const user = await auth0Service.getUserById(userId);
        if (!user) {
            return res.json({
                success: true,
                subscription: null,
                plan: 'basic',
                message: 'No user found'
            });
        }

        console.log('👤 User found:', { userId: user.id, customerId: user.customer_id, stripeCustomerId: user.stripe_customer_id });

        // Check if user has used trial
        const hasUsedTrial = await auth0Service.hasUsedTrial(user.email);
        console.log('🔍 Trial status:', { email: user.email, hasUsedTrial });

        // If user has no Stripe customer ID, they're likely on trial or basic plan
        if (!user.stripe_customer_id) {
            if (!hasUsedTrial) {
                // User is on trial
                const trialEndDate = new Date();
                trialEndDate.setDate(trialEndDate.getDate() + 7); // 7-day trial
                
                return res.json({
                    success: true,
                    subscription: {
                        id: 'trial',
                        status: 'trialing',
                        plan_name: 'Trial Plan',
                        billing_cycle: 'monthly',
                        current_period_end: Math.floor(trialEndDate.getTime() / 1000),
                        amount: 0,
                        currency: 'aud',
                        is_trial: true
                    }
                });
            } else {
                // User has used trial but no subscription - they're on basic plan
                return res.json({
                    success: true,
                    subscription: {
                        id: 'basic',
                        status: 'active',
                        plan_name: 'Basic Plan',
                        billing_cycle: 'monthly',
                        current_period_end: null,
                        amount: 0,
                        currency: 'aud',
                        is_basic: true
                    }
                });
            }
        }

        // Try to fetch Stripe subscription if customer has Stripe data
        let stripeSubscription = null;
        let planName = 'Basic Plan';
        let billingCycle = 'monthly';
        let amount = 0;

        try {
            const customerSubscriptions = await stripe.subscriptions.list({
                customer: user.stripe_customer_id,
                status: 'active',
                limit: 1
            });

            if (customerSubscriptions.data.length > 0) {
                stripeSubscription = customerSubscriptions.data[0];
                
                // Get price details
                if (stripeSubscription.items?.data?.[0]?.price) {
                    const price = stripeSubscription.items.data[0].price;
                    amount = price.unit_amount / 100; // Convert cents to dollars
                    billingCycle = price.recurring.interval === 'year' ? 'yearly' : 'monthly';
                    
                    // Determine plan name from price ID
                    const priceId = price.id;
                    if (priceId === process.env.STRIPE_STARTER_MONTHLY_PRICE_ID) {
                        planName = 'Starter Plan';
                    } else if (priceId === process.env.STRIPE_STARTER_YEARLY_PRICE_ID) {
                        planName = 'Starter Plan (Yearly)';
                    } else if (priceId === process.env.STRIPE_PROFESSIONAL_MONTHLY_PRICE_ID) {
                        planName = 'Professional Plan';
                    } else if (priceId === process.env.STRIPE_PROFESSIONAL_YEARLY_PRICE_ID) {
                        planName = 'Professional Plan (Yearly)';
                    }
                }
                
                console.log('💳 Stripe subscription found:', {
                    id: stripeSubscription.id,
                    status: stripeSubscription.status,
                    planName,
                    amount,
                    billingCycle,
                    currentPeriodEnd: stripeSubscription.current_period_end
                });
            }
        } catch (stripeError) {
            console.error('❌ Error fetching Stripe subscription:', stripeError);
        }
        
        res.json({
            success: true,
            subscription: stripeSubscription ? {
                id: stripeSubscription.id,
                status: stripeSubscription.status,
                plan_name: planName,
                billing_cycle: billingCycle,
                current_period_end: stripeSubscription.current_period_end,
                amount: amount,
                currency: stripeSubscription.currency || 'aud',
                cancel_at_period_end: stripeSubscription.cancel_at_period_end
            } : {
                plan_name: planName,
                billing_cycle: billingCycle,
                status: 'active',
                amount: 0,
                current_period_end: null,
                is_basic: true
            }
        });
    } catch (error) {
        console.error('❌ Error getting current subscription:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get subscription'
        });
    }
});

// Cancel subscription
router.post('/cancel', async (req, res) => {
    try {
        // Get user from JWT token
        const sessionService = require('../services/sessionService');
        const token = sessionService.extractToken(req);
        
        if (!token) {
            return res.status(401).json({
                success: false,
                message: 'Authentication required'
            });
        }

        const decoded = sessionService.verifyToken(token);
        const userId = decoded.userId;

        console.log('🔍 Canceling subscription for user:', userId);

        // Get user to get Stripe customer ID
        const user = await auth0Service.getUserById(userId);
        if (!user || !user.stripe_customer_id) {
            return res.status(404).json({
                success: false,
                message: 'No active subscription found to cancel'
            });
        }

        // Get active subscription from Stripe
        const customerSubscriptions = await stripe.subscriptions.list({
            customer: user.stripe_customer_id,
            status: 'active',
            limit: 1
        });

        if (customerSubscriptions.data.length === 0) {
            return res.status(404).json({
                success: false,
                message: 'No active subscription found to cancel'
            });
        }

        const subscription = customerSubscriptions.data[0];

        // Cancel subscription at period end (don't cancel immediately)
        const cancelledSubscription = await stripe.subscriptions.update(
            subscription.id,
            {
                cancel_at_period_end: true
            }
        );

        console.log('✅ Subscription cancelled at period end:', {
            subscriptionId: subscription.id,
            cancelAtPeriodEnd: cancelledSubscription.cancel_at_period_end,
            currentPeriodEnd: cancelledSubscription.current_period_end
        });

        res.json({
            success: true,
            message: 'Subscription cancelled successfully. You will retain access until the end of your billing period.',
            subscription: {
                id: cancelledSubscription.id,
                status: cancelledSubscription.status,
                cancel_at_period_end: cancelledSubscription.cancel_at_period_end,
                current_period_end: cancelledSubscription.current_period_end
            }
        });

    } catch (error) {
        console.error('❌ Error cancelling subscription:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to cancel subscription',
            error: error.message
        });
    }
});

// Update subscription plan
router.post('/update', async (req, res) => {
    try {
        const { subscriptionId, newPlan, billingCycle } = req.body;
        
        if (!subscriptionId || !newPlan || !billingCycle) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }

        // Check if new plan exists
        const plans = subscriptionService.getPlans();
        if (!plans[newPlan]) {
            return res.status(400).json({
                success: false,
                error: 'Invalid plan selected'
            });
        }

        const planDetails = plans[newPlan][billingCycle];
        if (!planDetails || !planDetails.priceId) {
            return res.status(400).json({
                success: false,
                error: 'Plan not available for selected billing cycle'
            });
        }

        const subscription = await subscriptionService.updateSubscription(
            subscriptionId,
            planDetails.priceId
        );

        res.json({
            success: true,
            subscription: {
                id: subscription.id,
                status: subscription.status
            }
        });
    } catch (error) {
        console.error('❌ Error updating subscription:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to update subscription'
        });
    }
});

// Check feature access
router.get('/feature-access/:feature', async (req, res) => {
    try {
        const { feature } = req.params;
        const userId = req.user?.id || req.query.user_id;
        
        if (!userId) {
            return res.status(400).json({
                success: false,
                error: 'User ID required'
            });
        }

        const hasAccess = await subscriptionService.checkFeatureAccess(userId, feature);
        
        res.json({
            success: true,
            hasAccess: hasAccess,
            feature: feature
        });
    } catch (error) {
        console.error('❌ Error checking feature access:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to check feature access'
        });
    }
});

// Create setup intent for payment method
router.post('/setup-intent', async (req, res) => {
    try {
        const { customerId } = req.body;
        
        if (!customerId) {
            return res.status(400).json({
                success: false,
                error: 'Customer ID required'
            });
        }

        const setupIntent = await subscriptionService.createSetupIntent(customerId);
        
        res.json({
            success: true,
            client_secret: setupIntent.client_secret
        });
    } catch (error) {
        console.error('❌ Error creating setup intent:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to create setup intent'
        });
    }
});

// Webhook endpoint for Stripe events
router.post('/webhook', express.raw({type: 'application/json'}), async (req, res) => {
    const sig = req.headers['stripe-signature'];
    let event;

    try {
        event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
    } catch (err) {
        console.error('❌ Webhook signature verification failed:', err.message);
        return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    // Handle the event
    switch (event.type) {
        case 'customer.subscription.created':
            console.log('📝 Subscription created:', event.data.object.id);
            break;
        case 'customer.subscription.updated':
            console.log('📝 Subscription updated:', event.data.object.id);
            await subscriptionService.saveSubscriptionToDatabase(event.data.object);
            break;
        case 'customer.subscription.deleted':
            console.log('📝 Subscription deleted:', event.data.object.id);
            break;
        case 'invoice.payment_succeeded':
            console.log('💰 Payment succeeded for invoice:', event.data.object.id);
            break;
        case 'invoice.payment_failed':
            console.log('❌ Payment failed for invoice:', event.data.object.id);
            break;
        case 'customer.subscription.trial_will_end':
            console.log('⏰ Trial ending soon for subscription:', event.data.object.id);
            // Send trial ending notification
            const subscription = event.data.object;
            const customer = await stripe.customers.retrieve(subscription.customer);
            await subscriptionService.sendTrialEndingNotification(
                customer.email,
                customer.name,
                subscription.id
            );
            break;
        default:
            console.log(`Unhandled event type ${event.type}`);
    }

    res.json({received: true});
});

// Create Stripe customer portal session for payment updates
router.post('/create-portal-session', async (req, res) => {
    try {
        // Get user from session or token
        const user = req.user || req.session?.user;
        if (!user) {
            return res.status(401).json({
                success: false,
                message: 'User not authenticated'
            });
        }

        // Get customer ID from user's subscription
        const { data: subscription } = await auth0Service.supabase
            .from('subscriptions')
            .select('stripe_customer_id')
            .eq('user_id', user.id)
            .single();

        if (!subscription || !subscription.stripe_customer_id) {
            return res.status(404).json({
                success: false,
                message: 'No subscription found'
            });
        }

        // Create portal session
        const portalSession = await stripe.billingPortal.sessions.create({
            customer: subscription.stripe_customer_id,
            return_url: `${process.env.FRONTEND_URL || 'http://localhost:3000'}/user-settings`,
        });

        res.json({
            success: true,
            url: portalSession.url
        });

    } catch (error) {
        console.error('Error creating portal session:', error);
        res.status(500).json({
            success: false,
            message: 'Failed to create portal session'
        });
    }
});

module.exports = router;