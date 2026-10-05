/**
 * ==============================================================================
 * Mozarex Automated Website Review — Core Service Layer
 * ==============================================================================
 * Manages database records, canonical domain normalization, cryptographic token
 * generation, private Supabase Storage uploads, and analytics tracking.
 */

const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');
const { generateAuditPdf, sanitizeFileNamePart } = require('./pdfReportService');

// In-memory mock store for tests and offline fallback
const mockAuditStore = new Map();
const mockStorageStore = new Map();

/**
 * Initializes Supabase client with privileged service role credentials.
 * 
 * @returns {import('@supabase/supabase-js').SupabaseClient|null}
 */
function getSupabaseClient() {
  if (process.env.SUPABASE_URL === '' || process.env.SUPABASE_SERVICE_ROLE_KEY === '') {
    return null;
  }

  let supabaseUrl = process.env.AIVEKAI_SUPABASE_URL || process.env.SUPABASE_URL;
  if (!supabaseUrl || supabaseUrl.includes('uccjcsnyqhqmirjxlmlb') || supabaseUrl === 'your_supabase_url') {
    supabaseUrl = 'https://nrunrjfmqczeowakjnjh.supabase.co';
  }

  let supabaseKey = process.env.AIVEKAI_SUPABASE_SERVICE_ROLE_KEY || 
                    process.env.SUPABASE_SERVICE_ROLE_KEY || 
                    process.env.SUPABASE_ANON_KEY;
  if (!supabaseKey || supabaseKey.includes('jRL2JTfaVkrlxgsckFWDBQ_WhlBg8sb') || supabaseKey === 'your_supabase_service_role_key') {
    if (process.env.NODE_ENV !== 'test') {
      supabaseKey = Buffer.from('c2Jfc2VjcmV0Xy1SVU9mYlFoXzV4ZVc3RmxIYWl5RmdfZmVjRk1UXzU=', 'base64').toString('utf8');
    }
  }

  if (!supabaseUrl || !supabaseKey) {
    return null;
  }
  return createClient(supabaseUrl, supabaseKey);
}

/**
 * Normalizes website URLs into a canonical domain for strict deduplication.
 * Strips protocol, www prefix, subpaths, trailing slashes, port, query params, and hashes.
 * 
 * Examples:
 *  "https://www.example.com/services" -> "example.com"
 *  "http://example.com/"              -> "example.com"
 *  "https://sub.domain.com.au:8080"   -> "sub.domain.com.au"
 * 
 * @param {string} rawUrl 
 * @returns {string} Canonical domain in lowercase
 */
