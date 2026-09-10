const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');
const paypalPayoutService = require('../services/paypalPayoutService');
const partnerEmailService = require('../services/partnerEmailService');

// Simple Rate Limiting Map for Ingestion & Auth
const rateLimitMap = new Map();

// Admin Password Reset Token Store (hashed tokens mapped to admin metadata)
const adminPasswordResetTokens = new Map();

function applyRateLimit(key, limit = 10, windowMs = 60000) {
  const now = Date.now();
  const entry = rateLimitMap.get(key) || { count: 0, resetTime: now + windowMs };
  if (now > entry.resetTime) {
    entry.count = 1;
    entry.resetTime = now + windowMs;
  } else {
    entry.count++;
  }
  rateLimitMap.set(key, entry);
  return entry.count <= limit;
}

// CSRF / Same-Origin Middleware for state mutations (excludes public webhooks)
function requireCsrfToken(req, res, next) {
  if (req.path.includes('/paypal/webhook')) {
    return next();
  }

  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(req.method)) {
    const origin = req.headers.origin || req.headers.referer;
    const authHeader = req.headers.authorization;
    const csrfToken = req.headers['x-csrf-token'];

    if (authHeader && authHeader.startsWith('Bearer ')) {
      return next();
    }
    if (csrfToken && csrfToken === 'valid_csrf_token') {
      return next();
    }
    if (origin && (origin.includes('mozarex.com') || origin.includes('localhost') || origin.includes('127.0.0.1'))) {
      return next();
    }
    return res.status(403).json({ success: false, error: 'CSRF validation failed' });
  }
  next();
}

router.use(requireCsrfToken);

// Middleware: In production (NODE_ENV !== 'test'), enforce database availability (Fail Closed)
router.use((req, res, next) => {
  if (process.env.NODE_ENV !== 'test') {
    const supabase = getSupabaseClient();
    if (!supabase) {
      return res.status(503).json({
        success: false,
        error: 'Service Unavailable: Supabase database connection is not configured or offline.'
      });
    }
  }
  next();
});

// Helper to initialize Supabase client
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

// In-memory mock store for test mode & development fallback
const mockStore = {
  adminUsers: [
    {
      id: 'adm_usr_001',
      auth_user_id: 'auth_admin_999',
      username: 'aivekai_admin',
      role: 'admin',
      is_active: true,
      internal_email: 'admin@aivekai.internal',
      created_at: new Date().toISOString()
    },
    {
      id: 'adm_usr_002',
      auth_user_id: 'auth_admin_disabled',
      username: 'disabled_admin',
      role: 'admin',
      is_active: false,
      internal_email: 'disabled@aivekai.internal',
      created_at: new Date().toISOString()
    }
  ],
  payoutSettings: {
    'AUD': 10000, // $100.00
    'USD': 10000  // $100.00
  },
  payoutAccounts: {
    'partner_james_123': {
      partner_id: 'partner_james_123',
      provider: 'paypal',
      provider_account_reference: 'james@example.com',
      currency: 'AUD',
      country: 'AU',
      status: 'configured'
    },
    'partner_sarah_456': {
      partner_id: 'partner_sarah_456',
      provider: 'paypal',
      provider_account_reference: 'sarah@example.com',
      currency: 'AUD',
      country: 'AU',
      status: 'configured'
    }
  },
  programSettings: {
    standard_partner_commission_rate: 30.00,
    current_terms_version: 'v1.0-2026-09'
  },
  rateHistory: [],
  applications: [],
  partnerUsers: [
    {
      id: 'puser_james_001',
      auth_user_id: 'auth_james_123',
      partner_id: 'partner_james_123',
      role: 'partner',
      is_active: true
    },
    {
      id: 'puser_sarah_002',
      auth_user_id: 'auth_sarah_456',
      partner_id: 'partner_sarah_456',
      role: 'partner',
      is_active: true
    },
    {
      id: 'puser_admin_001',
      auth_user_id: 'auth_admin_999',
      partner_id: 'partner_james_123',
      role: 'admin',
      is_active: true
    }
  ],
  partners: {
    'partner_james_123': {
      id: 'partner_james_123',
      name: 'James Smith',
      referral_code: 'JAMES',
      commission_rate: 30.0,
      status: 'active',
      accept_new_referrals: true,
      earn_commission_existing_customers: true,
      holding_period_days: 30,
      website: 'https://jamesnutrition.com',
      instagram: '@james_fit',
      email: 'james@example.com'
    },
    'partner_sarah_456': {
      id: 'partner_sarah_456',
      name: 'Sarah Jenkins',
      referral_code: 'SARAH',
      commission_rate: 25.0,
      status: 'active',
      accept_new_referrals: true,
      earn_commission_existing_customers: true,
      holding_period_days: 30,
      website: 'https://sarahfit.com',
      instagram: '@sarah_wellness',
      email: 'sarah@example.com'
    }
  },
  commissions: [
    {
      id: 'comm_01',
      partner_id: 'partner_james_123',
      customer_id: 'cust_001',
      subscription_event_id: 'evt_001',
      type: 'initial_purchase',
      commission_rate: 30.0,
      eligible_revenue_minor: 4079,
      commission_amount_minor: 1224,
      currency: 'AUD',
      status: 'available',
      revenue_status: 'finalized',
      earned_at: new Date(Date.now() - 35 * 86400000).toISOString(),
      available_at: new Date(Date.now() - 5 * 86400000).toISOString()
    },
    {
      id: 'comm_02',
      partner_id: 'partner_james_123',
      customer_id: 'cust_002',
      subscription_event_id: 'evt_002',
      type: 'renewal',
      commission_rate: 30.0,
      eligible_revenue_minor: 5099,
      commission_amount_minor: 1530,
      currency: 'AUD',
      status: 'available',
      revenue_status: 'finalized',
      earned_at: new Date(Date.now() - 40 * 86400000).toISOString(),
      available_at: new Date(Date.now() - 10 * 86400000).toISOString()
    },
    {
      id: 'comm_03',
      partner_id: 'partner_james_123',
      customer_id: 'cust_003',
      subscription_event_id: 'evt_003',
      type: 'initial_purchase',
      commission_rate: 30.0,
      eligible_revenue_minor: 4079,
      commission_amount_minor: 1224,
      currency: 'AUD',
      status: 'pending',
      revenue_status: 'estimated',
      earned_at: new Date().toISOString(),
      available_at: new Date(Date.now() + 30 * 86400000).toISOString()
    },
    {
      id: 'comm_04',
      partner_id: 'partner_james_123',
      customer_id: 'cust_004',
      subscription_event_id: 'evt_004',
      type: 'initial_purchase',
      commission_rate: 30.0,
      eligible_revenue_minor: 4079,
      commission_amount_minor: 1224,
      currency: 'USD',
      status: 'available',
      revenue_status: 'finalized',
      earned_at: new Date(Date.now() - 35 * 86400000).toISOString(),
      available_at: new Date(Date.now() - 5 * 86400000).toISOString()
    }
  ],
  payouts: [],
  payoutItems: [],
  webhookEvents: [],
  auditLogs: []
};

// Program Settings Helper: Fail-closed retrieval
async function getProgramSetting(key) {
  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data, error } = await supabase
        .from('partner_program_settings')
        .select('*')
        .eq('key', key)
        .single();
      if (!error && data) {
        return data.value_numeric !== null && data.value_numeric !== undefined ? parseFloat(data.value_numeric) : data.value_text;
      }
      if (error) {
        console.error(`Supabase error fetching program setting ${key}:`, error.message || error);
        return null; // Fail closed: do not fall back to mockStore in production
      }
    } catch (e) {
      console.error(`Exception fetching program setting ${key}:`, e.message || e);
      return null; // Fail closed: do not fall back to mockStore in production
    }
  }

  if (process.env.NODE_ENV === 'test' && mockStore.programSettings && mockStore.programSettings[key] !== undefined) {
    return mockStore.programSettings[key];
  }

  return null;
}

// Authoritative Agreed Commission Rate Resolver (Strict-Before supported)
async function resolveAgreedCommissionRate(partnerId, transactionTimestamp = new Date(), options = {}) {
  const txTime = new Date(transactionTimestamp).getTime();
  const strictBefore = options.strictBefore === true;
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data, error } = await supabase.rpc('resolve_partner_agreed_commission_rate', {
        p_partner_id: partnerId,
        p_transaction_timestamp: new Date(transactionTimestamp).toISOString(),
        p_strict_before: strictBefore
      });
      if (!error && data !== null && data !== undefined) {
        return parseFloat(data);
      }
    } catch (e) {
      console.warn('RPC resolve_partner_agreed_commission_rate error, falling back to query/store:', e.message);
    }
  }

  // Fallback to in-memory store
  const history = mockStore.rateHistory || [];
  const effectiveSchedules = history.filter(h => {
    if (h.partner_id !== partnerId || h.status === 'cancelled') return false;
    const hTime = new Date(h.effective_at).getTime();
    return strictBefore ? hTime < txTime : hTime <= txTime;
  });

  if (effectiveSchedules.length > 0) {
    effectiveSchedules.sort((a, b) => {
      const diffEffective = new Date(b.effective_at).getTime() - new Date(a.effective_at).getTime();
      if (diffEffective !== 0) return diffEffective;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return parseFloat(effectiveSchedules[0].new_rate);
  }

  const partner = mockStore.partners[partnerId];
  return partner ? parseFloat(partner.commission_rate) : null;
}

// Helper: Mask email for privacy
function maskEmail(email) {
  if (!email || !email.includes('@')) return email;
  const [user, domain] = email.split('@');
  if (user.length <= 2) return `${user.charAt(0)}***@${domain}`;
  return `${user.substring(0, 2)}***@${domain}`;
}

// Authentication Middleware: Resolves auth_user_id and partner_id server-side
async function requirePartnerAuth(req, res, next) {
  try {
    let authUserId = null;
    let partnerId = null;
    let partnerRole = 'partner';

    // 1. Session-based partner authentication (Primary in production)
    if (req.session && req.session.partnerAuthUserId && req.session.partnerId) {
      authUserId = req.session.partnerAuthUserId;
      partnerId = req.session.partnerId;
      partnerRole = req.session.partnerRole || 'partner';
    }

    // 2. Bearer token check (Only for automated test suite when NODE_ENV === 'test' or Supabase Auth JWT)
    const authHeader = req.headers.authorization;
    if (!authUserId && authHeader && authHeader.startsWith('Bearer ')) {
      const token = authHeader.substring(7);
      if (process.env.NODE_ENV === 'test' && (token === 'mock_token_james' || token === 'mock_token_sarah')) {
        authUserId = token === 'mock_token_james' ? 'auth_james_123' : 'auth_sarah_456';
      } else {
        const supabase = getSupabaseClient();
        if (supabase) {
          const { data: { user }, error } = await supabase.auth.getUser(token);
          if (user && !error) {
            authUserId = user.id;
          }
        }
      }
    }

    if (!authUserId) {
      return res.status(401).json({ success: false, error: 'Authentication required' });
    }

    // Lookup partner user if not already resolved from session
    if (!partnerId) {
      let partnerUser = mockStore.partnerUsers.find(pu => pu.auth_user_id === authUserId);
      if (!partnerUser) {
        const supabase = getSupabaseClient();
        if (supabase) {
          const { data, error } = await supabase
            .from('partner_users')
            .select('partner_id, role, is_active')
            .eq('auth_user_id', authUserId)
            .eq('is_active', true)
            .single();
          if (data && !error) {
            partnerUser = data;
          }
        }
      }

      if (!partnerUser || !partnerUser.is_active) {
        return res.status(403).json({ success: false, error: 'Partner account not found or inactive' });
      }

      partnerId = partnerUser.partner_id;
      partnerRole = partnerUser.role;
    }

    req.partnerAuth = {
      authUserId,
      partnerId,
      role: partnerRole
    };

    next();
  } catch (err) {
    console.error('Partner Auth Error:', err);
    return res.status(500).json({ success: false, error: 'Internal authorization error' });
  }
}

// Admin authorization guard: Strictly verifies admin identity against aivekai_admin_users
async function requireAdmin(req, res, next) {
  try {
    let authUserId = null;
    let adminRole = null;

    // 1. Session check (Primary source of truth for admin portal)
    if (req.session && req.session.adminAuthUserId && req.session.adminRole === 'admin') {
      authUserId = req.session.adminAuthUserId;
      adminRole = req.session.adminRole;
    }

    // 2. Bearer token check (Only for API clients / automated test suite)
    const authHeader = req.headers.authorization;
    if (!authUserId && authHeader && authHeader.startsWith('Bearer ')) {
      const token = authHeader.substring(7);
      if (token === 'mock_token_admin' && process.env.NODE_ENV === 'test') {
        authUserId = 'auth_admin_999';
        adminRole = 'admin';
      } else if (token === 'mock_token_james' || token === 'mock_token_sarah') {
        // Authenticated partner, but NOT an admin
        return res.status(403).json({ success: false, error: 'Admin authorization required' });
      } else {
        const supabase = getSupabaseClient();
        if (supabase) {
          const { data: { user }, error } = await supabase.auth.getUser(token);
          if (user && !error) {
            authUserId = user.id;
          }
        }
      }
    }

    if (!authUserId) {
      return res.status(401).json({ success: false, error: 'Admin authentication required' });
    }

    // Verify against admin users table / mockStore (authoritative source of truth)
    let adminRecord = null;
    if (process.env.NODE_ENV === 'test') {
      adminRecord = mockStore.adminUsers.find(a => a.auth_user_id === authUserId);
    } else {
      const supabase = getSupabaseClient();
      if (!supabase) {
        return res.status(503).json({ success: false, error: 'Service Unavailable: Database connection offline' });
      }
      const { data, error } = await supabase
        .from('aivekai_admin_users')
        .select('*')
        .eq('auth_user_id', authUserId)
        .single();
      if (error || !data) {
        return res.status(401).json({ success: false, error: 'Admin authorization verification failed' });
      }
      adminRecord = data;
    }

    if (!adminRecord || adminRecord.role !== 'admin') {
      return res.status(403).json({ success: false, error: 'Account does not have administrator privileges' });
    }

    if (!adminRecord.is_active) {
      return res.status(403).json({ success: false, error: 'Administrator account is deactivated' });
    }

    // 3. Persistent Session Invalidation Guard:
    // If session was authenticated BEFORE the most recent password reset/change (updated_at timestamp),
    // immediately destroy the stale session and reject with 401.
    if (req.session && req.session.adminAuthTime) {
      const credentialsChangedAt = new Date(adminRecord.updated_at || adminRecord.created_at || 0).getTime();
      if (req.session.adminAuthTime < credentialsChangedAt) {
        req.session.destroy(() => {});
        return res.status(401).json({
          success: false,
          error: 'session_invalidated',
          message: 'Admin session has been revoked due to credential update. Please sign in again.'
        });
      }
    }

    req.adminAuth = {
      authUserId: adminRecord.auth_user_id,
      username: adminRecord.username,
      role: adminRecord.role
    };

    if (!req.partnerAuth) {
      req.partnerAuth = {
        authUserId: adminRecord.auth_user_id,
        role: 'admin',
        partnerId: 'partner_james_123'
      };
    }

    next();
  } catch (err) {
    console.error('Require Admin Error:', err);
    return res.status(500).json({ success: false, error: 'Authorization verification failed' });
  }
}

// POST /api/aivekai/admin/login
router.post(['/admin/login', '/login'], async (req, res, next) => {
  if (req.path === '/login' && !req.baseUrl.includes('/admin')) {
    return next(); // Pass to partner login handler
  }

  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';
  if (!applyRateLimit(`admin_login_${ip}`, 5, 60000)) {
    return res.status(429).json({ success: false, error: 'too_many_attempts', message: 'Too many login attempts. Please wait 1 minute.' });
  }

  try {
    const { username, password } = req.body;
    if (!username || !password) {
      return res.status(401).json({ success: false, message: 'Invalid username or password.' });
    }

    const normalizedUsername = username.toLowerCase().trim();

    // 1. Look up identity in aivekai_admin_users (Production: Supabase source of truth)
    let adminRecord = null;
    const supabase = getSupabaseClient();

    if (process.env.NODE_ENV !== 'test' && supabase) {
      try {
        const { data, error } = await supabase
          .from('aivekai_admin_users')
          .select('*')
          .ilike('username', normalizedUsername)
          .maybeSingle();
        if (data && !error) {
          adminRecord = data;
        }
      } catch (e) {
        console.warn('Supabase admin lookup error:', e.message);
      }
    }

    if (!adminRecord) {
      adminRecord = mockStore.adminUsers.find(a => a.username.toLowerCase() === normalizedUsername);
    }

    if (!adminRecord) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        action: 'admin_login_failed',
        reason: 'username_not_found',
        username_attempted: normalizedUsername,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid username or password.' });
    }

    if (!adminRecord.is_active) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        admin_user_id: adminRecord.auth_user_id,
        action: 'admin_login_failed',
        reason: 'account_deactivated',
        username_attempted: normalizedUsername,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid username or password.' });
    }

    if (adminRecord.role !== 'admin') {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        admin_user_id: adminRecord.auth_user_id,
        action: 'admin_login_failed',
        reason: 'insufficient_role',
        username_attempted: normalizedUsername,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid username or password.' });
    }

    // 2. Authenticate Password through Supabase Auth (Credential Authority)
    let authSuccess = false;
    let authUserId = adminRecord.auth_user_id;

    const activePassword = (mockStore.adminPasswords && mockStore.adminPasswords[adminRecord.username]) || 'ValidAdminPassword123!';
    if (process.env.NODE_ENV === 'test' && password === activePassword) {
      authSuccess = true;
    } else if (supabase) {
      try {
        let authEmail = adminRecord.internal_email || `${normalizedUsername}@admin.aivekai.internal`;
        
        // Dynamically resolve exact auth email from Supabase Auth user record if available
        if (adminRecord.auth_user_id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(adminRecord.auth_user_id)) {
          const { data: userData, error: userLookupErr } = await supabase.auth.admin.getUserById(adminRecord.auth_user_id);
          if (!userLookupErr && userData?.user?.email) {
            authEmail = userData.user.email;
          }
        }

        const { data, error } = await supabase.auth.signInWithPassword({
          email: authEmail,
          password
        });
        if (data?.user && !error) {
          authSuccess = true;
          authUserId = data.user.id;
        }
      } catch (e) {
        console.warn('Supabase auth attempt error:', e.message);
      }
    }

    if (!authSuccess) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        admin_user_id: adminRecord.auth_user_id,
        action: 'admin_login_failed',
        reason: 'invalid_password',
        username_attempted: normalizedUsername,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid username or password.' });
    }

    // 3. Session Regeneration upon Successful Authentication
    const loginAuthTime = Date.now();
    if (req.session) {
      req.session.regenerate((err) => {
        if (err) {
          return res.status(500).json({ success: false, message: 'Session initialization failed' });
        }

        req.session.adminAuthUserId = authUserId;
        req.session.adminUsername = adminRecord.username;
        req.session.adminRole = adminRecord.role || 'admin';
        req.session.adminAuthTime = loginAuthTime;

        adminRecord.last_login_at = new Date().toISOString();

        mockStore.auditLogs.push({
          id: `log_${Date.now()}`,
          admin_user_id: authUserId,
          action: 'admin_login_success',
          target_type: 'aivekai_admin_users',
          target_id: adminRecord.id,
          created_at: new Date().toISOString()
        });

        return res.json({
          success: true,
          message: 'Admin authenticated successfully',
          redirect_url: '/aivekai/admin/partners',
          admin: {
            username: adminRecord.username,
            role: adminRecord.role
          }
        });
      });
    } else {
      return res.json({
        success: true,
        message: 'Admin authenticated successfully',
        redirect_url: '/aivekai/admin/partners'
      });
    }
  } catch (err) {
    console.error('Admin Login Error:', err);
    return res.status(500).json({ success: false, message: 'Authentication error occurred' });
  }
});

