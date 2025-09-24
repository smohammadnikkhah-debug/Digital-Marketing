-- Subscription Management Schema
-- This schema supports Stripe integration with 7-day trials and feature restrictions

-- Users table (if not already exists)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR(255) PRIMARY KEY, -- Stripe subscription ID
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    customer_id VARCHAR(255) NOT NULL, -- Stripe customer ID
    status VARCHAR(50) NOT NULL, -- active, trialing, canceled, past_due, etc.
    plan VARCHAR(50) NOT NULL, -- starter, professional, enterprise
    billing_cycle VARCHAR(20) NOT NULL, -- monthly, yearly
    
    -- Trial information
    trial_start TIMESTAMP WITH TIME ZONE,
    trial_end TIMESTAMP WITH TIME ZONE,
    
    -- Billing periods
    current_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Cancellation
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    canceled_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Subscription features tracking
CREATE TABLE IF NOT EXISTS subscription_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id VARCHAR(255) REFERENCES subscriptions(id) ON DELETE CASCADE,
    feature_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    usage_limit INTEGER, -- NULL means unlimited
    current_usage INTEGER DEFAULT 0,
    reset_period VARCHAR(20), -- daily, monthly, yearly
    last_reset TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(subscription_id, feature_name)
);

-- Subscription usage tracking
CREATE TABLE IF NOT EXISTS subscription_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id VARCHAR(255) REFERENCES subscriptions(id) ON DELETE CASCADE,
    feature_name VARCHAR(100) NOT NULL,
    usage_count INTEGER DEFAULT 1,
    usage_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Email notifications log
CREATE TABLE IF NOT EXISTS email_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    template_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(50) NOT NULL, -- trial_welcome, trial_ending, cancellation, etc.
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'sent', -- sent, failed, bounced
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Payment history
CREATE TABLE IF NOT EXISTS payment_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id VARCHAR(255) REFERENCES subscriptions(id) ON DELETE CASCADE,
    invoice_id VARCHAR(255) NOT NULL, -- Stripe invoice ID
    amount INTEGER NOT NULL, -- Amount in cents
    currency VARCHAR(3) DEFAULT 'usd',
    status VARCHAR(20) NOT NULL, -- paid, failed, pending
    payment_method VARCHAR(50),
    paid_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_plan ON subscriptions(plan);
CREATE INDEX IF NOT EXISTS idx_subscriptions_trial_end ON subscriptions(trial_end);
CREATE INDEX IF NOT EXISTS idx_subscriptions_current_period_end ON subscriptions(current_period_end);

CREATE INDEX IF NOT EXISTS idx_subscription_features_subscription_id ON subscription_features(subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscription_features_feature_name ON subscription_features(feature_name);

CREATE INDEX IF NOT EXISTS idx_subscription_usage_subscription_id ON subscription_usage(subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscription_usage_feature_name ON subscription_usage(feature_name);
CREATE INDEX IF NOT EXISTS idx_subscription_usage_date ON subscription_usage(usage_date);

CREATE INDEX IF NOT EXISTS idx_email_notifications_user_id ON email_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_email_notifications_type ON email_notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_email_notifications_sent_at ON email_notifications(sent_at);

CREATE INDEX IF NOT EXISTS idx_payment_history_subscription_id ON payment_history(subscription_id);
CREATE INDEX IF NOT EXISTS idx_payment_history_status ON payment_history(status);
CREATE INDEX IF NOT EXISTS idx_payment_history_paid_at ON payment_history(paid_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_subscriptions_updated_at BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subscription_features_updated_at BEFORE UPDATE ON subscription_features
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default subscription features for each plan
INSERT INTO subscription_features (subscription_id, feature_name, is_enabled, usage_limit, reset_period) VALUES
-- These will be populated when subscriptions are created
('default_starter', 'content_calendar', true, 30, 'monthly'),
('default_starter', 'seo_analysis', true, 50, 'monthly'),
('default_starter', 'keyword_research', true, 100, 'monthly'),
('default_starter', 'technical_seo', true, 20, 'monthly'),
('default_starter', 'ai_content_generation', false, 0, 'monthly'),
('default_starter', 'social_media_integration', false, 0, 'monthly'),

('default_professional', 'content_calendar', true, 90, 'monthly'),
('default_professional', 'seo_analysis', true, 200, 'monthly'),
('default_professional', 'keyword_research', true, 500, 'monthly'),
('default_professional', 'technical_seo', true, 100, 'monthly'),
('default_professional', 'ai_content_generation', true, 50, 'monthly'),
('default_professional', 'wordpress_integration', true, null, 'monthly'),
('default_professional', 'competitor_analysis', true, 20, 'monthly'),

('default_enterprise', 'content_calendar', true, null, 'monthly'),
('default_enterprise', 'seo_analysis', true, null, 'monthly'),
('default_enterprise', 'keyword_research', true, null, 'monthly'),
('default_enterprise', 'technical_seo', true, null, 'monthly'),
('default_enterprise', 'ai_content_generation', true, null, 'monthly'),
('default_enterprise', 'wordpress_integration', true, null, 'monthly'),
('default_enterprise', 'competitor_analysis', true, null, 'monthly'),
('default_enterprise', 'white_label', true, null, 'monthly'),
('default_enterprise', 'custom_integrations', true, null, 'monthly')
ON CONFLICT (subscription_id, feature_name) DO NOTHING;

-- Create view for active subscriptions with features
CREATE OR REPLACE VIEW active_subscriptions AS
SELECT 
    s.id,
    s.user_id,
    u.email,
    u.name,
    s.plan,
    s.billing_cycle,
    s.status,
    s.trial_start,
    s.trial_end,
    s.current_period_start,
    s.current_period_end,
    s.cancel_at_period_end,
    CASE 
        WHEN s.status = 'trialing' AND s.trial_end > NOW() THEN true
        WHEN s.status = 'active' THEN true
        ELSE false
    END as is_active,
    CASE 
        WHEN s.status = 'trialing' AND s.trial_end > NOW() THEN true
        ELSE false
    END as is_trial_active,
    s.created_at,
    s.updated_at
FROM subscriptions s
JOIN users u ON s.user_id = u.id
WHERE s.status IN ('active', 'trialing', 'past_due');

-- Create view for subscription features summary
CREATE OR REPLACE VIEW subscription_features_summary AS
SELECT 
    s.id as subscription_id,
    s.user_id,
    s.plan,
    s.billing_cycle,
    s.status,
    sf.feature_name,
    sf.is_enabled,
    sf.usage_limit,
    sf.current_usage,
    sf.reset_period,
    CASE 
        WHEN sf.usage_limit IS NULL THEN true
        WHEN sf.current_usage < sf.usage_limit THEN true
        ELSE false
    END as has_usage_remaining
FROM subscriptions s
LEFT JOIN subscription_features sf ON s.id = sf.subscription_id
WHERE s.status IN ('active', 'trialing', 'past_due');

-- Grant permissions (adjust as needed for your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
