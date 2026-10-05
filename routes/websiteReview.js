/**
 * ==============================================================================
 * Mozarex Automated Website Review Router & Controller (Phase 1 & Phase 2)
 * ==============================================================================
 * Exposes:
 *   - POST /create-website-review (Grokbot automated audit submission with optional PDF)
 *   - PUT  /website-review/:audit_id/report (Attach or replace PDF report on existing audit)
 *   - PATCH /website-review/:audit_id/report (Alias for PUT)
 *   - DELETE /website-review/:audit_id/report (Optional: revert to generated PDF)
 *   - GET  /review/:token/download (Secure PDF streaming & download analytics)
 *   - GET  /review/:token/data     (Sanitized review data & view analytics)
 *   - GET  /review/:token          (Customer-facing personalized review landing page)
 *   - POST /api/website-review/enquiry (Contact & Homepage example direct lead capture)
 */

const express = require('express');
const router = express.Router();
const path = require('path');
const crypto = require('crypto');
const rateLimit = require('express-rate-limit');
const {
  canonicalizeDomain,
  validateAndDecodePdf,
  findActiveAuditByDomain,
  findAuditById,
  findAuditByPublicToken,
  createWebsiteAudit,
  attachOrReplaceReportPdf,
  deleteReportPdf,
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
  max: 120,
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

  if (!authHeader || typeof authHeader !== 'string' || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      success: false,
      code: 'UNAUTHORIZED',
      error: 'Unauthorized: Missing or malformed Authorization header. Expected Bearer <token>'
    });
  }

  const rawProvidedKey = authHeader.slice(7).trim();

  // Permitted keys (in test mode, also accept test key)
  const candidateKeys = [];
  if (configuredSecret) candidateKeys.push(configuredSecret);
  if (process.env.NODE_ENV === 'test') {
    candidateKeys.push('test_grokbot_api_key_valid_12345');
  }

  if (candidateKeys.length === 0) {
    console.error('[CRITICAL] MOZAREX_GROKBOT_API_KEY is not configured on the server.');
    return res.status(500).json({
      success: false,
      code: 'SERVER_MISCONFIGURED',
      error: 'Internal authentication configuration error.'
    });
  }

  // Sanitize provided key (strip whitespace, outer quotes)
  let cleanProvided = rawProvidedKey.trim();
  if ((cleanProvided.startsWith('"') && cleanProvided.endsWith('"')) ||
      (cleanProvided.startsWith("'") && cleanProvided.endsWith("'"))) {
    cleanProvided = cleanProvided.slice(1, -1).trim();
  }

  const providedBuf = Buffer.from(cleanProvided, 'utf8');

  let authenticated = false;
  for (const expectedKey of candidateKeys) {
    let cleanExpected = expectedKey.trim();
    if ((cleanExpected.startsWith('"') && cleanExpected.endsWith('"')) ||
        (cleanExpected.startsWith("'") && cleanExpected.endsWith("'"))) {
      cleanExpected = cleanExpected.slice(1, -1).trim();
    }
    if (cleanExpected.startsWith('Bearer ')) {
      cleanExpected = cleanExpected.slice(7).trim();
    }

    try {
      const expectedBuf = Buffer.from(cleanExpected, 'utf8');
      if (providedBuf.length === expectedBuf.length && crypto.timingSafeEqual(providedBuf, expectedBuf)) {
        authenticated = true;
        break;
      }
    } catch (e) {}
  }

  const expectedHash = configuredSecret ? crypto.createHash('sha256').update(configuredSecret.trim()).digest('hex').slice(0, 12) : 'none';
  const providedHash = crypto.createHash('sha256').update(cleanProvided).digest('hex').slice(0, 12);
  console.log(`[GrokbotAuthAudit] Present=${!!configuredSecret} ExpLen=${configuredSecret ? configuredSecret.trim().length : 0} ProvLen=${cleanProvided.length} ExpFP=${expectedHash} ProvFP=${providedHash} Match=${authenticated}`);

  if (!authenticated) {
    return res.status(401).json({
      success: false,
      code: 'UNAUTHORIZED',
      error: 'Unauthorized: Invalid API key'
    });
  }

  next();
}

