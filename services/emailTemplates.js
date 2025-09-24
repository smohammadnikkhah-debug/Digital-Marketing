const sgMail = require('@sendgrid/mail');

// Initialize SendGrid only if API key is provided
if (process.env.SENDGRID_API_KEY && process.env.SENDGRID_API_KEY.startsWith('SG.')) {
    sgMail.setApiKey(process.env.SENDGRID_API_KEY);
    console.log('✅ SendGrid initialized successfully');
} else {
    console.warn('⚠️ SendGrid API key not configured or invalid. Email functionality will be disabled.');
}

// Email Templates Configuration
const EMAIL_TEMPLATES = {
    // Trial Welcome Email
    trial_welcome: {
        templateId: process.env.SENDGRID_TRIAL_WELCOME_TEMPLATE_ID,
        subject: 'Welcome to Mozarex SEO Platform - Your 7-Day Trial Starts Now! 🎉',
        html: `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to Mozarex</title>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f8fafc; }
                    .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
                    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem; text-align: center; }
                    .header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
                    .header p { margin: 0.5rem 0 0 0; opacity: 0.9; }
                    .content { padding: 2rem; }
                    .feature-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; margin: 2rem 0; }
                    .feature { background: #f8fafc; padding: 1rem; border-radius: 8px; border-left: 4px solid #667eea; }
                    .feature h3 { margin: 0 0 0.5rem 0; color: #667eea; font-size: 1.1rem; }
                    .feature p { margin: 0; color: #64748b; font-size: 0.9rem; }
                    .cta-button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 1rem 0; }
                    .footer { background: #f1f5f9; padding: 1.5rem; text-align: center; color: #64748b; font-size: 0.9rem; }
                    .trial-info { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
                    .trial-info h3 { color: #1d4ed8; margin: 0 0 0.5rem 0; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎉 Welcome to Mozarex!</h1>
                        <p>Your 7-day free trial is now active</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {{user_name}},</h2>
                        
                        <p>Thank you for choosing Mozarex SEO Platform! We're excited to help you boost your website's search engine performance.</p>
                        
                        <div class="trial-info">
                            <h3>🚀 Your Free Trial Includes:</h3>
                            <p>You now have <strong>{{trial_days}} days</strong> to explore all our premium features at no cost. No credit card required until your trial ends!</p>
                        </div>
                        
                        <h3>What you can do with your trial:</h3>
                        <div class="feature-grid">
                            <div class="feature">
                                <h3>📊 Advanced SEO Analysis</h3>
                                <p>Get comprehensive insights into your website's SEO performance</p>
                            </div>
                            <div class="feature">
                                <h3>🤖 AI Content Generation</h3>
                                <p>Create engaging, SEO-optimized content with our AI assistant</p>
                            </div>
                            <div class="feature">
                                <h3>📅 90-Day Content Calendar</h3>
                                <p>Plan and schedule your content strategy months ahead</p>
                            </div>
                            <div class="feature">
                                <h3>🔍 Keyword Research</h3>
                                <p>Discover high-value keywords to boost your rankings</p>
                            </div>
                            <div class="feature">
                                <h3>🛠️ Technical SEO Audit</h3>
                                <p>Identify and fix technical issues affecting your SEO</p>
                            </div>
                            <div class="feature">
                                <h3>🏆 Competitor Analysis</h3>
                                <p>Stay ahead of the competition with detailed insights</p>
                            </div>
                        </div>
                        
                        <div style="text-align: center; margin: 2rem 0;">
                            <a href="https://mozarex.com/dashboard" class="cta-button">Start Your SEO Journey</a>
                        </div>
                        
                        <p><strong>Need help getting started?</strong> Our support team is here to assist you. Just reply to this email or contact us at support@mozarex.com</p>
                        
                        <p>Best regards,<br>The Mozarex Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>Mozarex SEO Platform | <a href="https://mozarex.com">mozarex.com</a></p>
                        <p>This email was sent to {{email}}. If you didn't request this, please ignore this email.</p>
                    </div>
                </div>
            </body>
            </html>
        `
    },

    // Trial Ending Notification
    trial_ending: {
        templateId: process.env.SENDGRID_TRIAL_ENDING_TEMPLATE_ID,
        subject: 'Your Mozarex trial ends in 24 hours - Continue your SEO success! ⏰',
        html: `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Trial Ending Soon</title>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f8fafc; }
                    .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
                    .header { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 2rem; text-align: center; }
                    .header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
                    .content { padding: 2rem; }
                    .warning-box { background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 1rem; margin: 1rem 0; }
                    .warning-box h3 { color: #92400e; margin: 0 0 0.5rem 0; }
                    .plan-highlight { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1.5rem; border-radius: 8px; margin: 1.5rem 0; text-align: center; }
                    .plan-highlight h3 { margin: 0 0 0.5rem 0; font-size: 1.5rem; }
                    .plan-highlight .price { font-size: 2rem; font-weight: 700; margin: 0.5rem 0; }
                    .plan-highlight .period { opacity: 0.9; font-size: 0.9rem; }
                    .cta-button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 1rem 0; }
                    .footer { background: #f1f5f9; padding: 1.5rem; text-align: center; color: #64748b; font-size: 0.9rem; }
                    .features-list { list-style: none; padding: 0; }
                    .features-list li { padding: 0.5rem 0; display: flex; align-items: center; }
                    .features-list li::before { content: "✓"; color: #10b981; font-weight: bold; margin-right: 0.5rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>⏰ Trial Ending Soon</h1>
                        <p>Don't lose access to your SEO tools</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {{user_name}},</h2>
                        
                        <div class="warning-box">
                            <h3>⚠️ Important Notice</h3>
                            <p>Your free trial ends on <strong>{{trial_end_date}}</strong> (in 24 hours). After that, you'll need an active subscription to continue using Mozarex.</p>
                        </div>
                        
                        <p>We hope you've been enjoying the powerful SEO tools and insights Mozarex provides. To continue your SEO success journey, please choose a plan that works for you:</p>
                        
                        <div class="plan-highlight">
                            <h3>{{plan_name}} Plan</h3>
                            <div class="price">$PLAN_PRICE_PLACEHOLDER</div>
                            <div class="period">per {{billing_cycle}}</div>
                            <p>Continue with all the features you've been using</p>
                        </div>
                        
                        <h3>What you'll keep access to:</h3>
                        <ul class="features-list">
                            <li>Advanced SEO analysis and insights</li>
                            <li>AI-powered content generation</li>
                            <li>90-day content calendar</li>
                            <li>Keyword research and tracking</li>
                            <li>Technical SEO audits</li>
                            <li>Competitor analysis</li>
                            <li>Priority email support</li>
                            <li>WordPress integration</li>
                        </ul>
                        
                        <div style="text-align: center; margin: 2rem 0;">
                            <a href="https://mozarex.com/subscription" class="cta-button">Continue with {{plan_name}} Plan</a>
                        </div>
                        
                        <p><strong>Questions?</strong> Our support team is here to help. Reply to this email or contact us at support@mozarex.com</p>
                        
                        <p>Thank you for choosing Mozarex!</p>
                        <p>Best regards,<br>The Mozarex Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>Mozarex SEO Platform | <a href="https://mozarex.com">mozarex.com</a></p>
                        <p>This email was sent to {{email}}. If you don't want to continue, no action is needed.</p>
                    </div>
                </div>
            </body>
            </html>
        `
    },

    // Cancellation Email
    cancellation: {
        templateId: process.env.SENDGRID_CANCELLATION_TEMPLATE_ID,
        subject: 'We\'re sorry to see you go - Your feedback matters to us 💙',
        html: `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>We'll Miss You</title>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f8fafc; }
                    .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }
                    .header { background: linear-gradient(135deg, #64748b 0%, #475569 100%); color: white; padding: 2rem; text-align: center; }
                    .header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
                    .content { padding: 2rem; }
                    .feedback-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.5rem; margin: 1.5rem 0; }
                    .feedback-box h3 { color: #475569; margin: 0 0 1rem 0; }
                    .feedback-text { background: white; border: 1px solid #e2e8f0; border-radius: 4px; padding: 1rem; margin: 1rem 0; font-style: italic; }
                    .cta-button { display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 8px; font-weight: 600; margin: 1rem 0; }
                    .footer { background: #f1f5f9; padding: 1.5rem; text-align: center; color: #64748b; font-size: 0.9rem; }
                    .return-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 2rem 0; }
                    .return-option { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; text-align: center; }
                    .return-option h4 { margin: 0 0 0.5rem 0; color: #475569; }
                    .return-option p { margin: 0; color: #64748b; font-size: 0.9rem; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>💙 We'll Miss You</h1>
                        <p>Your Mozarex subscription has been canceled</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hi {{user_name}},</h2>
                        
                        <p>We're sorry to see you go! Your Mozarex subscription has been successfully canceled.</p>
                        
                        <div class="feedback-box">
                            <h3>💭 Your Feedback Matters</h3>
                            <p>We're constantly working to improve Mozarex. If you shared feedback about why you're leaving, thank you! If not, we'd love to hear from you:</p>
                            {{#if feedback}}
                                <div class="feedback-text">"{{feedback}}"</div>
                            {{/if}}
                            <p>You can always reach us at <a href="mailto:feedback@mozarex.com">feedback@mozarex.com</a></p>
                        </div>
                        
                        <p><strong>What happens next?</strong></p>
                        <ul>
                            <li>You'll continue to have access until the end of your current billing period</li>
                            <li>All your data and reports will be safely stored for 30 days</li>
                            <li>You can reactivate your subscription anytime before then</li>
                        </ul>
                        
                        <h3>Changed your mind?</h3>
                        <div class="return-options">
                            <div class="return-option">
                                <h4>🔄 Reactivate</h4>
                                <p>Restore your subscription and continue where you left off</p>
                                <a href="https://mozarex.com/subscription" class="cta-button">Reactivate Now</a>
                            </div>
                            <div class="return-option">
                                <h4>💬 Contact Support</h4>
                                <p>Need help or have questions? We're here to assist</p>
                                <a href="mailto:support@mozarex.com" class="cta-button">Contact Support</a>
                            </div>
                        </div>
                        
                        <p>Thank you for being part of the Mozarex community. We hope to see you back soon!</p>
                        
                        <p>Best regards,<br>The Mozarex Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>Mozarex SEO Platform | <a href="https://mozarex.com">mozarex.com</a></p>
                        <p>Need help? Contact us at <a href="mailto:support@mozarex.com">support@mozarex.com</a></p>
                    </div>
                </div>
            </body>
            </html>
        `
    }
};