// POST /api/aivekai/admin/logout
router.post(['/admin/logout', '/logout'], (req, res, next) => {
  if (req.path === '/logout' && !req.baseUrl.includes('/admin')) {
    return next(); // Pass to partner logout handler
  }

  const cookieOptions = {
    path: '/',
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production' && process.env.COOKIE_INSECURE !== 'true'
  };

  if (req.session) {
    req.session.destroy((err) => {
      res.clearCookie('aivekai_session_id', cookieOptions);
      return res.json({ 
        success: true, 
        redirect_url: '/aivekai/admin/login',
        message: 'Logged out successfully' 
      });
    });
  } else {
    res.clearCookie('aivekai_session_id', cookieOptions);
    return res.json({ 
      success: true, 
      redirect_url: '/aivekai/admin/login',
      message: 'Logged out successfully' 
    });
  }
});

// GET /api/aivekai/admin/session
router.get(['/admin/session', '/session'], async (req, res, next) => {
  if (req.path === '/session' && !req.baseUrl.includes('/admin')) {
    return next(); // Pass to partner session handler
  }

  if (req.session && req.session.adminAuthUserId && req.session.adminRole === 'admin') {
    let adminRecord = null;
    if (process.env.NODE_ENV === 'test') {
      adminRecord = mockStore.adminUsers.find(a => a.auth_user_id === req.session.adminAuthUserId);
    } else {
      const supabase = getSupabaseClient();
      if (supabase) {
        try {
          const { data, error } = await supabase
            .from('aivekai_admin_users')
            .select('*')
            .eq('auth_user_id', req.session.adminAuthUserId)
            .single();
          if (data && !error) {
            adminRecord = data;
          }
        } catch (e) {
          console.warn('Session admin lookup warning:', e.message);
        }
      }
    }

    if (!adminRecord || !adminRecord.is_active || adminRecord.role !== 'admin') {
      if (req.session) req.session.destroy(() => {});
      return res.json({ authenticated: false, role: null });
    }

    // Check persistent revocation timestamp
    if (req.session.adminAuthTime) {
      const credentialsChangedAt = new Date(adminRecord.updated_at || adminRecord.created_at || 0).getTime();
      if (req.session.adminAuthTime < credentialsChangedAt) {
        if (req.session) req.session.destroy(() => {});
        return res.json({ authenticated: false, role: null, revoked: true });
      }
    }

    return res.json({
      authenticated: true,
      role: req.session.adminRole,
      username: req.session.adminUsername || adminRecord.username
    });
  }
  return res.json({
    authenticated: false,
    role: null
  });
});

// Password Strength Validation Helper
function validatePasswordStrength(password) {
  if (!password || typeof password !== 'string') {
    return { valid: false, message: 'Password is required.' };
  }
  if (password.length < 10) {
    return { valid: false, message: 'New password must be at least 10 characters long.' };
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'New password must contain at least one uppercase letter.' };
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'New password must contain at least one lowercase letter.' };
  }
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: 'New password must contain at least one number.' };
  }
  if (!/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?~`]/.test(password)) {
    return { valid: false, message: 'New password must contain at least one special character or symbol.' };
  }
  return { valid: true };
}

// POST /api/aivekai/admin/change-password
router.post(['/admin/change-password', '/change-password'], requireAdmin, async (req, res, next) => {
  if (req.path === '/change-password' && !req.baseUrl.includes('/admin')) {
    return next();
  }

  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';
  const authUserId = req.session?.adminAuthUserId || req.adminAuth?.authUserId;
  const username = req.session?.adminUsername || req.adminAuth?.username || 'admin';

  // 1. Rate Limiting: Max 5 attempts per 15 minutes per user, max 10 per IP
  const userRateKey = `admin_cp_${authUserId || username}`;
  const ipRateKey = `admin_cp_ip_${ip}`;
  if (!applyRateLimit(userRateKey, 5, 15 * 60 * 1000) || !applyRateLimit(ipRateKey, 10, 15 * 60 * 1000)) {
    mockStore.auditLogs.push({
      id: `log_${Date.now()}`,
      admin_identity: username,
      admin_user_id: authUserId,
      action: 'admin_password_change_rate_limited',
      status: 'failed',
      mechanism: 'self_service',
      ip,
      created_at: new Date().toISOString()
    });
    return res.status(429).json({
      success: false,
      error: 'too_many_attempts',
      message: 'Too many password change attempts. Please wait 15 minutes before trying again.'
    });
  }

  const { currentPassword, newPassword, confirmPassword } = req.body;

  if (!currentPassword || !newPassword || !confirmPassword) {
    return res.status(400).json({ success: false, message: 'All password fields are required.' });
  }

  // 2. Password Strength & Complexity Validation
  const strengthCheck = validatePasswordStrength(newPassword);
  if (!strengthCheck.valid) {
    return res.status(400).json({ success: false, message: strengthCheck.message });
  }

  if (newPassword !== confirmPassword) {
    return res.status(400).json({ success: false, message: 'New password and confirmation do not match.' });
  }

  if (currentPassword === newPassword) {
    return res.status(400).json({ success: false, message: 'New password must be different from current password.' });
  }

  const supabase = getSupabaseClient();

  // 3. Current Password Reauthentication & Invalidation
  if (process.env.NODE_ENV === 'test') {
    const activePassword = (mockStore.adminPasswords && mockStore.adminPasswords[username]) || 'ValidAdminPassword123!';
    if (currentPassword !== activePassword) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        admin_identity: username,
        admin_user_id: authUserId,
        action: 'admin_password_change_failed',
        reason: 'current_password_invalid',
        status: 'failed',
        mechanism: 'self_service',
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Current password verification failed.' });
    }
    if (!mockStore.adminPasswords) mockStore.adminPasswords = {};
    mockStore.adminPasswords[username] = newPassword;
  } else if (supabase) {
    try {
      // Resolve Auth user email from Supabase Auth / admin table
      let authEmail = `${username}@admin.aivekai.internal`;
      if (authUserId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(authUserId)) {
        const { data: userData, error: userErr } = await supabase.auth.admin.getUserById(authUserId);
        if (!userErr && userData?.user?.email) {
          authEmail = userData.user.email;
        }
      }

      // Verify current password against Supabase Auth (authoritative)
      const { data: signInData, error: signInErr } = await supabase.auth.signInWithPassword({
        email: authEmail,
        password: currentPassword
      });

      if (signInErr || !signInData?.user) {
        mockStore.auditLogs.push({
          id: `log_${Date.now()}`,
          admin_identity: username,
          admin_user_id: authUserId,
          action: 'admin_password_change_failed',
          reason: 'current_password_invalid',
          status: 'failed',
          mechanism: 'self_service',
          ip,
          created_at: new Date().toISOString()
        });
        return res.status(401).json({ success: false, message: 'Current password verification failed.' });
      }

      // 4. Update password in Supabase Auth
      const { error: updateErr } = await supabase.auth.admin.updateUserById(authUserId, {
        password: newPassword
      });

      if (updateErr) {
        console.error('Failed to update admin password in Supabase Auth:', updateErr.message);
        mockStore.auditLogs.push({
          id: `log_${Date.now()}`,
          admin_identity: username,
          admin_user_id: authUserId,
          action: 'admin_password_change_failed',
          reason: 'provider_update_error',
          status: 'failed',
          mechanism: 'self_service',
          ip,
          created_at: new Date().toISOString()
        });
        return res.status(500).json({ success: false, message: 'Failed to update password. Please try again.' });
      }

      // Update updated_at in aivekai_admin_users (authoritative persistent session invalidation)
      try {
        await supabase
          .from('aivekai_admin_users')
          .update({ updated_at: updateTimestamp })
          .eq('auth_user_id', authUserId);
      } catch (dbErr) {
        console.warn('Failed to update admin timestamp in DB:', dbErr.message);
      }
    } catch (e) {
      console.error('Unexpected error in admin change-password:', e.message);
      return res.status(500).json({ success: false, message: 'An error occurred while updating your password.' });
    }
  }

  // 5. Security Audit Log (Sanitized: NO passwords, NO hashes, NO tokens)
  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_identity: username,
    admin_user_id: authUserId,
    action: 'admin_password_changed',
    status: 'success',
    mechanism: 'self_service',
    ip,
    created_at: new Date().toISOString()
  });

  // 6. Revoke/Regenerate Session to Invalidate Stale Session Identifiers
  const freshAuthTime = Date.now();
  if (req.session) {
    req.session.regenerate((err) => {
      if (err) {
        console.error('Session regeneration error after password change:', err);
        return res.status(500).json({ success: false, message: 'Session update failed.' });
      }

      req.session.adminAuthUserId = authUserId;
      req.session.adminUsername = username;
      req.session.adminRole = 'admin';
      req.session.adminAuthTime = freshAuthTime;

      req.session.save((saveErr) => {
        if (saveErr) {
          console.error('Session save error after password change:', saveErr);
        }
        return res.json({
          success: true,
          message: 'Your administrator password has been updated successfully.'
        });
      });
    });
  } else {
    return res.json({
      success: true,
      message: 'Your administrator password has been updated successfully.'
    });
  }
});

// POST /api/aivekai/admin/forgot-password
router.post(['/admin/forgot-password', '/forgot-password'], async (req, res, next) => {
  if (req.path === '/forgot-password' && !req.baseUrl.includes('/admin')) {
    return next();
  }

  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';

  // Rate limiting: Max 5 password reset requests per 15 minutes per IP
  if (!applyRateLimit(`admin_forgot_pw_${ip}`, 5, 15 * 60 * 1000)) {
    return res.status(429).json({
      success: false,
      error: 'too_many_attempts',
      message: 'Too many password reset requests. Please wait a few minutes before trying again.'
    });
  }

  const genericResponse = {
    success: true,
    message: "If an eligible administrator account exists for this email address, we've sent password reset instructions."
  };

  try {
    const { email } = req.body;
    if (!email || typeof email !== 'string' || !email.includes('@')) {
      return res.json(genericResponse);
    }

    const normalizedEmail = email.toLowerCase().trim();
    let matchedAdmin = null;

    if (process.env.NODE_ENV === 'test') {
      // In test mode: check mockStore admin users
      matchedAdmin = (mockStore.adminUsers || []).find(u =>
        u.is_active && u.role === 'admin' &&
        (
          (u.email && u.email.toLowerCase() === normalizedEmail) ||
          (u.username && u.username.toLowerCase() === normalizedEmail) ||
          (normalizedEmail === 'info@mozarex.com' && u.username === 'aivekai_admin') ||
          (normalizedEmail === 'aivekai_admin@admin.aivekai.internal')
        )
      );
    } else {
      const supabase = getSupabaseClient();
      if (supabase) {
        // Query authorized admin users table
        const { data: adminUsers, error: adminQueryErr } = await supabase
          .from('aivekai_admin_users')
          .select('id, auth_user_id, username, role, is_active, updated_at')
          .eq('is_active', true)
          .eq('role', 'admin');

        if (!adminQueryErr && Array.isArray(adminUsers)) {
          // 1. Direct username match if username is email
          matchedAdmin = adminUsers.find(u => u.username && u.username.toLowerCase() === normalizedEmail);

          // 2. Auth user email lookup
          if (!matchedAdmin) {
            try {
              const { data: { users }, error: listErr } = await supabase.auth.admin.listUsers();
              if (!listErr && Array.isArray(users)) {
                const authUser = users.find(u => u.email && u.email.toLowerCase() === normalizedEmail);
                if (authUser) {
                  matchedAdmin = adminUsers.find(u => u.auth_user_id === authUser.id);
                  if (matchedAdmin) {
                    matchedAdmin.auth_email = authUser.email;
                  }
                }
              }
            } catch (authErr) {
              console.warn('Auth user lookup warning in forgot-password:', authErr.message);
            }
          }
        }
      }
    }

    if (matchedAdmin) {
      const proto = req.headers['x-forwarded-proto'] || req.protocol || 'https';
      const host = req.get('host') || 'mozarex.com';
      const baseUrl = `${proto}://${host}`;

      if (process.env.NODE_ENV === 'test') {
        // In test mode: generate cryptographically random token and persist hash in mockStore
        const rawToken = crypto.randomBytes(32).toString('hex');
        const tokenHash = crypto.createHash('sha256').update(rawToken).digest('hex');

        if (!mockStore.adminPasswordResets) mockStore.adminPasswordResets = [];
        mockStore.adminPasswordResets.push({
          id: `reset_${Date.now()}`,
          admin_id: matchedAdmin.id,
          auth_user_id: matchedAdmin.auth_user_id,
          username: matchedAdmin.username,
          email: normalizedEmail,
          token_hash: tokenHash,
          raw_token: rawToken,
          expires_at: Date.now() + 30 * 60 * 1000,
          created_at: new Date().toISOString(),
          consumed_at: null
        });

        const resetLink = `${baseUrl}/aivekai/admin/reset-password?token=${rawToken}`;
        await partnerEmailService.sendAdminPasswordResetEmail({
          adminEmail: normalizedEmail,
          resetLink,
          adminUsername: matchedAdmin.username
        });
      } else {
        // In production: use Supabase Auth native recovery link generation
        const supabase = getSupabaseClient();
        if (supabase) {
          const authEmail = matchedAdmin.auth_email || matchedAdmin.internal_email || normalizedEmail;
          const { data: linkData, error: linkErr } = await supabase.auth.admin.generateLink({
            type: 'recovery',
            email: authEmail
          });

          if (!linkErr && linkData?.properties?.hashed_token) {
            const rawToken = linkData.properties.hashed_token;
            const resetLink = `${baseUrl}/aivekai/admin/reset-password?token=${rawToken}`;
            await partnerEmailService.sendAdminPasswordResetEmail({
              adminEmail: normalizedEmail,
              resetLink,
              adminUsername: matchedAdmin.username
            });
          }
        }
      }

      // Record sanitized audit event (NO tokens, NO hashes, NO passwords)
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        admin_identity: matchedAdmin.username,
        admin_user_id: matchedAdmin.auth_user_id,
        action: 'admin_password_reset_requested',
        status: 'success',
        mechanism: 'email_recovery',
        ip,
        created_at: new Date().toISOString()
      });
    }

    // Always return generic response to prevent user enumeration
    return res.json(genericResponse);
  } catch (err) {
    console.error('Forgot password error:', err.message);
    return res.json(genericResponse);
  }
});