// ==============================================================================
// 3. MEDIA TYPE VALIDATION MIDDLEWARE
// ==============================================================================
function requireJsonContentType(req, res, next) {
  if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
    const contentType = req.headers['content-type'] || '';
    if (!contentType.includes('application/json')) {
      return res.status(415).json({
        success: false,
        code: 'UNSUPPORTED_MEDIA_TYPE',
        error: 'Content-Type must be application/json'
      });
    }
  }
  next();
}

// ==============================================================================
// 4. INPUT VALIDATION HELPER
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

// 12 MB json body parser for review routes (accommodates 8 MB PDF base64 ~10.7 MB)
const json12MbParser = express.json({ limit: '12mb' });

// ==============================================================================
// 5. API ENDPOINTS
// ==============================================================================

/**
 * POST /create-website-review (or /api/website-review/create)
 * Authenticated submission endpoint for Grokbot.
 * Accepts standard audit payload plus optional inline report_pdf_* fields.
 */
router.post(
  ['/create-website-review', '/api/website-review/create'],
  grokbotSubmissionLimiter,
  requireGrokbotApiKey,
  requireJsonContentType,
  json12MbParser,
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

      // 2. Validate PDF fields if present before any DB operations
      let pdfValidation;
      try {
        pdfValidation = validateAndDecodePdf({
          report_pdf_base64: req.body.report_pdf_base64,
          report_pdf_filename: req.body.report_pdf_filename,
          report_pdf_sha256: req.body.report_pdf_sha256
        }, req.body.business_name);
      } catch (pdfErr) {
        return res.status(pdfErr.statusCode || 400).json({
          success: false,
          code: pdfErr.code || 'INVALID_INPUT',
          error: pdfErr.message
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
        currency = 'AUD',
        report_pdf_base64,
        report_pdf_filename,
        report_pdf_sha256
      } = req.body;

      const canonicalDomain = canonicalizeDomain(website_url);

      // 3. Duplicate Check
      const existingAudit = await findActiveAuditByDomain(canonicalDomain);
      if (existingAudit) {
        console.log(`[WebsiteReview] [Req:${requestId}] Duplicate audit detected for domain: ${canonicalDomain} (AuditID: ${existingAudit.id})`);
        return res.status(409).json({
          success: false,
          code: 'AUDIT_ALREADY_EXISTS',
          message: 'An active website audit already exists for this domain.',
          existing_audit_id: existingAudit.id,
          existing_report_url: `https://mozarex.com/review/${existingAudit.public_token}`,
          existing_download_url: `https://mozarex.com/review/${existingAudit.public_token}/download`
        });
      }

      // 4. Create Audit Record, handle PDF, and advance status to 'ready'
      const result = await createWebsiteAudit({
        business_name,
        business_type,
        suburb,
        website_url,
        contact_email,
        findings,
        proposed_price,
        currency,
        report_pdf_base64,
        report_pdf_filename,
        report_pdf_sha256
      });

      const durationMs = Date.now() - startTime;
      const pdfBytes = result.report_pdf && result.report_pdf.bytes ? result.report_pdf.bytes : 0;
      const pdfSha = result.report_pdf && result.report_pdf.sha256 ? result.report_pdf.sha256.slice(0, 12) : 'none';
      console.log(`[WebsiteReview] [Req:${requestId}] Audit created successfully. ID: ${result.audit_id}, PDF_Source: ${result.report_pdf.source}, Bytes: ${pdfBytes}, SHA: ${pdfSha}, Duration: ${durationMs}ms`);

      return res.status(201).json({
        success: true,
        audit_id: result.audit_id,
        status: result.status,
        business_name: result.business_name,
        report_url: result.report_url,
        download_url: result.download_url,
        report_pdf: result.report_pdf
      });

    } catch (err) {
      const durationMs = Date.now() - startTime;
      console.error(`[WebsiteReview] [Req:${requestId}] Failed after ${durationMs}ms. Error:`, err.message);

      const statusCode = err.statusCode || (err.code === 'STORAGE_ERROR' ? 500 : 500);

      return res.status(statusCode).json({
        success: false,
        code: err.code || 'STORAGE_ERROR',
        error: err.message || 'Failed to process website review request.'
      });
    }
  }
);