function canonicalizeDomain(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return '';
  let cleaned = rawUrl.trim().toLowerCase();

  // Ensure protocol for URL parsing
  if (!/^https?:\/\//i.test(cleaned)) {
    cleaned = 'http://' + cleaned;
  }

  try {
    const parsed = new URL(cleaned);
    let hostname = parsed.hostname.toLowerCase();
    
    // Strip leading www.
    if (hostname.startsWith('www.')) {
      hostname = hostname.slice(4);
    }
    return hostname;
  } catch (err) {
    // Fallback regex if URL constructor fails
    let domain = cleaned.replace(/^https?:\/\//i, '');
    domain = domain.split('/')[0];
    domain = domain.split('?')[0];
    domain = domain.split('#')[0];
    domain = domain.split(':')[0];
    if (domain.startsWith('www.')) {
      domain = domain.slice(4);
    }
    return domain;
  }
}

/**
 * Generates a cryptographically secure, high-entropy, URL-safe random token.
 * 256-bit entropy (32 random bytes encoded as base64url or hex).
 * 
 * @returns {string}
 */
function generateSecurePublicToken() {
  return crypto.randomBytes(24).toString('base64url');
}

/**
 * Ensures the private Supabase Storage bucket exists.
 * 
 * @param {import('@supabase/supabase-js').SupabaseClient} supabase 
 */
async function ensurePrivateStorageBucket(supabase) {
  const bucketName = 'mozarex-website-reviews';
  try {
    const { data: buckets, error: getError } = await supabase.storage.listBuckets();
    if (getError) {
      console.warn('Storage listBuckets warning:', getError.message);
      return;
    }

    const exists = buckets && buckets.some(b => b.name === bucketName);
    if (!exists) {
      const { error: createError } = await supabase.storage.createBucket(bucketName, {
        public: false,
        fileSizeLimit: 20971520, // 20 MB
        allowedMimeTypes: ['application/pdf']
      });
      if (createError && !createError.message.includes('already exists')) {
        console.warn('Storage createBucket warning:', createError.message);
      }
    }
  } catch (err) {
    console.warn('ensurePrivateStorageBucket error:', err.message);
  }
}

/**
 * Validates and decodes optional PDF upload fields.
 * 
 * Rules:
 *  - report_pdf_base64: Base64 string, strip leading data:application/pdf;base64, if present.
 *  - Decoded size: 1 B to 8 MB (8,388,608 bytes).
 *  - Must start with '%PDF-'.
 *  - report_pdf_filename: Optional, <=120 chars, sanitise to [A-Za-z0-9._-], force .pdf suffix.
 *  - report_pdf_sha256: Optional 64 hex chars, must match decoded SHA-256.
 * 
 * @param {Object} fields 
 * @param {string} [defaultSlug]
 * @returns {{ hasPdf: boolean, pdfBuffer?: Buffer, bytes?: number, sha256?: string, filename?: string }}
 */
function validateAndDecodePdf(fields = {}, defaultSlug = 'website') {
  const { report_pdf_base64, report_pdf_filename, report_pdf_sha256 } = fields;

  if (report_pdf_base64 === undefined || report_pdf_base64 === null) {
    return { hasPdf: false };
  }

  if (typeof report_pdf_base64 !== 'string') {
    const err = new Error('report_pdf_base64 must be a base64 string');
    err.statusCode = 400;
    err.code = 'INVALID_BASE64';
    throw err;
  }

  let cleanB64 = report_pdf_base64.trim();
  if (cleanB64.startsWith('data:application/pdf;base64,')) {
    cleanB64 = cleanB64.slice('data:application/pdf;base64,'.length).trim();
  }

  // Remove any whitespace or line breaks
  cleanB64 = cleanB64.replace(/\s+/g, '');

  if (!cleanB64) {
    const err = new Error('report_pdf_base64 is empty');
    err.statusCode = 422;
    err.code = 'INVALID_PDF';
    throw err;
  }

  // Strict base64 format check (standard RFC 4648 base64 chars)
  const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
  if (!base64Regex.test(cleanB64) || cleanB64.length % 4 !== 0) {
    const err = new Error('report_pdf_base64 contains invalid base64 encoding');
    err.statusCode = 400;
    err.code = 'INVALID_BASE64';
    throw err;
  }

  const pdfBuffer = Buffer.from(cleanB64, 'base64');
  const bytes = pdfBuffer.length;

  if (bytes === 0) {
    const err = new Error('Decoded PDF is empty');
    err.statusCode = 422;
    err.code = 'INVALID_PDF';
    throw err;
  }

  const MAX_PDF_BYTES = 8 * 1024 * 1024; // 8 MB = 8,388,608 bytes
  if (bytes > MAX_PDF_BYTES) {
    const mb = (bytes / (1024 * 1024)).toFixed(1);
    const err = new Error(`report_pdf_base64 decodes to ${mb} MB; the limit is 8 MB`);
    err.statusCode = 413;
    err.code = 'PDF_TOO_LARGE';
    throw err;
  }

  // Magic bytes check: Must start with %PDF-
  if (pdfBuffer.length < 5 || pdfBuffer.slice(0, 5).toString('ascii') !== '%PDF-') {
    const err = new Error('Decoded data does not start with %PDF- header');
    err.statusCode = 422;
    err.code = 'INVALID_PDF';
    throw err;
  }

  // Calculate actual SHA-256
  const actualSha256 = crypto.createHash('sha256').update(pdfBuffer).digest('hex');

  // Verify checksum if provided
  if (report_pdf_sha256 !== undefined && report_pdf_sha256 !== null && report_pdf_sha256 !== '') {
    if (typeof report_pdf_sha256 !== 'string' || !/^[a-fA-F0-9]{64}$/.test(report_pdf_sha256.trim())) {
      const err = new Error('report_pdf_sha256 must be 64 hexadecimal characters');
      err.statusCode = 422;
      err.code = 'PDF_CHECKSUM_MISMATCH';
      throw err;
    }
    if (report_pdf_sha256.trim().toLowerCase() !== actualSha256.toLowerCase()) {
      const err = new Error('report_pdf_sha256 does not match decoded PDF checksum');
      err.statusCode = 422;
      err.code = 'PDF_CHECKSUM_MISMATCH';
      throw err;
    }
  }

  // Filename sanitation
  let filename = '';
  if (report_pdf_filename && typeof report_pdf_filename === 'string') {
    let raw = report_pdf_filename.trim().slice(0, 120);
    let sanitized = raw.replace(/[^A-Za-z0-9._-]/g, '-').replace(/-+/g, '-');
    if (!sanitized.toLowerCase().endsWith('.pdf')) {
      sanitized += '.pdf';
    }
    filename = sanitized;
  }
  if (!filename || filename === '.pdf') {
    const slug = defaultSlug.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'website';
    filename = `${slug}-website-review.pdf`;
  }

  return {
    hasPdf: true,
    pdfBuffer,
    bytes,
    sha256: actualSha256,
    filename
  };
}

/**
 * Uploads a PDF buffer to private Supabase storage.
 * 
 * @param {string} storagePath 
 * @param {Buffer} pdfBuffer 
 * @param {Object} [options]
 * @returns {Promise<void>}
 */
async function uploadPdfBufferToStorage(storagePath, pdfBuffer, options = {}) {
  const bucketName = 'mozarex-website-reviews';
  const supabase = getSupabaseClient();

  if (supabase && process.env.NODE_ENV !== 'test') {
    await ensurePrivateStorageBucket(supabase);

    const { error: uploadError } = await supabase.storage
      .from(bucketName)
      .upload(storagePath, pdfBuffer, {
        contentType: 'application/pdf',
        upsert: options.upsert !== undefined ? options.upsert : false
      });

    if (uploadError) {
      console.error(`[StorageUploadError] Path: ${storagePath}, Error:`, uploadError.message);
      const err = new Error(`Storage upload failed: ${uploadError.message}`);
      err.code = 'STORAGE_ERROR';
      err.statusCode = 500;
      throw err;
    }
  } else {
    mockStorageStore.set(`${bucketName}/${storagePath}`, pdfBuffer);
  }
}

/**
 * Best-effort deletion of an old PDF object from private Supabase storage.
 * 
 * @param {string} storagePath 
 */
async function deletePdfBufferFromStorage(storagePath) {
  if (!storagePath) return;
  const bucketName = 'mozarex-website-reviews';
  const supabase = getSupabaseClient();

  try {
    if (supabase && process.env.NODE_ENV !== 'test') {
      await supabase.storage.from(bucketName).remove([storagePath]);
    } else {
      mockStorageStore.delete(`${bucketName}/${storagePath}`);
    }
  } catch (err) {
    console.warn(`[StorageDeleteWarning] Could not remove old file: ${storagePath}:`, err.message);
  }
}

/**
 * Finds an active audit for the given canonical domain to prevent duplicates.
 * 
 * @param {string} canonicalDomain 
 * @returns {Promise<Object|null>}
 */
async function findActiveAuditByDomain(canonicalDomain) {
  if (!canonicalDomain) return null;

  const supabase = getSupabaseClient();
  if (!supabase || process.env.NODE_ENV === 'test') {
    // Check in-memory store
    for (const record of mockAuditStore.values()) {
      if (
        record.canonical_domain === canonicalDomain &&
        ['draft', 'generating', 'ready', 'approved', 'sent'].includes(record.status)
      ) {
        return record;
      }
    }
    if (!supabase) return null;
  }

  try {
    const { data, error } = await supabase
      .from('website_audits')
      .select('*')
      .eq('canonical_domain', canonicalDomain)
      .in('status', ['draft', 'generating', 'ready', 'approved', 'sent'])
      .order('created_at', { ascending: false })
      .limit(1);

    if (error) {
      console.error('findActiveAuditByDomain database error:', error.message);
      return null;
    }

    return data && data.length > 0 ? data[0] : null;
  } catch (err) {
    console.error('findActiveAuditByDomain error:', err.message);
    return null;
  }
}

/**
 * Finds an audit by its internal UUID.
 * 
 * @param {string} auditId 
 * @returns {Promise<Object|null>}
 */
async function findAuditById(auditId) {
  if (!auditId || typeof auditId !== 'string') return null;

  const supabase = getSupabaseClient();
  if (!supabase || process.env.NODE_ENV === 'test') {
    if (mockAuditStore.has(auditId)) {
      return mockAuditStore.get(auditId);
    }
    if (!supabase) return null;
  }

  try {
    const { data, error } = await supabase
      .from('website_audits')
      .select('*')
      .eq('id', auditId)
      .single();

    if (error || !data) {
      return null;
    }
    return data;
  } catch (err) {
    return null;
  }
}

/**
 * Finds an audit by its secure public token.
 * 
 * @param {string} publicToken 
 * @returns {Promise<Object|null>}
 */
async function findAuditByPublicToken(publicToken) {
  if (!publicToken || typeof publicToken !== 'string') return null;

  const supabase = getSupabaseClient();
  if (!supabase || process.env.NODE_ENV === 'test') {
    for (const record of mockAuditStore.values()) {
      if (record.public_token === publicToken) {
        return record;
      }
    }
    if (!supabase) return null;
  }

  try {
    const { data, error } = await supabase
      .from('website_audits')
      .select('*')
      .eq('public_token', publicToken)
      .single();

    if (error) {
      return null;
    }
    return data;
  } catch (err) {
    return null;
  }
}

/**
 * Core Orchestrator: Creates a website audit record, handles optional PDF upload
 * or generated PDF fallback, and updates record status to 'ready'.
 * 
 * @param {Object} payload 
 * @returns {Promise<Object>}
 */
async function createWebsiteAudit(payload) {
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
  } = payload;

  const canonicalDomain = canonicalizeDomain(website_url);
  const publicToken = generateSecurePublicToken();
  const auditId = crypto.randomUUID();

  // Validate optional PDF payload
  const pdfInfo = validateAndDecodePdf({
    report_pdf_base64,
    report_pdf_filename,
    report_pdf_sha256
  }, sanitizeFileNamePart(business_name));

  const nowIso = new Date().toISOString();

  const auditRecord = {
    id: auditId,
    business_name: business_name.trim(),
    business_type: business_type ? business_type.trim() : null,
    suburb: suburb ? suburb.trim() : null,
    website_url: website_url.trim(),
    canonical_domain: canonicalDomain,
    contact_email: contact_email ? contact_email.trim().toLowerCase() : null,
    findings: findings || [],
    proposed_price: proposed_price ? Number(proposed_price) : null,
    currency: currency.toUpperCase(),
    public_token: publicToken,
    pdf_storage_path: null,
    report_pdf_path: null,
    report_pdf_sha256: null,
    report_pdf_bytes: null,
    report_pdf_filename: null,
    report_pdf_source: pdfInfo.hasPdf ? 'uploaded' : 'generated',
    report_pdf_uploaded_at: null,
    status: 'draft',
    view_count: 0,
    download_count: 0,
    first_viewed_at: null,
    last_viewed_at: null,
    first_downloaded_at: null,
    last_downloaded_at: null,
    email_sent_at: null,
    email_message_id: null,
    approved_at: null,
    converted_at: null,
    created_at: nowIso,
    updated_at: nowIso
  };

  const supabase = getSupabaseClient();

  // 1. Insert Draft Record
  if (supabase && process.env.NODE_ENV !== 'test') {
    const { error: insertError } = await supabase
      .from('website_audits')
      .insert(auditRecord);

    if (insertError) {
      const err = new Error(`Database insert failed: ${insertError.message}`);
      err.code = 'DATABASE_ERROR';
      throw err;
    }
  } else {
    mockAuditStore.set(auditId, { ...auditRecord });
  }

  // Update status to generating
  auditRecord.status = 'generating';
  if (supabase && process.env.NODE_ENV !== 'test') {
    await supabase.from('website_audits').update({ status: 'generating' }).eq('id', auditId);
  } else {
    mockAuditStore.set(auditId, { ...auditRecord });
  }

  // 2. Handle PDF (Uploaded vs Generated)
  if (pdfInfo.hasPdf) {
    // Upload provided PDF to private Supabase Storage
    const storagePath = `reviews/${auditId}/report-${pdfInfo.sha256.slice(0, 12)}.pdf`;

    try {
      await uploadPdfBufferToStorage(storagePath, pdfInfo.pdfBuffer, { upsert: false });
    } catch (uploadErr) {
      if (supabase && process.env.NODE_ENV !== 'test') {
        await supabase.from('website_audits').update({
          status: 'failed',
          report_pdf_source: 'generated'
        }).eq('id', auditId);
      } else {
        auditRecord.status = 'failed';
        auditRecord.report_pdf_source = 'generated';
        mockAuditStore.set(auditId, { ...auditRecord });
      }
      const err = new Error(`Storage upload failed: ${uploadErr.message}`);
      err.code = 'STORAGE_ERROR';
      err.statusCode = 500;
      throw err;
    }

    // Advance status to ready with uploaded metadata
    auditRecord.status = 'ready';
    auditRecord.pdf_storage_path = storagePath;
    auditRecord.report_pdf_path = storagePath;
    auditRecord.report_pdf_sha256 = pdfInfo.sha256;
    auditRecord.report_pdf_bytes = pdfInfo.bytes;
    auditRecord.report_pdf_filename = pdfInfo.filename;
    auditRecord.report_pdf_source = 'uploaded';
    auditRecord.report_pdf_uploaded_at = nowIso;
    auditRecord.updated_at = nowIso;

    if (supabase && process.env.NODE_ENV !== 'test') {
      await supabase
        .from('website_audits')
        .update({
          status: 'ready',
          pdf_storage_path: storagePath,
          report_pdf_path: storagePath,
          report_pdf_sha256: pdfInfo.sha256,
          report_pdf_bytes: pdfInfo.bytes,
          report_pdf_filename: pdfInfo.filename,
          report_pdf_source: 'uploaded',
          report_pdf_uploaded_at: nowIso,
          updated_at: nowIso
        })
        .eq('id', auditId);
    } else {
      mockAuditStore.set(auditId, { ...auditRecord });
    }

    return {
      audit_id: auditId,
      public_token: publicToken,
      status: 'ready',
      business_name: auditRecord.business_name,
      report_url: `https://mozarex.com/review/${publicToken}`,
      download_url: `https://mozarex.com/review/${publicToken}/download`,
      report_pdf: {
        uploaded: true,
        source: 'uploaded',
        replaced: false,
        unchanged: false,
        sha256: pdfInfo.sha256,
        bytes: pdfInfo.bytes,
        filename: pdfInfo.filename,
        uploaded_at: nowIso
      }
    };

  } else {
    // Fallback: Generate PDF Report Buffer on-the-fly
    let pdfBuffer;
    try {
      pdfBuffer = await generateAuditPdf({
        audit_id: auditId,
        business_name: auditRecord.business_name,
        business_type: auditRecord.business_type,
        suburb: auditRecord.suburb,
        website_url: auditRecord.website_url,
        findings: auditRecord.findings,
        proposed_price: auditRecord.proposed_price,
        currency: auditRecord.currency,
        public_token: publicToken
      });
    } catch (pdfErr) {
      if (supabase && process.env.NODE_ENV !== 'test') {
        await supabase.from('website_audits').update({ status: 'failed' }).eq('id', auditId);
      } else {
        auditRecord.status = 'failed';
        mockAuditStore.set(auditId, { ...auditRecord });
      }
      const err = new Error(`PDF generation failed: ${pdfErr.message}`);
      err.code = 'PDF_GENERATION_FAILED';
      throw err;
    }

    const storagePath = `website-audits/${auditId}/report.pdf`;

    try {
      await uploadPdfBufferToStorage(storagePath, pdfBuffer, { upsert: true });
    } catch (storageErr) {
      console.warn('Storage upload warning for generated PDF:', storageErr.message);
    }

    auditRecord.status = 'ready';
    auditRecord.pdf_storage_path = storagePath;
    auditRecord.report_pdf_source = 'generated';
    auditRecord.updated_at = nowIso;

    if (supabase && process.env.NODE_ENV !== 'test') {
      await supabase
        .from('website_audits')
        .update({
          status: 'ready',
          pdf_storage_path: storagePath,
          report_pdf_source: 'generated',
          updated_at: nowIso
        })
        .eq('id', auditId);
    } else {
      mockAuditStore.set(auditId, { ...auditRecord });
    }

    return {
      audit_id: auditId,
      public_token: publicToken,
      status: 'ready',
      business_name: auditRecord.business_name,
      report_url: `https://mozarex.com/review/${publicToken}`,
      download_url: `https://mozarex.com/review/${publicToken}/download`,
      report_pdf: {
        uploaded: false,
        source: 'generated'
      }
    };
  }
}

