/**
 * ==============================================================================
 * Mozarex Automated Website Review Router & Controller (Phase 1)
 * ==============================================================================
 * Exposes:
 *   - POST /create-website-review (Grokbot automated audit submission)
 *   - GET  /review/:token/download (Secure PDF streaming & download analytics)
 *   - GET  /review/:token/data     (Sanitized review data & view analytics)
 */

const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const rateLimit = require('express-rate-limit');
const {
  canonicalizeDomain,
  findActiveAuditByDomain,
  findAuditByPublicToken,
  createWebsiteAudit,
  getAuditPdfForDownload,
  recordAuditView
} = require('../services/websiteReviewService');
const { sanitizeText } = require('../services/pdfReportService');

// ==============================================================================
// 1. RATE LIMITING MIDDLEWARE
// ==============================================================================
// Configurable rate limit for Grokbot submissions (defaults to 200/hour)
const grokbotHourlyLimit = parseInt(process.env.GROKBOT_RATE_LIMIT_PER_HOUR, 10) || 200;

const grokbotSubmissionLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, // 1 hour
  max: grokbotHourlyLimit,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    success: false,
    code: 'RATE_LIMITED',
    error: 'Too many audit submission requests. Please try again later.'
  }
});

// Download limiter (prevents scraping or excessive automated downloads)
const downloadLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    success: false,
    code: 'RATE_LIMITED',
    error: 'Too many download requests. Please try again later.'
  }
});

// ==============================================================================
// 2. GROKBOT AUTHENTICATION MIDDLEWARE
// ==============================================================================
function requireGrokbotApiKey(req, res, next) {
  const authHeader = req.headers.authorization;
  const configuredSecret = process.env.MOZAREX_GROKBOT_API_KEY;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      success: false,
      code: 'INVALID_AUTH',
      error: 'Unauthorized: Missing or malformed Authorization header. Expected Bearer <token>'
    });
  }

  const providedKey = authHeader.slice(7).trim();

  // In test environment without explicit secret, permit testing key or validate
  const effectiveExpectedKey = configuredSecret || (process.env.NODE_ENV === 'test' ? 'test_grokbot_api_key_valid_12345' : null);

  if (!effectiveExpectedKey) {
    console.error('[CRITICAL] MOZAREX_GROKBOT_API_KEY is not configured on the server.');
    return res.status(500).json({
      success: false,
      code: 'SERVER_MISCONFIGURED',
      error: 'Internal authentication configuration error.'
    });
  }

  // Constant-time comparison to protect against timing attacks
  try {
    const providedBuf = Buffer.from(providedKey, 'utf8');
    const expectedBuf = Buffer.from(effectiveExpectedKey, 'utf8');

    if (providedBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(providedBuf, expectedBuf)) {
      return res.status(401).json({
        success: false,
        code: 'INVALID_AUTH',
        error: 'Unauthorized: Invalid API key'
      });
    }
  } catch (err) {
    return res.status(401).json({
      success: false,
      code: 'INVALID_AUTH',
      error: 'Unauthorized: Invalid API key'
    });
  }

  next();
}