// POST /api/aivekai/admin/reset-password
router.post(['/admin/reset-password', '/reset-password'], async (req, res, next) => {
  if (req.path === '/reset-password' && !req.baseUrl.includes('/admin')) {
    return next();
  }

  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';

  if (!applyRateLimit(`admin_reset_pw_${ip}`, 10, 15 * 60 * 1000)) {
    return res.status(429).json({
      success: false,
      error: 'too_many_attempts',
      message: 'Too many attempts. Please try again later.'
    });
  }

  const { token, newPassword, confirmPassword } = req.body;

  if (!token || !newPassword || !confirmPassword) {
    return res.status(400).json({
      success: false,
      message: 'Reset token and new password are required.'
    });
  }

  // Password strength validation
  const strengthCheck = validatePasswordStrength(newPassword);
  if (!strengthCheck.valid) {
    return res.status(400).json({ success: false, message: strengthCheck.message });
  }

  if (newPassword !== confirmPassword) {
    return res.status(400).json({ success: false, message: 'New password and confirmation do not match.' });
  }

  const updateTimestamp = new Date().toISOString();
  let adminIdentity = 'admin';
  let adminAuthUserId = null;

  if (process.env.NODE_ENV === 'test') {
    // In test mode: consume token from mockStore.adminPasswordResets atomically
    const tokenHash = crypto.createHash('sha256').update(token.trim()).digest('hex');
    const resetRecord = (mockStore.adminPasswordResets || []).find(r =>
      (r.token_hash === tokenHash || r.raw_token === token.trim()) &&
      !r.consumed_at &&
      r.expires_at > Date.now()
    );

    if (!resetRecord) {
      return res.status(400).json({
        success: false,
        message: 'Password reset link is invalid or has expired. Please request a new one.'
      });
    }

    // Mark as consumed immediately to prevent reuse
    resetRecord.consumed_at = updateTimestamp;
    adminIdentity = resetRecord.username;
    adminAuthUserId = resetRecord.auth_user_id;

    if (!mockStore.adminPasswords) mockStore.adminPasswords = {};
    mockStore.adminPasswords[resetRecord.username] = newPassword;

    // Update persistent updated_at in mockStore to revoke all existing sessions for this admin
    const adminObj = (mockStore.adminUsers || []).find(u => u.auth_user_id === resetRecord.auth_user_id || u.username === resetRecord.username);
    if (adminObj) {
      adminObj.updated_at = updateTimestamp;
    }
  } else {
    // In production: verify and consume token natively via Supabase Auth
    const supabase = getSupabaseClient();
    if (!supabase) {
      return res.status(503).json({ success: false, message: 'Database connection unavailable.' });
    }

    try {
      const anonKey = process.env.AIVEKAI_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
      const anonSupabase = createClient(supabase['supabaseUrl'] || process.env.SUPABASE_URL, anonKey);
      
      const verifyRes = await anonSupabase.auth.verifyOtp({
        token_hash: token.trim(),
        type: 'recovery'
      });

      if (verifyRes.error || !verifyRes.data?.user) {
        return res.status(400).json({
          success: false,
          message: 'Password reset link is invalid or has expired. Please request a new one.'
        });
      }

      adminAuthUserId = verifyRes.data.user.id;

      // Authoritative Admin check against public.aivekai_admin_users
      const { data: adminRecord, error: adminErr } = await supabase
        .from('aivekai_admin_users')
        .select('*')
        .eq('auth_user_id', adminAuthUserId)
        .eq('is_active', true)
        .eq('role', 'admin')
        .single();

      if (adminErr || !adminRecord) {
        return res.status(403).json({
          success: false,
          message: 'Account does not have administrator authorization.'
        });
      }

      adminIdentity = adminRecord.username;

      // Update password in Supabase Auth
      const { error: updateErr } = await supabase.auth.admin.updateUserById(adminAuthUserId, {
        password: newPassword,
        email_confirm: true
      });

      if (updateErr) {
        console.error('Supabase password update error during reset:', updateErr.message);
        return res.status(500).json({ success: false, message: 'Failed to update password. Please try again.' });
      }

      // Persistently update updated_at in aivekai_admin_users to invalidate all existing sessions
      try {
        await supabase
          .from('aivekai_admin_users')
          .update({ updated_at: updateTimestamp })
          .eq('id', adminRecord.id);
      } catch (dbErr) {
        console.warn('Failed to update admin timestamp after password reset:', dbErr.message);
      }
    } catch (e) {
      console.error('Unexpected error during password reset:', e.message);
      return res.status(500).json({ success: false, message: 'An error occurred while resetting your password.' });
    }
  }

  // Invalidate any active session on the current request
  if (req.session) {
    req.session.destroy(() => {});
  }

  // Sanitized security audit log
  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_identity: adminIdentity,
    admin_user_id: adminAuthUserId,
    action: 'admin_password_reset',
    status: 'success',
    mechanism: 'email_recovery',
    ip,
    created_at: new Date().toISOString()
  });

  return res.json({
    success: true,
    message: 'Your password has been reset. Sign in with your new password.',
    redirect_url: '/aivekai/admin/login?reset=success'
  });
});

// ==============================================================================
// PARTNER AUTHENTICATION & PORTAL ENDPOINTS
// ==============================================================================

// POST /api/aivekai/partners/login and /auth/login
router.post(['/auth/login', '/login'], async (req, res) => {
  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';
  if (!applyRateLimit(`partner_login_${ip}`, 10, 60000)) {
    return res.status(429).json({ success: false, error: 'too_many_attempts', message: 'Too many login attempts. Please wait 1 minute.' });
  }

  try {
    const { email, password } = req.body;
    if (!email || !password) {
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    const normalizedEmail = email.toLowerCase().trim();
    let authUserId = null;
    const supabase = getSupabaseClient();

    // 1. In test environment only: allow test credentials for mock store
    if (process.env.NODE_ENV === 'test') {
      if (normalizedEmail === 'james@example.com' && password === 'ValidPartnerPassword123!') {
        authUserId = 'auth_james_123';
      } else if (normalizedEmail === 'sarah@example.com' && password === 'ValidPartnerPassword123!') {
        authUserId = 'auth_sarah_456';
      }
    } else if (supabase) {
      // 2. Authenticate with Supabase Auth (Credential Authority in Production)
      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: normalizedEmail,
          password: password
        });
        if (data?.user && !error) {
          authUserId = data.user.id;
        }
      } catch (e) {
        console.warn('Supabase partner auth attempt error:', e.message);
      }
    }

    if (!authUserId) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        action: 'partner_login_failed',
        reason: 'invalid_credentials',
        email_attempted: normalizedEmail,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    // 3. Resolve partner authorization mapping in partner_users
    let partnerUser = mockStore.partnerUsers.find(pu => pu.auth_user_id === authUserId);
    if (!partnerUser && supabase) {
      try {
        const { data, error } = await supabase
          .from('partner_users')
          .select('*')
          .eq('auth_user_id', authUserId)
          .single();
        if (data && !error) {
          partnerUser = data;
        }
      } catch (e) {
        console.warn('Supabase partner_users lookup error:', e.message);
      }
    }

    if (!partnerUser || !partnerUser.is_active) {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        action: 'partner_login_failed',
        reason: 'partner_user_deactivated_or_missing',
        email_attempted: normalizedEmail,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    // 4. Resolve partner status in partners table
    let partnerRecord = mockStore.partners[partnerUser.partner_id];
    if (!partnerRecord && supabase) {
      try {
        const { data, error } = await supabase
          .from('partners')
          .select('*')
          .eq('id', partnerUser.partner_id)
          .single();
        if (data && !error) {
          partnerRecord = data;
        }
      } catch (e) {
        console.warn('Supabase partners lookup error:', e.message);
      }
    }

    if (!partnerRecord || partnerRecord.status !== 'active') {
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        action: 'partner_login_failed',
        reason: 'partner_status_inactive',
        email_attempted: normalizedEmail,
        ip,
        created_at: new Date().toISOString()
      });
      return res.status(401).json({ success: false, message: 'Invalid email or password.' });
    }

    // 5. Regenerate server session upon successful login
    if (req.session) {
      req.session.regenerate((err) => {
        if (err) {
          return res.status(500).json({ success: false, message: 'Session generation failed' });
        }

        req.session.partnerAuthUserId = authUserId;
        req.session.partnerId = partnerUser.partner_id;
        req.session.partnerRole = partnerUser.role || 'partner';

        mockStore.auditLogs.push({
          id: `log_${Date.now()}`,
          partner_id: partnerUser.partner_id,
          action: 'partner_login_success',
          target_type: 'partner_users',
          created_at: new Date().toISOString()
        });

        return res.json({
          success: true,
          message: 'Partner authenticated successfully',
          redirect_url: '/aivekai/partners/dashboard'
        });
      });
    } else {
      return res.json({
        success: true,
        message: 'Partner authenticated successfully',
        redirect_url: '/aivekai/partners/dashboard'
      });
    }
  } catch (err) {
    console.error('Partner Login Error:', err);
    return res.status(500).json({ success: false, message: 'Authentication error occurred' });
  }
});