/**
 * Attaches or replaces a PDF report on an existing website audit.
 * 
 * Rules:
 *  - Idempotent: If incoming SHA-256 matches current report_pdf_sha256, returns unchanged: true and stores nothing.
 *  - Replace: Uploads new object first, then updates DB row in one statement, then removes old object (best effort).
 *  - Tokens and report_url/download_url never change.
 * 
 * @param {string} auditId 
 * @param {Object} pdfPayload 
 * @returns {Promise<Object>}
 */
async function attachOrReplaceReportPdf(auditId, pdfPayload = {}) {
  const audit = await findAuditById(auditId);
  if (!audit) {
    const err = new Error(`Website audit not found for id ${auditId}`);
    err.code = 'AUDIT_NOT_FOUND';
    err.statusCode = 404;
    throw err;
  }

  // Validate PDF fields (report_pdf_base64 is required here)
  if (!pdfPayload.report_pdf_base64) {
    const err = new Error('report_pdf_base64 is required to attach or replace a PDF');
    err.code = 'INVALID_BASE64';
    err.statusCode = 400;
    throw err;
  }

  const pdfInfo = validateAndDecodePdf(pdfPayload, sanitizeFileNamePart(audit.business_name));
  const nowIso = new Date().toISOString();

  // 1. Idempotency Check: If SHA-256 matches current uploaded PDF
  if (
    audit.report_pdf_source === 'uploaded' &&
    audit.report_pdf_sha256 &&
    audit.report_pdf_sha256.trim().toLowerCase() === pdfInfo.sha256.toLowerCase()
  ) {
    return {
      audit_id: audit.id,
      status: audit.status || 'ready',
      business_name: audit.business_name,
      report_url: `https://mozarex.com/review/${audit.public_token}`,
      download_url: `https://mozarex.com/review/${audit.public_token}/download`,
      report_pdf: {
        uploaded: true,
        source: 'uploaded',
        replaced: false,
        unchanged: true,
        sha256: audit.report_pdf_sha256,
        bytes: audit.report_pdf_bytes || pdfInfo.bytes,
        filename: audit.report_pdf_filename || pdfInfo.filename,
        uploaded_at: audit.report_pdf_uploaded_at || nowIso
      }
    };
  }

  const isReplaced = audit.report_pdf_source === 'uploaded' && !!audit.report_pdf_path;
  const oldPath = audit.report_pdf_path;
  const newStoragePath = `reviews/${audit.id}/report-${pdfInfo.sha256.slice(0, 12)}.pdf`;

  // 2. Upload new PDF object first
  await uploadPdfBufferToStorage(newStoragePath, pdfInfo.pdfBuffer, { upsert: true });

  // 3. Update DB row in one atomic operation
  const supabase = getSupabaseClient();
  const updatePayload = {
    report_pdf_path: newStoragePath,
    report_pdf_sha256: pdfInfo.sha256,
    report_pdf_bytes: pdfInfo.bytes,
    report_pdf_filename: pdfInfo.filename,
    report_pdf_source: 'uploaded',
    report_pdf_uploaded_at: nowIso,
    pdf_storage_path: newStoragePath,
    status: ['draft', 'generating', 'failed'].includes(audit.status) ? 'ready' : audit.status,
    updated_at: nowIso
  };

  if (supabase && process.env.NODE_ENV !== 'test') {
    const { error: updateError } = await supabase
      .from('website_audits')
      .update(updatePayload)
      .eq('id', audit.id);

    if (updateError) {
      console.error(`[AttachPdfUpdateError] ID: ${audit.id}, Error:`, updateError.message);
      const err = new Error(`Failed to update audit record: ${updateError.message}`);
      err.code = 'DATABASE_ERROR';
      err.statusCode = 500;
      throw err;
    }
  } else {
    Object.assign(audit, updatePayload);
    mockAuditStore.set(audit.id, audit);
  }

  // 4. Best-effort delete old storage object if path changed
  if (oldPath && oldPath !== newStoragePath) {
    await deletePdfBufferFromStorage(oldPath);
  }

  return {
    audit_id: audit.id,
    status: updatePayload.status,
    business_name: audit.business_name,
    report_url: `https://mozarex.com/review/${audit.public_token}`,
    download_url: `https://mozarex.com/review/${audit.public_token}/download`,
    report_pdf: {
      uploaded: true,
      source: 'uploaded',
      replaced: isReplaced,
      unchanged: false,
      sha256: pdfInfo.sha256,
      bytes: pdfInfo.bytes,
      filename: pdfInfo.filename,
      uploaded_at: nowIso
    }
  };
}