// ==============================================================================
// 3. INPUT VALIDATION HELPER
// ==============================================================================
function validateAuditPayload(body) {
  const errors = [];

  if (!body || typeof body !== 'object') {
    return ['Request body must be a valid JSON object'];
  }

  // business_name
  if (!body.business_name || typeof body.business_name !== 'string' || !body.business_name.trim()) {
    errors.push('business_name is required and must be a non-empty string');
  } else if (body.business_name.trim().length > 200) {
    errors.push('business_name exceeds maximum length of 200 characters');
  }

  // website_url
  if (!body.website_url || typeof body.website_url !== 'string' || !body.website_url.trim()) {
    errors.push('website_url is required and must be a valid http/https URL');
  } else if (body.website_url.trim().length > 500) {
    errors.push('website_url exceeds maximum length of 500 characters');
  } else {
    try {
      const parsed = new URL(body.website_url.trim());
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        errors.push('website_url must use http or https protocol');
      }
    } catch (e) {
      errors.push('website_url is not a valid URL format');
    }
  }

  // contact_email (optional)
  if (body.contact_email !== undefined && body.contact_email !== null && body.contact_email !== '') {
    if (typeof body.contact_email !== 'string') {
      errors.push('contact_email must be a string');
    } else {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(body.contact_email.trim())) {
        errors.push('contact_email must be a valid email address');
      } else if (body.contact_email.trim().length > 255) {
        errors.push('contact_email exceeds maximum length of 255 characters');
      }
    }
  }

  // findings
  if (!body.findings || !Array.isArray(body.findings)) {
    errors.push('findings is required and must be an array');
  } else if (body.findings.length === 0) {
    errors.push('findings must contain at least one finding item');
  } else if (body.findings.length > 20) {
    errors.push('findings cannot contain more than 20 items');
  } else {
    body.findings.forEach((item, idx) => {
      const num = idx + 1;
      if (!item || typeof item !== 'object') {
        errors.push(`finding item #${num} must be an object`);
        return;
      }
      if (!item.title || typeof item.title !== 'string' || !item.title.trim()) {
        errors.push(`finding item #${num} title is required`);
      } else if (item.title.trim().length > 200) {
        errors.push(`finding item #${num} title exceeds 200 characters`);
      }

      if (!item.description || typeof item.description !== 'string' || !item.description.trim()) {
        errors.push(`finding item #${num} description is required`);
      } else if (item.description.trim().length > 2000) {
        errors.push(`finding item #${num} description exceeds 2000 characters`);
      }

      if (!item.recommendation || typeof item.recommendation !== 'string' || !item.recommendation.trim()) {
        errors.push(`finding item #${num} recommendation is required`);
      } else if (item.recommendation.trim().length > 2000) {
        errors.push(`finding item #${num} recommendation exceeds 2000 characters`);
      }
    });
  }

  // proposed_price (optional)
  if (body.proposed_price !== undefined && body.proposed_price !== null) {
    const numPrice = Number(body.proposed_price);
    if (isNaN(numPrice) || numPrice <= 0) {
      errors.push('proposed_price must be a positive number if provided');
    }
  }

  // currency (optional)
  if (body.currency !== undefined && body.currency !== null) {
    if (typeof body.currency !== 'string' || body.currency.toUpperCase() !== 'AUD') {
      errors.push('currency must be "AUD"');
    }
  }

  return errors;
}

// ==============================================================================
// 4. API ENDPOINTS
// ==============================================================================

/**
 * POST /create-website-review (or /api/website-review/create)
 * Authenticated submission endpoint for Grokbot.
 */
router.post(
  ['/create-website-review', '/api/website-review/create'],
  grokbotSubmissionLimiter,
  requireGrokbotApiKey,
  async (req, res) => {
    const requestId = crypto.randomUUID();
    const startTime = Date.now();

    try {
      // 1. Validate Input Payload
      const validationErrors = validateAuditPayload(req.body);
      if (validationErrors.length > 0) {
        return res.status(400).json({
          success: false,
          code: 'INVALID_INPUT',
          error: validationErrors.join('; ')
        });
      }

      const {
        business_name,
        business_type,
        suburb,
        website_url,
        contact_email,
        findings,
        proposed_price,
        currency = 'AUD'
      } = req.body;

      const canonicalDomain = canonicalizeDomain(website_url);

      console.log(`[WebsiteReview] [Req:${requestId}] Processing audit for domain: ${canonicalDomain}`);

      // 2. Duplicate Check
      const existingAudit = await findActiveAuditByDomain(canonicalDomain);
      if (existingAudit) {
        console.log(`[WebsiteReview] [Req:${requestId}] Duplicate audit detected for domain: ${canonicalDomain} (AuditID: ${existingAudit.id})`);
        return res.status(409).json({
          success: false,
          code: 'AUDIT_ALREADY_EXISTS',
          message: 'An active website audit already exists for this domain.',
          existing_audit_id: existingAudit.id,
          existing_report_url: `https://mozarex.com/review/${existingAudit.public_token}`
        });
      }

      // 3. Create Audit Record, Generate PDF, and Upload to Supabase Private Storage
      // IMPORTANT: Status advances to 'ready'. No email is dispatched.
      const result = await createWebsiteAudit({
        business_name,
        business_type,
        suburb,
        website_url,
        contact_email,
        findings,
        proposed_price,
        currency
      });

      const durationMs = Date.now() - startTime;
      console.log(`[WebsiteReview] [Req:${requestId}] Audit created successfully. ID: ${result.audit_id}, Duration: ${durationMs}ms`);

      return res.status(201).json({
        success: true,
        audit_id: result.audit_id,
        status: result.status,
        business_name: result.business_name,
        report_url: result.report_url,
        download_url: result.download_url
      });

    } catch (err) {
      const durationMs = Date.now() - startTime;
      console.error(`[WebsiteReview] [Req:${requestId}] Failed after ${durationMs}ms. Error:`, err.message);

      const statusCode = err.code === 'DATABASE_ERROR' ? 500 :
                         err.code === 'STORAGE_UPLOAD_FAILED' ? 502 :
                         err.code === 'PDF_GENERATION_FAILED' ? 500 : 500;

      return res.status(statusCode).json({
        success: false,
        code: err.code || 'INTERNAL_ERROR',
        error: 'Failed to process website review request.'
      });
    }
  }
);

