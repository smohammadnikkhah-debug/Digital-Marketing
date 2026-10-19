/**
 * Reverse Proxy & Security Guard for StockAnalysis Quantitative API (FastAPI backend).
 *
 * Requirements:
 * - Secures /stockanalysis/api/* routes forwarding to FastAPI backend.
 * - Enforces rate limiting on public access to prevent abuse.
 * - Allowlist permitted read-only research, valuation, and signals endpoints.
 * - Blocks administrative server trigger actions and raw file-system manipulation.
 * - Provides graceful fallback when Python service is offline.
 */
const express = require('express');
const http = require('http');
const crypto = require('crypto');
const rateLimit = require('express-rate-limit');
const router = express.Router();

// Target URL for FastAPI backend service (can be configured via environment variable)
const TARGET_API_URL = process.env.STOCKANALYSIS_API_URL || 'http://127.0.0.1:8000';

// 1. Rate Limiter: 120 requests per minute per IP
const proxyRateLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    status: 'RATE_LIMITED',
    message: 'Too many requests to StockAnalysis engine from this IP. Please try again in a minute.'
  }
});

// Dedicated Rate Limiter for Screener Commands (max 5 requests per 15 min per IP)
const refreshRateLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: {
    status: 'RATE_LIMITED',
    message: 'Too many screener trigger requests from this IP. Manual refreshes are rate-limited to prevent excessive job submissions.'
  }
});

function timingSafeCompare(provided, expected) {
  if (typeof provided !== 'string' || typeof expected !== 'string') return false;
  const bufA = Buffer.from(provided);
  const bufB = Buffer.from(expected);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
}

// 2. Allowlisted Endpoint Prefixes
const ALLOWED_PATH_PREFIXES = [
  '/api/health',
  '/api/dashboard',
  '/api/signals',
  '/api/scanner',
  '/api/stock-analysis',
  '/api/stocks',
  '/api/research',
  '/api/valuation',
  '/api/portfolio',
  '/api/risk',
  '/api/watchlist',
  '/api/backtesting',
  '/api/settings'
];

// Blocked administrative & internal endpoints
const BLOCKED_PATH_PATTERNS = [];

router.use(proxyRateLimiter);
router.use([
  '/scanner/refresh',
  '/api/scanner/refresh',
  '/scanner/cancel-refresh',
  '/api/scanner/cancel-refresh'
], refreshRateLimiter);

router.all('/*', (req, res) => {
  // Original target path inside FastAPI (e.g., req.url is '/valuation/GOOGL/workspace')
  const incomingPath = req.url.startsWith('/api') ? req.url : `/api${req.url}`;

  // Read client authentication credentials before stripping
  const clientAdminKey = req.headers['x-admin-key'] || '';
  const clientAuthHeader = req.headers['authorization'] || '';

  // Security Check: Restrict sensitive screener trigger endpoints (refresh and cancel-refresh)
  const isProtectedEndpoint = (
    incomingPath.startsWith('/api/scanner/refresh') ||
    incomingPath.startsWith('/api/scanner/cancel-refresh')
  ) && req.method === 'POST';

  let validatedAdminInternalKey = null;

  if (isProtectedEndpoint) {
    const expectedAdminKey = process.env.STOCKANALYSIS_ADMIN_KEY || '';

    // 1. Verify validated administrator identity from authenticated web session
    const isAdminSession = !!(
      req.session &&
      req.session.adminAuthUserId &&
      req.session.adminRole === 'admin'
    );

    // 2. Or verify authorized API token with timing-safe comparison against dedicated STOCKANALYSIS_ADMIN_KEY
    let isAuthorizedToken = false;
    if (expectedAdminKey) {
      const bearerToken = clientAuthHeader.startsWith('Bearer ') ? clientAuthHeader.slice(7).trim() : '';
      const provided = bearerToken || clientAdminKey;
      if (provided && timingSafeCompare(provided, expectedAdminKey)) {
        isAuthorizedToken = true;
      }
    }

    if (!isAdminSession && !isAuthorizedToken) {
      return res.status(401).json({
        status: 'UNAUTHORIZED',
        message: 'Scanner execution commands require a validated administrator identity or authorized API key.'
      });
    }

    // Prepare trusted internal credential for backend injection
    if (expectedAdminKey) {
      validatedAdminInternalKey = expectedAdminKey;
    }
  }

  // Security Check: Block dangerous administrative triggers
  for (const blocked of BLOCKED_PATH_PATTERNS) {
    if (incomingPath.startsWith(blocked)) {
      return res.status(403).json({
        status: 'FORBIDDEN',
        message: 'Administrative command endpoints are restricted and cannot be executed via the public web interface.'
      });
    }
  }

  // Allowlist verification
  const isAllowed = ALLOWED_PATH_PREFIXES.some(prefix => incomingPath.startsWith(prefix));
  if (!isAllowed) {
    return res.status(403).json({
      status: 'FORBIDDEN',
      message: 'Access to this internal API path is restricted.'
    });
  }

  try {
    const targetUrl = new URL(incomingPath, TARGET_API_URL);

    const headers = { ...req.headers };
    delete headers['host'];
    delete headers['connection'];
    delete headers['cookie'];
    delete headers['x-admin-key']; // Unconditionally strip client-supplied X-Admin-Key

    // For protected scanner commands: strip client-supplied credentials and inject ONLY trusted internal admin key
    if (isProtectedEndpoint) {
      delete headers['authorization'];
      delete headers['x-admin-key'];

      // Inject ONLY the trusted internal STOCKANALYSIS_ADMIN_KEY header for FastAPI verification
      if (validatedAdminInternalKey) {
        headers['x-admin-key'] = validatedAdminInternalKey;
      }
    }

    const proxyReq = http.request(
      targetUrl,
      {
        method: req.method,
        headers: headers,
        timeout: 60000 // 60 second timeout for analysis & market updates
      },
      (proxyRes) => {
        res.status(proxyRes.statusCode);
        for (const [key, value] of Object.entries(proxyRes.headers)) {
          res.setHeader(key, value);
        }
        proxyRes.pipe(res);
      }
    );

    proxyReq.on('error', (err) => {
      console.warn(`[StockAnalysis Proxy Warning] Backend unreachable at ${TARGET_API_URL}: ${err.message}`);
      if (!res.headersSent) {
        res.status(503).json({
          status: 'SERVICE_UNAVAILABLE',
          message: 'StockAnalysis quantitative engine is offline or unreachable. Please verify the Python FastAPI service is running.',
          target: TARGET_API_URL
        });
      }
    });

    proxyReq.on('timeout', () => {
      proxyReq.destroy();
      if (!res.headersSent) {
        res.status(504).json({
          status: 'GATEWAY_TIMEOUT',
          message: 'StockAnalysis engine response timed out (60s limit).'
        });
      }
    });

    // Forward request body if present
    if (req.body && (req.method === 'POST' || req.method === 'PUT')) {
      const bodyData = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
      proxyReq.setHeader('Content-Type', 'application/json');
      proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData));
      proxyReq.write(bodyData);
    }

    proxyReq.end();
  } catch (err) {
    res.status(500).json({
      status: 'PROXY_ERROR',
      message: err.message
    });
  }
});

module.exports = router;
