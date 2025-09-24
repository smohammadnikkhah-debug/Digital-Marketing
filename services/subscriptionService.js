// Initialize Stripe (only if secret key is provided)
let stripe = null;
if (process.env.STRIPE_SECRET_KEY) {
    stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
}
const sgMail = require('@sendgrid/mail');
const { createClient } = require('@supabase/supabase-js');

// Initialize SendGrid (only if API key is provided)
if (process.env.SENDGRID_API_KEY) {
    sgMail.setApiKey(process.env.SENDGRID_API_KEY);
}

// Initialize Supabase (only if URL is provided)
let supabase = null;
if (process.env.SUPABASE_URL && process.env.SUPABASE_ANON_KEY) {
    supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);
}

// Subscription Plans Configuration
const SUBSCRIPTION_PLANS = {
    starter: {
        name: 'Starter',
        description: 'Perfect for small businesses getting started with SEO',
        monthly: {
            price: 4990, // $49.90 in cents
            priceId: process.env.NODE_ENV === 'production' 
                ? (process.env.STRIPE_PROD_STARTER_MONTHLY_PRICE_ID || 'stripe_prod_Starter_Monthly')
                : (process.env.STRIPE_TEST_STARTER_MONTHLY_PRICE_ID || 'stripe_test_Starter_Monthly'),
            features: [
                'Basic SEO analysis',
                'Keyword research',
                'Technical SEO audit'
            ],
            restrictions: [
                'No AI content generation',
                'No social media integration'
            ]
        },
        yearly: {
            price: 41918, // $49.90 * 12 * 0.70 = $419.18 in cents (30% discount)
            priceId: process.env.NODE_ENV === 'production' 
                ? (process.env.STRIPE_PROD_STARTER_YEARLY_PRICE_ID || 'stripe_prod_Starter_Yearly')
                : (process.env.STRIPE_TEST_STARTER_YEARLY_PRICE_ID || 'stripe_test_Starter_Yearly'),
            features: [
                'Basic SEO analysis',
                'Keyword research',
                'Technical SEO audit',
                '30% savings with yearly billing'
            ],
            restrictions: [
                'No AI content generation',
                'No social media integration'
            ]
        }
    },
    professional: {
        name: 'Professional',
        description: 'Advanced features for growing businesses',
        monthly: {
            price: 9990, // $99.90 in cents
            priceId: process.env.NODE_ENV === 'production' 
                ? (process.env.STRIPE_PROD_PROFESSIONAL_MONTHLY_PRICE_ID || 'stripe_prod_Professional_Monthly')
                : (process.env.STRIPE_TEST_PROFESSIONAL_MONTHLY_PRICE_ID || 'stripe_test_Professional_Monthly'),
            features: [
                '90-day content calendar',
                'Advanced SEO analysis',
                'AI-powered content generation',
                'Keyword research & tracking',
                'Technical SEO audit',
                'Competitor analysis',
                'Priority email support',
                'WordPress integration'
            ],
            restrictions: []
        },
        yearly: {
            price: 83916, // $99.90 * 12 * 0.70 = $839.16 in cents (30% discount)
            priceId: process.env.NODE_ENV === 'production' 
                ? (process.env.STRIPE_PROD_PROFESSIONAL_YEARLY_PRICE_ID || 'stripe_prod_Professional_Yearly')
                : (process.env.STRIPE_TEST_PROFESSIONAL_YEARLY_PRICE_ID || 'stripe_test_Professional_Yearly'),
            features: [
                '90-day content calendar',
                'Advanced SEO analysis',
                'AI-powered content generation',
                'Keyword research & tracking',
                'Technical SEO audit',
                'Competitor analysis',
                'Priority email support',
                'WordPress integration',
                '30% savings with yearly billing'
            ],
            restrictions: []
        }
    },
    enterprise: {
        name: 'Enterprise',
        description: 'Custom solutions for large organizations',
        monthly: {
            price: null, // Contact us
            priceId: null,
            features: [
                'Unlimited content calendar',
                'Advanced SEO analysis',
                'AI-powered content generation',
                'Custom keyword research',
                'Technical SEO audit',
                'Advanced competitor analysis',
                'Dedicated account manager',
                'Phone & email support',
                'WordPress integration',
                'Custom integrations',
                'White-label options'
            ],
            restrictions: []
        },
        yearly: {
            price: null, // Contact us
            priceId: null,
            features: [
                'Unlimited content calendar',
                'Advanced SEO analysis',
                'AI-powered content generation',
                'Custom keyword research',
                'Technical SEO audit',
                'Advanced competitor analysis',
                'Dedicated account manager',
                'Phone & email support',
                'WordPress integration',
                'Custom integrations',
                'White-label options'
            ],
            restrictions: []
        }
    }
};