/**
 * GET /review/:token/download
 * Public secure download endpoint that streams the PDF and tracks download metrics.
 */
router.get(
  '/review/:token/download',
  downloadLimiter,
  async (req, res) => {
    const { token } = req.params;

    if (!token || typeof token !== 'string' || token.length < 10) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_TOKEN',
        error: 'Invalid report token.'
      });
    }

    try {
      const { pdfBuffer, fileName } = await getAuditPdfForDownload(token);

      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
      res.setHeader('Content-Length', pdfBuffer.length);
      res.setHeader('Cache-Control', 'private, no-cache, no-store, must-revalidate');

      return res.send(pdfBuffer);
    } catch (err) {
      if (err.code === 'NOT_FOUND') {
        return res.status(404).json({
          success: false,
          code: 'REPORT_NOT_FOUND',
          error: 'Website review report not found.'
        });
      }
      if (err.code === 'NOT_READY') {
        return res.status(422).json({
          success: false,
          code: 'REPORT_NOT_READY',
          error: 'The requested website review report is still being generated.'
        });
      }

      console.error(`[WebsiteReviewDownload] Download error for token ${token}:`, err.message);
      return res.status(500).json({
        success: false,
        code: 'DOWNLOAD_FAILED',
        error: 'Failed to stream website review report.'
      });
    }
  }
);

/**
 * GET /review/:token/data
 * Data retrieval endpoint for future report UI and view analytics tracking.
 */
router.get(
  '/review/:token/data',
  async (req, res) => {
    const { token } = req.params;

    if (!token || typeof token !== 'string' || token.length < 10) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_TOKEN',
        error: 'Invalid report token.'
      });
    }

    try {
      const isInternal = req.query.internal === 'true';
      const audit = await recordAuditView(token, { isInternalCheck: isInternal });

      if (!audit) {
        return res.status(404).json({
          success: false,
          code: 'REPORT_NOT_FOUND',
          error: 'Website review report not found.'
        });
      }

      // Strict Public DTO Allowlist (Excludes all internal IDs, emails, storage paths, metrics, and workflows)
      const publicReportDto = {
        success: true,
        business_name: audit.business_name,
        business_type: audit.business_type || null,
        suburb: audit.suburb || null,
        website_url: audit.website_url,
        findings: Array.isArray(audit.findings) ? audit.findings : [],
        proposed_price: (audit.proposed_price !== null && audit.proposed_price !== undefined) ? Number(audit.proposed_price) : null,
        currency: audit.currency || 'AUD',
        report_available: ['ready', 'approved', 'sent'].includes(audit.status),
        report_url: `https://mozarex.com/review/${audit.public_token}`,
        download_url: `https://mozarex.com/review/${audit.public_token}/download`
      };

      return res.json(publicReportDto);
    } catch (err) {
      console.error(`[WebsiteReviewView] Error fetching view data for token ${token}:`, err.message);
      return res.status(500).json({
        success: false,
        code: 'VIEW_DATA_FAILED',
        error: 'Failed to retrieve website review details.'
      });
    }
  }
);

module.exports = router;
