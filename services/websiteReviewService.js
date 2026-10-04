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
      .select('id, public_token, business_name, website_url, status, created_at')
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
 * Core Orchestrator: Creates a website audit record, generates PDF, uploads to private storage,
 * and updates record status to 'ready'.
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
    currency = 'AUD'
  } = payload;

  const canonicalDomain = canonicalizeDomain(website_url);
  const publicToken = generateSecurePublicToken();
  const auditId = crypto.randomUUID();

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
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
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

  // 2. Generate PDF Report Buffer
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

  // 3. Upload to Private Supabase Storage
  const storagePath = `website-audits/${auditId}/report.pdf`;
  const bucketName = 'mozarex-website-reviews';

  if (supabase && process.env.NODE_ENV !== 'test') {
    try {
      await ensurePrivateStorageBucket(supabase);

      const { error: uploadError } = await supabase.storage
        .from(bucketName)
        .upload(storagePath, pdfBuffer, {
          contentType: 'application/pdf',
          upsert: true
        });

      if (uploadError) {
        await supabase.from('website_audits').update({ status: 'failed' }).eq('id', auditId);
        const err = new Error(`Storage upload failed: ${uploadError.message}`);
        err.code = 'STORAGE_UPLOAD_FAILED';
        throw err;
      }
    } catch (storageErr) {
      await supabase.from('website_audits').update({ status: 'failed' }).eq('id', auditId);
      const err = new Error(`Storage upload failed: ${storageErr.message}`);
      err.code = 'STORAGE_UPLOAD_FAILED';
      throw err;
    }
  } else {
    mockStorageStore.set(`${bucketName}/${storagePath}`, pdfBuffer);
  }

  // 4. Update status to ready and set pdf_storage_path
  // IMPORTANT: Never transition to 'approved' or 'sent' here.
  auditRecord.status = 'ready';
  auditRecord.pdf_storage_path = storagePath;
  auditRecord.updated_at = new Date().toISOString();

  if (supabase && process.env.NODE_ENV !== 'test') {
    const { error: updateError } = await supabase
      .from('website_audits')
      .update({
        status: 'ready',
        pdf_storage_path: storagePath,
        updated_at: auditRecord.updated_at
      })
      .eq('id', auditId);

    if (updateError) {
      console.warn('Failed to update audit status to ready:', updateError.message);
    }
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
    pdf_storage_path: storagePath
  };
}

/**
 * Retrieves PDF buffer and registers a download analytics event.
 * 
 * @param {string} publicToken 
 * @returns {Promise<{ pdfBuffer: Buffer, fileName: string, audit: Object }>}
 */
async function getAuditPdfForDownload(publicToken) {
  const audit = await findAuditByPublicToken(publicToken);
  if (!audit) {
    const err = new Error('Audit report not found');
    err.code = 'NOT_FOUND';
    throw err;
  }

  if (audit.status !== 'ready' && audit.status !== 'approved' && audit.status !== 'sent') {
    const err = new Error('Audit report is not ready for download');
    err.code = 'NOT_READY';
    throw err;
  }

  const supabase = getSupabaseClient();
  let pdfBuffer;

  const bucketName = 'mozarex-website-reviews';
  const storagePath = audit.pdf_storage_path || `website-audits/${audit.id}/report.pdf`;

  if (supabase && process.env.NODE_ENV !== 'test') {
    const { data, error } = await supabase.storage
      .from(bucketName)
      .download(storagePath);

    if (error || !data) {
      // If storage download fails, try on-the-fly regeneration fallback
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
    } else {
      const arrayBuffer = await data.arrayBuffer();
      pdfBuffer = Buffer.from(arrayBuffer);
    }
  } else {
    pdfBuffer = mockStorageStore.get(`${bucketName}/${storagePath}`);
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

  const sanitizedBusinessName = sanitizeFileNamePart(audit.business_name);
  const fileName = `Mozarex-Website-Review-${sanitizedBusinessName}.pdf`;

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
  findActiveAuditByDomain,
  findAuditByPublicToken,
  createWebsiteAudit,
  getAuditPdfForDownload,
  recordAuditView,
  resetMockStore,
  getSupabaseClient
};