// Trial Configuration
const TRIAL_CONFIG = {
    durationDays: 7,
    features: [
        '90-day content calendar',
        'Advanced SEO analysis',
        'AI-powered content generation',
        'Keyword research & tracking',
        'Technical SEO audit',
        'Competitor analysis',
        'Priority email support',
        'WordPress integration'
    ]
};

class SubscriptionService {
    constructor() {
        this.plans = SUBSCRIPTION_PLANS;
        this.trialConfig = TRIAL_CONFIG;
    }

    // Get all subscription plans
    getPlans() {
        return this.plans;
    }

    // Get trial configuration
    getTrialConfig() {
        return this.trialConfig;
    }

    // Create Stripe customer
    async createCustomer(email, name) {
        try {
            if (!stripe) {
                throw new Error('Stripe not configured. Please set STRIPE_SECRET_KEY environment variable.');
            }
            
            const customer = await stripe.customers.create({
                email: email,
                name: name,
                metadata: {
                    source: 'mozarex_seo_platform'
                }
            });

            console.log('✅ Stripe customer created:', customer.id);
            return customer;
        } catch (error) {
            console.error('❌ Error creating Stripe customer:', error);
            throw error;
        }
    }

    // Create subscription with trial
    async createSubscriptionWithTrial(customerId, priceId, trialDays = 7) {
        try {
            const subscription = await stripe.subscriptions.create({
                customer: customerId,
                items: [{ price: priceId }],
                trial_period_days: trialDays,
                payment_behavior: 'default_incomplete',
                payment_settings: {
                    save_default_payment_method: 'on_subscription'
                },
                expand: ['latest_invoice.payment_intent']
            });

            console.log('✅ Subscription with trial created:', subscription.id);
            return subscription;
        } catch (error) {
            console.error('❌ Error creating subscription with trial:', error);
            throw error;
        }
    }

    // Create subscription without trial
    async createSubscription(customerId, priceId) {
        try {
            const subscription = await stripe.subscriptions.create({
                customer: customerId,
                items: [{ price: priceId }],
                payment_behavior: 'default_incomplete',
                payment_settings: {
                    save_default_payment_method: 'on_subscription'
                },
                expand: ['latest_invoice.payment_intent']
            });

            console.log('✅ Subscription created:', subscription.id);
            return subscription;
        } catch (error) {
            console.error('❌ Error creating subscription:', error);
            throw error;
        }
    }

    // Get subscription details
    async getSubscription(subscriptionId) {
        try {
            const subscription = await stripe.subscriptions.retrieve(subscriptionId, {
                expand: ['latest_invoice', 'customer']
            });

            return subscription;
        } catch (error) {
            console.error('❌ Error retrieving subscription:', error);
            throw error;
        }
    }

    // Cancel subscription
    async cancelSubscription(subscriptionId, immediately = false) {
        try {
            const subscription = await stripe.subscriptions.update(subscriptionId, {
                cancel_at_period_end: !immediately,
                ...(immediately && { status: 'canceled' })
            });

            console.log('✅ Subscription canceled:', subscription.id);
            return subscription;
        } catch (error) {
            console.error('❌ Error canceling subscription:', error);
            throw error;
        }
    }