class EmailTemplateService {
    constructor() {
        this.templates = EMAIL_TEMPLATES;
    }

    // Send trial welcome email
    async sendTrialWelcomeEmail(userEmail, userName, trialDays = 7) {
        try {
            if (!process.env.SENDGRID_API_KEY || !process.env.SENDGRID_API_KEY.startsWith('SG.')) {
                console.warn('⚠️ SendGrid not configured. Email not sent to:', userEmail);
                return false;
            }
            
            const template = this.templates.trial_welcome;
            
            const msg = {
                to: userEmail,
                from: {
                    email: process.env.SENDGRID_FROM_EMAIL || 'noreply@mozarex.com',
                    name: 'Mozarex SEO Platform'
                },
                subject: template.subject,
                html: template.html
                    .replace(/\{\{user_name\}\}/g, userName)
                    .replace(/\{\{trial_days\}\}/g, trialDays)
                    .replace(/\{\{email\}\}/g, userEmail)
            };

            await sgMail.send(msg);
            console.log('✅ Trial welcome email sent to:', userEmail);
            return true;
        } catch (error) {
            console.error('❌ Error sending trial welcome email:', error);
            throw error;
        }
    }

    // Send trial ending notification
    async sendTrialEndingEmail(userEmail, userName, planName, price, billingCycle, trialEndDate) {
        try {
            if (!process.env.SENDGRID_API_KEY || !process.env.SENDGRID_API_KEY.startsWith('SG.')) {
                console.warn('⚠️ SendGrid not configured. Email not sent to:', userEmail);
                return false;
            }
            
            const template = this.templates.trial_ending;
            
            const msg = {
                to: userEmail,
                from: {
                    email: process.env.SENDGRID_FROM_EMAIL || 'noreply@mozarex.com',
                    name: 'Mozarex SEO Platform'
                },
                subject: template.subject,
                html: template.html
                    .replace(/\{\{user_name\}\}/g, userName)
                    .replace(/\{\{plan_name\}\}/g, planName)
                    .replace(/PLAN_PRICE_PLACEHOLDER/g, price)
                    .replace(/\{\{billing_cycle\}\}/g, billingCycle)
                    .replace(/\{\{trial_end_date\}\}/g, trialEndDate)
                    .replace(/\{\{email\}\}/g, userEmail)
            };

            await sgMail.send(msg);
            console.log('✅ Trial ending email sent to:', userEmail);
            return true;
        } catch (error) {
            console.error('❌ Error sending trial ending email:', error);
            throw error;
        }
    }

