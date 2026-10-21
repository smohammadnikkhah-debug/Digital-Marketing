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

// Known development / test keys that must be rejected in production
const KNOWN_DEV_INGEST_KEYS = new Set([
  'ibkr-ingest-key-dev-local-2026',
  'test_gateway_ibkr_ingest_key_2026',
  'dev-key',
  'default'
]);

const KNOWN_DEV_EXECUTION_KEYS = new Set([
  'ibkr-execution-key-dev-local-2026',
  'test_gateway_ibkr_execution_key_2026',
  'dev-exec-key',
  'default'
]);

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
  const clientIngestKey = req.headers['x-ibkr-ingest-key'] || '';
  const clientExecutionKey = req.headers['x-ibkr-execution-key'] || '';
  const clientAuthHeader = req.headers['authorization'] || '';

  // Endpoint Security Classification:
  // 1. Public: health probes
  const isPublicEndpoint = incomingPath === '/api/health' || incomingPath === '/api/health/';

  // 2. Ingestion-Only: dedicated IBKR paper adapter snapshot pushes
  const isIBKRSyncProtected = incomingPath.startsWith('/api/portfolio/ibkr/sync') && req.method === 'POST';

  // 3. Execution-Agent-Only: machine-to-machine execution endpoints (poll, claim, report, heartbeat)
  const isIBKRExecutionProtected = incomingPath.startsWith('/api/portfolio/ibkr/execution/orders') ||
    incomingPath.startsWith('/api/portfolio/ibkr/execution/agent/heartbeat');

  // 4. Administrator-Only: all other StockAnalysis endpoints (portfolio, orders, emergency-stop, settings, scanner, valuation)
  const isAdminProtected = !isPublicEndpoint && !isIBKRSyncProtected && !isIBKRExecutionProtected;
  const isProtectedEndpoint = isAdminProtected || isIBKRSyncProtected || isIBKRExecutionProtected;

  let validatedAdminInternalKey = null;
  let validatedIngestInternalKey = null;
  let validatedExecutionInternalKey = null;

  if (isProtectedEndpoint) {
    const expectedAdminKey = process.env.STOCKANALYSIS_ADMIN_KEY || '';
    const expectedIngestKey = process.env.IBKR_INGESTION_KEY || process.env.STOCKANALYSIS_IBKR_INGEST_KEY || '';
    const expectedExecKey = process.env.IBKR_EXECUTION_KEY || process.env.STOCKANALYSIS_IBKR_EXECUTION_KEY || '';

    // 1. Verify validated administrator identity from authenticated web session
    const isAdminSession = !!(
      req.session &&
      req.session.adminAuthUserId &&
      req.session.adminRole === 'admin'
    );

    const bearerToken = clientAuthHeader.startsWith('Bearer ') ? clientAuthHeader.slice(7).trim() : '';

    if (isAdminProtected) {
      // Admin endpoints STRICTLY require admin session or STOCKANALYSIS_ADMIN_KEY (IBKR ingest/exec keys are forbidden)
      let isAuthorizedAdmin = isAdminSession;
      const providedAdmin = bearerToken || clientAdminKey;
      if (expectedAdminKey && providedAdmin && timingSafeCompare(providedAdmin, expectedAdminKey)) {
        isAuthorizedAdmin = true;
      }

      if (!isAuthorizedAdmin) {
        return res.status(401).json({
          status: 'UNAUTHORIZED',
          message: 'Administrator authorization required. Ingestion-only credentials or anonymous access cannot access this endpoint.'
        });
      }

      if (expectedAdminKey) validatedAdminInternalKey = expectedAdminKey;

    } else if (isIBKRSyncProtected) {
      // Production fail-closed guard: missing or known development credentials forbidden
      if (process.env.NODE_ENV === 'production') {
        if (!expectedIngestKey || KNOWN_DEV_INGEST_KEYS.has(expectedIngestKey)) {
          return res.status(500).json({
            status: 'CONFIGURATION_ERROR',
            message: 'Production configuration failure: IBKR_INGESTION_KEY is missing, empty, or using an insecure development value.'
          });
        }
      }

      // IBKR sync strictly requires dedicated ingestion credentials
      let isAuthorizedIngest = false;
      const providedToken = bearerToken || clientIngestKey;

      if (expectedIngestKey && providedToken && timingSafeCompare(providedToken, expectedIngestKey)) {
        isAuthorizedIngest = true;
      }

      if (!isAuthorizedIngest) {
        return res.status(401).json({
          status: 'UNAUTHORIZED',
          message: 'IBKR paper sync is restricted to authorized ingestion credentials.'
        });
      }

      validatedIngestInternalKey = expectedIngestKey;

    } else if (isIBKRExecutionProtected) {
      // Production fail-closed guard: missing or known development execution credentials forbidden
      if (process.env.NODE_ENV === 'production') {
        if (!expectedExecKey || KNOWN_DEV_EXECUTION_KEYS.has(expectedExecKey)) {
          return res.status(500).json({
            status: 'CONFIGURATION_ERROR',
            message: 'Production configuration failure: IBKR_EXECUTION_KEY is missing, empty, or using an insecure development value.'
          });
        }
      }

      // IBKR execution strictly requires dedicated machine-to-machine execution credentials
      let isAuthorizedExec = false;
      const providedToken = bearerToken || clientExecutionKey;

      if (expectedExecKey && providedToken && timingSafeCompare(providedToken, expectedExecKey)) {
        isAuthorizedExec = true;
      }

      if (!isAuthorizedExec) {
        return res.status(401).json({
          status: 'UNAUTHORIZED',
          message: 'IBKR execution endpoints are restricted to authorized execution credentials.'
        });
      }

      validatedExecutionInternalKey = expectedExecKey;
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
    delete headers['x-ibkr-ingest-key']; // Unconditionally strip client-supplied X-IBKR-Ingest-Key
    delete headers['x-ibkr-execution-key']; // Unconditionally strip client-supplied X-IBKR-Execution-Key

    // For protected commands: strip client-supplied credentials and inject ONLY trusted internal keys
    if (isProtectedEndpoint) {
      delete headers['authorization'];
      delete headers['x-admin-key'];
      delete headers['x-ibkr-ingest-key'];
      delete headers['x-ibkr-execution-key'];

      if (validatedAdminInternalKey) {
        headers['x-admin-key'] = validatedAdminInternalKey;
      }
      if (validatedIngestInternalKey) {
        headers['x-ibkr-ingest-key'] = validatedIngestInternalKey;
      }
      if (validatedExecutionInternalKey) {
        headers['x-ibkr-execution-key'] = validatedExecutionInternalKey;
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