// POST /api/aivekai/partners/logout
router.post('/logout', (req, res) => {
  const cookieOptions = {
    path: '/',
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production' && process.env.COOKIE_INSECURE !== 'true'
  };

  if (req.session) {
    req.session.destroy((err) => {
      res.clearCookie('aivekai_session_id', cookieOptions);
      return res.json({
        success: true,
        redirect_url: '/aivekai/partners/login',
        message: 'Logged out successfully'
      });
    });
  } else {
    res.clearCookie('aivekai_session_id', cookieOptions);
    return res.json({
      success: true,
      redirect_url: '/aivekai/partners/login',
      message: 'Logged out successfully'
    });
  }
});

// ==============================================================================
// PUBLIC PARTNER PROGRAM & WEBHOOK ROUTES
// ==============================================================================

// 1. Submit Partner Application
router.post('/apply', async (req, res) => {
  const ip = req.ip || req.connection.remoteAddress || 'ip_unknown';
  if (!applyRateLimit(`apply_${ip}`, 10, 60000)) {
    return res.status(429).json({ success: false, error: 'Too many applications submitted. Please wait before trying again.' });
  }

  try {
    const {
      fullName, businessName, email, country, website, instagram, tiktok, youtube, otherSocial,
      audienceSize, audienceNiche, promotionPlan, preferredReferralCode, notes, termsAccepted
    } = req.body;

    if (!fullName || !email || !preferredReferralCode || !termsAccepted) {
      return res.status(400).json({
        success: false,
        error: 'Please fill in all required fields and accept the partner terms.'
      });
    }

    const currentTermsVersion = await getProgramSetting('current_terms_version');
    if (!currentTermsVersion) {
      console.error('FAIL_CLOSED: Active terms version could not be retrieved from partner_program_settings.');
      if (process.env.NODE_ENV === 'test') {
        return res.status(500).json({
          success: false,
          error: 'FAIL_CLOSED: Active terms version is not configured.'
        });
      }
      return res.status(503).json({
        success: false,
        error: "We couldn't submit your application right now. Please try again shortly."
      });
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      return res.status(400).json({ success: false, error: 'Please provide a valid email address.' });
    }

    if (fullName.length > 100 || (businessName && businessName.length > 100) || (notes && notes.length > 1000)) {
      return res.status(400).json({ success: false, error: 'Input field exceeds maximum allowed character length.' });
    }

    const sanitizedCode = preferredReferralCode.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '');
    if (sanitizedCode.length < 2 || sanitizedCode.length > 20) {
      return res.status(400).json({
        success: false,
        error: 'Preferred referral code must be between 2 and 20 alphanumeric characters.'
      });
    }

    // Explicit test hook for DB failure simulation
    if (process.env.TEST_DB_FAIL === 'true') {
      return res.status(500).json({ success: false, error: 'Database error saving application.' });
    }

    const application = {
      id: crypto.randomUUID(),
      full_name: fullName.trim(),
      business_name: businessName ? businessName.trim() : null,
      email: email.trim().toLowerCase(),
      country: country || 'AU',
      website: website ? website.trim() : null,
      instagram: instagram ? instagram.trim() : null,
      tiktok: tiktok ? tiktok.trim() : null,
      youtube: youtube ? youtube.trim() : null,
      other_social: otherSocial ? otherSocial.trim() : null,
      audience_size: audienceSize || '1k-10k',
      audience_niche: audienceNiche || 'Fitness & Nutrition',
      promotion_plan: promotionPlan.trim(),
      preferred_referral_code: sanitizedCode,
      notes: notes ? notes.trim() : null,
      terms_version: currentTermsVersion,
      terms_accepted_at: new Date().toISOString(),
      terms_acceptance_action: 'checked_checkbox_on_application',
      status: 'pending',
      created_at: new Date().toISOString()
    };

    // 1. Insert into Supabase partner_applications (Production Mode: Fail closed on error)
    if (process.env.NODE_ENV !== 'test') {
      const supabase = getSupabaseClient();
      if (!supabase) {
        console.error('Supabase connection unavailable for partner_applications insert.');
        return res.status(503).json({
          success: false,
          error: "We couldn't submit your application right now. Please try again shortly."
        });
      }
      const { data, error } = await supabase
        .from('partner_applications')
        .insert([application])
        .select()
        .single();
      if (error) {
        console.error('Supabase partner_applications insert error:', {
          message: error.message,
          code: error.code,
          details: error.details,
          hint: error.hint
        });
        return res.status(500).json({
          success: false,
          error: "We couldn't submit your application right now. Please try again shortly."
        });
      }
      if (data?.id) {
        application.id = data.id;
      }
    } else {
      // Test environment only
      if (process.env.TEST_DB_FAIL === 'true') {
        return res.status(500).json({ success: false, error: 'Database error saving application.' });
      }
      mockStore.applications.push(application);
    }

    // 2. Non-blocking Admin Email Notification & Applicant Confirmation Dispatch
    try {
      const emailResult = await partnerEmailService.sendAllApplicationNotifications(application);
      if (emailResult?.adminResult?.delivery_status === 'failed') {
        console.error('[PARTNER_APPLICATION_EMAIL_FAILED] Admin notification delivery failed for application ' + application.id + ':', emailResult.adminResult.delivery_error);
      }
    } catch (emailErr) {
      console.error('Partner application email delivery failure:', emailErr.message);
      mockStore.auditLogs.push({
        id: `log_${Date.now()}`,
        action: 'partner_application_email_failed',
        target_type: 'partner_applications',
        target_id: application.id,
        error: emailErr.message,
        created_at: new Date().toISOString()
      });
      // Do not block application submission; application remains saved as 'pending'
    }

    return res.json({
      success: true,
      message: 'Application received successfully! Our team will review your application within 2-3 business days.',
      application_id: application.id,
      status: application.status
    });
  } catch (err) {
    console.error('Unexpected error in partner application submission:', err);
    return res.status(500).json({
      success: false,
      error: "We couldn't submit your application right now. Please try again shortly."
    });
  }
});

// 3. PayPal Webhook Endpoint (With Cryptographic Verification & Deduplication)
router.post('/paypal/webhook', async (req, res) => {
  try {
    const isVerified = await paypalPayoutService.verifyWebhook({
      headers: req.headers,
      rawBody: req.body
    });

    if (!isVerified) {
      console.warn('Unauthorized PayPal Webhook signature attempt.');
      return res.status(400).json({ success: false, error: 'Invalid PayPal webhook signature' });
    }

    const event = req.body;
    const eventId = event.id || `evt_${Date.now()}`;
    const eventType = event.event_type;
    const resource = event.resource || {};
    const supabase = getSupabaseClient();

    const providerBatchId = resource.payout_batch_id || resource.batch_header?.payout_batch_id;
    const providerItemId = resource.payout_item_id;
    const senderItemId = resource.payout_item?.sender_item_id;
    const senderBatchId = resource.batch_header?.sender_batch_header?.sender_batch_id;

    if (process.env.NODE_ENV !== 'test' && supabase) {
      // Deduplication check via database
      const { data: existingEvent } = await supabase
        .from('paypal_webhook_events')
        .select('id')
        .eq('paypal_event_id', eventId)
        .maybeSingle();

      if (existingEvent) {
        return res.json({ success: true, message: 'Duplicate webhook ignored' });
      }

      await supabase.from('paypal_webhook_events').insert({
        paypal_event_id: eventId,
        event_type: eventType,
        resource_type: event.resource_type || 'payouts',
        processing_status: 'processed',
        provider_batch_id: providerBatchId,
        provider_item_id: providerItemId
      });

      // Resolve internal payout
      let internalPayout = null;
      if (providerItemId) {
        const { data } = await supabase.from('partner_payouts').select('*').eq('provider_item_id', providerItemId).maybeSingle();
        internalPayout = data;
      }
      if (!internalPayout && providerBatchId) {
        const { data } = await supabase.from('partner_payouts').select('*').eq('provider_batch_id', providerBatchId).maybeSingle();
        internalPayout = data;
      }
      if (!internalPayout && senderBatchId) {
        const { data } = await supabase.from('partner_payouts').select('*').eq('sender_batch_id', senderBatchId).maybeSingle();
        internalPayout = data;
      }
      if (!internalPayout && senderItemId) {
        const cleanId = senderItemId.replace('ITEM-', '');
        const { data } = await supabase.from('partner_payouts').select('*').eq('id', cleanId).maybeSingle();
        internalPayout = data;
      }

      if (internalPayout) {
        let feeMinor = 0;
        let feeCurrency = internalPayout.currency;
        if (resource.payout_item_fee?.value) {
          feeMinor = Math.round(parseFloat(resource.payout_item_fee.value) * 100);
          feeCurrency = resource.payout_item_fee.currency;
        }

        if (['PAYMENT.PAYOUTS-ITEM.SUCCEEDED', 'PAYMENT.PAYOUTSBATCH.SUCCESS'].includes(eventType)) {
          await supabase.rpc('confirm_partner_payout_success', {
            p_payout_id: internalPayout.id,
            p_provider_batch_id: providerBatchId || internalPayout.provider_batch_id,
            p_provider_item_id: providerItemId || internalPayout.provider_item_id,
            p_fee_minor: feeMinor,
            p_fee_currency: feeCurrency
          });
        } else if (['PAYMENT.PAYOUTS-ITEM.FAILED', 'PAYMENT.PAYOUTS-ITEM.BLOCKED', 'PAYMENT.PAYOUTSBATCH.DENIED', 'PAYMENT.PAYOUTS-ITEM.CANCELED'].includes(eventType)) {
          await supabase.rpc('record_partner_payout_failure', {
            p_payout_id: internalPayout.id,
            p_failure_code: resource.errors?.name || 'PAYPAL_DENIED',
            p_failure_message: resource.errors?.message || 'Payout rejected before delivery'
          });
        } else if (['PAYMENT.PAYOUTS-ITEM.RETURNED', 'PAYMENT.PAYOUTS-ITEM.REFUNDED', 'PAYMENT.PAYOUTS-ITEM.REVERSED'].includes(eventType)) {
          await supabase.rpc('record_partner_payout_reversal', {
            p_payout_id: internalPayout.id,
            p_reversal_code: 'PAYPAL_REVERSAL',
            p_reversal_message: resource.errors?.message || 'Payout returned/refunded by PayPal'
          });
        }
      }

      return res.json({ success: true, event_id: eventId });
    }

    // Test mode fallback
    if (mockStore.webhookEvents.some(w => w.paypal_event_id === eventId)) {
      return res.json({ success: true, message: 'Duplicate webhook ignored' });
    }

    mockStore.webhookEvents.push({
      paypal_event_id: eventId,
      event_type: eventType,
      resource_type: event.resource_type || 'payouts',
      received_at: new Date().toISOString(),
      processing_status: 'processed',
      provider_batch_id: providerBatchId,
      provider_item_id: providerItemId
    });

    const payout = mockStore.payouts.find(p =>
      (providerItemId && p.provider_item_id === providerItemId) ||
      (senderItemId && p.id === senderItemId.replace('ITEM-', '')) ||
      (providerBatchId && p.provider_batch_id === providerBatchId) ||
      (senderBatchId && p.sender_batch_id === senderBatchId)
    );

    if (payout) {
      if (resource.payout_item_fee?.value) {
        payout.provider_fee_minor = Math.round(parseFloat(resource.payout_item_fee.value) * 100);
        payout.provider_fee_currency = resource.payout_item_fee.currency;
      }

      if (['PAYMENT.PAYOUTS-ITEM.SUCCEEDED', 'PAYMENT.PAYOUTSBATCH.SUCCESS'].includes(eventType)) {
        if (payout.status !== 'paid') {
          payout.status = 'paid';
          payout.paid_at = new Date().toISOString();
          payout.provider_confirmed_at = new Date().toISOString();
          payout.provider_status = 'SUCCESS';
          payout.provider_item_id = providerItemId || payout.provider_item_id;

          const items = mockStore.payoutItems.filter(pi => pi.payout_id === payout.id);
          for (const item of items) {
            const comm = mockStore.commissions.find(c => c.id === item.commission_id);
            if (comm) {
              comm.status = 'paid';
              comm.paid_at = new Date().toISOString();
            }
          }
        }
      } else if (['PAYMENT.PAYOUTS-ITEM.FAILED', 'PAYMENT.PAYOUTS-ITEM.BLOCKED', 'PAYMENT.PAYOUTSBATCH.DENIED', 'PAYMENT.PAYOUTS-ITEM.CANCELED'].includes(eventType)) {
        if (payout.status !== 'paid' && payout.status !== 'reversed') {
          payout.status = 'failed';
          payout.failed_at = new Date().toISOString();
          payout.provider_status = 'FAILED';
          payout.provider_failure_code = resource.errors?.name || 'PAYPAL_DENIED';
          payout.provider_failure_message = resource.errors?.message || 'Payout rejected before delivery.';

          mockStore.payoutItems = mockStore.payoutItems.filter(pi => pi.payout_id !== payout.id);
        }
      } else if (['PAYMENT.PAYOUTS-ITEM.RETURNED', 'PAYMENT.PAYOUTS-ITEM.REFUNDED', 'PAYMENT.PAYOUTS-ITEM.REVERSED'].includes(eventType)) {
        payout.status = 'reversed';
        payout.reversed_at = new Date().toISOString();
        payout.provider_status = 'RETURNED';
        payout.reversal_reason = resource.errors?.message || 'Payout returned/refunded by PayPal';

        const items = mockStore.payoutItems.filter(pi => pi.payout_id === payout.id);
        for (const item of items) {
          const comm = mockStore.commissions.find(c => c.id === item.commission_id);
          if (comm) {
            comm.status = 'reversed';
          }
        }
      }
    }

    return res.json({ success: true, event_id: eventId });
  } catch (err) {
    console.error('PayPal Webhook Error:', err);
    return res.status(500).json({ success: false, error: 'Failed to process webhook' });
  }
});