    // Send cancellation email
    async sendCancellationEmail(userEmail, userName, feedback = null) {
        try {
            if (!process.env.SENDGRID_API_KEY || !process.env.SENDGRID_API_KEY.startsWith('SG.')) {
                console.warn('⚠️ SendGrid not configured. Email not sent to:', userEmail);
                return false;
            }
            
            const template = this.templates.cancellation;
            let html = template.html;
            
            // Handle feedback replacement
            if (feedback) {
                html = html.replace(/\{\{#if feedback\}\}[\s\S]*?\{\{\/if\}\}/g, 
                    `<div class="feedback-text">"${feedback}"</div>`);
            } else {
                html = html.replace(/\{\{#if feedback\}\}[\s\S]*?\{\{\/if\}\}/g, '');
            }
            
            const msg = {
                to: userEmail,
                from: {
                    email: process.env.SENDGRID_FROM_EMAIL || 'noreply@mozarex.com',
                    name: 'Mozarex SEO Platform'
                },
                subject: template.subject,
                html: html
                    .replace(/\{\{user_name\}\}/g, userName)
                    .replace(/\{\{email\}\}/g, userEmail)
            };

            await sgMail.send(msg);
            console.log('✅ Cancellation email sent to:', userEmail);
            return true;
        } catch (error) {
            console.error('❌ Error sending cancellation email:', error);
            throw error;
        }
    }

    // Send custom email
    async sendCustomEmail(to, subject, htmlContent, fromName = 'Mozarex SEO Platform') {
        try {
            if (!process.env.SENDGRID_API_KEY || !process.env.SENDGRID_API_KEY.startsWith('SG.')) {
                console.warn('⚠️ SendGrid not configured. Email not sent to:', to);
                return false;
            }
            
            const msg = {
                to: to,
                from: {
                    email: process.env.SENDGRID_FROM_EMAIL || 'noreply@mozarex.com',
                    name: fromName
                },
                subject: subject,
                html: htmlContent
            };

            await sgMail.send(msg);
            console.log('✅ Custom email sent to:', to);
            return true;
        } catch (error) {
            console.error('❌ Error sending custom email:', error);
            throw error;
        }
    }

    // Test email configuration
    async testEmailConfiguration() {
        try {
            const testEmail = process.env.SENDGRID_TEST_EMAIL || 'test@example.com';
            await this.sendCustomEmail(
                testEmail,
                'Mozarex Email Test',
                '<h1>Email configuration test</h1><p>If you receive this email, your SendGrid configuration is working correctly!</p>'
            );
            console.log('✅ Email configuration test successful');
            return true;
        } catch (error) {
            console.error('❌ Email configuration test failed:', error);
            return false;
        }
    }
}

module.exports = new EmailTemplateService();