    // Update subscription plan
    async updateSubscription(subscriptionId, newPriceId) {
        try {
            const subscription = await stripe.subscriptions.retrieve(subscriptionId);
            
            const updatedSubscription = await stripe.subscriptions.update(subscriptionId, {
                items: [{
                    id: subscription.items.data[0].id,
                    price: newPriceId,
                }],
                proration_behavior: 'create_prorations'
            });

            console.log('✅ Subscription updated:', updatedSubscription.id);
            return updatedSubscription;
        } catch (error) {
            console.error('❌ Error updating subscription:', error);
            throw error;
        }
    }

    // Create payment intent for setup
    async createSetupIntent(customerId) {
        try {
            const setupIntent = await stripe.setupIntents.create({
                customer: customerId,
                payment_method_types: ['card'],
                usage: 'off_session'
            });

            return setupIntent;
        } catch (error) {
            console.error('❌ Error creating setup intent:', error);
            throw error;
        }
    }

    // Save subscription to database
    async saveSubscriptionToDatabase(subscriptionData) {
        try {
            if (!supabase) {
                console.warn('⚠️ Supabase not configured. Subscription not saved to database.');
                return null;
            }
            
            const { data, error } = await supabase
                .from('subscriptions')
                .upsert([{
                    stripe_subscription_id: subscriptionData.id,
                    user_id: subscriptionData.metadata.user_id,
                    stripe_customer_id: subscriptionData.customer,
                    stripe_price_id: subscriptionData.items.data[0].price.id,
                    plan_name: subscriptionData.metadata.plan,
                    billing_cycle: subscriptionData.metadata.billing_cycle,
                    status: subscriptionData.status,
                    trial_start: subscriptionData.trial_start ? new Date(subscriptionData.trial_start * 1000).toISOString() : null,
                    trial_end: subscriptionData.trial_end ? new Date(subscriptionData.trial_end * 1000).toISOString() : null,
                    current_period_start: new Date(subscriptionData.current_period_start * 1000).toISOString(),
                    current_period_end: new Date(subscriptionData.current_period_end * 1000).toISOString(),
                    cancel_at_period_end: subscriptionData.cancel_at_period_end,
                    canceled_at: subscriptionData.canceled_at ? new Date(subscriptionData.canceled_at * 1000).toISOString() : null,
                    created_at: new Date(subscriptionData.created * 1000).toISOString(),
                    updated_at: new Date().toISOString()
                }]);

            if (error) {
                console.error('❌ Error saving subscription to database:', error);
                throw error;
            }

            console.log('✅ Subscription saved to database');
            return data;
        } catch (error) {
            console.error('❌ Error saving subscription to database:', error);
            throw error;
        }
    }

    // Get user subscription from database
    async getUserSubscription(userId) {
        try {
            const { data, error } = await supabase
                .from('subscriptions')
                .select('*')
                .eq('user_id', userId)
                .single();

            if (error && error.code !== 'PGRST116') { // PGRST116 is "not found"
                console.error('❌ Error getting user subscription:', error);
                throw error;
            }

            return data;
        } catch (error) {
            console.error('❌ Error getting user subscription:', error);
            throw error;
        }
    }

    // Check if user has access to feature
    async checkFeatureAccess(userId, feature) {
        try {
            const subscription = await this.getUserSubscription(userId);
            
            if (!subscription) {
                return false;
            }

            const plan = this.plans[subscription.plan];
            if (!plan) {
                return false;
            }

            // Check if subscription is active
            if (subscription.status !== 'active' && subscription.status !== 'trialing') {
                return false;
            }

            // Check trial status
            if (subscription.status === 'trialing') {
                const trialEnd = new Date(subscription.trial_end);
                if (trialEnd < new Date()) {
                    return false;
                }
            }

            // Check feature restrictions
            const billingCycle = subscription.billing_cycle;
            const planFeatures = plan[billingCycle] || plan.monthly;
            
            if (planFeatures.restrictions && planFeatures.restrictions.includes(feature)) {
                return false;
            }

            return true;
        } catch (error) {
            console.error('❌ Error checking feature access:', error);
            return false;
        }
    }