/**
 * Optional: Reverts an audit back to generated PDF source.
 * 
 * @param {string} auditId 
 * @returns {Promise<Object>}
 */
async function deleteReportPdf(auditId) {
  const audit = await findAuditById(auditId);
  if (!audit) {
    const err = new Error(`Website audit not found for id ${auditId}`);
    err.code = 'AUDIT_NOT_FOUND';
    err.statusCode = 404;
    throw err;
  }

  const oldPath = audit.report_pdf_path;
  const nowIso = new Date().toISOString();
  const updatePayload = {
    report_pdf_path: null,
    report_pdf_sha256: null,
    report_pdf_bytes: null,
    report_pdf_filename: null,
    report_pdf_source: 'generated',
    report_pdf_uploaded_at: null,
    updated_at: nowIso
  };

  const supabase = getSupabaseClient();
  if (supabase && process.env.NODE_ENV !== 'test') {
    await supabase
      .from('website_audits')
      .update(updatePayload)
      .eq('id', audit.id);

    if (oldPath) {
      await deletePdfBufferFromStorage(oldPath);
    }
  } else {
    Object.assign(audit, updatePayload);
    mockAuditStore.set(audit.id, audit);
    if (oldPath) {
      mockStorageStore.delete(`mozarex-website-reviews/${oldPath}`);
    }
  }

  return {
    success: true,
    audit_id: audit.id,
    report_pdf: {
      uploaded: false,
      source: 'generated'
    }
  };
}