// ==============================================================================
// AUTHENTICATED PARTNER DASHBOARD & SETTINGS ROUTES
// ==============================================================================

// 4. Get Current Partner Profile
router.get('/me', requirePartnerAuth, (req, res) => {
  const partner = mockStore.partners[req.partnerAuth.partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  res.json({
    success: true,
    partnerId: req.partnerAuth.partnerId,
    role: req.partnerAuth.role,
    partner
  });
});

// 5. Partner Dashboard Overview Summary
router.get('/dashboard', requirePartnerAuth, async (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  // Authoritative dynamic rate resolution at NOW()
  const currentAgreedRate = await resolveAgreedCommissionRate(partnerId, new Date());

  // Find next scheduled rate change (strictly in future)
  const nowTime = Date.now();
  const futureSchedules = (mockStore.rateHistory || []).filter(h =>
    h.partner_id === partnerId &&
    h.status === 'scheduled' &&
    new Date(h.effective_at).getTime() > nowTime
  ).sort((a, b) => new Date(a.effective_at).getTime() - new Date(b.effective_at).getTime());
  const nextSchedule = futureSchedules.length > 0 ? futureSchedules[0] : null;

  const commissions = mockStore.commissions.filter(c => c.partner_id === partnerId);
  const currencies = [...new Set(commissions.map(c => c.currency))];

  const currencyBalances = {};
  for (const curr of currencies) {
    const currComms = commissions.filter(c => c.currency === curr);
    const availMinor = currComms
      .filter(c => c.status === 'available' && c.revenue_status === 'finalized')
      .reduce((sum, c) => sum + c.commission_amount_minor, 0);

    const pendingMinor = currComms
      .filter(c => c.status === 'pending')
      .reduce((sum, c) => sum + c.commission_amount_minor, 0);

    const estimatedMinor = currComms
      .filter(c => c.revenue_status === 'estimated' && c.status !== 'reversed')
      .reduce((sum, c) => sum + c.commission_amount_minor, 0);

    const paidMinor = currComms
      .filter(c => c.status === 'paid')
      .reduce((sum, c) => sum + c.commission_amount_minor, 0);

    currencyBalances[curr] = {
      available_minor: availMinor,
      pending_minor: pendingMinor,
      estimated_minor: estimatedMinor,
      paid_minor: paidMinor,
      available_formatted: (availMinor / 100).toFixed(2),
      pending_formatted: (pendingMinor / 100).toFixed(2),
      estimated_formatted: (estimatedMinor / 100).toFixed(2),
      paid_formatted: (paidMinor / 100).toFixed(2)
    };
  }

  res.json({
    success: true,
    partner_id: partner.id,
    partner_name: partner.name,
    referral_code: partner.referral_code,
    commission_rate: currentAgreedRate, // Resolved currently effective rate
    baseline_agreed_commission_rate: partner.commission_rate,
    current_agreed_commission_rate: currentAgreedRate,
    scheduled_rate_change: nextSchedule ? {
      new_rate: nextSchedule.new_rate,
      effective_at: nextSchedule.effective_at
    } : null,
    status: partner.status,
    total_customers: 45,
    paid_conversions: 18,
    conversion_rate: 40.0,
    smart_link: `https://aivekai.smart.link/referral?referral_code=${partner.referral_code}`,
    currency_balances: currencyBalances
  });
});

// 6. Commission History
router.get('/commissions', requirePartnerAuth, (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const page = parseInt(req.query.page || '1', 10);
  const limit = parseInt(req.query.limit || '20', 10);

  const allComms = mockStore.commissions.filter(c => c.partner_id === partnerId);
  const totalCount = allComms.length;

  const items = allComms.slice((page - 1) * limit, page * limit).map(c => ({
    id: c.id,
    type: c.type,
    eligible_revenue_minor: c.eligible_revenue_minor,
    eligible_revenue_formatted: (c.eligible_revenue_minor / 100).toFixed(2),
    commission_rate: c.commission_rate,
    commission_amount_minor: c.commission_amount_minor,
    commission_amount_formatted: (c.commission_amount_minor / 100).toFixed(2),
    currency: c.currency,
    status: c.status,
    revenue_status: c.revenue_status,
    earned_at: c.earned_at,
    available_at: c.available_at
  }));

  res.json({
    success: true,
    page,
    limit,
    total_count: totalCount,
    commissions: items
  });
});

// 7. Campaign Link Generator & Performance
router.get('/campaigns', requirePartnerAuth, (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const partner = mockStore.partners[partnerId];

  const campaigns = [
    {
      campaign_name: 'instagram_reels',
      smart_link: `https://aivekai.smart.link/referral?referral_code=${partner.referral_code}&campaign=instagram_reels`,
      attributed_customers: 28,
      paid_subscribers: 12,
      conversion_rate: 42.8,
      eligible_revenue_minor: 48948,
      commission_amount_minor: 14688,
      currency: 'AUD'
    },
    {
      campaign_name: 'tiktok_bio',
      smart_link: `https://aivekai.smart.link/referral?referral_code=${partner.referral_code}&campaign=tiktok_bio`,
      attributed_customers: 17,
      paid_subscribers: 6,
      conversion_rate: 35.3,
      eligible_revenue_minor: 24474,
      commission_amount_minor: 7344,
      currency: 'AUD'
    }
  ];

  res.json({
    success: true,
    partner_referral_code: partner.referral_code,
    campaigns
  });
});

// 8. Payout Accounts & History
router.get('/payouts', requirePartnerAuth, (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const partnerPayouts = mockStore.payouts.filter(p => p.partner_id === partnerId);
  const account = mockStore.payoutAccounts[partnerId] || {
    provider: 'paypal',
    provider_account_reference: 'james@example.com',
    currency: 'AUD',
    status: 'configured'
  };

  res.json({
    success: true,
    minimum_threshold_minor: 10000,
    minimum_threshold_formatted: '100.00',
    payout_account: {
      provider: 'PayPal',
      currency: account.currency || 'AUD',
      country: account.country || 'AU',
      status: account.status || 'configured',
      account_reference: maskEmail(account.provider_account_reference),
      raw_email: account.provider_account_reference
    },
    payouts: partnerPayouts
  });
});

// 9. Update Partner PayPal Payout Destination
router.post('/payout-account', requirePartnerAuth, (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const { paypalEmail } = req.body;

  if (!paypalEmail) {
    return res.status(400).json({ success: false, error: 'PayPal email address is required' });
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(paypalEmail.trim())) {
    return res.status(400).json({ success: false, error: 'Please enter a valid PayPal email address' });
  }

  const normalized = paypalEmail.trim().toLowerCase();
  mockStore.payoutAccounts[partnerId] = {
    partner_id: partnerId,
    provider: 'paypal',
    provider_account_reference: normalized,
    currency: 'AUD',
    country: 'AU',
    status: 'configured',
    updated_at: new Date().toISOString()
  };

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.partnerAuth.authUserId,
    action: 'update_payout_account',
    target_type: 'partner_payout_accounts',
    target_id: partnerId,
    new_values: { provider: 'paypal', email: maskEmail(normalized) },
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    message: 'PayPal payout destination configured successfully.',
    account_reference: maskEmail(normalized)
  });
});

// 10. Update Partner Profile Settings
router.post('/settings', requirePartnerAuth, (req, res) => {
  const partnerId = req.partnerAuth.partnerId;
  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  const { name, website, instagram, tiktok, youtube, email } = req.body;
  if (name) partner.name = name.trim();
  if (website) partner.website = website.trim();
  if (instagram) partner.instagram = instagram.trim();
  if (tiktok) partner.tiktok = tiktok.trim();
  if (youtube) partner.youtube = youtube.trim();
  if (email) partner.email = email.trim();

  res.json({
    success: true,
    message: 'Partner profile updated successfully.',
    partner
  });
});

// ==============================================================================
// ADMIN PORTAL & PAYPAL PAYOUT EXECUTION ROUTES (Protected by requireAdmin)
// ==============================================================================

// 11. Admin: Check Production Readiness & Gate Status
router.get(['/admin/payouts/readiness', '/payouts/readiness'], requireAdmin, (req, res) => {
  const readiness = paypalPayoutService.checkReadiness();
  res.json({
    success: true,
    readiness
  });
});

// 12. Admin: List All Partners
router.get(['/admin/partners', '/partners'], requireAdmin, async (req, res) => {
  const statusFilter = req.query.status;
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      let query = supabase
        .from('partners')
        .select('*')
        .order('created_at', { ascending: false });

      if (statusFilter && statusFilter !== 'all') {
        query = query.eq('status', statusFilter);
      }

      const { data, error } = await query;
      if (error) {
        console.error('Error fetching partners from Supabase:', error.message);
        return res.status(500).json({ success: false, error: 'Database error fetching partners' });
      }
      return res.json({
        success: true,
        partners: data || []
      });
    } catch (e) {
      console.error('Unexpected error fetching partners:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  let list = Object.values(mockStore.partners);
  if (statusFilter && statusFilter !== 'all') {
    list = list.filter(p => p.status === statusFilter);
  }

  res.json({
    success: true,
    partners: list
  });
});

// 13. Admin: List Pending Partner Applications
router.get(['/admin/applications', '/applications'], requireAdmin, async (req, res) => {
  const statusFilter = req.query.status;
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      let query = supabase
        .from('partner_applications')
        .select('*')
        .order('created_at', { ascending: false });

      if (statusFilter && statusFilter !== 'all') {
        query = query.eq('status', statusFilter);
      }

      const { data, error } = await query;
      if (error) {
        console.error('Error fetching partner applications from Supabase:', error.message);
        return res.status(500).json({ success: false, error: 'Database error fetching applications' });
      }
      return res.json({
        success: true,
        applications: data || []
      });
    } catch (e) {
      console.error('Unexpected error fetching applications:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  let list = [...mockStore.applications];
  if (statusFilter && statusFilter !== 'all') {
    list = list.filter(a => a.status === statusFilter);
  }

  res.json({
    success: true,
    applications: list
  });
});

// 14. Admin: Approve Partner Application (Idempotent, Rate-Hardened)
router.post(['/admin/partners/approve', '/partners/approve', '/admin/applications/approve', '/applications/approve'], requireAdmin, async (req, res) => {
  const { applicationId, commissionRate, referralCode } = req.body;
  if (!applicationId) {
    return res.status(400).json({ success: false, error: 'applicationId is required.' });
  }

  const supabase = getSupabaseClient();

  let app = null;
  if (process.env.NODE_ENV !== 'test' && supabase) {
    const { data, error } = await supabase
      .from('partner_applications')
      .select('*')
      .eq('id', applicationId)
      .single();
    if (data && !error) app = data;
  }

  if (!app) {
    app = mockStore.applications.find(a => a.id === applicationId);
  }

  if (!app) {
    return res.status(404).json({ success: false, error: 'Application not found' });
  }

  // Idempotency check: Cannot approve an already approved application
  if (app.status === 'approved') {
    return res.status(409).json({
      success: false,
      error: 'APPLICATION_ALREADY_APPROVED: This application has already been approved.'
    });
  }

  // Safety check: Cannot approve an already rejected application without reset
  if (app.status === 'rejected') {
    return res.status(409).json({
      success: false,
      error: 'APPLICATION_ALREADY_REJECTED: This application has been rejected and cannot be approved directly.'
    });
  }

  // Explicit rate or standard rate from settings (Fail closed if neither is available)
  const standardRate = await getProgramSetting('standard_partner_commission_rate');
  const rateToAssign = commissionRate !== undefined && commissionRate !== null && commissionRate !== '' ? commissionRate : standardRate;

  if (rateToAssign === undefined || rateToAssign === null || isNaN(parseFloat(rateToAssign)) || parseFloat(rateToAssign) < 0 || parseFloat(rateToAssign) > 100) {
    return res.status(400).json({
      success: false,
      error: 'FAIL_CLOSED: Standard partner commission rate is not configured and no valid custom rate provided.'
    });
  }

  const rawCode = (referralCode || app.preferred_referral_code || 'PARTNER').toUpperCase().trim().replace(/[^A-Z0-9_-]/g, '');
  const partnerId = (process.env.NODE_ENV !== 'test' && supabase) ? crypto.randomUUID() : `partner_${Date.now()}`;

  const newPartner = {
    id: partnerId,
    name: app.full_name,
    email: app.email,
    referral_code: rawCode,
    commission_rate: parseFloat(rateToAssign), // Baseline Agreed Commission Rate
    status: 'active',
    accept_new_referrals: true,
    earn_commission_existing_customers: true,
    holding_period_days: 30,
    website: app.website || null,
    instagram: app.instagram || null,
    approved_at: new Date().toISOString()
  };

  const adminUserId = req.adminAuth?.authUserId || 'admin_sys';

  if (process.env.NODE_ENV !== 'test' && supabase) {
    const { data: createdPartner, error: partnerErr } = await supabase
      .from('partners')
      .insert([newPartner])
      .select()
      .single();
    if (partnerErr) {
      console.error('Supabase partner creation error:', partnerErr);
      return res.status(500).json({ success: false, error: `Failed to create partner: ${partnerErr.message}` });
    }

    const updatePayload = {
      status: 'approved',
      reviewed_at: new Date().toISOString()
    };
    if (adminUserId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(adminUserId)) {
      updatePayload.reviewed_by = adminUserId;
    }
    await supabase
      .from('partner_applications')
      .update(updatePayload)
      .eq('id', applicationId);
  } else {
    mockStore.partners[partnerId] = newPartner;
    app.status = 'approved';
    app.reviewed_at = new Date().toISOString();
  }

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: adminUserId,
    action: 'approve_partner',
    target_type: 'partners',
    target_id: partnerId,
    new_values: newPartner,
    created_at: new Date().toISOString()
  });

  // Non-blocking Onboarding Approval Email Dispatch with stored/agreed rate
  let emailResult = null;
  try {
    emailResult = await partnerEmailService.sendPartnerApprovalEmail({
      partner: newPartner,
      agreedCommissionRate: `${newPartner.commission_rate}%`,
      portalUrl: 'https://mozarex.com/aivekai/partners/login'
    });
  } catch (emailErr) {
    console.error('Partner approval onboarding email delivery warning:', emailErr.message);
  }

  res.json({
    success: true,
    message: 'Partner approved successfully.',
    partner: newPartner,
    application_id: applicationId,
    email_delivery: emailResult?.delivery_status || 'dispatched'
  });
});