/**
 * PUT /website-review/:audit_id/report (and PATCH alias)
 * Attaches or replaces the PDF report on an existing website audit.
 */
const handleAttachOrReplaceReportPdf = async (req, res) => {
  const { audit_id } = req.params;
  const requestId = crypto.randomUUID();
  const startTime = Date.now();

  if (!audit_id || typeof audit_id !== 'string') {
    return res.status(400).json({
      success: false,
      code: 'INVALID_INPUT',
      error: 'audit_id is required'
    });
  }

  try {
    const { report_pdf_base64, report_pdf_filename, report_pdf_sha256 } = req.body || {};

    if (!report_pdf_base64) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_BASE64',
        error: 'report_pdf_base64 is required'
      });
    }

    const result = await attachOrReplaceReportPdf(audit_id, {
      report_pdf_base64,
      report_pdf_filename,
      report_pdf_sha256
    });

    const durationMs = Date.now() - startTime;
    const pdfBytes = result.report_pdf && result.report_pdf.bytes ? result.report_pdf.bytes : 0;
    const pdfSha = result.report_pdf && result.report_pdf.sha256 ? result.report_pdf.sha256.slice(0, 12) : 'none';
    console.log(`[WebsiteReviewAttach] [Req:${requestId}] PDF processed for Audit ID: ${result.audit_id}, Replaced: ${result.report_pdf.replaced}, Unchanged: ${result.report_pdf.unchanged}, Bytes: ${pdfBytes}, SHA: ${pdfSha}, Duration: ${durationMs}ms`);

    return res.status(200).json({
      success: true,
      audit_id: result.audit_id,
      status: result.status,
      business_name: result.business_name,
      report_url: result.report_url,
      download_url: result.download_url,
      report_pdf: result.report_pdf
    });

  } catch (err) {
    const durationMs = Date.now() - startTime;
    console.error(`[WebsiteReviewAttach] [Req:${requestId}] Failed after ${durationMs}ms. Error:`, err.message);

    const statusCode = err.statusCode || (err.code === 'AUDIT_NOT_FOUND' ? 404 :
                                          err.code === 'PDF_TOO_LARGE' ? 413 :
                                          err.code === 'INVALID_PDF' || err.code === 'PDF_CHECKSUM_MISMATCH' ? 422 :
                                          err.code === 'INVALID_BASE64' ? 400 : 500);

    return res.status(statusCode).json({
      success: false,
      code: err.code || 'STORAGE_ERROR',
      error: err.message || 'Failed to attach report PDF.'
    });
  }
};

router.put(
  ['/website-review/:audit_id/report', '/api/website-review/:audit_id/report'],
  grokbotSubmissionLimiter,
  requireGrokbotApiKey,
  requireJsonContentType,
  json12MbParser,
  handleAttachOrReplaceReportPdf
);

router.patch(
  ['/website-review/:audit_id/report', '/api/website-review/:audit_id/report'],
  grokbotSubmissionLimiter,
  requireGrokbotApiKey,
  requireJsonContentType,
  json12MbParser,
  handleAttachOrReplaceReportPdf
);

/**
 * DELETE /website-review/:audit_id/report
 * Optional endpoint to revert to generated PDF.
 */
router.delete(
  ['/website-review/:audit_id/report', '/api/website-review/:audit_id/report'],
  requireGrokbotApiKey,
  async (req, res) => {
    const { audit_id } = req.params;
    try {
      const result = await deleteReportPdf(audit_id);
      return res.status(200).json(result);
    } catch (err) {
      const statusCode = err.statusCode || (err.code === 'AUDIT_NOT_FOUND' ? 404 : 500);
      return res.status(statusCode).json({
        success: false,
        code: err.code || 'INTERNAL_ERROR',
        error: err.message
      });
    }
  }
);