    // Send email notification
    async sendEmailNotification(to, templateId, dynamicData) {
        try {
            if (!process.env.SENDGRID_API_KEY) {
                console.warn('⚠️ SendGrid not configured. Email not sent.');
                return false;
            }
            
            const msg = {
                to: to,
                from: {
                    email: process.env.SENDGRID_FROM_EMAIL || 'noreply@mozarex.com',
                    name: 'Mozarex SEO Platform'
                },
                templateId: templateId,
                dynamicTemplateData: dynamicData
            };

            await sgMail.send(msg);
            console.log('✅ Email sent successfully to:', to);
        } catch (error) {
            console.error('❌ Error sending email:', error);
            throw error;
        }
    }

    // Send trial welcome email
    async sendTrialWelcomeEmail(userEmail, userName) {
        try {
            await this.sendEmailNotification(userEmail, process.env.SENDGRID_TRIAL_WELCOME_TEMPLATE_ID, {
                user_name: userName,
                trial_days: this.trialConfig.durationDays,
                features: this.trialConfig.features
            });
        } catch (error) {
            console.error('❌ Error sending trial welcome email:', error);
            throw error;
        }
    }

    // Send trial ending notification
    async sendTrialEndingNotification(userEmail, userName, subscriptionId) {
        try {
            const subscription = await this.getSubscription(subscriptionId);
            const plan = this.plans[subscription.metadata.plan];
            const billingCycle = subscription.metadata.billing_cycle;
            const planDetails = plan[billingCycle];

            await this.sendEmailNotification(userEmail, process.env.SENDGRID_TRIAL_ENDING_TEMPLATE_ID, {
                user_name: userName,
                plan_name: plan.name,
                price: (planDetails.price / 100).toFixed(2),
                billing_cycle: billingCycle,
                trial_end_date: new Date(subscription.trial_end * 1000).toLocaleDateString()
            });
        } catch (error) {
            console.error('❌ Error sending trial ending notification:', error);
            throw error;
        }
    }

    // Send cancellation email
    async sendCancellationEmail(userEmail, userName, feedback = null) {
        try {
            await this.sendEmailNotification(userEmail, process.env.SENDGRID_CANCELLATION_TEMPLATE_ID, {
                user_name: userName,
                feedback: feedback
            });
        } catch (error) {
            console.error('❌ Error sending cancellation email:', error);
            throw error;
        }
    }

    // Calculate yearly discount
    calculateYearlyDiscount(monthlyPrice) {
        const yearlyPrice = monthlyPrice * 12 * 0.70; // 30% discount
        const savings = (monthlyPrice * 12) - yearlyPrice;
        return {
            yearlyPrice: Math.round(yearlyPrice),
            savings: Math.round(savings),
            discountPercentage: 30
        };
    }

    // Get plan pricing display
    getPlanPricing(planKey, billingCycle) {
        const plan = this.plans[planKey];
        if (!plan) return null;

        const planDetails = plan[billingCycle];
        if (!planDetails) return null;

        if (planKey === 'enterprise') {
            return {
                price: null,
                priceDisplay: 'Contact Us',
                yearlyPrice: null,
                yearlyPriceDisplay: 'Contact Us',
                savings: null
            };
        }

        const monthlyPrice = planDetails.price;
        const yearlyDiscount = this.calculateYearlyDiscount(monthlyPrice);

        return {
            price: monthlyPrice,
            priceDisplay: `$${(monthlyPrice / 100).toFixed(2)}`,
            yearlyPrice: yearlyDiscount.yearlyPrice,
            yearlyPriceDisplay: `$${(yearlyDiscount.yearlyPrice / 100).toFixed(2)}`,
            savings: yearlyDiscount.savings,
            savingsDisplay: `$${(yearlyDiscount.savings / 100).toFixed(2)}`
        };
    }
}

module.exports = new SubscriptionService();