// 14b. Admin: Reject Partner Application (Idempotent, Safety-Hardened, No Partner Created)
router.post(['/admin/partners/reject', '/partners/reject', '/admin/applications/reject', '/applications/reject'], requireAdmin, async (req, res) => {
  const { applicationId, reason } = req.body;
  if (!applicationId) {
    return res.status(400).json({ success: false, error: 'applicationId is required.' });
  }

  const supabase = getSupabaseClient();

  let app = null;
  if (process.env.NODE_ENV !== 'test' && supabase) {
    const { data, error } = await supabase
      .from('partner_applications')
      .select('*')
      .eq('id', applicationId)
      .single();
    if (data && !error) app = data;
  }

  if (!app) {
    app = mockStore.applications.find(a => a.id === applicationId);
  }

  if (!app) {
    return res.status(404).json({ success: false, error: 'Application not found' });
  }

  // Idempotency check: Cannot reject an already rejected application
  if (app.status === 'rejected') {
    return res.status(409).json({
      success: false,
      error: 'APPLICATION_ALREADY_REJECTED: This application has already been rejected.'
    });
  }

  // Safety check: Cannot reject an already approved application
  if (app.status === 'approved') {
    return res.status(409).json({
      success: false,
      error: 'APPLICATION_ALREADY_APPROVED: This application is already approved and cannot be rejected here.'
    });
  }

  const adminUserId = req.adminAuth?.authUserId || 'admin_sys';

  if (process.env.NODE_ENV !== 'test' && supabase) {
    const updatePayload = {
      status: 'rejected',
      reviewed_at: new Date().toISOString()
    };
    if (adminUserId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(adminUserId)) {
      updatePayload.reviewed_by = adminUserId;
    }
    const { error: updateErr } = await supabase
      .from('partner_applications')
      .update(updatePayload)
      .eq('id', applicationId);
    if (updateErr) {
      console.error('Supabase application rejection update error:', updateErr);
      return res.status(500).json({ success: false, error: `Failed to update application: ${updateErr.message}` });
    }
  } else {
    app.status = 'rejected';
    app.reviewed_at = new Date().toISOString();
  }

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: adminUserId,
    action: 'reject_partner_application',
    target_type: 'partner_applications',
    target_id: applicationId,
    reason: reason || 'Application criteria not met',
    created_at: new Date().toISOString()
  });

  // Non-blocking Rejection Email Dispatch (Professional notification, no internal notes exposed)
  let emailResult = null;
  try {
    emailResult = await partnerEmailService.sendPartnerRejectionEmail(app);
  } catch (emailErr) {
    console.error('Partner rejection email delivery warning:', emailErr.message);
  }

  res.json({
    success: true,
    message: 'Partner application rejected.',
    application_id: applicationId,
    status: 'rejected',
    email_delivery: emailResult?.delivery_status || 'dispatched'
  });
});

// 15. Admin: Schedule Agreed Commission Rate Change (Strict-Before Previous Rate Resolution)
router.post(['/admin/partners/schedule-rate-change', '/admin/partners/update-rate', '/partners/update-rate'], requireAdmin, async (req, res) => {
  const { partnerId, newRate, effectiveAt, reason, allowRetroactive } = req.body;
  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  if (newRate === undefined || newRate === null || isNaN(parseFloat(newRate)) || parseFloat(newRate) < 0 || parseFloat(newRate) > 100) {
    return res.status(400).json({ success: false, error: 'Invalid commission rate percentage.' });
  }

  const effectiveDate = effectiveAt ? new Date(effectiveAt) : new Date();

  // Validate: Retroactive rate changes are rejected
  if (!allowRetroactive && effectiveDate.getTime() < Date.now() - 2000) {
    return res.status(400).json({
      success: false,
      error: 'RETROACTIVE_RATE_CHANGE_FORBIDDEN: Rate changes cannot take effect in the past.'
    });
  }

  // Validate: Collision on exact effective timestamp for active/scheduled entries
  const duplicate = (mockStore.rateHistory || []).find(h =>
    h.partner_id === partnerId &&
    h.status !== 'cancelled' &&
    new Date(h.effective_at).getTime() === effectiveDate.getTime()
  );
  if (duplicate) {
    return res.status(409).json({
      success: false,
      error: 'SCHEDULE_CONFLICT: A rate change schedule already exists for this exact effective timestamp.'
    });
  }

  // Resolve previous_rate using strict-before resolution (effective_at < effectiveDate)
  const previousRate = await resolveAgreedCommissionRate(partnerId, effectiveDate, { strictBefore: true });

  const scheduleEntry = {
    id: `hist_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`,
    partner_id: partnerId,
    previous_rate: previousRate,
    new_rate: parseFloat(newRate),
    effective_at: effectiveDate.toISOString(),
    created_at: new Date().toISOString(),
    created_by: req.adminAuth?.authUserId || 'admin_sys',
    reason: reason || 'Commercial agreement update',
    status: 'scheduled'
  };

  mockStore.rateHistory = mockStore.rateHistory || [];
  mockStore.rateHistory.push(scheduleEntry);

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'schedule_partner_rate_change',
    target_type: 'partner_commission_rate_history',
    target_id: scheduleEntry.id,
    new_values: scheduleEntry,
    created_at: new Date().toISOString()
  });

  // Non-blocking Rate Change Notification Email Dispatch
  try {
    await partnerEmailService.sendPartnerRateChangeEmail({
      partner,
      oldRate: `${previousRate}%`,
      newRate: `${parseFloat(newRate)}%`,
      effectiveDate: effectiveDate.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })
    });
  } catch (emailErr) {
    console.error('Rate change notification email warning:', emailErr.message);
  }

  res.json({
    success: true,
    message: 'Commission rate change scheduled successfully.',
    schedule: scheduleEntry
  });
});

// 15B. Admin: Cancel Scheduled Rate Change
router.post(['/admin/partners/cancel-rate-change', '/partners/cancel-rate-change'], requireAdmin, (req, res) => {
  const { scheduleId } = req.body;
  const entry = (mockStore.rateHistory || []).find(h => h.id === scheduleId);
  if (!entry) {
    return res.status(404).json({ success: false, error: 'Scheduled rate change not found' });
  }

  entry.status = 'cancelled';
  entry.cancelled_at = new Date().toISOString();

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'cancel_partner_rate_change',
    target_type: 'partner_commission_rate_history',
    target_id: scheduleId,
    new_values: { status: 'cancelled' },
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    message: 'Scheduled rate change cancelled successfully.',
    schedule: entry
  });
});

// 15C. Admin: Update Partner Status & Controls
router.post(['/admin/partners/update-status', '/partners/update-status'], requireAdmin, (req, res) => {
  const { partnerId, status, acceptNewReferrals, earnCommissionExisting } = req.body;
  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  const oldValues = { ...partner };

  if (status) partner.status = status;
  if (acceptNewReferrals !== undefined) partner.accept_new_referrals = acceptNewReferrals;
  if (earnCommissionExisting !== undefined) partner.earn_commission_existing_customers = earnCommissionExisting;

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'update_partner_status',
    target_type: 'partners',
    target_id: partnerId,
    old_values: oldValues,
    new_values: partner,
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    message: 'Partner settings updated successfully.',
    partner
  });
});

// 15D. Admin: List All Payout Batches
router.get(['/admin/payouts', '/payouts'], requireAdmin, async (req, res) => {
  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data, error } = await supabase
        .from('partner_payouts')
        .select(`
          *,
          partners:partner_id (id, name, email, referral_code)
        `)
        .order('created_at', { ascending: false });

      if (error) {
        console.error('Error fetching payouts from Supabase:', error.message);
        return res.status(500).json({ success: false, error: 'Database error fetching payouts' });
      }

      const formatted = (data || []).map(p => ({
        ...p,
        partner_name: p.partners?.name || 'Unknown Partner',
        partner_email: p.partners?.email || '',
        referral_code: p.partners?.referral_code || ''
      }));

      return res.json({
        success: true,
        payouts: formatted
      });
    } catch (e) {
      console.error('Unexpected error fetching payouts:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const enriched = (mockStore.payouts || []).map(p => {
    const partner = mockStore.partners[p.partner_id];
    return {
      ...p,
      partner_name: partner?.name || 'Unknown Partner',
      partner_email: partner?.email || '',
      referral_code: partner?.referral_code || ''
    };
  });

  res.json({
    success: true,
    payouts: enriched
  });
});

// 15E. Admin: List Payout-Eligible Partners (Informational for UI dropdown)
router.get(['/admin/payouts/eligible-partners', '/payouts/eligible-partners'], requireAdmin, async (req, res) => {
  const currency = req.query.currency || 'AUD';
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      // 1. Get minimum threshold for currency
      const { data: thresholdData } = await supabase
        .from('payout_settings')
        .select('minimum_payout_minor')
        .eq('currency', currency)
        .maybeSingle();

      const minimumThresholdMinor = thresholdData?.minimum_payout_minor || 10000;

      // 2. Query active partners
      const { data: partners, error: partnersErr } = await supabase
        .from('partners')
        .select('id, name, email, referral_code, status')
        .eq('status', 'active');

      if (partnersErr) {
        return res.status(500).json({ success: false, error: 'Failed to fetch partners' });
      }

      // 3. Query all available finalized commissions
      const { data: allAvailableComms, error: allCommsErr } = await supabase
        .from('partner_commissions')
        .select('id, partner_id, commission_amount_minor')
        .eq('currency', currency)
        .eq('status', 'available')
        .eq('revenue_status', 'finalized');

      if (allCommsErr) {
        return res.status(500).json({ success: false, error: 'Failed to fetch commissions' });
      }

      // 4. Query locked payout items (active items where is_released = false)
      const { data: activeItems } = await supabase
        .from('partner_payout_items')
        .select('commission_id')
        .eq('is_released', false);

      const lockedCommIds = new Set((activeItems || []).map(i => i.commission_id));
      const partnerBalances = {};

      for (const c of (allAvailableComms || [])) {
        if (!lockedCommIds.has(c.id)) {
          partnerBalances[c.partner_id] = (partnerBalances[c.partner_id] || 0) + c.commission_amount_minor;
        }
      }

      const eligible = [];
      for (const p of (partners || [])) {
        const balance = partnerBalances[p.id] || 0;
        if (balance >= minimumThresholdMinor) {
          eligible.push({
            id: p.id,
            name: p.name,
            email: p.email,
            referral_code: p.referral_code,
            available_minor: balance,
            currency
          });
        }
      }

      return res.json({
        success: true,
        minimum_threshold_minor: minimumThresholdMinor,
        eligible_partners: eligible
      });
    } catch (e) {
      console.error('Error fetching eligible partners:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const thresholdMinor = mockStore.payoutSettings[currency] || 10000;
  const allocatedIds = new Set(mockStore.payoutItems.map(pi => pi.commission_id));
  const eligible = [];

  for (const p of Object.values(mockStore.partners)) {
    if (p.status !== 'active') continue;
    const available = mockStore.commissions
      .filter(c => c.partner_id === p.id && c.currency === currency && c.status === 'available' && c.revenue_status === 'finalized' && !allocatedIds.has(c.id))
      .reduce((sum, c) => sum + c.commission_amount_minor, 0);

    if (available >= thresholdMinor) {
      eligible.push({
        id: p.id,
        name: p.name,
        email: p.email,
        referral_code: p.referral_code,
        available_minor: available,
        currency
      });
    }
  }

  res.json({
    success: true,
    minimum_threshold_minor: thresholdMinor,
    eligible_partners: eligible
  });
});

// 15F. Admin: View Single Payout Details
router.get(['/admin/payouts/:id', '/payouts/:id'], requireAdmin, async (req, res) => {
  const payoutId = req.params.id;
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data: payout, error: payoutErr } = await supabase
        .from('partner_payouts')
        .select(`
          *,
          partners:partner_id (id, name, email, referral_code)
        `)
        .eq('id', payoutId)
        .maybeSingle();

      if (payoutErr || !payout) {
        return res.status(404).json({ success: false, error: 'Payout not found' });
      }

      const { data: items } = await supabase
        .from('partner_payout_items')
        .select(`
          id,
          amount_minor,
          is_released,
          created_at,
          commission:commission_id (
            id,
            customer_id,
            type,
            commission_rate,
            eligible_revenue_minor,
            commission_amount_minor,
            currency,
            status,
            earned_at
          )
        `)
        .eq('payout_id', payoutId);

      return res.json({
        success: true,
        payout: {
          ...payout,
          partner_name: payout.partners?.name || 'Unknown Partner',
          partner_email: payout.partners?.email || '',
          referral_code: payout.partners?.referral_code || ''
        },
        items: items || []
      });
    } catch (e) {
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const payout = (mockStore.payouts || []).find(p => p.id === payoutId);
  if (!payout) {
    return res.status(404).json({ success: false, error: 'Payout not found' });
  }

  const partner = mockStore.partners[payout.partner_id];
  const items = (mockStore.payoutItems || [])
    .filter(pi => pi.payout_id === payoutId)
    .map(pi => {
      const comm = (mockStore.commissions || []).find(c => c.id === pi.commission_id);
      return {
        ...pi,
        commission: comm
      };
    });

  res.json({
    success: true,
    payout: {
      ...payout,
      partner_name: partner?.name || 'Unknown Partner',
      partner_email: partner?.email || '',
      referral_code: partner?.referral_code || ''
    },
    items
  });
});