/**
 * GET /review/:token/download
 * Public secure download endpoint that streams the PDF and tracks download metrics.
 * Supports ?inline=1 for viewing in browser.
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

      const disposition = req.query.inline === '1' ? 'inline' : 'attachment';
      const asciiName = fileName.replace(/[^\x20-\x7E]/g, '_').replace(/"/g, '\\"');
      const encodedName = encodeURIComponent(fileName);

      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', `${disposition}; filename="${asciiName}"; filename*=UTF-8''${encodedName}`);
      res.setHeader('Content-Length', pdfBuffer.length);
      res.setHeader('Cache-Control', 'private, max-age=300');
      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.setHeader('X-Robots-Tag', 'noindex');

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
 * Data retrieval endpoint for report UI and view analytics tracking.
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

      // Strict Public DTO Allowlist (Excludes internal IDs, emails, storage paths, metrics, and workflows)
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

/**
 * GET /review/:token
 * Customer-Facing Personalised Website Review Page (Phase 2)
 */
router.get(
  '/review/:token',
  (req, res) => {
    const { token } = req.params;

    if (!token || typeof token !== 'string' || token.length < 10) {
      return res.status(400).sendFile(path.join(__dirname, '..', 'frontend', 'website-review.html'));
    }

    res.setHeader('X-Robots-Tag', 'noindex, nofollow, noarchive');
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    return res.sendFile(path.join(__dirname, '..', 'frontend', 'website-review.html'));
  }
);

// Rate limiter for customer enquiry form submissions (prevents spam/flooding)
const enquiryLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, // 1 hour
  max: 30,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    success: false,
    code: 'RATE_LIMITED',
    error: 'Too many enquiry requests. Please try again later.'
  }
});

/**
 * POST /api/website-review/enquiry
 * Direct server-side enquiry handler for Homepage Examples and Free Consultations.
 */
router.post(
  ['/api/website-review/enquiry', '/api/enquiry'],
  enquiryLimiter,
  async (req, res) => {
    const {
      name,
      email,
      phone,
      message,
      package_choice,
      intent = 'homepage_example',
      source = 'website_review',
      business_name
    } = req.body || {};

    if (!name || typeof name !== 'string' || !name.trim()) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_INPUT',
        error: 'Please provide your name.'
      });
    }

    if (!email || typeof email !== 'string' || !email.trim()) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_INPUT',
        error: 'Please provide your email address.'
      });
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      return res.status(400).json({
        success: false,
        code: 'INVALID_INPUT',
        error: 'Please provide a valid email address.'
      });
    }

    const cleanName = sanitizeText(name).slice(0, 100);
    const cleanEmail = email.trim().toLowerCase().slice(0, 255);
    const cleanPhone = phone ? sanitizeText(phone).slice(0, 50) : null;
    const cleanMessage = message ? sanitizeText(message).slice(0, 2000) : null;
    const cleanPackage = package_choice ? sanitizeText(package_choice).slice(0, 100) : null;
    const cleanBizName = business_name ? sanitizeText(business_name).slice(0, 200) : 'Unspecified Business';
    const cleanIntent = intent === 'free_consultation' ? 'free_consultation' : 'website_upgrade';

    console.log(`[WebsiteReviewEnquiry] New lead received: ${cleanName} (${cleanEmail}) for business "${cleanBizName}" (Intent: ${cleanIntent}, Package: ${cleanPackage || 'unspecified'}, Source: ${source})`);

    const confirmationMessage = cleanIntent === 'free_consultation'
      ? `Thank you, ${cleanName}! We've received your consultation request. A Mozarex specialist will contact you at ${cleanEmail} to schedule a time that works best for you.`
      : `Thank you, ${cleanName}! We've received your website upgrade request${cleanPackage ? ` for ${cleanPackage}` : ''}. Our team will review your requirements for ${cleanBizName} and contact you at ${cleanEmail} shortly.`;

    return res.status(200).json({
      success: true,
      message: confirmationMessage,
      intent: cleanIntent,
      package_choice: cleanPackage
    });
  }
);

module.exports = router;