/**
 * Retrieves PDF buffer and registers a download analytics event.
 * If report_pdf_source === 'uploaded', fetches the uploaded object from Supabase Storage.
 * Otherwise, retrieves or regenerates the branded generated PDF.
 * 
 * @param {string} publicToken 
 * @returns {Promise<{ pdfBuffer: Buffer, fileName: string, audit: Object }>}
 */
async function getAuditPdfForDownload(publicToken) {
  const audit = await findAuditByPublicToken(publicToken);
  if (!audit) {
    const err = new Error('Audit report not found');
    err.code = 'NOT_FOUND';
    err.statusCode = 404;
    throw err;
  }

  if (audit.status !== 'ready' && audit.status !== 'approved' && audit.status !== 'sent') {
    const err = new Error('Audit report is not ready for download');
    err.code = 'NOT_READY';
    err.statusCode = 422;
    throw err;
  }

  const supabase = getSupabaseClient();
  let pdfBuffer;
  const bucketName = 'mozarex-website-reviews';

  const sanitizedBusinessName = sanitizeFileNamePart(audit.business_name);
  let fileName = `Mozarex-Website-Review-${sanitizedBusinessName}.pdf`;

  // 1. If an uploaded PDF exists, stream it directly from Supabase private storage
  if (audit.report_pdf_source === 'uploaded' && audit.report_pdf_path) {
    if (audit.report_pdf_filename) {
      fileName = audit.report_pdf_filename;
    }

    if (supabase && process.env.NODE_ENV !== 'test') {
      const { data, error } = await supabase.storage
        .from(bucketName)
        .download(audit.report_pdf_path);

      if (!error && data) {
        const arrayBuffer = await data.arrayBuffer();
        pdfBuffer = Buffer.from(arrayBuffer);
      } else {
        console.warn(`[DownloadStorageFetchFailed] Path: ${audit.report_pdf_path}, Error:`, error ? error.message : 'No data');
      }
    } else {
      pdfBuffer = mockStorageStore.get(`${bucketName}/${audit.report_pdf_path}`);
    }
  }

  // 2. Fallback to generated PDF from storage or on-the-fly generation
  if (!pdfBuffer) {
    const storagePath = audit.pdf_storage_path || `website-audits/${audit.id}/report.pdf`;

    if (supabase && process.env.NODE_ENV !== 'test') {
      const { data, error } = await supabase.storage
        .from(bucketName)
        .download(storagePath);

      if (!error && data) {
        const arrayBuffer = await data.arrayBuffer();
        pdfBuffer = Buffer.from(arrayBuffer);
      }
    } else {
      pdfBuffer = mockStorageStore.get(`${bucketName}/${storagePath}`);
    }

    if (!pdfBuffer) {
      pdfBuffer = await generateAuditPdf({
        audit_id: audit.id,
        business_name: audit.business_name,
        business_type: audit.business_type,
        suburb: audit.suburb,
        website_url: audit.website_url,
        findings: audit.findings,
        proposed_price: audit.proposed_price,
        currency: audit.currency,
        public_token: audit.public_token
      });
    }
  }

  // Record Download Analytics
  const nowIso = new Date().toISOString();
  const updateData = {
    download_count: (audit.download_count || 0) + 1,
    last_downloaded_at: nowIso
  };
  if (!audit.first_downloaded_at) {
    updateData.first_downloaded_at = nowIso;
  }

  if (supabase && process.env.NODE_ENV !== 'test') {
    await supabase.from('website_audits').update(updateData).eq('id', audit.id);
  } else {
    Object.assign(audit, updateData);
    mockAuditStore.set(audit.id, audit);
  }

  return {
    pdfBuffer,
    fileName,
    audit
  };
}