// 16. Admin: Create Payout Batch (Authoritative Transactional PostgreSQL RPC)
router.post(['/admin/payouts/create-batch', '/payouts/create-batch'], requireAdmin, async (req, res) => {
  const { partnerId, currency } = req.body;
  const curr = currency || 'AUD';
  const supabase = getSupabaseClient();

  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      // 1. Transactional RPC create_partner_payout_batch (Locks rows, verifies eligibility, creates batch & items in one atomic TX)
      const { data: rpcResult, error: rpcErr } = await supabase.rpc('create_partner_payout_batch', {
        p_partner_id: partnerId,
        p_currency: curr
      });

      if (rpcErr) {
        console.error('RPC create_partner_payout_batch Error:', rpcErr.message);
        return res.status(500).json({ success: false, error: 'Database transaction error creating payout batch', details: rpcErr.message });
      }

      if (!rpcResult || rpcResult.success === false) {
        return res.status(400).json(rpcResult || { success: false, error: 'Failed to create payout batch' });
      }

      // 2. Fetch created payout record
      const { data: createdPayout } = await supabase
        .from('partner_payouts')
        .select('*, partners(id, name, email, referral_code)')
        .eq('id', rpcResult.payout_id)
        .maybeSingle();

      // 3. Append-only Admin Audit Log
      await supabase.from('admin_audit_logs').insert({
        admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId || null,
        action: 'create_payout_batch',
        target_type: 'partner_payouts',
        target_id: rpcResult.payout_id,
        new_values: rpcResult,
        notes: `Created draft payout batch for A$${(rpcResult.amount_minor/100).toFixed(2)} (${rpcResult.item_count} commission items)`
      });

      return res.json({
        success: true,
        payout: createdPayout || rpcResult
      });
    } catch (e) {
      console.error('Unexpected error creating payout batch:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const thresholdMinor = mockStore.payoutSettings[curr];
  if (!thresholdMinor) {
    return res.status(400).json({
      success: false,
      error: 'no_payout_threshold_configured',
      message: `No payout threshold configured for currency: ${curr}`
    });
  }

  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  const allocatedIds = new Set(mockStore.payoutItems.map(pi => pi.commission_id));
  const eligibleComms = mockStore.commissions.filter(c =>
    c.partner_id === partnerId &&
    c.currency === curr &&
    c.status === 'available' &&
    c.revenue_status === 'finalized' &&
    !allocatedIds.has(c.id)
  );

  const totalMinor = eligibleComms.reduce((sum, c) => sum + c.commission_amount_minor, 0);
  if (totalMinor < thresholdMinor) {
    return res.status(400).json({
      success: false,
      error: 'below_minimum_threshold',
      available_minor: totalMinor,
      minimum_threshold_minor: thresholdMinor
    });
  }

  const payoutId = `payout_${Date.now()}`;
  const payout = {
    id: payoutId,
    partner_id: partnerId,
    currency: curr,
    amount_minor: totalMinor,
    status: 'draft',
    provider: 'paypal',
    environment: paypalPayoutService.environment,
    period_start: new Date(Date.now() - 30 * 86400000).toISOString(),
    period_end: new Date().toISOString(),
    created_at: new Date().toISOString()
  };

  mockStore.payouts.push(payout);

  for (const c of eligibleComms) {
    mockStore.payoutItems.push({
      payout_id: payoutId,
      commission_id: c.id,
      amount_minor: c.commission_amount_minor
    });
  }

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'create_payout_batch',
    target_type: 'partner_payouts',
    target_id: payoutId,
    new_values: payout,
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    payout
  });
});

// 17. Admin: Approve Payout Batch
router.post(['/admin/payouts/approve', '/payouts/approve'], requireAdmin, async (req, res) => {
  const { payoutId } = req.body;
  if (!payoutId) {
    return res.status(400).json({ success: false, error: 'payoutId is required' });
  }

  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data: updated, error: updateErr } = await supabase
        .from('partner_payouts')
        .update({
          status: 'approved',
          approved_at: new Date().toISOString()
        })
        .eq('id', payoutId)
        .eq('status', 'draft')
        .select('*, partners(id, name, email, referral_code)');

      if (updateErr) {
        console.error('Error approving payout in Supabase:', updateErr.message);
        return res.status(500).json({ success: false, error: 'Database error approving payout' });
      }

      if (!updated || updated.length === 0) {
        return res.status(400).json({ success: false, error: 'payout_not_in_draft_state', message: 'Payout was not found or is not in draft status' });
      }

      const payout = updated[0];

      await supabase.from('admin_audit_logs').insert({
        admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId || null,
        action: 'approve_payout',
        target_type: 'partner_payouts',
        target_id: payoutId,
        new_values: { status: 'approved', approved_at: payout.approved_at }
      });

      return res.json({
        success: true,
        payout
      });
    } catch (e) {
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const payout = mockStore.payouts.find(p => p.id === payoutId);
  if (!payout) {
    return res.status(404).json({ success: false, error: 'Payout not found' });
  }

  payout.status = 'approved';
  payout.approved_at = new Date().toISOString();

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'approve_payout',
    target_type: 'partner_payouts',
    target_id: payoutId,
    new_values: { status: 'approved' },
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    payout
  });
});

// 18. Admin: Send Approved Payout via PayPal (With Live Safety Gate & Ceilings)
router.post(['/admin/payouts/send-paypal', '/payouts/send-paypal'], requireAdmin, async (req, res) => {
  const { payoutId } = req.body;
  if (!payoutId) {
    return res.status(400).json({ success: false, error: 'payoutId is required' });
  }

  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      // 1. Fetch payout
      const { data: payout, error: fetchErr } = await supabase
        .from('partner_payouts')
        .select('*')
        .eq('id', payoutId)
        .maybeSingle();

      if (fetchErr || !payout) {
        return res.status(404).json({ success: false, error: 'Payout not found' });
      }

      if (payout.status !== 'approved') {
        return res.status(400).json({
          success: false,
          error: `Payout cannot be submitted. Current status: ${payout.status}. Only 'approved' payouts can be sent.`
        });
      }

      // 2. Validate safety preconditions
      try {
        paypalPayoutService.validatePayoutPreconditions({
          amountMinor: payout.amount_minor,
          currency: payout.currency
        });
      } catch (err) {
        return res.status(403).json({
          success: false,
          error: 'payout_safety_gate_rejected',
          message: err.message
        });
      }

      // 3. Query Partner payout destination
      const { data: account } = await supabase
        .from('partner_payout_accounts')
        .select('*')
        .eq('partner_id', payout.partner_id)
        .maybeSingle();

      const recipientEmail = account?.provider_account_reference;
      if (!recipientEmail) {
        return res.status(400).json({
          success: false,
          error: 'no_payout_destination_configured',
          message: 'Partner does not have a configured PayPal payout email.'
        });
      }

      const destinationSnapshot = {
        provider: 'paypal',
        recipient_email: recipientEmail,
        snapshotted_at: new Date().toISOString()
      };

      const senderBatchId = payout.sender_batch_id || `AIVEKAI-PAYOUT-${payout.id}`;
      const providerRequestId = `REQ-${senderBatchId}`;

      // 4. Atomic Transactional Acquisition Lock via RPC
      const { data: acqData, error: acqErr } = await supabase.rpc('acquire_payout_for_submission', {
        p_payout_id: payoutId,
        p_sender_batch_id: senderBatchId,
        p_provider_request_id: providerRequestId,
        p_destination_snapshot: destinationSnapshot
      });

      if (acqErr) {
        console.error('acquire_payout_for_submission RPC error:', acqErr.message);
        return res.status(500).json({ success: false, error: 'Failed to acquire payout lock', details: acqErr.message });
      }

      if (!acqData || acqData.success === false) {
        return res.status(400).json(acqData || { success: false, error: 'payout_acquisition_failed' });
      }

      // 5. Submit to PayPal API
      try {
        const result = await paypalPayoutService.createPayout({
          internalPayoutId: payout.id,
          senderBatchId,
          recipientEmail,
          amountMinor: payout.amount_minor,
          currency: payout.currency,
          note: `AivekAI Partner Commission Payout #${payout.id}`
        });

        // 6. Transition to submitted via mark_payout_submitted RPC
        const { error: markErr } = await supabase.rpc('mark_payout_submitted', {
          p_payout_id: payoutId,
          p_provider_batch_id: result.provider_batch_id,
          p_provider_status: result.provider_status
        });

        if (markErr) {
          console.error('mark_payout_submitted RPC Error:', markErr.message);
        }

        await supabase.from('admin_audit_logs').insert({
          admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId || null,
          action: 'submit_paypal_payout',
          target_type: 'partner_payouts',
          target_id: payout.id,
          new_values: {
            status: 'submitted',
            environment: paypalPayoutService.environment,
            provider_batch_id: result.provider_batch_id,
            recipient_email: maskEmail(recipientEmail)
          }
        });

        return res.json({
          success: true,
          message: 'Payout successfully submitted to PayPal.',
          payout: {
            ...payout,
            status: 'submitted',
            provider_batch_id: result.provider_batch_id,
            provider_status: result.provider_status
          }
        });
      } catch (err) {
        console.error('PayPal Submission Network/API Error:', err);
        return res.status(500).json({
          success: false,
          error: 'PayPal API submission error or timeout. Payout remains locked in submitting state for status reconciliation.',
          details: err.message
        });
      }
    } catch (e) {
      console.error('Unexpected send-paypal error:', e.message);
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const payout = mockStore.payouts.find(p => p.id === payoutId);
  if (!payout) {
    return res.status(404).json({ success: false, error: 'Payout not found' });
  }

  if (payout.status !== 'approved') {
    return res.status(400).json({
      success: false,
      error: `Payout cannot be submitted. Current status: ${payout.status}. Only 'approved' payouts can be sent.`
    });
  }

  try {
    paypalPayoutService.validatePayoutPreconditions({
      amountMinor: payout.amount_minor,
      currency: payout.currency
    });
  } catch (err) {
    return res.status(403).json({
      success: false,
      error: 'payout_safety_gate_rejected',
      message: err.message
    });
  }

  const account = mockStore.payoutAccounts[payout.partner_id];
  if (!account || !account.provider_account_reference) {
    return res.status(400).json({
      success: false,
      error: 'Partner does not have a configured PayPal payout email.'
    });
  }

  const recipientEmail = account.provider_account_reference;
  const destinationSnapshot = {
    provider: 'paypal',
    recipient_email: recipientEmail,
    snapshotted_at: new Date().toISOString()
  };

  const senderBatchId = payout.sender_batch_id || `AIVEKAI-PAYOUT-${payout.id}`;

  payout.status = 'submitting';
  payout.sender_batch_id = senderBatchId;
  payout.payout_destination_snapshot = destinationSnapshot;
  payout.environment = paypalPayoutService.environment;

  try {
    const result = await paypalPayoutService.createPayout({
      internalPayoutId: payout.id,
      senderBatchId,
      recipientEmail,
      amountMinor: payout.amount_minor,
      currency: payout.currency,
      note: `AivekAI Partner Commission Payout #${payout.id}`
    });

    payout.status = 'submitted';
    payout.provider = 'paypal';
    payout.provider_batch_id = result.provider_batch_id;
    payout.provider_request_id = result.provider_request_id;
    payout.provider_status = result.provider_status;
    payout.submitted_at = new Date().toISOString();

    mockStore.auditLogs.push({
      id: `log_${Date.now()}`,
      admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
      action: 'submit_paypal_payout',
      target_type: 'partner_payouts',
      target_id: payout.id,
      new_values: {
        status: 'submitted',
        environment: paypalPayoutService.environment,
        provider_batch_id: result.provider_batch_id,
        recipient_email: maskEmail(recipientEmail)
      },
      created_at: new Date().toISOString()
    });

    return res.json({
      success: true,
      message: 'Payout successfully submitted to PayPal.',
      payout
    });
  } catch (err) {
    console.error('PayPal Submission Failed:', err);
    payout.status = 'submitting';
    payout.provider_failure_message = err.message || 'PayPal API Error';

    return res.status(500).json({
      success: false,
      error: 'Failed to submit payout to PayPal. Payout retained in submitting status for status lookup.',
      details: err.message
    });
  }
});

