// Load environment variables in development
if (process.env.NODE_ENV !== 'production') {
    require('dotenv').config();
}

const express = require('express');
const cors = require('cors');
const path = require('path');
const http = require('http');
const session = require('express-session');
const cookieParser = require('cookie-parser');

const app = express();
const server = http.createServer(app);
const PORT = process.env.PORT || 3000;

// Security & Middleware
app.use(cors());
app.use(cookieParser());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Content Security Policy middleware
app.use((req, res, next) => {
  res.setHeader('Content-Security-Policy', 
    "default-src 'self'; " +
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.jsdelivr.net https://www.googletagmanager.com https://www.google-analytics.com; " +
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; " +
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; " +
    "img-src 'self' data: https:; " +
    "connect-src 'self' https://*.supabase.co https://api.openai.com https://api-m.paypal.com https://api-m.sandbox.paypal.com https://www.google-analytics.com;"
  );
  next();
});

// Session middleware for authenticated partner portal
app.use(session({
  secret: process.env.SESSION_SECRET || 'aivekai_partner_portal_session_secret_default',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    maxAge: 7 * 24 * 60 * 60 * 1000 // 7 days
  }
}));

// Static files with Cache-Control headers
app.use(express.static(path.join(__dirname, 'frontend'), {
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) {
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
  }
}));

// ==============================================================================
// PUBLIC WEBSITE ROUTES (MOZAREX & APPS)
// ==============================================================================

// Mozarex Homepage
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

// AivekAI Consumer App Landing Page
app.get('/aivekai', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai.html'));
});

// Puratryx App Landing Page
app.get('/puratryx', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'puratryx.html'));
});

// StopTimetryx App Landing Page
app.get('/stoptimetryx', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'stoptimetryx.html'));
});

// Privacy Policy
app.get('/policy', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'policy.html'));
});

// Account & Data Deletion Information
app.get('/data-deletion', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'data-deletion.html'));
});

// ==============================================================================
// AIVEKAI PARTNER PROGRAM & ADMIN PORTAL
// ==============================================================================

app.get('/aivekai/partners', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners.html'));
});

app.get('/aivekai/partners/apply', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-apply.html'));
});

app.get('/aivekai/partners/login', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-login.html'));
});

app.get('/aivekai/partners/dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-dashboard.html'));
});

app.get('/aivekai/partners/commissions', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-commissions.html'));
});

app.get('/aivekai/partners/payouts', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-payouts.html'));
});

app.get('/aivekai/partners/settings', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-partners-settings.html'));
});

app.get('/aivekai/admin/partners', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'aivekai-admin-partners.html'));
});

// ==============================================================================
// BACKEND API ROUTERS
// ==============================================================================

// AivekAI Partner Program API Router
const aivekaiPartnersRouter = require('./routes/aivekaiPartners');
app.use('/api/aivekai/partners', aivekaiPartnersRouter);

// PayPal Webhook Alias Route
app.post('/api/aivekai/paypal/webhook', (req, res, next) => {
  req.url = '/paypal/webhook';
  aivekaiPartnersRouter(req, res, next);
});

// AivekAI AI & Nutrition Endpoints Router
const aiRoutes = require('./routes/ai');
app.use('/api/ai', aiRoutes);

// Health Check Endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: 'Mozarex App Platform & AivekAI Backend',
    environment: process.env.NODE_ENV || 'development'
  });
});

// 404 Handler
app.use((req, res) => {
  res.status(404).sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

// Start Server
if (require.main === module) {
  server.listen(PORT, () => {
    console.log(`=======================================================`);
    console.log(`🚀 Mozarex Platform Server running on port ${PORT}`);
    console.log(`🌐 Marketing: http://localhost:${PORT}/aivekai`);
    console.log(`🤝 Partner Portal: http://localhost:${PORT}/aivekai/partners`);
    console.log(`👑 Admin Portal: http://localhost:${PORT}/aivekai/admin/partners`);
    console.log(`=======================================================`);
  });
}

module.exports = { app, server };
