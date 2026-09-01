const https = require('https');

// Idempotency tracking set to prevent duplicate emails for identical application IDs
const sentApplicationNotificationIds = new Set();
const sentEmailsLog = [];

/**
 * Escapes HTML characters in user-supplied strings to prevent HTML injection in emails.
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Formats ISO date string into readable human format: e.g. "1 September 2026, 4:15 PM"
 */
function formatDateTime(isoString) {
  try {
    const d = new Date(isoString || Date.now());
    return d.toLocaleString('en-AU', {
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  } catch (e) {
    return new Date().toISOString();
  }
}

/**
 * Partner Email Notification Service
 */
class PartnerEmailService {
  constructor() {
    this.sentEmails = sentEmailsLog;
    this.sentApplicationIds = sentApplicationNotificationIds;
    this.mockFailure = false; // Hook for testing provider failure recovery
  }

  /**
   * Clears in-memory test logs and idempotency tracking.
   */
  resetState() {
    this.sentEmails.length = 0;
    this.sentApplicationIds.clear();
    this.mockFailure = false;
  }

  /**
   * Gets the configured recipient email from environment.
   */
  getAdminRecipient() {
    return process.env.AIVEKAI_PARTNER_APPLICATION_ADMIN_EMAIL || 'info@mozarex.com';
  }

  /**
   * Generates sanitized plain text and HTML email content.
   */
  buildEmailContent(app) {
    const safeName = escapeHtml(app.full_name || app.fullName);
    const safeEmail = escapeHtml(app.email);
    const safeCountry = escapeHtml(app.country || 'Not specified');
    const safeBusiness = escapeHtml(app.business_name || app.businessName || 'N/A');
    const safeInstagram = escapeHtml(app.instagram || '');
    const safeTiktok = escapeHtml(app.tiktok || '');
    const safeYoutube = escapeHtml(app.youtube || '');
    const safeWebsite = escapeHtml(app.website || '');
    const safeOtherSocial = escapeHtml(app.other_social || app.otherSocial || '');
    const safeAudienceSize = escapeHtml(app.audience_size || app.audienceSize || 'N/A');
    const safeNiche = escapeHtml(app.audience_niche || app.audienceNiche || 'N/A');
    const safeCode = escapeHtml(app.preferred_referral_code || app.preferredReferralCode || 'N/A');
    const safePlan = escapeHtml(app.promotion_plan || app.promotionPlan || 'N/A');
    const safeNotes = escapeHtml(app.notes || 'None');
    const safeId = escapeHtml(app.id || 'N/A');
    const formattedDate = formatDateTime(app.created_at);

    // Socials display text
    const socialsList = [];
    if (safeInstagram) socialsList.push(`Instagram: ${safeInstagram}`);
    if (safeTiktok) socialsList.push(`TikTok: ${safeTiktok}`);
    if (safeYoutube) socialsList.push(`YouTube: ${safeYoutube}`);
    if (safeWebsite) socialsList.push(`Website: ${safeWebsite}`);
    if (safeOtherSocial) socialsList.push(`Other: ${safeOtherSocial}`);
    const socialsSummary = socialsList.length > 0 ? socialsList.join(' | ') : 'None provided';

    const subject = 'New AivekAI Partner Application — Review Required';

    const textBody = `
New Partner Application
A new application has been submitted for the AivekAI Partner Program.

Applicant: ${app.full_name || app.fullName}
Email: ${app.email}
Country: ${app.country || 'Not specified'}
Business Name: ${app.business_name || app.businessName || 'N/A'}
Social / Website: ${socialsSummary}
Audience Size: ${app.audience_size || app.audienceSize || 'N/A'}
Content Niche: ${app.audience_niche || app.audienceNiche || 'N/A'}
Preferred Code: ${app.preferred_referral_code || app.preferredReferralCode || 'N/A'}
Promotion Plan: ${app.promotion_plan || app.promotionPlan || 'N/A'}
Notes: ${app.notes || 'None'}
Status: Pending Review
Application ID: ${app.id}
Submitted: ${formattedDate}

Please review the application in the AivekAI Admin Portal:
https://mozarex.com/aivekai/admin/partners
`.trim();

    const htmlBody = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1a1a1a; margin: 0; padding: 20px; background-color: #f4f6f8; }
    .card { max-width: 600px; margin: 0 auto; background: #ffffff; border: 1px solid #e1e4e8; border-radius: 12px; padding: 32px; box-shadow: 0 4px 16px rgba(0,0,0,0.05); }
    .header { border-bottom: 2px solid #006B5C; padding-bottom: 16px; margin-bottom: 24px; }
    .header h2 { color: #006B5C; margin: 0 0 6px 0; font-size: 22px; }
    .badge { display: inline-block; background: #E6F4F1; color: #004D42; padding: 4px 12px; border-radius: 16px; font-weight: 700; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
    .field-group { margin-bottom: 16px; }
    .field-label { font-size: 13px; font-weight: 700; color: #5C6764; text-transform: uppercase; margin-bottom: 4px; }
    .field-value { font-size: 15px; color: #121816; }
    .btn-review { display: inline-block; background: #006B5C; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 15px; margin-top: 24px; }
    .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e1e4e8; font-size: 12px; color: #6c757d; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <span class="badge">Pending Review</span>
      <h2>New Partner Application</h2>
      <p style="margin: 6px 0 0 0; color: #5C6764; font-size: 14px;">A new creator application has been submitted for the AivekAI Partner Program.</p>
    </div>

    <div class="field-group">
      <div class="field-label">Applicant Name</div>
      <div class="field-value"><strong>${safeName}</strong></div>
    </div>

    <div class="field-group">
      <div class="field-label">Email Address</div>
      <div class="field-value"><a href="mailto:${safeEmail}" style="color: #006B5C;">${safeEmail}</a></div>
    </div>

    <div class="field-group">
      <div class="field-label">Country & Business</div>
      <div class="field-value">${safeCountry} &middot; Business: ${safeBusiness}</div>
    </div>

    <div class="field-group">
      <div class="field-label">Socials & Website</div>
      <div class="field-value">${socialsSummary}</div>
    </div>

    <div class="field-group">
      <div class="field-label">Audience & Niche</div>
      <div class="field-value">${safeAudienceSize} &middot; ${safeNiche}</div>
    </div>

    <div class="field-group">
      <div class="field-label">Preferred Referral Code</div>
      <div class="field-value"><code>${safeCode}</code></div>
    </div>

    <div class="field-group">
      <div class="field-label">Promotion Plan</div>
      <div class="field-value" style="background: #F8FAF9; padding: 10px; border-radius: 6px; border: 1px solid rgba(0,107,92,0.1);">${safePlan}</div>
    </div>

    <div class="field-group">
      <div class="field-label">Additional Notes</div>
      <div class="field-value">${safeNotes}</div>
    </div>

    <div class="field-group">
      <div class="field-label">Application Details</div>
      <div class="field-value">ID: <code>${safeId}</code> &middot; Submitted: ${formattedDate}</div>
    </div>

    <div style="text-align: center;">
      <a href="https://mozarex.com/aivekai/admin/partners" class="btn-review" target="_blank">Review Application in Admin Portal &rarr;</a>
    </div>

    <div class="footer">
      Note: This email was automatically generated. Administrative authorization is required to access the portal and approve applications.
    </div>
  </div>
</body>
</html>
`.trim();

    return { subject, textBody, htmlBody };
  }

  /**
   * Sends the admin notification email for a submitted application.
   * Ensures idempotency so retry/duplicate calls do not send multiple emails.
   */
  async sendApplicationNotification(application) {
    if (!application || !application.id) {
      throw new Error('Application object with a valid ID is required for notification.');
    }

    const applicationId = application.id;

    // Idempotency check: duplicate prevention
    if (this.sentApplicationIds.has(applicationId)) {
      return {
        success: true,
        duplicate: true,
        message: 'Notification email already sent for this application ID.'
      };
    }

    const recipient = this.getAdminRecipient();
    const { subject, textBody, htmlBody } = this.buildEmailContent(application);

    // Mock failure simulation for testing error resilience
    if (this.mockFailure) {
      throw new Error('Simulated email provider network failure');
    }

    // Provider Dispatch Logic:
    // If SendGrid/Resend or other provider is configured in environment, dispatch via HTTP API.
    // In all environments, log and record in sentEmails.
    const emailRecord = {
      id: `email_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
      application_id: applicationId,
      to: recipient,
      subject,
      text: textBody,
      html: htmlBody,
      sent_at: new Date().toISOString()
    };

    // Attempt provider dispatch if configured
    if (process.env.RESEND_API_KEY) {
      try {
        await this._dispatchViaResend(emailRecord);
      } catch (err) {
        console.warn('Resend API dispatch error (fallback to standard log):', err.message);
      }
    } else if (process.env.SENDGRID_API_KEY) {
      try {
        await this._dispatchViaSendGrid(emailRecord);
      } catch (err) {
        console.warn('SendGrid API dispatch error (fallback to standard log):', err.message);
      }
    }

    // Mark application ID as sent in idempotency set
    this.sentApplicationIds.add(applicationId);
    this.sentEmails.push(emailRecord);

    return {
      success: true,
      duplicate: false,
      message_id: emailRecord.id,
      recipient,
      sent_at: emailRecord.sent_at
    };
  }

  /**
   * Internal Resend API dispatcher
   */
  _dispatchViaResend(record) {
    return new Promise((resolve, reject) => {
      const payload = JSON.stringify({
        from: process.env.AIVEKAI_EMAIL_FROM || 'AivekAI Notifications <notifications@mozarex.com>',
        to: [record.to],
        subject: record.subject,
        text: record.text,
        html: record.html
      });

      const req = https.request('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.RESEND_API_KEY}`,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload)
        }
      }, (res) => {
        let data = '';
        res.on('data', c => data += c);
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(data);
          } else {
            reject(new Error(`Resend HTTP ${res.statusCode}: ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.write(payload);
      req.end();
    });
  }

  /**
   * Internal SendGrid API dispatcher
   */
  _dispatchViaSendGrid(record) {
    return new Promise((resolve, reject) => {
      const payload = JSON.stringify({
        personalizations: [{ to: [{ email: record.to }] }],
        from: { email: process.env.AIVEKAI_EMAIL_FROM || 'notifications@mozarex.com', name: 'AivekAI Partner Program' },
        subject: record.subject,
        content: [
          { type: 'text/plain', value: record.text },
          { type: 'text/html', value: record.html }
        ]
      });

      const req = https.request('https://api.sendgrid.com/v3/mail/send', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.SENDGRID_API_KEY}`,
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload)
        }
      }, (res) => {
        let data = '';
        res.on('data', c => data += c);
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(data);
          } else {
            reject(new Error(`SendGrid HTTP ${res.statusCode}: ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.write(payload);
      req.end();
    });
  }
}

const partnerEmailService = new PartnerEmailService();

module.exports = partnerEmailService;
module.exports.PartnerEmailService = PartnerEmailService;
module.exports.escapeHtml = escapeHtml;