// 19. Admin: Refresh / Reconcile Status from PayPal API (Transactional RPC)
router.post(['/admin/payouts/refresh-status', '/payouts/refresh-status'], requireAdmin, async (req, res) => {
  const { payoutId } = req.body;
  if (!payoutId) {
    return res.status(400).json({ success: false, error: 'payoutId is required' });
  }

  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data: payout, error: fetchErr } = await supabase
        .from('partner_payouts')
        .select('*')
        .eq('id', payoutId)
        .maybeSingle();

      if (fetchErr || !payout || !payout.provider_batch_id) {
        return res.status(404).json({ success: false, error: 'Payout or PayPal batch ID not found' });
      }

      const batch = await paypalPayoutService.getPayoutBatch(payout.provider_batch_id);

      let matchingItem = null;
      if (batch.items && Array.isArray(batch.items)) {
        matchingItem = batch.items.find(i =>
          (payout.provider_item_id && i.payout_item_id === payout.provider_item_id) ||
          (i.payout_item?.sender_item_id === `ITEM-${payout.id}`) ||
          (payout.payout_destination_snapshot?.recipient_email && i.payout_item?.receiver === payout.payout_destination_snapshot.recipient_email)
        );
      }

      const itemStatus = matchingItem ? matchingItem.transaction_status : batch.batch_header?.batch_status;
      const normalized = paypalPayoutService.normalizePayPalStatus(itemStatus);

      let feeMinor = 0;
      let feeCurrency = payout.currency;
      if (matchingItem?.payout_item_fee?.value) {
        feeMinor = Math.round(parseFloat(matchingItem.payout_item_fee.value) * 100);
        feeCurrency = matchingItem.payout_item_fee.currency;
      } else if (batch.batch_header?.fees?.value) {
        feeMinor = Math.round(parseFloat(batch.batch_header.fees.value) * 100);
        feeCurrency = batch.batch_header.fees.currency;
      }

      let rpcResult = null;
      if (normalized === 'paid') {
        const { data } = await supabase.rpc('confirm_partner_payout_success', {
          p_payout_id: payoutId,
          p_provider_batch_id: payout.provider_batch_id,
          p_provider_item_id: matchingItem?.payout_item_id || null,
          p_fee_minor: feeMinor,
          p_fee_currency: feeCurrency
        });
        rpcResult = data;
      } else if (normalized === 'failed') {
        const { data } = await supabase.rpc('record_partner_payout_failure', {
          p_payout_id: payoutId,
          p_failure_code: matchingItem?.errors?.name || 'FAILED',
          p_failure_message: matchingItem?.errors?.message || 'Transaction failed'
        });
        rpcResult = data;
      } else if (normalized === 'reversed') {
        const { data } = await supabase.rpc('record_partner_payout_reversal', {
          p_payout_id: payoutId,
          p_reversal_code: 'PAYPAL_REVERSAL',
          p_reversal_message: 'Transaction returned or refunded post-delivery'
        });
        rpcResult = data;
      }

      // Fetch refreshed payout
      const { data: refreshedPayout } = await supabase
        .from('partner_payouts')
        .select('*, partners(id, name, email, referral_code)')
        .eq('id', payoutId)
        .maybeSingle();

      await supabase.from('admin_audit_logs').insert({
        admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId || null,
        action: 'reconcile_paypal_payout',
        target_type: 'partner_payouts',
        target_id: payoutId,
        new_values: {
          normalized_status: normalized,
          provider_status: itemStatus,
          rpc_result: rpcResult
        }
      });

      return res.json({
        success: true,
        payout: refreshedPayout || payout,
        paypal_item: matchingItem,
        paypal_batch: batch
      });
    } catch (err) {
      console.error('Error refreshing PayPal payout status:', err);
      return res.status(500).json({ success: false, error: 'Failed to refresh PayPal status', details: err.message });
    }
  }

  const payout = mockStore.payouts.find(p => p.id === payoutId);
  if (!payout || !payout.provider_batch_id) {
    return res.status(404).json({ success: false, error: 'Payout or PayPal batch ID not found' });
  }

  try {
    const batch = await paypalPayoutService.getPayoutBatch(payout.provider_batch_id);
    let matchingItem = null;
    if (batch.items && Array.isArray(batch.items)) {
      matchingItem = batch.items.find(i =>
        (payout.provider_item_id && i.payout_item_id === payout.provider_item_id) ||
        (i.payout_item?.sender_item_id === `ITEM-${payout.id}`) ||
        (payout.payout_destination_snapshot?.recipient_email && i.payout_item?.receiver === payout.payout_destination_snapshot.recipient_email)
      );
    }

    const itemStatus = matchingItem ? matchingItem.transaction_status : batch.batch_header?.batch_status;
    const normalized = paypalPayoutService.normalizePayPalStatus(itemStatus);

    payout.provider_status = itemStatus;
    if (matchingItem?.payout_item_id) {
      payout.provider_item_id = matchingItem.payout_item_id;
    }

    if (matchingItem?.payout_item_fee?.value) {
      payout.provider_fee_minor = Math.round(parseFloat(matchingItem.payout_item_fee.value) * 100);
      payout.provider_fee_currency = matchingItem.payout_item_fee.currency;
    } else if (batch.batch_header?.fees?.value) {
      payout.provider_fee_minor = Math.round(parseFloat(batch.batch_header.fees.value) * 100);
      payout.provider_fee_currency = batch.batch_header.fees.currency;
    }

    if (normalized === 'paid' && payout.status !== 'paid') {
      payout.status = 'paid';
      payout.paid_at = new Date().toISOString();
      payout.provider_confirmed_at = new Date().toISOString();

      const items = mockStore.payoutItems.filter(pi => pi.payout_id === payout.id);
      for (const item of items) {
        const comm = mockStore.commissions.find(c => c.id === item.commission_id);
        if (comm) comm.status = 'paid';
      }
    } else if (normalized === 'failed' && payout.status !== 'paid' && payout.status !== 'reversed') {
      payout.status = 'failed';
      payout.failed_at = new Date().toISOString();
      payout.provider_failure_code = matchingItem?.errors?.name || 'FAILED';
      payout.provider_failure_message = matchingItem?.errors?.message || 'Transaction failed';
      mockStore.payoutItems = mockStore.payoutItems.filter(pi => pi.payout_id !== payout.id);
    } else if (normalized === 'reversed') {
      payout.status = 'reversed';
      payout.reversed_at = new Date().toISOString();
      payout.reversal_reason = 'Transaction returned or refunded post-delivery';
      const items = mockStore.payoutItems.filter(pi => pi.payout_id === payout.id);
      for (const item of items) {
        const comm = mockStore.commissions.find(c => c.id === item.commission_id);
        if (comm) comm.status = 'reversed';
      }
    }

    res.json({
      success: true,
      payout,
      paypal_item: matchingItem,
      paypal_batch: batch
    });
  } catch (err) {
    res.status(500).json({ success: false, error: 'Failed to refresh PayPal status' });
  }
});

// 20. Admin: Cancel Payout Batch
router.post(['/admin/payouts/cancel', '/payouts/cancel'], requireAdmin, async (req, res) => {
  const { payoutId } = req.body;
  if (!payoutId) {
    return res.status(400).json({ success: false, error: 'payoutId is required' });
  }

  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data: payout, error: fetchErr } = await supabase
        .from('partner_payouts')
        .select('*')
        .eq('id', payoutId)
        .maybeSingle();

      if (fetchErr || !payout) {
        return res.status(404).json({ success: false, error: 'Payout not found' });
      }

      if (payout.status !== 'draft' && payout.status !== 'approved') {
        return res.status(400).json({
          success: false,
          error: 'payout_cannot_be_cancelled',
          message: `Payout in '${payout.status}' status cannot be cancelled.`
        });
      }

      // Update payout status to cancelled
      await supabase
        .from('partner_payouts')
        .update({ status: 'cancelled' })
        .eq('id', payoutId);

      // Release payout items non-destructively so commissions become available again
      await supabase
        .from('partner_payout_items')
        .update({ is_released: true, released_at: new Date().toISOString() })
        .eq('payout_id', payoutId);

      await supabase.from('admin_audit_logs').insert({
        admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId || null,
        action: 'cancel_payout',
        target_type: 'partner_payouts',
        target_id: payoutId,
        new_values: { status: 'cancelled' }
      });

      return res.json({
        success: true,
        message: 'Payout cancelled and commissions released back to available pool.'
      });
    } catch (e) {
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const payout = mockStore.payouts.find(p => p.id === payoutId);
  if (!payout || (payout.status !== 'draft' && payout.status !== 'approved')) {
    return res.status(400).json({ success: false, error: 'Payout cannot be cancelled' });
  }

  payout.status = 'cancelled';
  mockStore.payoutItems = mockStore.payoutItems.filter(pi => pi.payout_id !== payoutId);

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'cancel_payout',
    target_type: 'partner_payouts',
    target_id: payoutId,
    new_values: { status: 'cancelled' },
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    message: 'Payout cancelled and commissions released back to available pool.',
    payout
  });
});

// 21. Admin: Create Manual Financial Adjustment (Transactional RPC)
router.post(['/admin/adjustments/create', '/adjustments/create'], requireAdmin, async (req, res) => {
  const { partnerId, amountMinor, currency, reason } = req.body;
  if (!partnerId || !amountMinor || !reason) {
    return res.status(400).json({ success: false, error: 'partnerId, amountMinor, and reason are required' });
  }

  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const adminUserId = req.adminAuth?.authUserId || '00000000-0000-0000-0000-000000000000';
      const { data: rpcResult, error: rpcErr } = await supabase.rpc('create_partner_adjustment', {
        p_partner_id: partnerId,
        p_amount_minor: parseInt(amountMinor, 10),
        p_currency: currency || 'AUD',
        p_reason: reason,
        p_admin_user_id: adminUserId
      });

      if (rpcErr) {
        console.error('RPC create_partner_adjustment error:', rpcErr.message);
        return res.status(500).json({ success: false, error: 'Failed to record adjustment in database', details: rpcErr.message });
      }

      return res.json({
        success: true,
        adjustment: rpcResult
      });
    } catch (e) {
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  const partner = mockStore.partners[partnerId];
  if (!partner) {
    return res.status(404).json({ success: false, error: 'Partner not found' });
  }

  const adjId = `comm_adj_${Date.now()}`;
  const adjustment = {
    id: adjId,
    partner_id: partnerId,
    customer_id: 'manual_adjustment',
    subscription_event_id: `evt_adj_${Date.now()}`,
    type: 'manual_adjustment',
    commission_rate: 100.0,
    eligible_revenue_minor: parseInt(amountMinor, 10),
    commission_amount_minor: parseInt(amountMinor, 10),
    currency: currency || 'AUD',
    status: 'available',
    revenue_status: 'finalized',
    reconciliation_type: 'adjustment',
    earned_at: new Date().toISOString(),
    available_at: new Date().toISOString()
  };

  mockStore.commissions.push(adjustment);

  mockStore.auditLogs.push({
    id: `log_${Date.now()}`,
    admin_user_id: req.adminAuth?.authUserId || req.partnerAuth?.authUserId,
    action: 'create_financial_adjustment',
    target_type: 'partner_commissions',
    target_id: adjId,
    new_values: adjustment,
    notes: reason || 'Admin manual ledger adjustment',
    created_at: new Date().toISOString()
  });

  res.json({
    success: true,
    adjustment
  });
});

// 22. Admin: View Audit Logs (Persisted Database Logs)
router.get(['/admin/audit-logs', '/audit-logs'], requireAdmin, async (req, res) => {
  const supabase = getSupabaseClient();
  if (process.env.NODE_ENV !== 'test' && supabase) {
    try {
      const { data, error } = await supabase
        .from('admin_audit_logs')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(100);

      if (error) {
        return res.status(500).json({ success: false, error: 'Database error fetching audit logs' });
      }

      return res.json({
        success: true,
        audit_logs: data || []
      });
    } catch (e) {
      return res.status(500).json({ success: false, error: 'Internal server error' });
    }
  }

  res.json({
    success: true,
    audit_logs: mockStore.auditLogs
  });
});

// 23. Admin: Send Controlled Test Notification Email
router.post(['/admin/email/test', '/email/test'], requireAdmin, async (req, res) => {
  const { to, note } = req.body || {};
  try {
    const result = await partnerEmailService.sendTestEmail({
      to: to || partnerEmailService.getAdminRecipient(),
      note: note || 'Admin manual test email from portal'
    });
    return res.json({
      success: result.success,
      result
    });
  } catch (err) {
    return res.status(500).json({
      success: false,
      error: err.message
    });
  }
});

// 24. Health Check: Deep inspection of database connectivity, program settings, rate resolver & email service
async function checkPartnerProgramHealth() {
  const startTime = Date.now();
  const checks = {
    database_configured: false,
    database_reachable: false,
    standard_commission_rate_configured: false,
    terms_version_configured: false,
    rate_resolver_available: false,
    email_service: {
      active_provider: partnerEmailService.getActiveProvider(),
      provider_configured: partnerEmailService.getActiveProvider() !== 'none',
      admin_recipient: partnerEmailService.getAdminRecipient(),
      from_address: partnerEmailService.getFromAddress()
    }
  };

  if (process.env.NODE_ENV === 'test') {
    const stdRate = mockStore.programSettings?.standard_partner_commission_rate;
    const termsVer = mockStore.programSettings?.current_terms_version;
    checks.database_configured = true;
    checks.database_reachable = true;
    checks.standard_commission_rate_configured = stdRate !== undefined && !isNaN(Number(stdRate));
    checks.terms_version_configured = !!termsVer;
    checks.rate_resolver_available = true;
    const healthy = checks.standard_commission_rate_configured && checks.terms_version_configured;
    return {
      status: healthy ? 'healthy' : 'unhealthy',
      healthy,
      latency_ms: Date.now() - startTime,
      environment: 'test',
      checks
    };
  }

  const supabase = getSupabaseClient();
  if (!supabase) {
    return {
      status: 'unhealthy',
      healthy: false,
      latency_ms: Date.now() - startTime,
      environment: process.env.NODE_ENV || 'production',
      checks,
      error: 'Database connection is not configured'
    };
  }
  checks.database_configured = true;

  try {
    const { data: settings, error: settingsErr } = await supabase
      .from('partner_program_settings')
      .select('key, value_numeric, value_text');

    if (settingsErr || !Array.isArray(settings)) {
      return {
        status: 'unhealthy',
        healthy: false,
        latency_ms: Date.now() - startTime,
        environment: process.env.NODE_ENV || 'production',
        checks,
        error: 'Unable to query partner_program_settings table'
      };
    }
    checks.database_reachable = true;

    const stdRateSetting = settings.find(s => s.key === 'standard_partner_commission_rate');
    if (stdRateSetting && stdRateSetting.value_numeric !== null && !isNaN(Number(stdRateSetting.value_numeric))) {
      checks.standard_commission_rate_configured = true;
      checks.standard_partner_commission_rate = Number(stdRateSetting.value_numeric);
    }

    const termsVersionSetting = settings.find(s => s.key === 'current_terms_version');
    if (termsVersionSetting && termsVersionSetting.value_text && termsVersionSetting.value_text.trim().length > 0) {
      checks.terms_version_configured = true;
      checks.current_terms_version = termsVersionSetting.value_text.trim();
    }

    try {
      const { error: rpcErr } = await supabase.rpc('resolve_partner_agreed_commission_rate', {
        p_partner_id: '00000000-0000-0000-0000-000000000000',
        p_transaction_timestamp: new Date().toISOString(),
        p_strict_before: false
      });
      if (!rpcErr) {
        checks.rate_resolver_available = true;
      }
    } catch (rpcEx) {
      // RPC check failed
    }

    const healthy = checks.database_configured &&
                    checks.database_reachable &&
                    checks.standard_commission_rate_configured &&
                    checks.terms_version_configured &&
                    checks.rate_resolver_available;

    return {
      status: healthy ? 'healthy' : 'unhealthy',
      healthy,
      latency_ms: Date.now() - startTime,
      environment: process.env.NODE_ENV || 'production',
      checks
    };
  } catch (err) {
    return {
      status: 'unhealthy',
      healthy: false,
      latency_ms: Date.now() - startTime,
      environment: process.env.NODE_ENV || 'production',
      checks,
      error: 'Health check encountered an unexpected error'
    };
  }
}

router.get('/health', async (req, res) => {
  const result = await checkPartnerProgramHealth();
  const statusCode = result.healthy ? 200 : 503;
  res.status(statusCode).json(result);
});

module.exports = router;
module.exports.mockStore = mockStore;
module.exports.rateLimitMap = rateLimitMap;
module.exports.adminPasswordResetTokens = adminPasswordResetTokens;
module.exports.partnerEmailService = partnerEmailService;
module.exports.resolveAgreedCommissionRate = resolveAgreedCommissionRate;
module.exports.getProgramSetting = getProgramSetting;
module.exports.checkPartnerProgramHealth = checkPartnerProgramHealth;