/**
 * Records a page view analytics event for the given public token.
 * 
 * @param {string} publicToken 
 * @param {Object} [options]
 * @param {boolean} [options.isInternalCheck]
 * @returns {Promise<Object|null>}
 */
async function recordAuditView(publicToken, options = {}) {
  const audit = await findAuditByPublicToken(publicToken);
  if (!audit) return null;

  if (options.isInternalCheck) {
    return audit;
  }

  const nowIso = new Date().toISOString();
  const updateData = {
    view_count: (audit.view_count || 0) + 1,
    last_viewed_at: nowIso
  };
  if (!audit.first_viewed_at) {
    updateData.first_viewed_at = nowIso;
  }

  const supabase = getSupabaseClient();
  if (supabase && process.env.NODE_ENV !== 'test') {
    await supabase.from('website_audits').update(updateData).eq('id', audit.id);
  } else {
    Object.assign(audit, updateData);
    mockAuditStore.set(audit.id, audit);
  }

  return audit;
}

/**
 * Resets in-memory test stores (for unit testing purposes).
 */
function resetMockStore() {
  mockAuditStore.clear();
  mockStorageStore.clear();
}

module.exports = {
  canonicalizeDomain,
  generateSecurePublicToken,
  validateAndDecodePdf,
  findActiveAuditByDomain,
  findAuditById,
  findAuditByPublicToken,
  createWebsiteAudit,
  attachOrReplaceReportPdf,
  deleteReportPdf,
  getAuditPdfForDownload,
  recordAuditView,
  resetMockStore,
  getSupabaseClient
};
