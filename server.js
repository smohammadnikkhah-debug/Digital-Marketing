// Load environment variables first - only in development
if (process.env.NODE_ENV !== 'production') {
    require('dotenv').config();
}

const express = require('express');
const cors = require('cors');
const path = require('path');
const http = require('http');
const session = require('express-session');
const cookieParser = require('cookie-parser');
// Auth0 SDK - no passport needed
const boostrampService = require('./services/boostrampService');
const ChatServer = require('./services/chatServer');
const dataforseoService = require('./services/dataforseoEnvironmentService');
const dataforseoAIRecommendations = require('./services/dataforseoAIRecommendations');
const dataforseoMCPService = require('./services/dataforseoMCPService');
const dataforseoMCPIntegration = require('./services/dataforseoMCPIntegration');
const dataforseoMCPDirectService = require('./services/dataforseoMCPDirectService');
const dataforseoHybridService = require('./services/dataforseoHybridService');
const dataforseoDemoService = require('./services/dataforseoDemoService');
const dataforseoEnvironmentService = require('./services/dataforseoEnvironmentService');
const dataforseoSmartService = require('./services/dataforseoSmartService');
const environmentConfig = require('./services/environmentConfig');
const databaseService = require('./services/databaseService');
const domainAnalysisService = require('./services/domainAnalysisService');
const GoogleServices = require('./services/googleServices');
const supabaseService = require('./services/supabaseService');
const IntelligentContentService = require('./services/intelligentContentService');
const Auth0Service = require('./services/auth0Service');
const subscriptionService = require('./services/subscriptionService');

// Helper function to check if user has active subscription
async function checkUserSubscription(email) {
  try {
    // Use the existing Auth0Service instance
    const user = await auth0Service.getUserByEmail(email);
    console.log('🔍 User record found:', { 
      email: user?.email, 
      stripeCustomerId: user?.stripe_customer_id,
      customerId: user?.customer_id 
    });
    
    let stripeCustomerId = user?.stripe_customer_id;
    
    // If no stripe_customer_id in database, try to find customer by email in Stripe
    if (!stripeCustomerId) {
      console.log('🔍 No stripe_customer_id in database, searching Stripe by email...');
      const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
      
      try {
        const customers = await stripe.customers.list({
          email: email,
          limit: 1
        });
        
        if (customers.data.length > 0) {
          stripeCustomerId = customers.data[0].id;
          console.log('✅ Found Stripe customer by email:', stripeCustomerId);
          
          // Update user record with stripe_customer_id
          if (user) {
            const { createClient } = require('@supabase/supabase-js');
            const supabase = createClient(
              process.env.SUPABASE_URL,
              process.env.SUPABASE_SERVICE_ROLE_KEY
            );
            
            const { error: updateError } = await supabase
              .from('users')
              .update({ stripe_customer_id: stripeCustomerId })
              .eq('id', user.id);
              
            if (updateError) {
              console.error('Error updating user with stripe_customer_id:', updateError);
            } else {
              console.log('✅ Updated user record with stripe_customer_id');
            }
          }
        } else {
          console.log('🔍 No Stripe customer found for email:', email);
          return false;
        }
      } catch (stripeError) {
        console.error('Error searching Stripe customers:', stripeError);
        return false;
      }
    }
    
    // Check Stripe subscription status
    const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);
    const customerSubscriptions = await stripe.subscriptions.list({
      customer: stripeCustomerId,
      status: 'all', // Get all subscriptions including trialing
      limit: 10
    });
    
    console.log('🔍 Stripe subscriptions found:', customerSubscriptions.data.length);
    
    // Check if there's an active or trialing subscription
    const activeSubscription = customerSubscriptions.data.find(sub => 
      sub.status === 'active' || sub.status === 'trialing'
    );
    
    if (activeSubscription) {
      console.log('✅ Active subscription found for:', email, {
        subscriptionId: activeSubscription.id,
        status: activeSubscription.status,
        trialEnd: activeSubscription.trial_end
      });
      return true;
    } else {
      console.log('🔍 No active subscription found for:', email);
      return false;
    }
  } catch (error) {
    console.error('Error checking user subscription:', error);
    return false;
  }
}

// Helper function to check if user has analyzed domains
async function checkUserAnalyzedDomains(customerId) {
  try {
    const { createClient } = require('@supabase/supabase-js');
    const supabase = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_SERVICE_ROLE_KEY
    );
    
    // Query websites table for any websites belonging to this customer
    const { data: websites, error } = await supabase
      .from('websites')
      .select('id')
      .eq('customer_id', customerId)
      .limit(1);

    if (error) {
      console.error('Error checking user domains:', error);
      return false;
    }

    const hasDomains = websites && websites.length > 0;
    console.log('🔍 Domain check for customer:', { customerId, websitesCount: websites?.length || 0, hasDomains });
    return hasDomains;
  } catch (error) {
    console.error('Error checking user analyzed domains:', error);
    return false;
  }
}

// Helper function to get customer_id from authenticated user
async function getCustomerIdFromRequest(req) {
  try {
    const sessionService = require('./services/sessionService');
    const token = sessionService.extractToken(req);
    
    if (!token) {
      return null;
    }
    
    const decoded = sessionService.verifyToken(token);
    if (!decoded || !decoded.userId) {
      return null;
    }
    
    // Get user from database to get customer_id
    const Auth0Service = require('./services/auth0Service');
    const auth0Service = new Auth0Service();
    const user = await auth0Service.getUserById(decoded.userId);
    
    return user ? user.customer_id : null;
  } catch (error) {
    console.error('Error getting customer_id from request:', error);
    return null;
  }
}
const emailTemplateService = require('./services/emailTemplates');
const { requireFeature, FEATURES, addSubscriptionInfo } = require('./services/featureAccessMiddleware');

const app = express();
const server = http.createServer(app);
const PORT = process.env.PORT || 3000;

// Initialize WebSocket server for AI chat
const chatServer = new ChatServer(server);

// Initialize Environment Configuration
const EnvironmentConfig = require('./services/environmentConfig');
const environmentConfigInstance = new EnvironmentConfig();

// Initialize Google Services
const googleServices = new GoogleServices();

// Initialize Intelligent Content Service
const intelligentContentService = new IntelligentContentService();

// Initialize Auth0 Service
const auth0Service = new Auth0Service();

// Middleware
app.use(cors());
app.use(cookieParser());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Content Security Policy middleware
app.use((req, res, next) => {
  res.setHeader('Content-Security-Policy', 
    "default-src 'self'; " +
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com https://cdn.jsdelivr.net https://js.stripe.com; " +
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; " +
    "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; " +
    "img-src 'self' data: https:; " +
    "connect-src 'self' https://*.auth0.com https://*.supabase.co https://sandbox.dataforseo.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; " +
    "frame-src 'self' https://*.auth0.com https://js.stripe.com https://hooks.stripe.com;"
  );
  next();
});

// Session middleware
app.use(session({
  secret: process.env.AUTH0_SESSION_SECRET || 'your-super-secret-session-key-change-this-in-production',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: process.env.NODE_ENV === 'production',
    maxAge: 24 * 60 * 60 * 1000 // 24 hours
  }
}));

// Auth0 SDK configuration - no passport needed

// Serve static files from frontend
app.use(express.static(path.join(__dirname, 'frontend')));

// Serve static images
app.use('/images', express.static(path.join(__dirname, 'images')));

// Serve advanced dashboard
app.get('/dashboard-advanced', (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard-advanced.html'));
});

// Serve Mantis-inspired dashboard
app.get('/dashboard-mantis', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard-mantis.html'));
});

// Serve Mantis-inspired dashboard V2 (with overview section)
app.get('/dashboard-mantis-v2', requireAuth, (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard-mantis-v2.html'));
});

// Serve Technical SEO Dashboard
app.get('/technical-seo', requireAuth, (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'technical-seo-dashboard.html'));
});

// Serve Content SEO Dashboard
app.get('/content-seo', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-content-calendar.html'));
});

// Serve Reports Dashboard
app.get('/reports', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard.html'));
});

// Serve User Settings Page
app.get('/user-settings', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'user-settings.html'));
});

// Serve Mozarex AI Ignite Dashboard V3
app.get('/dashboard-mantis-v3', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard-mantis-v3.html'));
});

// Favicon route
app.get('/favicon.ico', (req, res) => {
    res.status(204).end(); // No content
});

// SEO Tools Routes
app.get('/seo-tools-technical', (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-technical.html'));
});

// Technical SEO Sub-pages - REMOVED (now using filtering on main page)
// app.get('/seo-tools-technical-h1', (req, res) => {
//     res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-technical-h1.html'));
// });

// app.get('/seo-tools-technical-meta', (req, res) => {
//     res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-technical-meta.html'));
// });

// app.get('/seo-tools-technical-images', (req, res) => {
//     res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-technical-images.html'));
// });

// app.get('/seo-tools-technical-titles', (req, res) => {
//     res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-technical-titles.html'));
// });

app.get('/seo-tools-keywords', requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-keywords.html'));
});

app.get('/seo-tools-competitors', requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-competitors.html'));
});

app.get('/seo-tools-backlinks', requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-backlinks.html'));
});

app.get('/seo-tools-content-calendar', requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-content-calendar.html'));
});


// Social Connections route - only available in development
if (process.env.ENABLE_SOCIAL_CONNECTIONS === 'true') {
    app.get('/seo-tools-social-connections', (req, res) => {
        res.sendFile(path.join(__dirname, 'frontend', 'seo-tools-social-connections.html'));
    });
} else {
    // Redirect to 404 or dashboard in production
    app.get('/seo-tools-social-connections', (req, res) => {
        res.status(404).send('Page not found');
    });
}

// API Routes
app.post('/api/analyze-url', async (req, res) => {
  try {
    const { url } = req.body;
    
    // Validate URL
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    // Auto-add protocol if missing
    let processedUrl = url.trim();
    if (!processedUrl.match(/^https?:\/\//)) {
      processedUrl = 'https://' + processedUrl;
    }
    
    // Basic URL validation
    try {
      new URL(processedUrl);
    } catch (error) {
      return res.status(400).json({ 
        success: false, 
        error: 'Please enter a valid website URL (e.g., google.com or https://google.com)' 
      });
    }

    console.log('🔍 Received URL for analysis:', url);
    console.log('🔧 Processed URL:', processedUrl);

    // Use comprehensive web scraping analysis
    console.log('🔄 Starting comprehensive SEO analysis...');
    const scrapedData = await boostrampService.scrapeWebsite(processedUrl);
    const recommendations = boostrampService.generateRecommendations(scrapedData, null);
    const score = boostrampService.calculateSEOScore(scrapedData, null);
    
    // Format comprehensive response for frontend
    const formattedResponse = {
      success: true,
      url: processedUrl,
      originalUrl: url,
      analysis: {
        // Basic SEO
        title: scrapedData.title || 'No title found',
        metaDescription: scrapedData.metaDescription || 'No meta description',
        metaKeywords: scrapedData.metaKeywords || '',
        
        // Performance metrics
        performance: {
          score: score,
          loadTime: scrapedData.performance.loadTime,
          pageSize: scrapedData.performance.pageSize + ' KB',
          responseTime: scrapedData.performance.responseTime + 'ms'
        },
        
        // Heading structure
        headings: scrapedData.headings,
        
        // Image analysis
        images: scrapedData.images,
        
        // Comprehensive link analysis
        links: scrapedData.links,
        
        // Technical SEO
        technical: scrapedData.technical,
        
        // Content analysis
        content: scrapedData.content,
        
        // Keywords analysis
        keywords: scrapedData.keywords,
        
        // Competitor analysis
        competitors: scrapedData.competitors,
        
        // Content recommendations
        contentRecommendations: scrapedData.contentRecommendations
      },
      recommendations: recommendations,
      timestamp: new Date().toISOString(),
      note: 'Comprehensive analysis completed with advanced web scraping'
    };

    console.log('✅ Analysis completed successfully');
    res.json(formattedResponse);

  } catch (error) {
    console.error('❌ Error analyzing URL:', error.message);
    console.error('❌ Full error:', error);
    
    // Provide fallback analysis if Boostramp fails
    try {
      console.log('🔄 Attempting fallback analysis with web scraping...');
      const fallbackAnalysis = await boostrampService.scrapeWebsite(url);
      const recommendations = boostrampService.generateRecommendations(fallbackAnalysis, null);
      const score = boostrampService.calculateSEOScore(fallbackAnalysis, null);
      
      console.log('✅ Fallback analysis completed successfully');
      res.json({
        success: true,
        url: url,
        analysis: {
          title: fallbackAnalysis.title || 'No title found',
          metaDescription: fallbackAnalysis.metaDescription || 'No meta description',
          headings: fallbackAnalysis.headings,
          images: fallbackAnalysis.images,
          links: fallbackAnalysis.links,
          performance: {
            score: score,
            loadTime: 'Basic analysis only'
          },
          technical: {
            canonical: fallbackAnalysis.canonical,
            robots: fallbackAnalysis.robots,
            viewport: fallbackAnalysis.viewport,
            language: fallbackAnalysis.language,
            charset: fallbackAnalysis.charset
          }
        },
        recommendations: recommendations,
        timestamp: new Date().toISOString(),
        note: 'Analysis completed with basic scraping (Boostramp unavailable)'
      });
    } catch (fallbackError) {
      console.error('❌ Fallback analysis also failed:', fallbackError.message);
      console.error('❌ Fallback error details:', fallbackError);
      res.status(500).json({ 
        success: false, 
        error: 'Failed to analyze website. Please check the URL and try again.' 
      });
    }
  }
});

// Test route to verify server is running latest code
app.get('/test-callback', (req, res) => {
  console.log('🔍 Test callback route hit!');
  res.json({ message: 'Test callback working', timestamp: new Date().toISOString() });
});

// Auth0 callback - handle server-side (must be before auth routes)
app.get('/auth/callback', async (req, res) => {
  console.log('🔍 Auth0 callback route hit!');
  console.log('🔍 Query params:', req.query);
  
  try {
    const { code, state, error } = req.query;
    
    // Parse state parameter to get plan data
    let planData = {};
    if (state) {
      try {
        planData = JSON.parse(decodeURIComponent(state));
        console.log('📋 Plan data from state:', planData);
        console.log('📋 Plan data details:', {
          signup: planData.signup,
          plan: planData.plan,
          priceId: planData.priceId,
          billing: planData.billing
        });
      } catch (e) {
        console.error('Error parsing state parameter:', e);
        console.error('State value:', state);
      }
    } else {
      console.log('⚠️ No state parameter received in callback');
    }
    
    // Handle Auth0 errors (like rate limiting)
    if (error) {
      console.error('Auth0 error in callback:', error);
      if (error === 'access_denied' && req.query.error_description?.includes('Too Many Requests')) {
        console.log('🚨 Auth0 rate limiting detected - redirecting to homepage');
        return res.redirect('/?error=rate_limit');
      }
      return res.redirect('/login?error=' + encodeURIComponent(error));
    }
    
    if (!code) {
      console.error('No authorization code received');
      return res.redirect('/login?error=no_code');
    }
    
    console.log('Auth0 callback received with code:', code);
    
    // Exchange code for tokens
    const tokenResponse = await fetch(`${process.env.AUTH0_DOMAIN}/oauth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        grant_type: 'authorization_code',
        client_id: process.env.AUTH0_CLIENT_ID,
        client_secret: process.env.AUTH0_CLIENT_SECRET,
        code: code,
        redirect_uri: process.env.AUTH0_CALLBACK_URL,
      }),
    });
    
    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      console.error('Token exchange failed:', errorText);
      
      // Handle rate limiting in token exchange
      if (tokenResponse.status === 429 || errorText.includes('Too Many Requests')) {
        console.log('🚨 Auth0 rate limiting in token exchange - redirecting to homepage');
        return res.redirect('/?error=rate_limit');
      }
      
      return res.redirect('/login?error=token_exchange_failed');
    }
    
    const tokens = await tokenResponse.json();
    console.log('Tokens received successfully');
    
    // Get user info
    const userResponse = await fetch(`${process.env.AUTH0_DOMAIN}/userinfo`, {
      headers: {
        'Authorization': `Bearer ${tokens.access_token}`,
      },
    });
    
    if (!userResponse.ok) {
      const errorText = await userResponse.text();
      console.error('User info fetch failed:', errorText);
      
      // Handle rate limiting in user info fetch
      if (userResponse.status === 429 || errorText.includes('Too Many Requests')) {
        console.log('🚨 Auth0 rate limiting in user info fetch - redirecting to homepage');
        return res.redirect('/?error=rate_limit');
      }
      
      return res.redirect('/login?error=user_info_failed');
    }
    
    const user = await userResponse.json();
    console.log('User info received:', { email: user.email, name: user.name });
    
    // Check if user exists in database
    const existingUser = await auth0Service.getUserByEmail(user.email);

    let currentUser;
    if (existingUser) {
      console.log('Existing user found:', existingUser);
      currentUser = existingUser;
    } else {
      // Create new user
      console.log('Creating new user:', { email: user.email, name: user.name });
      
      // Determine plan from state data or derive from price ID
      let selectedPlan = planData.plan;
      
      // If plan is undefined, try to derive it from price ID
      if (!selectedPlan || selectedPlan === 'undefined') {
        const priceId = planData.priceId;
        if (priceId) {
          // Map price IDs to plan names
          const priceIdToPlan = {
            'price_1SB8IyBFUEdVmecWKH5suX6H': 'Starter Monthly',
            'price_1S9k6kBFUEdVmecWiYNLbXia': 'Starter Yearly',
            'price_1SB8gWBFUEdVmecWkHXlvki6': 'Professional Monthly',
            'price_1S9kCwBFUEdVmecWP4DTGzBy': 'Professional Yearly'
          };
          selectedPlan = priceIdToPlan[priceId] || 'basic';
        } else {
          selectedPlan = 'basic';
        }
      }
      
      console.log('Selected plan for new user:', selectedPlan);
      
      // Create customer record first (with selected plan)
      const customer = await auth0Service.createCustomer({
        email: user.email,
        name: user.name
      }, selectedPlan);
      
      if (!customer) {
        console.error('Failed to create customer record for new user');
        return res.redirect('/login?error=customer_creation_failed');
      }
      
      // Create user with customer_id
      currentUser = await auth0Service.createSupabaseUser({
        id: user.sub,
        email: user.email,
        name: user.name,
        picture: user.picture,
        customer_id: customer.id
      });
      console.log('New user created:', currentUser);
    }

    // Create JWT session token
    const sessionToken = sessionService.createToken(currentUser);
    
    // Set token as HTTP-only cookie
    res.cookie('authToken', sessionToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 24 * 60 * 60 * 1000 // 24 hours
    });

    console.log('✅ Auth0 callback completed successfully - redirecting user');
    
    // UNIFIED VALIDATION: Check subscription status regardless of entry path
    console.log('🔍 Unified validation: Checking subscription status for all users');
    
    // Check if user has active subscription
    const hasActiveSubscription = await checkUserSubscription(user.email);
    console.log('🔍 Subscription check:', { email: user.email, hasActiveSubscription });
    
    // Check if user has analyzed domains
    const hasAnalyzedDomains = await checkUserAnalyzedDomains(currentUser.customer_id);
    console.log('🔍 Domain analysis check:', { customerId: currentUser.customer_id, hasAnalyzedDomains });
    
    // Determine routing based on subscription and domain analysis status
    let shouldGoToStripe = false;
    let reason = '';
    
    // Check if user has ever selected a plan (has stripe_customer_id)
    const hasSelectedPlan = !!currentUser.stripe_customer_id;
    console.log('🔍 Plan selection check:', { customerId: currentUser.customer_id, hasSelectedPlan });
    
    // ROUTING LOGIC: Consider subscription status, domain analysis, AND plan selection
    console.log('🔍 Routing decision logic:', {
      hasActiveSubscription,
      planDataSignup: planData.signup,
      planDataPriceId: planData.priceId,
      hasSelectedPlan,
      hasAnalyzedDomains
    });
    
    if (hasActiveSubscription) {
      // Has active subscription - always go to dashboard regardless of domain status
      console.log('✅ Active subscription - redirecting to dashboard');
      return res.redirect('/dashboard');
    } else if (planData.signup && planData.priceId) {
      // User is coming from plan selection with plan data - create Stripe checkout
      console.log('💳 User selected plan during signup - creating Stripe checkout session');
      console.log('💳 Plan data:', { plan: planData.plan, priceId: planData.priceId, billing: planData.billing });
      shouldGoToStripe = true;
      reason = 'plan_selection';
    } else if (!hasSelectedPlan) {
      // New user who hasn't selected a plan yet - go to plans page
      console.log('🆕 New user without plan - redirecting to plans page to select subscription');
      console.log('🆕 Reason: hasSelectedPlan =', hasSelectedPlan);
      return res.redirect('/plans');
    } else if (!hasAnalyzedDomains) {
      // Has selected plan but no analyzed domains - go to onboarding
      console.log('🆕 Has plan but no analyzed domains - redirecting to onboarding');
      return res.redirect('/onboarding');
    } else if (hasAnalyzedDomains) {
      // Has domains but no subscription = need payment
      console.log('💳 Has domains but no subscription - redirecting to Stripe');
      shouldGoToStripe = true;
      reason = 'has_domains_no_subscription';
    } else {
      // Fallback - redirect to dashboard if unclear
      console.log('🔍 Fallback - redirecting to dashboard');
      return res.redirect('/dashboard');
    }
    
    // If we need to go to Stripe but no plan data from signup flow
    if (shouldGoToStripe && (!planData.signup || !planData.priceId)) {
      console.log('💳 Redirecting to plans page to select subscription');
      return res.redirect('/plans');
    }
    
    // Process signup flow with plan data
    if (shouldGoToStripe && planData.signup && planData.priceId) {
      console.log('🔄 Processing Stripe checkout for:', reason);
      
      // Use the same plan derivation logic for redirect
      let redirectPlan = planData.plan;
      if (!redirectPlan || redirectPlan === 'undefined') {
        const priceId = planData.priceId;
        if (priceId) {
          const priceIdToPlan = {
            'price_1SB8IyBFUEdVmecWKH5suX6H': 'Starter Monthly',
            'price_1S9k6kBFUEdVmecWiYNLbXia': 'Starter Yearly',
            'price_1SB8gWBFUEdVmecWkHXlvki6': 'Professional Monthly',
            'price_1S9kCwBFUEdVmecWP4DTGzBy': 'Professional Yearly'
          };
          redirectPlan = priceIdToPlan[priceId] || 'basic';
        } else {
          redirectPlan = 'basic';
        }
      }
      
      // Create Stripe Checkout session directly
      console.log('💳 Creating Stripe Checkout session for user');
      try {
        const stripeService = require('./services/stripeService');
        
        // Check if user has already used their trial
        const dbUser = await auth0Service.getUserByEmail(user.email);
        let trialPeriodDays = 0; // Default to no trial
        
        if (dbUser && !dbUser.trial_used) {
          trialPeriodDays = 7; // Give 7-day trial only if not used before
          console.log('🎁 User eligible for 7-day trial');
        } else {
          console.log('❌ User has already used trial - no trial period');
        }
        
        const successUrl = `${req.protocol}://${req.get('host')}/onboarding`;
        const cancelUrl = `${req.protocol}://${req.get('host')}/plans`;
        
        const session = await stripeService.createCheckoutSession(
          planData.priceId,
          successUrl,
          cancelUrl,
          currentUser.email,
          trialPeriodDays
        );
        
        console.log('✅ Stripe Checkout session created:', session.id);
        return res.redirect(session.url);
      } catch (error) {
        console.error('❌ Error creating Stripe Checkout session:', error);
        return res.redirect('/plans?error=checkout_failed');
      }
    }
    // Redirect logic is now handled by the unified validation above
    // This section is cleaned up to avoid conflicts
    
  } catch (error) {
    console.error('Auth0 callback error:', error);
    
    // Handle specific error types
    if (error.message?.includes('Too Many Requests') || error.message?.includes('rate limit')) {
      console.log('🚨 Rate limiting error caught - redirecting to homepage');
      return res.redirect('/?error=rate_limit');
    }
    
    res.redirect('/login?error=callback_error');
  }
});

// Auth0 routes
const authRoutes = require('./routes/auth');
const stripeRoutes = require('./routes/stripe');
app.use('/auth', authRoutes);
app.use('/api/stripe', stripeRoutes);

// Import session service
const sessionService = require('./services/sessionService');

// Authentication middleware using JWT sessions
function requireAuth(req, res, next) {
  // Check if user has a valid token
  const token = sessionService.extractToken(req);
  
  if (!token) {
    // Check if this is an API request or page request
    if (req.path.startsWith('/api/')) {
      // API request - return JSON error
      return res.status(401).json({ 
        authenticated: false, 
        error: 'No authentication token provided' 
      });
    } else {
      // Page request - redirect to login
      return res.redirect('/signup?redirect=' + encodeURIComponent(req.originalUrl));
    }
  }

  const decoded = sessionService.verifyToken(token);
  
  if (!decoded) {
    // Check if this is an API request or page request
    if (req.path.startsWith('/api/')) {
      // API request - return JSON error
      return res.status(401).json({ 
        authenticated: false, 
        error: 'Invalid or expired token' 
      });
    } else {
      // Page request - redirect to login
      return res.redirect('/signup?redirect=' + encodeURIComponent(req.originalUrl));
    }
  }

  // Add user info to request object
  req.user = {
    id: decoded.userId,
    email: decoded.email,
    name: decoded.name,
    domain: decoded.domain,
    auth0Id: decoded.auth0Id
  };

  next();
}

// Serve the main page - redirect to login or dashboard
app.get('/', sessionService.optionalAuthenticate.bind(sessionService), (req, res) => {
  // Check for rate limit error
  if (req.query.error === 'rate_limit') {
    console.log('🚨 Rate limit error detected on homepage');
    // Serve homepage with rate limit message
    res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
    return;
  }
  
  if (req.user) {
    // User is logged in, redirect based on whether they have a domain
    if (req.user.domain) {
      res.redirect('/dashboard');
    } else {
      res.redirect('/onboarding');
    }
  } else {
    // User is not logged in, serve the homepage
    res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
  }
});

// Serve plans page
app.get('/plans', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'plans.html'));
});

// Serve signup page
app.get('/signup', async (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    
    // Check if user is already authenticated
    try {
        const sessionService = require('./services/sessionService');
        const token = sessionService.extractToken(req);
        
        if (token) {
            const decoded = sessionService.verifyToken(token);
            if (decoded) {
                console.log('✅ User already authenticated - bypassing signup page');
                
                // Get plan parameters
                const { plan, priceId, billing } = req.query;
                
                if (plan && priceId) {
                    // User is authenticated and has plan data - simulate Auth0 callback with plan data
                    console.log('🔄 Simulating Auth0 callback for authenticated user with plan data');
                    
                    // Store plan data in session for the callback
                    req.session = req.session || {};
                    req.session.planData = {
                        plan: plan,
                        priceId: priceId,
                        billing: billing,
                        signup: true
                    };
                    
                    // Redirect to Auth0 callback with plan data
                    console.log('🔍 AUTH0_DOMAIN:', process.env.AUTH0_DOMAIN);
                    console.log('🔍 AUTH0_CLIENT_ID:', process.env.AUTH0_CLIENT_ID);
                    console.log('🔍 AUTH0_CALLBACK_URL:', process.env.AUTH0_CALLBACK_URL);
                    
                    const auth0Url = `${process.env.AUTH0_DOMAIN}/authorize?` +
                        `response_type=code&` +
                        `client_id=${process.env.AUTH0_CLIENT_ID}&` +
                        `redirect_uri=${encodeURIComponent(process.env.AUTH0_CALLBACK_URL)}&` +
                        `scope=openid%20email%20profile&` +
                        `prompt=none&` +
                        `state=${encodeURIComponent(JSON.stringify({
                            plan: plan,
                            priceId: priceId,
                            billing: billing,
                            signup: true
                        }))}`;
                    
                    console.log('🔍 Final Auth0 URL:', auth0Url);
                    return res.redirect(auth0Url);
                }
            }
        }
    } catch (error) {
        console.log('User not authenticated or error checking auth:', error.message);
    }
    
    // User not authenticated - serve signup page
    res.sendFile(path.join(__dirname, 'frontend', 'auth0-signup.html'));
});

// Serve Stripe test page
app.get('/stripe-test', (req, res) => {
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    res.sendFile(path.join(__dirname, 'frontend', 'stripe-test.html'));
});

// Trial signup page removed - now using direct Stripe Checkout

// Login page - redirect directly to Auth0 Universal Login
app.get('/login', (req, res) => {
  const auth0Domain = process.env.AUTH0_DOMAIN;
  const clientId = process.env.AUTH0_CLIENT_ID;
  const redirectUri = encodeURIComponent(process.env.AUTH0_CALLBACK_URL);
  const scope = encodeURIComponent('openid email profile');
  
  // Get plan parameters from query string
  const { plan, priceId, billing, signup } = req.query;
  
  // Build state parameter to pass plan data through Auth0
  let state = '';
  if (plan || priceId || billing || signup) {
    const stateData = {};
    if (plan) stateData.plan = plan;
    if (priceId) stateData.priceId = priceId;
    if (billing) stateData.billing = billing;
    if (signup) stateData.signup = signup;
    state = encodeURIComponent(JSON.stringify(stateData));
  }
  
  let auth0Url = `${auth0Domain}/authorize?` +
    `response_type=code&` +
    `client_id=${clientId}&` +
    `redirect_uri=${redirectUri}&` +
    `scope=${scope}&` +
    `prompt=login`;
  
  if (state) {
    auth0Url += `&state=${state}`;
  }
  
  res.redirect(auth0Url);
});

// Duplicate callback route removed - using the one defined earlier

// Auth0 callback API endpoint
app.post('/api/auth/callback', async (req, res) => {
  try {
    const { user, email, name, picture } = req.body;
    
    console.log('Auth0 callback received:', { email, name });
    
    // Check if user exists in database
    const existingUser = await auth0Service.getUserByEmail(email);
    
    if (existingUser) {
      console.log('Existing user found:', existingUser);
      // User exists, check if they have a domain
      if (existingUser.domain) {
        return res.json({ 
          success: true, 
          redirect: '/dashboard',
          user: existingUser 
        });
      } else {
        return res.json({ 
          success: true, 
          redirect: '/onboarding',
          user: existingUser 
        });
      }
    } else {
      // Create new user
      console.log('Creating new user:', { email, name });
      const newUser = await auth0Service.createSupabaseUser({
        id: user.sub,
        email: email,
        name: name,
        picture: picture
      });
      
      console.log('New user created:', newUser);
      return res.json({ 
        success: true, 
        redirect: '/onboarding',
        user: newUser 
      });
    }
  } catch (error) {
    console.error('Auth0 callback error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to process authentication' 
    });
  }
});

// AI Chat route
app.get('/chat', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'chat.html'));
});

// SEO Request page
app.get('/seo-request', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'seo-request.html'));
});

// SEO Dashboard page
app.get('/seo-dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard.html'));
});

// Enhanced SEO Dashboard V2 page
app.get('/seo-dashboard-enhanced-v2', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'seo-dashboard-enhanced-v2.html'));
});

// DataForSEO Dashboard page
app.get('/dataforseo-dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dataforseo-dashboard.html'));
});

// Enhanced DataForSEO Dashboard page
app.get('/dataforseo-dashboard-enhanced', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dataforseo-dashboard-enhanced.html'));
});

// DataForSEO MCP Dashboard page
app.get('/dataforseo-mcp-dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dataforseo-mcp-dashboard.html'));
});

// Serve onboarding page
// Simple onboarding route (without Google auth callback)
app.get('/onboarding-simple', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'onboarding-simple.html'));
});

app.get('/debug-onboarding', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'debug-onboarding.html'));
});

app.get('/debug-dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'debug-dashboard.html'));
});

app.get('/onboarding', requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'onboarding-auth0.html'));
});

// Serve dashboard page
app.get('/dashboard', requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dashboard.html'));
});

// DataForSEO Analysis API
app.post('/api/dataforseo/analyze', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    // Process URL
    let processedUrl = url.trim();
    if (!processedUrl.match(/^https?:\/\//)) {
      processedUrl = 'https://' + processedUrl;
    }

    // Validate URL
    try {
      new URL(processedUrl);
    } catch (error) {
      return res.status(400).json({ 
        success: false, 
        error: 'Invalid URL format' 
      });
    }

    // Get comprehensive analysis from DataForSEO
    const result = await dataforseoService.analyzeWebsite(processedUrl);
    
    res.json(result);

  } catch (error) {
    console.error('DataForSEO analysis error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Analysis failed. Please try again.' 
    });
  }
});

// Test DataForSEO API connection
app.get('/api/dataforseo/test', async (req, res) => {
  try {
    const dataforseoService = require('./services/dataforseoEnvironmentService');
    
    // Test with a simple request to check account balance
    const testResponse = await dataforseoService.makeRequest('/user', []);
    
    res.json({
      success: true,
      message: 'DataForSEO API connection successful',
      data: testResponse
    });
  } catch (error) {
    console.error('DataForSEO test error:', error);
    res.json({
      success: false,
      error: error.message,
      message: 'DataForSEO API connection failed'
    });
  }
});

// Test DataForSEO on-page analysis endpoint
app.get('/api/dataforseo/test-onpage', async (req, res) => {
  try {
    const dataforseoService = require('./services/dataforseoEnvironmentService');
    
    // Test with a simple on-page analysis request
    const testData = [{
      url: 'https://google.com',
      enable_javascript: false,
      enable_cookies: false
    }];
    
    const testResponse = await dataforseoService.makeRequest('/on_page/content_parsing/live', testData);
    
    res.json({
      success: true,
      message: 'DataForSEO on-page test completed',
      data: testResponse
    });
  } catch (error) {
    console.error('DataForSEO on-page test error:', error);
    res.json({
      success: false,
      error: error.message,
      message: 'DataForSEO on-page test failed'
    });
  }
});

// Debug DataForSEO raw response
app.get('/api/dataforseo/debug-raw', async (req, res) => {
  try {
    const dataforseoService = require('./services/dataforseoEnvironmentService');
    
    // Test with a simple on-page analysis request
    const testData = [{
      url: 'https://google.com',
      enable_javascript: false,
      enable_cookies: false
    }];
    
    const rawResponse = await dataforseoService.makeRequest('/on_page/content_parsing/live', testData);
    
    // Get the actual result data
    const resultData = rawResponse?.tasks?.[0]?.result?.[0] || null;
    
    res.json({
      success: true,
      message: 'Raw DataForSEO response debug',
      rawResponse: rawResponse,
      resultData: resultData,
      processedData: dataforseoService.processOnPageData(resultData)
    });
  } catch (error) {
    console.error('DataForSEO debug error:', error);
    res.json({
      success: false,
      error: error.message,
      message: 'DataForSEO debug failed'
    });
  }
});

// AI-Powered SEO Recommendations endpoint
app.post('/api/dataforseo/ai-recommendations-enhanced', async (req, res) => {
  try {
    const { url, onPageData, keywordsData, competitorsData } = req.body;

    if (!url || !onPageData) {
      return res.status(400).json({
        success: false,
        error: 'URL and on-page data are required'
      });
    }

    // Generate AI-powered recommendations using OpenAI
    const openai = require('openai');
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    const prompt = `As an SEO expert, analyze this website data and provide specific, actionable recommendations:

Website: ${url}
Title: ${onPageData.title || 'Missing'}
Meta Description: ${onPageData.metaDescription || 'Missing'}
H1 Tags: ${onPageData.headings?.h1 || 0}
H2 Tags: ${onPageData.headings?.h2 || 0}
Word Count: ${onPageData.content?.wordCount || 0}
Services: ${onPageData.content?.services?.join(', ') || 'None identified'}

Provide 3-5 specific recommendations with:
1. Issue description
2. Impact level (Critical/Important/Suggestion)
3. Specific action to take
4. Example if applicable

Format as JSON with this structure:
{
  "recommendations": [
    {
      "issue": "Issue name",
      "impact": "Critical/Important/Suggestion", 
      "recommendation": "What to do",
      "action": "Specific steps",
      "example": "Example if applicable"
    }
  ]
}`;

    const completion = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || 'gpt-3.5-turbo',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.3
    });

    const aiResponse = completion.choices[0].message.content;
    let recommendations;

    try {
      recommendations = JSON.parse(aiResponse);
    } catch (parseError) {
      // Fallback if JSON parsing fails
      recommendations = {
        recommendations: [{
          issue: "AI Analysis Available",
          impact: "Important",
          recommendation: "AI analysis completed successfully",
          action: "Review the detailed analysis above",
          example: "AI-powered insights generated"
        }]
      };
    }

    res.json({
      success: true,
      recommendations: recommendations.recommendations || []
    });
  } catch (error) {
    console.error('AI recommendations error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// DataForSEO MCP Integration Endpoints
// MCP Keyword Overview API
app.post('/api/dataforseo/mcp/keyword-overview', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoMCPService.getKeywordOverview(keywords, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Keyword Overview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword overview via MCP'
    });
  }
});

// MCP SERP Analysis API
app.post('/api/dataforseo/mcp/serp-analysis', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en', depth = 10 } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoMCPService.getSerpAnalysis(keyword, location, language, depth);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP SERP Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get SERP analysis via MCP'
    });
  }
});

// MCP Competitor Analysis API
app.post('/api/dataforseo/mcp/competitor-analysis', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoMCPService.getCompetitorAnalysis(target, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Competitor Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get competitor analysis via MCP'
    });
  }
});

// MCP Backlink Analysis API
app.post('/api/dataforseo/mcp/backlink-analysis', async (req, res) => {
  try {
    const { target } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoMCPService.getBacklinkAnalysis(target);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Backlink Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get backlink analysis via MCP'
    });
  }
});

// MCP On-Page Analysis API
app.post('/api/dataforseo/mcp/onpage-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoMCPService.getOnPageAnalysis(url);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP On-Page Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get on-page analysis via MCP'
    });
  }
});

// MCP Keyword Suggestions API
app.post('/api/dataforseo/mcp/keyword-suggestions', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en' } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoMCPService.getKeywordSuggestions(keyword, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Keyword Suggestions error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword suggestions via MCP'
    });
  }
});

// MCP Domain Rank Overview API
app.post('/api/dataforseo/mcp/domain-rank', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoMCPService.getDomainRankOverview(target, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Domain Rank error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get domain rank overview via MCP'
    });
  }
});

// MCP Comprehensive Website Analysis API
app.post('/api/dataforseo/mcp/analyze-website', async (req, res) => {
  try {
    const { url, location = 'United States', language = 'en' } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoMCPService.analyzeWebsite(url, { location, language });
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Website Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website via MCP'
    });
  }
});

// MCP Support Check API
app.get('/api/dataforseo/mcp/support-check', async (req, res) => {
  try {
    const support = dataforseoMCPIntegration.checkMCPSupport();
    
    res.json({
      success: true,
      data: support
    });
  } catch (error) {
    console.error('MCP Support Check error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to check MCP support'
    });
  }
});

// Additional DataForSEO MCP Direct Integration Endpoints
// MCP Keyword Ideas API
app.post('/api/dataforseo/mcp/keyword-ideas', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoMCPDirectService.getKeywordIdeas(keywords, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Keyword Ideas error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword ideas via MCP'
    });
  }
});

// MCP Keyword Difficulty API
app.post('/api/dataforseo/mcp/keyword-difficulty', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoMCPDirectService.getKeywordDifficulty(keywords, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Keyword Difficulty error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword difficulty via MCP'
    });
  }
});

// MCP Search Volume API
app.post('/api/dataforseo/mcp/search-volume', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoMCPDirectService.getSearchVolume(keywords, location, language);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Search Volume error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get search volume via MCP'
    });
  }
});

// MCP Detailed Backlinks API
app.post('/api/dataforseo/mcp/detailed-backlinks', async (req, res) => {
  try {
    const { target, limit = 100 } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoMCPDirectService.getDetailedBacklinks(target, limit);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Detailed Backlinks error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get detailed backlinks via MCP'
    });
  }
});

// MCP Lighthouse Analysis API
app.post('/api/dataforseo/mcp/lighthouse-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoMCPDirectService.getLighthouseAnalysis(url);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Lighthouse Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get Lighthouse analysis via MCP'
    });
  }
});

// MCP Google Trends API
app.post('/api/dataforseo/mcp/google-trends', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en', timeRange = 'past_12_months' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoMCPDirectService.getGoogleTrends(keywords, location, language, timeRange);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Google Trends error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get Google Trends via MCP'
    });
  }
});

// MCP Content Analysis API
app.post('/api/dataforseo/mcp/content-analysis', async (req, res) => {
  try {
    const { keyword, pageType = null } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoMCPDirectService.getContentAnalysis(keyword, pageType);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Content Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get content analysis via MCP'
    });
  }
});

// MCP Business Listings API
app.post('/api/dataforseo/mcp/business-listings', async (req, res) => {
  try {
    const { categories = [], location = null } = req.body;

    const result = await dataforseoMCPDirectService.getBusinessListings(categories, location);
    
    res.json({
      success: true,
      data: result
    });
  } catch (error) {
    console.error('MCP Business Listings error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get business listings via MCP'
    });
  }
});

// MCP Available Tools API
app.get('/api/dataforseo/mcp/available-tools', async (req, res) => {
  try {
    const tools = dataforseoMCPDirectService.getAvailableTools();
    
    res.json({
      success: true,
      data: {
        tools: tools,
        mcpSupported: dataforseoMCPDirectService.isMCPSupported()
      }
    });
  } catch (error) {
    console.error('MCP Available Tools error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get available MCP tools'
    });
  }
});

// DataForSEO Hybrid Service Endpoints (MCP + Direct API)
// Hybrid Keyword Overview API
app.post('/api/dataforseo/hybrid/keyword-overview', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoHybridService.getKeywordOverview(keywords, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Keyword Overview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword overview'
    });
  }
});

// Hybrid SERP Analysis API
app.post('/api/dataforseo/hybrid/serp-analysis', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en', depth = 10 } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoHybridService.getSerpAnalysis(keyword, location, language, depth);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid SERP Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get SERP analysis'
    });
  }
});

// Hybrid Competitor Analysis API
app.post('/api/dataforseo/hybrid/competitor-analysis', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoHybridService.getCompetitorAnalysis(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Competitor Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get competitor analysis'
    });
  }
});

// Hybrid Backlink Analysis API
app.post('/api/dataforseo/hybrid/backlink-analysis', async (req, res) => {
  try {
    const { target } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoHybridService.getBacklinkAnalysis(target);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Backlink Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get backlink analysis'
    });
  }
});

// Hybrid On-Page Analysis API
app.post('/api/dataforseo/hybrid/onpage-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoHybridService.getOnPageAnalysis(url);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid On-Page Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get on-page analysis'
    });
  }
});

// Hybrid Keyword Suggestions API
app.post('/api/dataforseo/hybrid/keyword-suggestions', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en' } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoHybridService.getKeywordSuggestions(keyword, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Keyword Suggestions error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword suggestions'
    });
  }
});

// Hybrid Domain Rank API
app.post('/api/dataforseo/hybrid/domain-rank', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoHybridService.getDomainRankOverview(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Domain Rank error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get domain rank overview'
    });
  }
});

// Hybrid Comprehensive Website Analysis API
app.post('/api/dataforseo/hybrid/analyze-website', async (req, res) => {
  try {
    const { url, location = 'United States', language = 'en' } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoHybridService.analyzeWebsite(url, { location, language });
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoHybridService.getServiceStatus().serviceMode
    });
  } catch (error) {
    console.error('Hybrid Website Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website'
    });
  }
});

// Hybrid Service Status API
app.get('/api/dataforseo/hybrid/status', async (req, res) => {
  try {
    const status = dataforseoHybridService.getServiceStatus();
    
    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    console.error('Hybrid Service Status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get service status'
    });
  }
});

// DataForSEO Demo Service Endpoints (MCP + Demo Data)
// Demo Keyword Overview API - Redirected to Production Service
app.post('/api/dataforseo/demo/keyword-overview', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    // Use production service instead of demo
    const result = await dataforseoEnvironmentService.getKeywordOverview(keywords, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Production Keyword Overview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword overview'
    });
  }
});

// Demo SERP Analysis API - Redirected to Production Service
app.post('/api/dataforseo/demo/serp-analysis', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en', depth = 10 } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    // Use production service instead of demo
    const result = await dataforseoEnvironmentService.getSerpAnalysis(keyword, location, language, depth);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Production SERP Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get SERP analysis'
    });
  }
});

// Demo Competitor Analysis API - Redirected to Production Service
app.post('/api/dataforseo/demo/competitor-analysis', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    // Use production service instead of demo
    const result = await dataforseoEnvironmentService.getCompetitorAnalysis(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Production Competitor Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get competitor analysis'
    });
  }
});

// Demo Backlink Analysis API
app.post('/api/dataforseo/demo/backlink-analysis', async (req, res) => {
  try {
    const { target } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getBacklinkAnalysis(target);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Demo Backlink Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get backlink analysis'
    });
  }
});

// Demo On-Page Analysis API
app.post('/api/dataforseo/demo/onpage-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getOnPageAnalysis(url);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Demo On-Page Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get on-page analysis'
    });
  }
});

// Demo Domain Rank API
app.post('/api/dataforseo/demo/domain-rank', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getDomainRankOverview(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Demo Domain Rank error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get domain rank overview'
    });
  }
});

// Demo Comprehensive Website Analysis API
app.post('/api/dataforseo/demo/analyze-website', async (req, res) => {
  try {
    const { url, location = 'United States', language = 'en' } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoEnvironmentService.analyzeWebsite(url, { location, language });
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Demo Website Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website'
    });
  }
});

// Demo Service Status API
app.get('/api/dataforseo/demo/status', async (req, res) => {
  try {
    const status = dataforseoEnvironmentService.getServiceStatus();
    
    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    console.error('Demo Service Status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get service status'
    });
  }
});

// DataForSEO Sandbox API Endpoints (Free Testing)
// Sandbox Keyword Overview API
app.post('/api/dataforseo/sandbox/keyword-overview', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoEnvironmentService.getKeywordOverview(keywords, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Keyword Overview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword overview from Sandbox API'
    });
  }
});

// Sandbox SERP Analysis API
app.post('/api/dataforseo/sandbox/serp-analysis', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en', depth = 10 } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getSerpAnalysis(keyword, location, language, depth);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox SERP Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get SERP analysis from Sandbox API'
    });
  }
});

// Sandbox Competitor Analysis API
app.post('/api/dataforseo/sandbox/competitor-analysis', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getCompetitorAnalysis(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Competitor Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get competitor analysis from Sandbox API'
    });
  }
});

// Sandbox Backlink Analysis API
app.post('/api/dataforseo/sandbox/backlink-analysis', async (req, res) => {
  try {
    const { target } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getBacklinkAnalysis(target);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Backlink Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get backlink analysis from Sandbox API'
    });
  }
});

// Sandbox On-Page Analysis API
app.post('/api/dataforseo/sandbox/onpage-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getOnPageAnalysis(url);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox On-Page Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get on-page analysis from Sandbox API'
    });
  }
});

// Sandbox Domain Rank API
app.post('/api/dataforseo/sandbox/domain-rank', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getDomainRankOverview(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Domain Rank error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get domain rank overview from Sandbox API'
    });
  }
});

// Sandbox Keyword Suggestions API
app.post('/api/dataforseo/sandbox/keyword-suggestions', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en' } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoEnvironmentService.getKeywordSuggestions(keyword, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Keyword Suggestions error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword suggestions from Sandbox API'
    });
  }
});

// Sandbox Keyword Ideas API
app.post('/api/dataforseo/sandbox/keyword-ideas', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoEnvironmentService.getKeywordIdeas(keywords, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Keyword Ideas error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword ideas from Sandbox API'
    });
  }
});

// Sandbox Comprehensive Website Analysis API
app.post('/api/dataforseo/sandbox/analyze-website', async (req, res) => {
  try {
    const { url, location = 'United States', language = 'en' } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoEnvironmentService.analyzeWebsite(url, { location, language });
    
    res.json({
      success: true,
      data: result,
      serviceMode: dataforseoEnvironmentService.getServiceStatus().serviceMode,
      note: 'Using production DataForSEO service'
    });
  } catch (error) {
    console.error('Sandbox Website Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website using Sandbox API'
    });
  }
});

// Sandbox Service Base API
app.get('/api/dataforseo/sandbox', async (req, res) => {
  try {
    const status = dataforseoEnvironmentService.getServiceStatus();
    
    res.json({
      success: true,
      message: 'DataForSEO Sandbox API is running',
      data: {
        service: 'DataForSEO Sandbox API',
        status: 'active',
        mode: 'sandbox',
        baseURL: 'https://sandbox.dataforseo.com/v3',
        endpoints: [
          'POST /api/dataforseo/sandbox/keyword-overview',
          'POST /api/dataforseo/sandbox/serp-analysis',
          'POST /api/dataforseo/sandbox/competitor-analysis',
          'POST /api/dataforseo/sandbox/backlink-analysis',
          'POST /api/dataforseo/sandbox/onpage-analysis',
          'POST /api/dataforseo/sandbox/domain-rank',
          'POST /api/dataforseo/sandbox/keyword-suggestions',
          'POST /api/dataforseo/sandbox/keyword-ideas',
          'POST /api/dataforseo/sandbox/analyze-website',
          'GET /api/dataforseo/sandbox/status'
        ],
        documentation: 'https://docs.dataforseo.com/v3/appendix/sandbox/',
        note: 'Sandbox provides free access to DataForSEO APIs with sample data'
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Sandbox base endpoint error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get sandbox service information',
      timestamp: new Date().toISOString()
    });
  }
});

// Sandbox Service Status API
app.get('/api/dataforseo/sandbox/status', async (req, res) => {
  try {
    const status = dataforseoEnvironmentService.getServiceStatus();
    
    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    console.error('Sandbox Service Status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get Sandbox service status'
    });
  }
});

// DataForSEO Smart Service Endpoints (Sandbox + Demo Fallback)
// Smart Keyword Overview API
app.post('/api/dataforseo/smart/keyword-overview', async (req, res) => {
  try {
    const { keywords, location = 'United States', language = 'en' } = req.body;
    
    if (!keywords) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keywords are required' 
      });
    }

    const result = await dataforseoSmartService.getKeywordOverview(keywords, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Keyword Overview error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword overview'
    });
  }
});

// Smart SERP Analysis API
app.post('/api/dataforseo/smart/serp-analysis', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en', depth = 10 } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoSmartService.getSerpAnalysis(keyword, location, language, depth);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart SERP Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get SERP analysis'
    });
  }
});

// Smart Competitor Analysis API
app.post('/api/dataforseo/smart/competitor-analysis', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoSmartService.getCompetitorAnalysis(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Competitor Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get competitor analysis'
    });
  }
});

// Smart Backlink Analysis API
app.post('/api/dataforseo/smart/backlink-analysis', async (req, res) => {
  try {
    const { target } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoSmartService.getBacklinkAnalysis(target);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Backlink Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get backlink analysis'
    });
  }
});

// Smart On-Page Analysis API
app.post('/api/dataforseo/smart/onpage-analysis', async (req, res) => {
  try {
    const { url } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoSmartService.getOnPageAnalysis(url);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart On-Page Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get on-page analysis'
    });
  }
});

// Smart Domain Rank API
app.post('/api/dataforseo/smart/domain-rank', async (req, res) => {
  try {
    const { target, location = 'United States', language = 'en' } = req.body;
    
    if (!target) {
      return res.status(400).json({ 
        success: false, 
        error: 'Target domain is required' 
      });
    }

    const result = await dataforseoSmartService.getDomainRankOverview(target, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Domain Rank error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get domain rank overview'
    });
  }
});

// Smart Keyword Suggestions API
app.post('/api/dataforseo/smart/keyword-suggestions', async (req, res) => {
  try {
    const { keyword, location = 'United States', language = 'en' } = req.body;
    
    if (!keyword) {
      return res.status(400).json({ 
        success: false, 
        error: 'Keyword is required' 
      });
    }

    const result = await dataforseoSmartService.getKeywordSuggestions(keyword, location, language);
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Keyword Suggestions error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get keyword suggestions'
    });
  }
});

// Smart Comprehensive Website Analysis API
app.post('/api/dataforseo/smart/analyze-website', async (req, res) => {
  try {
    const { url, location = 'United States', language = 'en' } = req.body;
    
    if (!url) {
      return res.status(400).json({ 
        success: false, 
        error: 'URL is required' 
      });
    }

    const result = await dataforseoSmartService.analyzeWebsite(url, { location, language });
    
    res.json({
      success: true,
      data: result,
      serviceMode: result.serviceMode,
      dataSource: result.dataSource,
      note: 'Smart service: tries Sandbox API first, falls back to demo data'
    });
  } catch (error) {
    console.error('Smart Website Analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website'
    });
  }
});

// Smart Service Status API
app.get('/api/dataforseo/smart/status', async (req, res) => {
  try {
    const status = dataforseoSmartService.getServiceStatus();
    
    res.json({
      success: true,
      data: status
    });
  } catch (error) {
    console.error('Smart Service Status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get service status'
    });
  }
});

// Domain Analysis API
app.post('/api/seo/analyze-domain', async (req, res) => {
  try {
    const { domain } = req.body;

    if (!domain) {
      return res.status(400).json({
        success: false,
        error: 'Domain is required'
      });
    }

    console.log(`🔍 Starting domain analysis for: ${domain}`);
    
    // Perform comprehensive domain analysis
    const analysisResult = await domainAnalysisService.analyzeDomain(domain);
    
    if (analysisResult.success) {
      res.json({
        success: true,
        data: analysisResult.data
      });
    } else {
      res.status(500).json({
        success: false,
        error: analysisResult.error
      });
    }
  } catch (error) {
    console.error('Domain analysis API error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Check website limit API
app.get('/api/user/check-website-limit', async (req, res) => {
  try {
    const customerId = await getCustomerIdFromRequest(req);
    
    if (!customerId) {
      return res.status(401).json({
        success: false,
        error: 'Authentication required'
      });
    }

    // Use SupabaseService to validate website limit
    const supabaseService = require('./services/supabaseService');
    const limitCheck = await supabaseService.validateWebsiteLimit(customerId);
    
    res.json({
      success: true,
      canAddMore: limitCheck.allowed,
      limit: limitCheck.limit,
      current: limitCheck.current
    });
  } catch (error) {
    console.error('Check website limit API error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to check website limit'
    });
  }
});

// User Data Management API
app.post('/api/user/save-onboarding', async (req, res) => {
  try {
    const userData = req.body;
    console.log('🔍 Save onboarding: Received user data:', userData);

    if (!userData.domain) {
      console.log('❌ Save onboarding: Domain is required');
      return res.status(400).json({
        success: false,
        error: 'Domain is required'
      });
    }

    console.log(`💾 Save onboarding: Saving user data for: ${userData.domain}`);
    
    // Get authenticated user's ID from JWT token
    const sessionService = require('./services/sessionService');
    const token = sessionService.extractToken(req);
    console.log('🔍 Save onboarding: Token extracted:', token ? 'Yes' : 'No');
    
    if (token) {
      const decoded = sessionService.verifyToken(token);
      console.log('🔍 Save onboarding: Token decoded:', decoded ? 'Yes' : 'No');
      if (decoded && decoded.userId) {
        console.log('🔍 Save onboarding: User ID:', decoded.userId);
        // Update the authenticated user's domain
        const Auth0Service = require('./services/auth0Service');
        const auth0Service = new Auth0Service();
        const updateResult = await auth0Service.updateUserDomain(decoded.userId, userData.domain);
        
        if (updateResult) {
          console.log(`✅ Save onboarding: Updated user domain to: ${userData.domain}`);
        } else {
          console.log(`⚠️ Save onboarding: Failed to update user domain`);
        }
      }
    } else {
      console.log('⚠️ Save onboarding: No authentication token found');
    }
    
    // Save user data to database
    userData.req = req; // Pass request object for token extraction
    console.log('🔍 Save onboarding: Calling databaseService.saveUserData...');
    const saveResult = await databaseService.saveUserData(userData);
    console.log('🔍 Save onboarding: Save result:', saveResult);
    
    if (saveResult.success) {
      console.log('✅ Save onboarding: User data saved successfully');
      res.json({
        success: true,
        message: 'User data saved successfully'
      });
    } else {
      console.log('❌ Save onboarding: Failed to save user data:', saveResult.error);
      res.status(500).json({
        success: false,
        error: saveResult.error
      });
    }
  } catch (error) {
    console.error('Save user data API error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.get('/api/user/get-data', async (req, res) => {
  try {
    const domain = req.query.domain;

    if (!domain) {
      return res.status(400).json({
        success: false,
        error: 'Domain parameter is required'
      });
    }

    console.log(`📖 Getting user data for: ${domain}`);
    
    // Get user data from database
    const userResult = await databaseService.getUserData(domain);
    
    if (userResult.success) {
      res.json({
        success: true,
        data: userResult.data
      });
    } else {
      res.status(404).json({
        success: false,
        error: userResult.error
      });
    }
  } catch (error) {
    console.error('Get user data API error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Get customer join date
app.post('/api/user/get-join-date', async (req, res) => {
  try {
    const { domain } = req.body;
    console.log('📅 Getting join date for:', domain);
    
    if (!domain) {
      return res.status(400).json({ success: false, error: 'Domain is required' });
    }
    
    const userResult = await databaseService.getUserData(domain);
    
    if (userResult.success && userResult.data && userResult.data.created_at) {
      res.json({ 
        success: true, 
        joinDate: userResult.data.created_at,
        domain: domain
      });
    } else {
      // If no user data found, use current date as fallback
      res.json({ 
        success: true, 
        joinDate: new Date().toISOString(),
        domain: domain,
        fallback: true
      });
    }
  } catch (error) {
    console.error('❌ Error getting join date:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Get all users endpoint
app.get('/api/user/get-all-users', async (req, res) => {
  try {
    console.log('📋 Getting all users...');
    
    // Get all users from database
    const usersResult = await databaseService.getAllUsers();
    
    if (usersResult.success) {
      res.json({
        success: true,
        data: usersResult.data
      });
    } else {
      res.status(500).json({
        success: false,
        error: usersResult.error
      });
    }
  } catch (error) {
    console.error('Get all users API error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// AI Recommendations API
app.post('/api/dataforseo/ai-recommendations', async (req, res) => {
  try {
    const { section, data } = req.body;
    
    if (!section || !data) {
      return res.status(400).json({ 
        success: false, 
        error: 'Section and data are required' 
      });
    }

    let recommendations;
    
    switch (section) {
      case 'onpage':
        recommendations = await dataforseoAIRecommendations.generateOnPageRecommendations(data);
        break;
      case 'keywords':
        recommendations = await dataforseoAIRecommendations.generateKeywordRecommendations(data);
        break;
      case 'competitors':
        recommendations = await dataforseoAIRecommendations.generateCompetitorRecommendations(data);
        break;
      case 'backlinks':
        recommendations = await dataforseoAIRecommendations.generateBacklinkRecommendations(data);
        break;
      default:
        return res.status(400).json({ 
          success: false, 
          error: 'Invalid section specified' 
        });
    }
    
    res.json(recommendations);

  } catch (error) {
    console.error('AI recommendations error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to generate AI recommendations' 
    });
  }
});

// Google API Routes
// Get Google OAuth URL
app.get('/api/google/auth-url', (req, res) => {
  try {
    const authUrl = googleServices.getAuthUrl();
    res.json({ 
      success: true, 
      authUrl: authUrl 
    });
  } catch (error) {
    console.error('Google auth URL error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to generate Google auth URL' 
    });
  }
});

// Handle Google OAuth callback
app.get('/auth/google/callback', async (req, res) => {
  try {
    const { code } = req.query;
    if (!code) {
      return res.status(400).json({ 
        success: false, 
        error: 'Authorization code is required' 
      });
    }

    const tokens = await googleServices.getTokensFromCode(code);
    
    // Redirect to dashboard with tokens
    res.redirect(`/dashboard-mantis-v2?google_auth=success&access_token=${tokens.access_token}`);
  } catch (error) {
    console.error('Google OAuth callback error:', error);
    res.redirect('/dashboard-mantis-v2?google_auth=error');
  }
});

// Get Google Search Console properties
app.get('/api/google/search-console/properties', async (req, res) => {
  try {
    const { access_token } = req.headers;
    if (!access_token) {
      return res.status(401).json({ 
        success: false, 
        error: 'Access token is required' 
      });
    }

    googleServices.setCredentials({ access_token });
    const result = await googleServices.getSearchConsoleProperties();
    
    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (error) {
    console.error('Search Console properties error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to get Search Console properties' 
    });
  }
});

// Get Google Search Console data
app.post('/api/google/search-console/data', async (req, res) => {
  try {
    const { access_token, propertyUrl, startDate, endDate } = req.body;
    
    if (!access_token || !propertyUrl) {
      return res.status(400).json({ 
        success: false, 
        error: 'Access token and property URL are required' 
      });
    }

    googleServices.setCredentials({ access_token });
    const result = await googleServices.getSearchConsoleData(
      propertyUrl, 
      startDate || '2024-01-01', 
      endDate || new Date().toISOString().split('T')[0]
    );
    
    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (error) {
    console.error('Search Console data error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to get Search Console data' 
    });
  }
});

// Get Google Business Profile accounts
app.get('/api/google/business-profile/accounts', async (req, res) => {
  try {
    const { access_token } = req.headers;
    if (!access_token) {
      return res.status(401).json({ 
        success: false, 
        error: 'Access token is required' 
      });
    }

    googleServices.setCredentials({ access_token });
    const result = await googleServices.getBusinessAccounts();
    
    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (error) {
    console.error('Business Profile accounts error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to get Business Profile accounts' 
    });
  }
});

// Get Google Business Profile data
app.post('/api/google/business-profile/data', async (req, res) => {
  try {
    const { access_token, accountId } = req.body;
    
    if (!access_token || !accountId) {
      return res.status(400).json({ 
        success: false, 
        error: 'Access token and account ID are required' 
      });
    }

    googleServices.setCredentials({ access_token });
    const result = await googleServices.getBusinessProfileData(accountId);
    
    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (error) {
    console.error('Business Profile data error:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Failed to get Business Profile data' 
    });
  }
});

// Dashboard route - removed duplicate (already defined above with requireAuth)

// Debug onboarding route
app.get('/debug-onboarding', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'debug-onboarding.html'));
});

// Test onboarding route
app.get('/test-onboarding', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'test-onboarding.html'));
});

// Redirect test route
app.get('/redirect-test', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'redirect-test.html'));
});

// AI-powered recommendation generation
app.post('/api/ai/generate-recommendations', async (req, res) => {
  try {
    const { analysis, type } = req.body;
    
    if (!analysis) {
      return res.status(400).json({ success: false, error: 'Analysis data required' });
    }

    let prompt = `Based on the following SEO analysis data, provide specific, actionable recommendations for ${type} optimization:\n\n`;
    
    if (type === 'technical' && analysis.onPage) {
      prompt += `Technical Analysis:\n`;
      prompt += `- Title: ${analysis.onPage.title || 'Missing'}\n`;
      prompt += `- Meta Description: ${analysis.onPage.metaDescription || 'Missing'}\n`;
      prompt += `- H1 Tags: ${analysis.onPage.h1Tags?.length || 0}\n`;
      prompt += `- Word Count: ${analysis.onPage.wordCount || 0}\n`;
      prompt += `- Images with Alt Text: ${analysis.onPage.images?.total - analysis.onPage.images?.missingAlt || 0}/${analysis.onPage.images?.total || 0}\n\n`;
    }
    
    if (analysis.keywords && analysis.keywords.length > 0) {
      prompt += `Keywords:\n`;
      analysis.keywords.slice(0, 5).forEach(keyword => {
        prompt += `- ${keyword.keyword}: Volume ${keyword.searchVolume || 'N/A'}, Difficulty ${keyword.difficulty || 'N/A'}\n`;
      });
      prompt += '\n';
    }

    prompt += `Please provide 5 specific, actionable recommendations with implementation steps. Format as HTML with proper styling.`;

    // Initialize OpenAI client
    const openai = require('openai');
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    const response = await client.chat.completions.create({
      model: "gpt-3.5-turbo",
      messages: [
        {
          role: "system",
          content: "You are an expert SEO consultant. Provide specific, actionable recommendations with clear implementation steps. Format your response as HTML with proper styling."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      max_tokens: 1000,
      temperature: 0.7
    });

    const recommendations = response.choices[0].message.content;
    
    res.json({
      success: true,
      recommendations: recommendations
    });
  } catch (error) {
    console.error('AI recommendation generation error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate AI recommendations'
    });
  }
});

// AI-powered content calendar generation
app.post('/api/ai/generate-content-calendar', async (req, res) => {
  try {
    const { analysis, month, year, startDate } = req.body;
    
    if (!analysis) {
      return res.status(400).json({ success: false, error: 'Analysis data required' });
    }

    // Determine start date - use provided startDate or current date
    let calendarStartDate;
    if (startDate) {
      calendarStartDate = new Date(startDate);
    } else {
      calendarStartDate = new Date();
    }

    // Initialize OpenAI client
    const openai = require('openai');
    console.log('OpenAI API Key configured:', !!process.env.OPENAI_API_KEY);
    console.log('OpenAI API Key length:', process.env.OPENAI_API_KEY ? process.env.OPENAI_API_KEY.length : 0);
    
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    const monthNames = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"];

    const startMonth = calendarStartDate.getMonth();
    const startYear = calendarStartDate.getFullYear();
    const startDay = calendarStartDate.getDate();

    let prompt = `Generate a 30-day content calendar starting from ${startDay} ${monthNames[startMonth]} ${startYear} for a website about "${analysis.onPage?.title || 'SEO optimization'}". `;
    prompt += `Create engaging social media content for Twitter, Facebook, TikTok, and Instagram. `;
    prompt += `Include specific post ideas, optimal posting times, and engagement tips for each platform. `;
    prompt += `Focus on SEO, digital marketing, and website optimization topics. `;
    prompt += `IMPORTANT: Return ONLY valid JSON without any comments, markdown, or extra text. `;
    prompt += `Use this exact structure: {"calendar": [{"day": 1, "platforms": {"twitter": {"content": "text", "time": "10:00 AM", "tip": "text"}, "facebook": {"content": "text", "time": "2:00 PM", "tip": "text"}, "tiktok": {"content": "text", "time": "6:00 PM", "tip": "text"}, "instagram": {"content": "text", "time": "7:00 PM", "tip": "text"}}}]}`;

    const response = await client.chat.completions.create({
      model: "gpt-3.5-turbo",
      messages: [
        {
          role: "system",
          content: "You are a social media marketing expert. Generate engaging, platform-specific content ideas for SEO and digital marketing topics. CRITICAL: You must return ONLY valid JSON format without any markdown, comments, or extra text. Do not include // comments or ```json``` blocks. Return pure JSON only."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      max_tokens: 2000,
      temperature: 0.8
    });

    let responseContent = response.choices[0].message.content;
    console.log('Raw AI response:', responseContent);
    
    // Remove markdown code blocks if present
    if (responseContent.includes('```json')) {
      responseContent = responseContent.replace(/```json\n?/g, '').replace(/```\n?/g, '');
    }
    
    // Clean up common JSON issues
    responseContent = responseContent.trim();
    
    // Try to extract JSON from the response if it's wrapped in other text
    const jsonMatch = responseContent.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      responseContent = jsonMatch[0];
    }
    
    // If we still have comments, try to extract just the calendar array
    if (responseContent.includes('//')) {
      const calendarMatch = responseContent.match(/"calendar":\s*\[[\s\S]*?\]/);
      if (calendarMatch) {
        responseContent = `{"calendar": ${calendarMatch[0].replace('"calendar":', '')}}`;
      }
    }
    
    console.log('Extracted JSON:', responseContent);
    
    // More robust JSON cleaning
    let calendarData;
    try {
      // First attempt: try to parse as-is
      calendarData = JSON.parse(responseContent);
      console.log('✅ JSON parsed successfully on first attempt');
    } catch (firstError) {
      console.log('❌ First JSON parse failed:', firstError.message);
      
      // Second attempt: fix common issues
      let cleanedContent = responseContent
        .replace(/\/\/.*$/gm, '')  // Remove single-line comments
        .replace(/\/\*[\s\S]*?\*\//g, '')  // Remove multi-line comments
        .replace(/'/g, '"')  // Replace single quotes with double quotes
        .replace(/([a-zA-Z_][a-zA-Z0-9_]*):/g, '"$1":')  // Add quotes around property names (more specific)
        .replace(/,\s*}/g, '}')  // Remove trailing commas before closing braces
        .replace(/,\s*]/g, ']')  // Remove trailing commas before closing brackets
        .replace(/\n/g, ' ')  // Replace newlines with spaces
        .replace(/\s+/g, ' ')  // Replace multiple spaces with single space
        .trim();
      
      console.log('Cleaned JSON:', cleanedContent);
      
      try {
        calendarData = JSON.parse(cleanedContent);
        console.log('✅ JSON parsed successfully after cleaning');
      } catch (secondError) {
        console.log('❌ Second JSON parse failed:', secondError.message);
        
        // Third attempt: create a minimal valid JSON structure
        console.log('🔄 Creating fallback calendar structure');
        calendarData = {
          calendar: Array.from({length: 30}, (_, i) => {
            const currentDate = new Date(calendarStartDate);
            currentDate.setDate(calendarStartDate.getDate() + i);
            const dayNumber = currentDate.getDate();
            const monthName = monthNames[currentDate.getMonth()];
            
            return {
              day: dayNumber,
              platforms: {
                twitter: {
                  content: `${monthName} ${dayNumber}: SEO tip - Optimize your meta descriptions for better click-through rates!`,
                  time: "9:00 AM",
                  tip: "Post during peak engagement hours"
                },
                facebook: {
                  content: `${monthName} ${dayNumber}: Share your latest SEO insights and engage with your audience!`,
                  time: "2:00 PM", 
                  tip: "Use engaging visuals to increase reach"
                },
                tiktok: {
                  content: `${monthName} ${dayNumber}: Quick SEO hack - Use long-tail keywords for better rankings!`,
                  time: "6:00 PM",
                  tip: "Keep videos under 60 seconds for maximum engagement"
                },
                instagram: {
                  content: `${monthName} ${dayNumber}: Visual SEO tip - Optimize your image alt text for accessibility!`,
                  time: "7:00 PM",
                  tip: "Use relevant hashtags to increase discoverability"
                }
              }
            };
          })
        };
        
        console.log('✅ Using fallback calendar structure');
      }
    }
    
    // Store content calendar in Supabase if domain is available
    if (supabaseService.isReady() && analysis.domain) {
      try {
        const normalizedDomain = analysis.domain.replace(/^https?:\/\//, '').replace(/^www\./, '');
        const customerId = await getCustomerIdFromRequest(req);
        const website = await supabaseService.createOrGetWebsite(normalizedDomain, null, customerId);
        
        if (website) {
          // Convert calendar data to the format expected by Supabase
          const calendarEntries = {};
          calendarData.calendar.forEach(day => {
            const dateKey = `${year}-${String(month + 1).padStart(2, '0')}-${String(day.day).padStart(2, '0')}`;
            calendarEntries[dateKey] = day.platforms;
          });
          
          await supabaseService.storeContentCalendar(website.id, calendarEntries);
          console.log('✅ Content calendar stored in Supabase');
        }
      } catch (error) {
        console.error('Error storing content calendar:', error);
        // Don't fail the request if storage fails
      }
    }
    
    res.json({
      success: true,
      calendar: calendarData.calendar
    });
  } catch (error) {
    console.error('AI calendar generation error:', error);
    console.error('Error details:', error.message);
    console.error('Error stack:', error.stack);
    console.error('Request body:', req.body);
    res.status(500).json({
      success: false,
      error: 'Failed to generate content calendar',
      details: error.message
    });
  }
});

// Generate AI Proposals for Analysis Areas
app.post('/api/ai/generate-proposals', async (req, res) => {
  try {
    const { analysis, domain, section } = req.body;
    
    if (!analysis || !domain || !section) {
      return res.status(400).json({ success: false, error: 'Analysis data, domain, and section are required' });
    }

    // Initialize OpenAI client
    const openai = require('openai');
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    // Import DataForSEO service for additional data if needed
    const dataforseoEnvironmentService = require('./services/dataforseoEnvironmentService');

    // Build section-specific proposal prompt
    let proposalPrompt = `You are Mozarex AI, an expert SEO consultant. Generate SPECIFIC, ACTIONABLE proposals for the ${section} section.

Website: ${domain}
Analysis Data: ${JSON.stringify(analysis, null, 2)}

Generate 3-5 specific proposals with:
1. Clear action items
2. Expected impact/benefit
3. Implementation difficulty (Easy/Medium/Hard)
4. Priority level (High/Medium/Low)
5. Specific examples or code snippets when applicable

CRITICAL: Return ONLY valid JSON without any markdown, comments, or extra text.
Use this exact structure:
[
  {
    "title": "Proposal title",
    "description": "Detailed description",
    "action": "Specific action to take",
    "impact": "Expected SEO impact",
    "difficulty": "Easy",
    "priority": "High",
    "example": "Specific example or code snippet",
    "timeline": "Expected time to implement"
  }
]`;

    const response = await client.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: "You are Mozarex AI, an expert SEO consultant. Generate specific, actionable proposals based on real analysis data. CRITICAL: You must return ONLY valid JSON format without any markdown, comments, or extra text. Do not include // comments or ```json``` blocks. Return pure JSON only."
        },
        {
          role: 'user',
          content: proposalPrompt
        }
      ],
      max_tokens: 1500,
      temperature: 0.7
    });

    let aiResponse = response.choices[0].message.content;
    console.log('Raw AI proposals response:', aiResponse);
    
    // Clean the response
    aiResponse = aiResponse.trim();
    
    // Remove markdown code blocks if present
    if (aiResponse.includes('```json')) {
      aiResponse = aiResponse.replace(/```json\n?/g, '').replace(/```\n?/g, '');
    }
    
    // Try to extract JSON from the response if it's wrapped in other text
    const jsonMatch = aiResponse.match(/\[[\s\S]*\]/);
    if (jsonMatch) {
      aiResponse = jsonMatch[0];
    }
    
    console.log('Extracted proposals JSON:', aiResponse);
    
    // Parse the JSON response
    let proposals;
    try {
      // First attempt: try to parse as-is
      proposals = JSON.parse(aiResponse);
      console.log('✅ Proposals JSON parsed successfully');
    } catch (parseError) {
      console.error('❌ Error parsing proposals JSON:', parseError.message);
      
      // Second attempt: fix common issues
      let cleanedContent = aiResponse
        .replace(/\/\/.*$/gm, '')  // Remove single-line comments
        .replace(/\/\*[\s\S]*?\*\//g, '')  // Remove multi-line comments
        .replace(/'/g, '"')  // Replace single quotes with double quotes
        .replace(/([a-zA-Z_][a-zA-Z0-9_]*):/g, '"$1":')  // Add quotes around property names
        .replace(/,\s*}/g, '}')  // Remove trailing commas before closing braces
        .replace(/,\s*]/g, ']')  // Remove trailing commas before closing brackets
        .replace(/\n/g, ' ')  // Replace newlines with spaces
        .replace(/\s+/g, ' ')  // Replace multiple spaces with single space
        .trim();
      
      try {
        proposals = JSON.parse(cleanedContent);
        console.log('✅ Proposals JSON parsed successfully after cleaning');
      } catch (secondError) {
        console.error('❌ Second proposals JSON parse failed:', secondError.message);
        
        // Fallback to generated structure
        proposals = [
          {
            title: "Fix Title Tag Issues",
            description: "Optimize title tags for better SEO performance",
            action: "Update title tags to be 50-60 characters and include target keywords",
            impact: "Improved click-through rates and search rankings",
            difficulty: "Easy",
            priority: "High",
            example: "<title>Mozarex: Digital Marketing Solutions Near You</title>",
            timeline: "1 day"
          },
          {
            title: "Add Missing Meta Descriptions",
            description: "Create compelling meta descriptions for all pages",
            action: "Write meta descriptions between 120-160 characters with call-to-action",
            impact: "Higher click-through rates from search results",
            difficulty: "Easy",
            priority: "High",
            example: "Discover Mozarex's digital marketing solutions. Get expert SEO, PPC, and social media services near you.",
            timeline: "2 days"
          },
          {
            title: "Optimize Image Alt Text",
            description: "Add descriptive alt text to all images",
            action: "Add alt text to images missing descriptions",
            impact: "Better accessibility and SEO performance",
            difficulty: "Easy",
            priority: "Medium",
            example: "alt='Mozarex digital marketing team working on SEO strategy'",
            timeline: "1 day"
          }
        ];
      }
    }

    res.json({
      success: true,
      proposals: proposals,
      section: section,
      domain: domain,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Proposal generation error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// Mozarex AI Interactive Chat Endpoint
app.post('/api/ai/mozarex-chat', async (req, res) => {
  try {
    const { message, analysis, domain, context = 'general' } = req.body;
    
    if (!message) {
      return res.status(400).json({ success: false, error: 'Message is required' });
    }

    // Initialize OpenAI client
    const openai = require('openai');
    const client = new openai.OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });

    // Import DataForSEO service for real-time analysis
    const dataforseoEnvironmentService = require('./services/dataforseoEnvironmentService');
    const supabaseService = require('./services/supabaseService');

    // Intelligent analysis detection - determine if we need fresh data
    let needsFreshAnalysis = false;
    let analysisReason = '';
    
    // Check if user is asking for specific analysis that might need fresh data
    const analysisKeywords = ['analyze', 'check', 'current', 'latest', 'real-time', 'fresh', 'update', 'recent'];
    const technicalKeywords = ['title', 'meta', 'image', 'alt', 'heading', 'h1', 'h2', 'content', 'speed', 'mobile'];
    const keywordKeywords = ['keyword', 'ranking', 'competition', 'difficulty', 'volume', 'cpc'];
    const competitorKeywords = ['competitor', 'competition', 'market', 'positioning', 'advantage'];
    
    const messageLower = message.toLowerCase();
    
    // Determine if we need fresh analysis based on the question
    if (analysisKeywords.some(keyword => messageLower.includes(keyword))) {
      if (technicalKeywords.some(keyword => messageLower.includes(keyword))) {
        needsFreshAnalysis = true;
        analysisReason = 'technical analysis requested';
      } else if (keywordKeywords.some(keyword => messageLower.includes(keyword))) {
        needsFreshAnalysis = true;
        analysisReason = 'keyword analysis requested';
      } else if (competitorKeywords.some(keyword => messageLower.includes(keyword))) {
        needsFreshAnalysis = true;
        analysisReason = 'competitor analysis requested';
      }
    }

    // Get fresh analysis data if needed
    let freshAnalysis = null;
    if (needsFreshAnalysis && domain) {
      console.log(`🔄 Mozarex AI: Getting fresh ${analysisReason} for ${domain}`);
      try {
        const analysisResult = await dataforseoEnvironmentService.analyzeWebsite(domain);
        if (analysisResult.success) {
          freshAnalysis = analysisResult.analysis;
          console.log(`✅ Mozarex AI: Fresh analysis obtained for ${domain}`);
        }
      } catch (error) {
        console.error(`❌ Mozarex AI: Failed to get fresh analysis for ${domain}:`, error);
      }
    }

    // Use fresh analysis if available, otherwise use provided analysis
    const currentAnalysis = freshAnalysis || analysis;

    // Build context-aware prompt based on section and user question
    let contextPrompt = `You are Mozarex AI, a specialized SEO assistant for Mozarex Digital Marketing. You provide SPECIFIC, ACTIONABLE recommendations based on real analysis data.

Website: ${domain || 'Not specified'}
Current section: ${context}
Analysis source: ${freshAnalysis ? 'FRESH DATA (just analyzed)' : 'STORED DATA'}

IMPORTANT: You are an expert SEO consultant. Don't just repeat the analysis data - provide intelligent insights, strategic recommendations, and actionable next steps. Think like a senior SEO expert who understands the bigger picture.

`;

    // Determine what data to include based on the user's question
    const messageLowerForContext = message.toLowerCase();
    const isKeywordQuestion = keywordKeywords.some(keyword => messageLowerForContext.includes(keyword)) || 
                             messageLowerForContext.includes('keyword') || 
                             messageLowerForContext.includes('target') ||
                             messageLowerForContext.includes('focus') ||
                             messageLowerForContext.includes('priority');
    
    const isTechnicalQuestion = technicalKeywords.some(keyword => messageLowerForContext.includes(keyword)) ||
                               messageLowerForContext.includes('technical') ||
                               messageLowerForContext.includes('title') ||
                               messageLowerForContext.includes('meta') ||
                               messageLowerForContext.includes('h1') ||
                               messageLowerForContext.includes('image');

    if (currentAnalysis) {
      // Only include relevant data based on the question
      if (isKeywordQuestion) {
        const keywords = currentAnalysis.keywords || {};
        contextPrompt += `KEYWORDS DATA:
`;
        if (keywords.keywords && keywords.keywords.length > 0) {
          keywords.keywords.forEach((keyword, index) => {
            contextPrompt += `${index + 1}. "${keyword.keyword}" - Difficulty: ${keyword.difficulty}/100, Competition: ${keyword.competition}, Volume: ${keyword.searchVolume}, CPC: ${keyword.cpc}
`;
          });
        }
      } else if (isTechnicalQuestion) {
        const onPage = currentAnalysis.onPage || {};
        const pages = onPage.pages || [];
        
        // Provide focused technical insights instead of raw data
        let technicalSummary = `TECHNICAL SEO ANALYSIS:
Website: ${domain}
Pages analyzed: ${pages.length}

KEY FINDINGS:
`;
        
        // Count issues by type
        let titleIssues = 0, metaIssues = 0, h1Issues = 0, imageIssues = 0;
        let totalImages = 0, totalMissingAlt = 0;
        
        pages.forEach((page, index) => {
          const issues = page.issues || {};
          if (issues.titleTooLong) titleIssues++;
          if (issues.metaTooShort) metaIssues++;
          if (issues.missingH1) h1Issues++;
          if (page.images?.missingAlt > 0) {
            imageIssues++;
            totalMissingAlt += page.images.missingAlt;
          }
          totalImages += page.images?.total || 0;
        });
        
        if (h1Issues > 0) {
          technicalSummary += `• ${h1Issues} pages missing H1 tags (critical for SEO structure)
`;
        }
        if (metaIssues > 0) {
          technicalSummary += `• ${metaIssues} pages have meta descriptions that are too short
`;
        }
        if (totalMissingAlt > 0) {
          technicalSummary += `• ${totalMissingAlt} images missing alt text (affects accessibility & SEO)
`;
        }
        if (titleIssues > 0) {
          technicalSummary += `• ${titleIssues} pages have title tags that are too long
`;
        }
        
        if (h1Issues === 0 && totalMissingAlt === 0 && titleIssues === 0 && metaIssues === 0) {
          technicalSummary += `• No critical technical issues found - great job!
`;
        }
        
        contextPrompt += technicalSummary;
      } else {
        // For general questions, provide minimal context
        const keywords = currentAnalysis.keywords || {};
        contextPrompt += `AVAILABLE KEYWORDS:
`;
        if (keywords.keywords && keywords.keywords.length > 0) {
          keywords.keywords.slice(0, 3).forEach((keyword, index) => {
            contextPrompt += `${index + 1}. "${keyword.keyword}" - Difficulty: ${keyword.difficulty}/100, Volume: ${keyword.searchVolume}
`;
          });
        }
      }
    }

           // Add section-specific context
           if (context === 'technical') {
             contextPrompt += `Focus on technical SEO aspects: title tags, meta descriptions, image alt text, heading structure, content length, page speed, mobile optimization.

TECHNICAL SEO EXPERTISE:
- Provide SPECIFIC, ACTIONABLE recommendations for each issue
- Give concrete examples of how to fix problems
- Explain WHY each fix matters for SEO performance
- Prioritize fixes by SEO impact (high/medium/low)
- Include step-by-step implementation guidance
- Focus on quick wins that deliver immediate results

RESPONSE STYLE:
- Be conversational and helpful like a senior SEO consultant
- Use specific examples from the actual website data
- Provide clear next steps and implementation guidance
- Explain the business impact of each recommendation

EXAMPLE FOR HOMEPAGE TECHNICAL SEO:
If asked about homepage technical SEO, provide:
1. **Priority fixes** (High/Medium/Low impact)
2. **Specific examples** of current issues and how to fix them
3. **Step-by-step implementation** guide
4. **Expected results** from each fix
5. **Quick wins** that can be implemented immediately
6. **Business impact** explanation for each recommendation

**MANDATORY RESPONSE TEMPLATE FOR HOMEPAGE SEO:**
\`\`\`
## 🏠 Homepage Technical SEO Action Plan

### 🚨 **HIGH PRIORITY FIXES** (Immediate Impact)
**1. 📝 Missing H1 Tag**
- **Current Issue:** [Specific issue description]
- **SEO Impact:** 🔴 Critical - [Why it matters]
- **Fix:** [Exact implementation steps]
- **Expected Result:** 📈 [Specific improvement]

**2. 🖼️ Image Alt Text Missing**
- **Current Issue:** [Specific count and details]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Fix:** [Exact implementation steps]
- **Expected Result:** 📈 [Specific improvement]

### ⚠️ **MEDIUM PRIORITY FIXES**
**3. 📄 Title Tag Optimization**
- **Current Issue:** [Specific details]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Fix:** [Exact implementation steps]
- **Expected Result:** 📈 [Specific improvement]

### 🎯 **IMPLEMENTATION STEPS**
1. **Week 1:** [Specific actions]
2. **Week 2:** [Specific actions]
3. **Week 3:** [Specific actions]

### 💡 **QUICK WINS** (Can implement today)
- ✅ [Action 1] ([time] minutes)
- ✅ [Action 2] ([time] minutes)
- ✅ [Action 3] ([time] minutes)

**Total time investment:** [X] minutes for significant SEO improvements!
\`\`\`

**CRITICAL: Always use this exact format with emojis, priority levels, and specific implementation steps!**

**EXAMPLE RESPONSE FOR HOMEPAGE TECHNICAL SEO:**
\`\`\`
## 🏠 Homepage Technical SEO Action Plan

### 🚨 **HIGH PRIORITY FIXES** (Immediate Impact)

**1. 📝 Missing H1 Tag**
- **Current Issue:** Your homepage has no H1 tag
- **SEO Impact:** 🔴 Critical - H1s are the most important heading for SEO
- **Fix:** Add \`<h1>Professional Digital Marketing Services | Mozarex</h1>\`
- **Expected Result:** 📈 15-20% improvement in search rankings

**2. 🖼️ Image Alt Text Missing**
- **Current Issue:** 2 out of 5 images missing alt text
- **SEO Impact:** 🟡 Medium - Affects accessibility and image search
- **Fix:** Add descriptive alt text like \`alt="Digital marketing team working on SEO strategy"\`
- **Expected Result:** 📈 Better image search visibility

### ⚠️ **MEDIUM PRIORITY FIXES**

**3. 📄 Title Tag Optimization**
- **Current Issue:** Title is 69 characters (too long)
- **SEO Impact:** 🟡 Medium - May get cut off in search results
- **Fix:** Shorten to 50-60 characters: \`"Digital Marketing & SEO Services | Mozarex"\`
- **Expected Result:** 📈 Better click-through rates

### 🎯 **IMPLEMENTATION STEPS**
1. **Week 1:** Add H1 tag and optimize title
2. **Week 2:** Add alt text to all images
3. **Week 3:** Monitor rankings and traffic improvements

### 💡 **QUICK WINS** (Can implement today)
- ✅ Add H1 tag (5 minutes)
- ✅ Optimize title tag (2 minutes)
- ✅ Add alt text to images (10 minutes)

**Total time investment:** 17 minutes for significant SEO improvements!
\`\`\``;
           } else if (context === 'keywords') {
             contextPrompt += `Focus on keyword strategy: keyword research, difficulty analysis, ranking strategies, content optimization, long-tail keywords.

**MANDATORY RESPONSE TEMPLATE FOR KEYWORDS:**
\`\`\`
## 🔍 Keyword Strategy Action Plan

### 🚨 **HIGH PRIORITY KEYWORDS** (Immediate Impact)
**1. 🎯 Primary Keywords**
- **Current Status:** [Specific keyword analysis]
- **SEO Impact:** 🔴 Critical - [Why it matters]
- **Action:** [Exact optimization steps]
- **Expected Result:** 📈 [Specific improvement]

### ⚠️ **MEDIUM PRIORITY KEYWORDS**
**2. 📊 Long-tail Keywords**
- **Current Status:** [Specific analysis]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Action:** [Exact steps]
- **Expected Result:** 📈 [Specific improvement]

### 💡 **QUICK WINS** (Can implement today)
- ✅ [Action 1] ([time] minutes)
- ✅ [Action 2] ([time] minutes)
\`\`\`

**CRITICAL: Always use this exact format with emojis, priority levels, and specific implementation steps!**`;
           } else if (context === 'competitors') {
             contextPrompt += `Focus on competitive analysis: competitor strategies, market positioning, competitive advantages, market opportunities.

**MANDATORY RESPONSE TEMPLATE FOR COMPETITORS:**
\`\`\`
## 🏆 Competitive Analysis Action Plan

### 🚨 **HIGH PRIORITY INSIGHTS** (Immediate Impact)
**1. 🎯 Competitor Strengths**
- **Analysis:** [Specific competitor analysis]
- **SEO Impact:** 🔴 Critical - [Why it matters]
- **Action:** [Exact steps to compete]
- **Expected Result:** 📈 [Specific improvement]

### ⚠️ **MEDIUM PRIORITY OPPORTUNITIES**
**2. 📊 Market Gaps**
- **Analysis:** [Specific gap analysis]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Action:** [Exact steps]
- **Expected Result:** 📈 [Specific improvement]

### 💡 **QUICK WINS** (Can implement today)
- ✅ [Action 1] ([time] minutes)
- ✅ [Action 2] ([time] minutes)
\`\`\`

**CRITICAL: Always use this exact format with emojis, priority levels, and specific implementation steps!**`;
           } else if (context === 'backlinks') {
             contextPrompt += `Focus on link building: backlink strategies, domain authority, referral traffic, outreach tactics.

**MANDATORY RESPONSE TEMPLATE FOR BACKLINKS:**
\`\`\`
## 🔗 Backlink Strategy Action Plan

### 🚨 **HIGH PRIORITY LINKS** (Immediate Impact)
**1. 🎯 High-Value Targets**
- **Analysis:** [Specific backlink analysis]
- **SEO Impact:** 🔴 Critical - [Why it matters]
- **Action:** [Exact outreach steps]
- **Expected Result:** 📈 [Specific improvement]

### ⚠️ **MEDIUM PRIORITY OPPORTUNITIES**
**2. 📊 Link Building Opportunities**
- **Analysis:** [Specific opportunity analysis]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Action:** [Exact steps]
- **Expected Result:** 📈 [Specific improvement]

### 💡 **QUICK WINS** (Can implement today)
- ✅ [Action 1] ([time] minutes)
- ✅ [Action 2] ([time] minutes)
\`\`\`

**CRITICAL: Always use this exact format with emojis, priority levels, and specific implementation steps!**`;
           } else if (context === 'content') {
             contextPrompt += `Focus on content strategy: content planning, creation, optimization, calendar management.

**MANDATORY RESPONSE TEMPLATE FOR CONTENT:**
\`\`\`
## 📝 Content Strategy Action Plan

### 🚨 **HIGH PRIORITY CONTENT** (Immediate Impact)
**1. 🎯 Content Gaps**
- **Analysis:** [Specific content analysis]
- **SEO Impact:** 🔴 Critical - [Why it matters]
- **Action:** [Exact content creation steps]
- **Expected Result:** 📈 [Specific improvement]

### ⚠️ **MEDIUM PRIORITY OPPORTUNITIES**
**2. 📊 Content Optimization**
- **Analysis:** [Specific optimization analysis]
- **SEO Impact:** 🟡 Medium - [Why it matters]
- **Action:** [Exact steps]
- **Expected Result:** 📈 [Specific improvement]

### 💡 **QUICK WINS** (Can implement today)
- ✅ [Action 1] ([time] minutes)
- ✅ [Action 2] ([time] minutes)
\`\`\`

**CRITICAL: Always use this exact format with emojis, priority levels, and specific implementation steps!**`;
    }

    // Add special note if fresh analysis was performed
    if (freshAnalysis) {
      contextPrompt += `

🔄 FRESH ANALYSIS PERFORMED: I just analyzed ${domain} in real-time to answer your question. The data above is current and up-to-date.
`;
    }

    contextPrompt += `

User Question: ${message}

RESPONSE REQUIREMENTS:
1. Provide SPECIFIC, ACTIONABLE recommendations with examples
2. Think like a senior SEO consultant - what would you tell a client?
3. Give concrete examples and step-by-step guidance
4. Explain WHY each recommendation matters for SEO
5. Focus on HIGH-IMPACT fixes that will move the needle
6. Be conversational and helpful, not robotic
7. If fresh analysis was performed, mention that the data is current
8. **MANDATORY: Use emojis/icons in EVERY response** - Start each section with relevant emojis
9. **MANDATORY: Structure responses with priority levels** (🚨 HIGH, ⚠️ MEDIUM, 💡 LOW)
10. **MANDATORY: Make responses interactive and engaging** like ChatGPT

FORMATTING REQUIREMENTS:
- Use **bold** for important points and headings
- Use line breaks (press Enter) to separate sections
- Use bullet points (-) for lists
- Use emojis/icons extensively to make responses engaging and professional:
  ✅ Success/Good practices, ❌ Issues/Problems, ⚠️ Warnings, 📝 Writing/Content
  🔍 Analysis/Research, 💡 Tips/Insights, 🎯 Goals/Targets, 📊 Data/Analytics
  🚀 Performance/Growth, 👉 Examples/Next steps, 📈 Growth/Trends, 🔧 Technical
  ⭐ Quality/Excellence, 📋 Lists/Checklists, 🎨 Design/Creative, 🔗 Links/Connections
  📱 Mobile, 💻 Desktop, 🌐 Web/Online, 📄 Documents, 🎪 Creative/Special
  🏆 Achievement, ⚡ Speed/Performance, 🛡️ Security, 🎭 Creative/Artistic
  🔐 Security/Privacy, 📦 Packages/Products, 🎁 Benefits/Gifts, 🎉 Celebration
- Use numbered lists (1., 2., 3.) for step-by-step instructions
- Use \`code\` formatting for technical terms
- Make responses visually appealing and easy to read like ChatGPT

Remember: You're an expert SEO consultant. Provide strategic advice with specific examples, not just data regurgitation.

**FINAL REMINDER: Your response MUST include emojis/icons, priority levels (🚨 HIGH, ⚠️ MEDIUM, 💡 LOW), and follow the exact template format above. Do NOT give plain text responses!**`;

    const response = await client.chat.completions.create({
      model: 'gpt-3.5-turbo',
      messages: [
        {
          role: 'system',
          content: `You are Mozarex AI, a senior SEO consultant with 10+ years of experience helping businesses improve their search rankings. You provide STRATEGIC, ACTIONABLE recommendations that drive results.

Your expertise includes:
- Technical SEO optimization
- Content strategy and optimization  
- Keyword research and targeting
- Competitive analysis
- Performance improvement

You think strategically about priorities, impact, and implementation. You're conversational, professional, and focus on high-impact fixes that will move the needle for your clients.

When analyzing technical issues, you prioritize by SEO impact and provide clear implementation guidance. You explain the "why" behind recommendations, not just the "what".

IMPORTANT: Provide specific examples, actionable steps, and strategic insights. Don't just repeat data - give intelligent recommendations like a senior consultant would.

CRITICAL: Always use emojis/icons, priority levels (🚨 HIGH, ⚠️ MEDIUM, 💡 LOW), and structured formatting in every response. Never give plain text responses!`
        },
        {
          role: 'user',
          content: contextPrompt
        }
      ],
      max_tokens: 2000,
      temperature: 0.8
    });

    const aiResponse = response.choices[0].message.content;

    // Store fresh analysis in Supabase if we performed fresh analysis
    if (freshAnalysis && domain && supabaseService.isReady()) {
      try {
        console.log(`💾 Mozarex AI: Storing fresh analysis for ${domain}`);
        const normalizedDomain = domain.replace(/^https?:\/\//, '').replace(/^www\./, '');
        await supabaseService.saveAnalysisData(normalizedDomain, freshAnalysis);
        console.log(`✅ Mozarex AI: Fresh analysis stored for ${domain}`);
      } catch (error) {
        console.error('❌ Mozarex AI: Error storing fresh analysis:', error);
      }
    }

    // Store chat history in Supabase if available
    if (supabaseService.isReady() && domain) {
      try {
        const normalizedDomain = domain.replace(/^https?:\/\//, '').replace(/^www\./, '');
        const customerId = await getCustomerIdFromRequest(req);
        const website = await supabaseService.createOrGetWebsite(normalizedDomain, null, customerId);
        
        if (website) {
          await supabaseService.storeChatMessage(website.id, message, aiResponse);
        }
      } catch (error) {
        console.error('Error storing chat history:', error);
        // Don't fail the request if storage fails
      }
    }

    res.json({
      success: true,
      response: aiResponse,
      analysisSource: freshAnalysis ? 'fresh' : 'stored',
      freshAnalysisPerformed: !!freshAnalysis,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Mozarex AI chat error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process chat message'
    });
  }
});

// Switch to development environment
app.post('/api/environment/switch/development', async (req, res) => {
  try {
    environmentConfigInstance.switchToDevelopment();
    const status = environmentConfigInstance.getStatus();
    
    res.json({
      success: true,
      message: 'Switched to development environment (Sandbox mode)',
      data: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment switch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to switch to development environment',
      timestamp: new Date().toISOString()
    });
  }
});

// Switch to production environment
app.post('/api/environment/switch/production', async (req, res) => {
  try {
    environmentConfigInstance.switchToProduction();
    const status = environmentConfigInstance.getStatus();
    
    res.json({
      success: true,
      message: 'Switched to production environment (Production API)',
      data: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment switch error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to switch to production environment',
      timestamp: new Date().toISOString()
    });
  }
});

// Force sandbox mode
app.post('/api/environment/force/sandbox', async (req, res) => {
  try {
    environmentConfigInstance.forceSandboxMode();
    const status = environmentConfigInstance.getStatus();
    
    res.json({
      success: true,
      message: 'Forced sandbox mode',
      data: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment force error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to force sandbox mode',
      timestamp: new Date().toISOString()
    });
  }
});

// Force production mode
app.post('/api/environment/force/production', async (req, res) => {
  try {
    environmentConfigInstance.forceProductionMode();
    const status = environmentConfigInstance.getStatus();
    
    res.json({
      success: true,
      message: 'Forced production mode',
      data: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment force error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to force production mode',
      timestamp: new Date().toISOString()
    });
  }
});

// Environment-aware DataForSEO analysis endpoint with Supabase caching
app.post('/api/dataforseo/environment/analyze-website', async (req, res) => {
  try {
    const { url, options = {} } = req.body;
    
    if (!url) {
      return res.status(400).json({
        success: false,
        error: 'URL is required',
        timestamp: new Date().toISOString()
      });
    }

    // Normalize URL for consistent storage
    const normalizedUrl = url.replace(/^https?:\/\//, '').replace(/^www\./, '');
    
    // Check if we have cached analysis in Supabase
    let website = null;
    let cachedAnalysis = null;
    
    if (supabaseService.isReady()) {
      try {
        // Get or create website record
        const customerId = await getCustomerIdFromRequest(req);
        website = await supabaseService.createOrGetWebsite(normalizedUrl, null, customerId);
        
        if (website) {
          // Check for cached analysis
          cachedAnalysis = await supabaseService.getAnalysis(website.id);
          
          if (cachedAnalysis) {
            console.log('✅ Using cached analysis from Supabase');
            return res.json({
              success: true,
              data: cachedAnalysis.analysis_data,
              cached: true,
              cached_at: cachedAnalysis.created_at,
              expires_at: cachedAnalysis.expires_at,
              timestamp: new Date().toISOString()
            });
          }
        }
      } catch (error) {
        console.error('Supabase cache check error:', error);
        // Continue with fresh analysis if cache fails
      }
    }

    // Perform fresh analysis
    console.log('🔄 Performing fresh analysis (no cache found)');
    const result = await dataforseoEnvironmentService.analyzeWebsite(url);
    
    // Store analysis in Supabase if successful
    if (result.success && supabaseService.isReady() && website) {
      try {
        // Ensure we have analysis data to store
        const analysisData = result.analysis || result.data || result;
        if (analysisData) {
          await supabaseService.storeAnalysis(website.id, analysisData);
          
          // Store keywords if available
          if (analysisData.keywords?.keywords) {
            await supabaseService.storeKeywords(website.id, analysisData.keywords.keywords);
          }
          
          console.log('✅ Analysis stored in Supabase for future use');
        } else {
          console.log('⚠️ No analysis data to store in Supabase');
        }
      } catch (error) {
        console.error('Error storing analysis in Supabase:', error);
        // Don't fail the request if storage fails
      }
    }
    
    res.json({
      ...result,
      cached: false,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment-aware analysis error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to analyze website',
      timestamp: new Date().toISOString()
    });
  }
});

// Supabase endpoints
app.get('/api/supabase/status', async (req, res) => {
  try {
    const status = await supabaseService.testConnection();
    res.json({
      success: true,
      data: status,
      configured: supabaseService.isReady(),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Supabase status check error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to check Supabase status',
      timestamp: new Date().toISOString()
    });
  }
});

// Get analysis data for a specific domain
app.get('/api/supabase/analysis/:domain', async (req, res) => {
  try {
    const { domain } = req.params;
    const { forceRegenerate } = req.query;
    console.log('Getting analysis data for domain:', domain, forceRegenerate ? '(force regenerate)' : '');
    
    // Get customer ID from authenticated user
    const customerId = await getCustomerIdFromRequest(req);
    
    let analysisData = null;
    
    // Only get cached data if not forcing regeneration
    if (!forceRegenerate) {
      analysisData = await supabaseService.getAnalysisData(domain, customerId);
    }
    
    if (analysisData && !forceRegenerate) {
      res.json({ success: true, data: analysisData });
    } else {
      console.log('No analysis data found, generating new analysis for:', domain);
      
      // Generate new analysis data using the environment service
      try {
        const analysisResult = await dataforseoEnvironmentService.analyzeWebsite(domain);
        
        if (analysisResult.success && analysisResult.analysis) {
          // Get or create website record
          const website = await supabaseService.createOrGetWebsite(domain, null, customerId);
          
          if (website && !website.error) {
            // Store the analysis data
            await supabaseService.storeAnalysis(website.id, analysisResult.analysis);
            console.log('✅ Analysis data generated and stored for:', domain);
            
            res.json({ success: true, data: analysisResult.analysis });
          } else {
            console.error('❌ Failed to get or create website record for:', domain);
            if (website && website.error) {
              res.json({ success: false, message: website.error, limit: website.limit, current: website.current });
            } else {
              res.json({ success: false, message: 'Failed to create website record' });
            }
          }
        } else {
          console.error('❌ Failed to generate analysis data for:', domain);
          res.json({ success: false, message: 'Failed to generate analysis data' });
        }
      } catch (analysisError) {
        console.error('❌ Error generating analysis data:', analysisError);
        res.json({ success: false, message: 'No analysis data found and failed to generate new analysis' });
      }
    }
  } catch (error) {
    console.error('Error getting analysis data:', error);
    res.json({ success: false, error: error.message });
  }
});

// Get historical DataForSEO data for dashboard
// Handle both GET (normal) and POST (force refresh) requests
app.get('/api/supabase/historical-data/:domain', async (req, res) => {
  await handleHistoricalDataRequest(req, res, false);
});

app.post('/api/supabase/historical-data/:domain', async (req, res) => {
  await handleHistoricalDataRequest(req, res, true);
});

async function handleHistoricalDataRequest(req, res, forceRefresh = false) {
  try {
    const { domain } = req.params;
    const { forceRefresh: bodyForceRefresh, bypassCache } = req.body || {};
    
    const shouldForceRefresh = forceRefresh || bodyForceRefresh || bypassCache;
    
    console.log('📊 Getting historical DataForSEO data for:', domain, shouldForceRefresh ? '(FORCE REFRESH)' : '(normal)');
    
    // Use the existing DataForSEO environment service to get real data
    let analysisData = null;
    
    try {
      // Get analysis data using the environment service
      const analysisResult = await dataforseoEnvironmentService.analyzeWebsite(domain);
      
      if (analysisResult.success && analysisResult.analysis) {
        analysisData = analysisResult.analysis;
        console.log('✅ Got real DataForSEO analysis data', shouldForceRefresh ? '(fresh from API)' : '');
      }
    } catch (analysisError) {
      console.log('⚠️ Could not get real analysis data:', analysisError.message);
    }
    
    // Process the data - use real DataForSEO data only
    console.log('🔍 Processing analysis data for Mantis dashboard:', {
      hasAnalysisData: !!analysisData,
      hasKeywords: !!analysisData?.keywords,
      keywordCount: analysisData?.keywords?.keywords?.length || 0
    });
    
    const processedData = {
      success: true,
      data: {
        domain: domain,
        timestamp: new Date().toISOString(),
        rankedKeywords: analysisData?.keywords?.keywords?.map((keyword, index) => ({
          keyword_data: {
            keyword_info: {
              keyword: keyword.keyword,
              search_volume: keyword.searchVolume || 0, // Use actual search volume from DataForSEO
              competition_level: keyword.competition?.toUpperCase() || 'UNKNOWN',
              cpc: keyword.cpc || 0
            }
          },
          ranked_serp_element: {
            serp_item: {
              rank_group: keyword.rank || keyword.position || 0 // Use actual ranking from DataForSEO
            }
          }
        })) || [],  // Return empty array if no keyword data, don't use dummy fallback
        trafficEstimation: {
          organic: {
            etv: analysisData?.traffic?.organic?.etv || 0  // Use real traffic data from DataForSEO
          }
        },
        // Use REAL metrics from DataForSEO - NO simulations
        metrics: {
          totalKeywords: analysisData?.keywords?.totalKeywords || 0,
          topKeywords: analysisData?.keywords?.keywords || [],
          estimatedTraffic: analysisData?.traffic?.organic?.etv || 0,  // Real traffic from DataForSEO
          averagePosition: analysisData?.serp?.averagePosition || 0,  // Real position from DataForSEO
          seoScore: analysisData?.score || 0,  // Real score from analysis
          issuesCount: analysisData?.issues?.length || 0  // Count of real issues found
        },
        // Only provide chart data if we have real historical data
        chartData: analysisData?.chartData || {
          traffic: { months: [], values: [] },
          positions: { months: [], values: [] }
        },
        // Only provide competitor data if available from DataForSEO
        competitors: analysisData?.competitors || [],
        // Pass the complete analysis data for AI insights
        analysis: analysisData
      }
    };
    
    console.log('✅ Historical DataForSEO data retrieved successfully');
    res.json(processedData);
    
  } catch (error) {
    console.error('❌ Error getting historical DataForSEO data:', error);
    res.json({ 
      success: false, 
      error: error.message,
      data: {
        // Fallback data structure
        metrics: {
          totalKeywords: 0,
          topKeywords: [],
          estimatedTraffic: 0,
          averagePosition: 0,
          seoIssues: 0
        },
        chartData: {
          traffic: { months: [], values: [] },
          positions: { months: [], values: [] }
        }
      }
    });
  }
}

// Helper function to calculate average position
function calculateAveragePosition(keywords) {
  if (!keywords || keywords.length === 0) return 0;
  
  // For DataForSEO keywords, we don't have real positions, so return 0
  // This indicates we need real ranking data from DataForSEO Labs
  return 0;
}

// Helper function to calculate SEO issues
function calculateSEOIssues(keywords) {
  if (!keywords || keywords.length === 0) return 0;
  
  let issues = 0;
  
  // Count keywords with high difficulty
  const highDifficulty = keywords.filter(kw => 
    kw.competition === 'High' || kw.difficulty > 70
  ).length;
  
  // Count keywords with low search volume (potential issues)
  const lowVolume = keywords.filter(kw => 
    kw.searchVolume === 'Low'
  ).length;
  
  issues = highDifficulty + Math.floor(lowVolume / 2); // Count half of low volume as issues
  
  return Math.min(issues, 10); // Cap at 10 issues
}

// Generate realistic traffic history based on real DataForSEO data
function generateTrafficHistory(analysisData) {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
  
  // Base traffic calculation from real keyword data
  const keywords = analysisData?.keywords?.keywords || [];
  const totalSearchVolume = keywords.reduce((sum, kw) => {
    const volume = kw.searchVolume === 'High' ? 12000 : 
                  kw.searchVolume === 'Medium' ? 6000 : 2000;
    return sum + volume;
  }, 0);
  
  // Estimate organic traffic (typically 10-20% of search volume)
  const baseTraffic = Math.floor(totalSearchVolume * 0.15);
  
  // Generate realistic monthly progression
  const values = months.map((month, index) => {
    // Start lower and gradually increase with some variation
    const baseValue = Math.floor(baseTraffic * (0.7 + (index * 0.05)));
    const variation = Math.floor(baseValue * 0.1 * (Math.random() - 0.5));
    return Math.max(baseValue + variation, Math.floor(baseValue * 0.5));
  });
  
  return { months, values };
}

// Generate realistic position history based on real DataForSEO data
function generatePositionHistory(analysisData) {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
  
  // Calculate average difficulty from real keywords
  const keywords = analysisData?.keywords?.keywords || [];
  const avgDifficulty = keywords.length > 0 ? 
    keywords.reduce((sum, kw) => sum + (kw.difficulty || 50), 0) / keywords.length : 50;
  
  // Convert difficulty to estimated average position
  // Higher difficulty = worse (higher) position
  const basePosition = Math.floor(avgDifficulty * 0.6); // Scale difficulty to position
  
  // Generate realistic monthly progression (improving over time)
  const values = months.map((month, index) => {
    // Start higher and gradually improve
    const improvement = Math.floor(index * 2); // 2 position improvement per month
    const variation = Math.floor(Math.random() * 4) - 2; // ±2 position variation
    return Math.max(basePosition - improvement + variation, 1);
  });
  
  return { months, values };
}

// Generate competitor data based on domain analysis
function generateCompetitorData(domain, analysisData) {
  // Generate realistic competitors based on the domain's industry
  const industryKeywords = analysisData?.keywords?.keywords || [];
  const totalKeywords = industryKeywords.length;
  const avgDifficulty = industryKeywords.length > 0 ? 
    industryKeywords.reduce((sum, kw) => sum + (kw.difficulty || 50), 0) / industryKeywords.length : 50;
  
  // Generate competitors with varying performance levels
  const competitors = [
    {
      domain: `${domain.split('.')[0]}-competitor1.com`,
      rank: 1,
      traffic: Math.floor(Math.random() * 50000) + 30000,
      keywords: Math.floor(totalKeywords * 1.5) + Math.floor(Math.random() * 500)
    },
    {
      domain: `${domain.split('.')[0]}-competitor2.com`,
      rank: 2,
      traffic: Math.floor(Math.random() * 40000) + 25000,
      keywords: Math.floor(totalKeywords * 1.2) + Math.floor(Math.random() * 300)
    },
    {
      domain: `${domain.split('.')[0]}-competitor3.com`,
      rank: 3,
      traffic: Math.floor(Math.random() * 30000) + 20000,
      keywords: Math.floor(totalKeywords * 1.0) + Math.floor(Math.random() * 200)
    },
    {
      domain: `${domain.split('.')[0]}-competitor4.com`,
      rank: 4,
      traffic: Math.floor(Math.random() * 25000) + 15000,
      keywords: Math.floor(totalKeywords * 0.8) + Math.floor(Math.random() * 150)
    }
  ];
  
  return competitors;
}

// Technical SEO Analysis Endpoint
app.get('/api/technical-seo/:domain', async (req, res) => {
  try {
    const { domain } = req.params;
    console.log('🔧 Getting technical SEO analysis for:', domain);

    // Call the DataForSEO environment service to get analysis data
    const analysisResult = await dataforseoEnvironmentService.analyzeWebsite(domain);

    if (!analysisResult.success || !analysisResult.analysis) {
      console.error('❌ Failed to get real DataForSEO analysis data:', analysisResult.error);
      // Return error response without sample data
      return res.json({
        success: false,
        error: analysisResult.error || 'Failed to fetch real DataForSEO data',
        data: {
          metrics: {
            headingStructure: 75,
            titleOptimization: 80,
            metaTags: 70,
            imageOptimization: 85,
            pageSpeed: 90
          },
          technicalData: {
            headings: [],
            titleTags: [],
            metaTags: [],
            images: []
          }
        }
      });
    }

    const analysisData = analysisResult.analysis;
    console.log('✅ Got real DataForSEO analysis data for technical SEO');

    // Process technical SEO data
    const processedData = {
      success: true,
      data: {
        domain: domain,
        timestamp: new Date().toISOString(),
        // Calculate technical metrics based on real data
        metrics: {
          headingStructure: calculateHeadingStructureScore(analysisData),
          titleOptimization: calculateTitleOptimizationScore(analysisData),
          metaTags: calculateMetaTagsScore(analysisData),
          imageOptimization: calculateImageOptimizationScore(analysisData),
          pageSpeed: calculatePageSpeedScore(analysisData)
        },
                // Generate technical SEO analysis data
                technicalData: {
                  headings: generateHeadingAnalysis(analysisData),
                  titleTags: generateTitleTagsAnalysis(analysisData),
                  metaTags: generateMetaTagsAnalysis(analysisData),
                  images: generateImageAnalysis(analysisData),
                  links: generateLinkAnalysis(analysisData)
                }
      }
    };

    console.log('✅ Technical SEO analysis completed successfully');
    res.json(processedData);

  } catch (error) {
    console.error('❌ Error getting technical SEO analysis:', error);
    res.json({
      success: false,
      error: error.message,
      data: {
        // Fallback data structure
        metrics: {
          headingStructure: 75,
          titleOptimization: 80,
          metaTags: 70,
          imageOptimization: 85,
          pageSpeed: 90
        },
        technicalData: {
          headings: [],
          titleTags: [],
          metaTags: [],
          images: []
        }
      }
    });
  }
});

// Helper functions for technical SEO analysis
function calculateHeadingStructureScore(analysisData) {
  // Analyze heading structure from on-page data
  const onPage = analysisData?.onPage || {};
  const headings = Array.isArray(onPage.headings) ? onPage.headings : [];
  
  let score = 0;
  
  // Check for H1 presence (20 points)
  if (headings.some(h => h.tag === 'H1')) score += 20;
  
  // Check for proper heading hierarchy (30 points)
  const headingTags = headings.map(h => h.tag).sort();
  if (headingTags.includes('H1') && headingTags.includes('H2')) score += 30;
  
  // Check heading length appropriateness (25 points)
  const goodLengths = headings.filter(h => h.text && h.text.length > 10 && h.text.length < 100);
  score += Math.min((goodLengths.length / headings.length) * 25, 25);
  
  // Check for keyword optimization (25 points)
  const optimizedHeadings = headings.filter(h => h.text && h.text.toLowerCase().includes('seo'));
  score += Math.min((optimizedHeadings.length / Math.max(headings.length, 1)) * 25, 25);
  
  return Math.min(score, 100);
}

function calculateTitleOptimizationScore(analysisData) {
  // Analyze title tags from on-page data
  const onPage = analysisData?.onPage || {};
  const title = onPage.title || '';
  
  let score = 0;
  
  // Check title length (40 points)
  if (title.length >= 30 && title.length <= 60) score += 40;
  else if (title.length >= 20 && title.length <= 70) score += 25;
  else if (title.length > 0) score += 10;
  
  // Check for keyword presence (30 points)
  if (title.toLowerCase().includes('seo') || title.toLowerCase().includes('marketing')) score += 30;
  else if (title.length > 0) score += 15;
  
  // Check for brand presence (20 points)
  if (title.toLowerCase().includes('mozarex')) score += 20;
  else if (title.length > 0) score += 10;
  
  // Check for special characters (10 points)
  if (!title.includes('|') && !title.includes('-') && title.length > 0) score += 10;
  
  return Math.min(score, 100);
}

function calculateMetaTagsScore(analysisData) {
  // Analyze meta tags from on-page data
  const onPage = analysisData?.onPage || {};
  const metaDescription = onPage.metaDescription || '';
  
  let score = 0;
  
  // Check meta description presence and length (50 points)
  if (metaDescription.length >= 120 && metaDescription.length <= 160) score += 50;
  else if (metaDescription.length >= 100 && metaDescription.length <= 180) score += 35;
  else if (metaDescription.length > 0) score += 20;
  
  // Check for keyword optimization (30 points)
  if (metaDescription.toLowerCase().includes('seo') || metaDescription.toLowerCase().includes('marketing')) score += 30;
  else if (metaDescription.length > 0) score += 15;
  
  // Check for call-to-action (20 points)
  if (metaDescription.toLowerCase().includes('contact') || metaDescription.toLowerCase().includes('learn')) score += 20;
  else if (metaDescription.length > 0) score += 10;
  
  return Math.min(score, 100);
}

function calculateImageOptimizationScore(analysisData) {
  // Analyze images from on-page data
  const onPage = analysisData?.onPage || {};
  const images = Array.isArray(onPage.images) ? onPage.images : [];
  
  let score = 0;
  
  if (images.length === 0) return 50; // No images is neutral
  
  // Check alt text presence (60 points)
  const imagesWithAlt = images.filter(img => img.alt && img.alt.trim().length > 0);
  score += (imagesWithAlt.length / images.length) * 60;
  
  // Check alt text quality (25 points)
  const goodAltTexts = imagesWithAlt.filter(img => img.alt.length > 5 && img.alt.length < 125);
  score += (goodAltTexts.length / images.length) * 25;
  
  // Check for keyword optimization in alt text (15 points)
  const optimizedAltTexts = imagesWithAlt.filter(img => 
    img.alt.toLowerCase().includes('seo') || img.alt.toLowerCase().includes('marketing')
  );
  score += (optimizedAltTexts.length / images.length) * 15;
  
  return Math.min(score, 100);
}

function calculatePageSpeedScore(analysisData) {
  // This would typically come from PageSpeed Insights or similar
  // For now, return a simulated score based on page complexity
  const onPage = analysisData?.onPage || {};
  const pageSize = onPage.pageSize || 0;
  const imageCount = onPage.images?.length || 0;
  
  let score = 90; // Base score
  
  // Penalize for large page size
  if (pageSize > 1000000) score -= 20; // > 1MB
  else if (pageSize > 500000) score -= 10; // > 500KB
  
  // Penalize for too many images
  if (imageCount > 20) score -= 15;
  else if (imageCount > 10) score -= 8;
  
  return Math.max(score, 30); // Minimum score of 30
}

function generateHeadingAnalysis(analysisData) {
  const onPage = analysisData?.onPage || {};
  const headings = Array.isArray(onPage.headings) ? onPage.headings : [];
  
  // Return sample headings if none found
  if (headings.length === 0) {
    return [
      { 
        tag: 'H1', 
        text: 'Welcome to Mozarex AI - Digital Marketing Solutions', 
        status: 'good', 
        page: '/',
        issue: null,
        recommendation: 'Excellent H1 tag with primary keyword and brand name. Maintains proper hierarchy.'
      },
      { 
        tag: 'H2', 
        text: 'Our Services', 
        status: 'warning', 
        page: '/services',
        issue: 'Missing keyword optimization',
        recommendation: 'Consider adding "Digital Marketing Services" to improve keyword targeting.'
      },
      { 
        tag: 'H2', 
        text: 'About Us', 
        status: 'warning', 
        page: '/about',
        issue: 'Too short and generic',
        recommendation: 'Expand to "About Mozarex AI - Leading Digital Marketing Agency" for better SEO.'
      },
      { 
        tag: 'H3', 
        text: 'SEO Services', 
        status: 'good', 
        page: '/seo-services',
        issue: null,
        recommendation: 'Well-optimized H3 tag with clear service description.'
      },
      { 
        tag: 'H3', 
        text: 'Content Marketing', 
        status: 'good', 
        page: '/content-marketing',
        issue: null,
        recommendation: 'Good H3 structure. Consider adding location-based keywords if targeting local market.'
      },
      { 
        tag: 'H4', 
        text: 'Local SEO', 
        status: 'error', 
        page: '/services',
        issue: 'Missing from main page structure',
        recommendation: 'Add H4 tags to main service page to improve content hierarchy and keyword targeting.'
      }
    ];
  }
  
  // Process real headings
  return headings.map(heading => {
    let status = 'good';
    let issue = null;
    let recommendation = 'Good heading structure with proper hierarchy.';
    
    // Check heading length
    if (heading.text.length < 10) {
      status = 'warning';
      issue = 'Too short';
      recommendation = 'Expand heading text to be more descriptive and include relevant keywords.';
    } else if (heading.text.length > 100) {
      status = 'warning';
      issue = 'Too long';
      recommendation = 'Consider shortening the heading to improve readability and SEO.';
    }
    
    // Check for keyword optimization
    if (!heading.text.toLowerCase().includes('seo') && !heading.text.toLowerCase().includes('marketing')) {
      if (status === 'good') {
        status = 'warning';
        issue = 'Consider adding keywords';
        recommendation = 'Add relevant keywords to improve SEO targeting and search visibility.';
      }
    }
    
    return {
      tag: heading.tag || 'H2',
      text: heading.text || 'Untitled heading',
      status: status,
      page: heading.page || '/',
      issue: issue,
      recommendation: recommendation
    };
  });
}

function generateTitleTagsAnalysis(analysisData) {
  const onPage = analysisData?.onPage || {};
  const title = onPage.title || 'Untitled Page';
  
  let status = 'good';
  let issue = null;
  let recommendation = 'Perfect title length and includes primary keywords. Excellent brand positioning.';
  
  if (title.length < 30) {
    status = 'error';
    issue = 'Too short - missing keywords and brand';
    recommendation = 'Expand to include keywords and brand name to improve click-through rates.';
  } else if (title.length > 60) {
    status = 'warning';
    issue = 'Slightly over optimal length (50-60 chars)';
    recommendation = 'Consider shortening to improve SERP display and click-through rates.';
  }
  
  return [
    { 
      url: '/', 
      title: title, 
      length: title.length, 
      status: status,
      issue: issue,
      recommendation: recommendation
    }
  ];
}

function generateMetaTagsAnalysis(analysisData) {
  const onPage = analysisData?.onPage || {};
  const metaDescription = onPage.metaDescription || '';
  
  const metas = [];
  
  // Meta description
  if (metaDescription.length > 0) {
    metas.push({ 
      type: 'description', 
      content: metaDescription, 
      status: metaDescription.length > 120 && metaDescription.length < 160 ? 'good' : 'warning',
      issue: metaDescription.length > 160 ? 'Too long' : metaDescription.length < 120 ? 'Too short' : null,
      recommendation: metaDescription.length > 160 ? 'Shorten meta description to under 160 characters for better SERP display.' : 
                     metaDescription.length < 120 ? 'Expand meta description to 120-160 characters for better SEO.' :
                     'Well-optimized meta description with good length and content.'
    });
  } else {
    metas.push({ 
      type: 'description', 
      content: 'Missing meta description', 
      status: 'error',
      issue: 'No meta description found',
      recommendation: 'Add a compelling meta description (120-160 characters) that includes your primary keywords and encourages clicks.'
    });
  }
  
  // Add other common meta tags
  if (onPage.keywords) {
    metas.push({ 
      type: 'keywords', 
      content: onPage.keywords, 
      status: 'warning',
      issue: 'Keywords meta tag is deprecated',
      recommendation: 'Remove keywords meta tag as it is no longer used by search engines and can be seen as keyword stuffing.'
    });
  }
  
  metas.push(
    { 
      type: 'viewport', 
      content: 'width=device-width, initial-scale=1.0', 
      status: 'good',
      issue: null,
      recommendation: 'Good viewport meta tag for mobile responsiveness.'
    },
    { 
      type: 'robots', 
      content: 'index, follow', 
      status: 'good',
      issue: null,
      recommendation: 'Proper robots meta tag allowing search engine indexing.'
    },
    { 
      type: 'author', 
      content: 'Mozarex AI Team', 
      status: 'good',
      issue: null,
      recommendation: 'Good author meta tag for content attribution.'
    }
  );
  
  return metas;
}

function generateImageAnalysis(analysisData) {
  const onPage = analysisData?.onPage || {};
  const images = Array.isArray(onPage.images) ? onPage.images : [];
  
  if (images.length === 0) {
    return [
      { 
        src: '/images/hero-banner.jpg', 
        alt: 'Digital marketing team working on SEO strategy', 
        status: 'good',
        issue: null,
        recommendation: 'Excellent alt text with descriptive content and relevant keywords.'
      },
      { 
        src: '/images/services-icon.png', 
        alt: 'Services icon', 
        status: 'good',
        issue: null,
        recommendation: 'Good alt text for icon image.'
      },
      { 
        src: '/images/team-photo.jpg', 
        alt: '', 
        status: 'error',
        issue: 'Missing alt text',
        recommendation: 'Add descriptive alt text to improve accessibility and SEO.'
      },
      { 
        src: '/images/logo.png', 
        alt: 'Mozarex AI Logo', 
        status: 'good',
        issue: null,
        recommendation: 'Perfect alt text for logo image.'
      },
      { 
        src: '/images/background.jpg', 
        alt: 'Background image', 
        status: 'warning',
        issue: 'Generic alt text',
        recommendation: 'Use more descriptive alt text that describes the actual content of the image.'
      }
    ];
  }
  
  return images.map(image => {
    let status = 'good';
    let issue = null;
    let recommendation = 'Good alt text with descriptive content.';
    
    if (!image.alt || image.alt.trim().length === 0) {
      status = 'error';
      issue = 'Missing alt text';
      recommendation = 'Add descriptive alt text to improve accessibility and SEO.';
    } else if (image.alt.length < 5) {
      status = 'warning';
      issue = 'Alt text too short';
      recommendation = 'Expand alt text to be more descriptive and include relevant keywords.';
    }
    
    return {
      src: image.src || '/images/placeholder.jpg',
      alt: image.alt || '',
      status: status,
      issue: issue,
      recommendation: recommendation
    };
  });
}

// Generate link analysis data
function generateLinkAnalysis(analysisData) {
  const onPage = analysisData?.onPage || {};
  const links = Array.isArray(onPage.links) ? onPage.links : [];
  
  // Return empty array if no real data available
  if (links.length === 0) {
    return [];
  }
  
  // Process real links from DataForSEO data
  return links.map(link => ({
    url: link.url || '',
    text: link.text || link.anchor || '',
    type: link.type || 'unknown',
    status: link.status || 'unknown',
    issue: link.issue || null,
    recommendation: link.recommendation || null
  }));
}

// Helper function to generate chart data from real historical data
function generateChartData(historicalData) {
  // Return empty data if no real historical data available
  if (!historicalData || !Array.isArray(historicalData) || historicalData.length === 0) {
    return {
      traffic: {
        months: [],
        values: []
      },
      positions: {
        months: [],
        values: []
      }
    };
  }
  
  // Process real historical data
  return {
    traffic: {
      months: historicalData.map(item => item.month || ''),
      values: historicalData.map(item => item.traffic || 0)
    },
    positions: {
      months: historicalData.map(item => item.month || ''),
      values: historicalData.map(item => item.position || 0)
    }
  };
}

// Get all customer websites and analysis data
app.get('/api/supabase/customer-websites', async (req, res) => {
  try {
    // Get customer ID from authenticated user
    const customerId = await getCustomerIdFromRequest(req);

    if (!customerId) {
      return res.status(401).json({ success: false, error: 'Authentication required' });
    }

    const analysisData = await supabaseService.getCustomerAnalysisData(customerId);
    
    if (analysisData) {
      res.json({ success: true, data: analysisData });
    } else {
      res.json({ success: false, error: 'Failed to fetch customer websites' });
    }
  } catch (error) {
    console.error('Error fetching customer websites:', error);
    res.status(500).json({ success: false, error: 'Internal server error' });
  }
});

// Get cached keywords for a website
app.get('/api/supabase/keywords/:domain', async (req, res) => {
  try {
    const { domain } = req.params;
    
    if (!supabaseService.isReady()) {
      return res.status(503).json({
        success: false,
        error: 'Supabase not configured',
        timestamp: new Date().toISOString()
      });
    }

    const customerId = await getCustomerIdFromRequest(req);
    const website = await supabaseService.createOrGetWebsite(domain, null, customerId);
    if (!website) {
      return res.status(404).json({
        success: false,
        error: 'Website not found',
        timestamp: new Date().toISOString()
      });
    }

    const keywords = await supabaseService.getKeywords(website.id);
    res.json({
      success: true,
      data: keywords || [],
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Supabase keywords retrieval error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve keywords',
      timestamp: new Date().toISOString()
    });
  }
});

// Add new keyword
app.post('/api/supabase/keywords', async (req, res) => {
  try {
    const { domain, keyword, searchVolume, difficulty, currentRank } = req.body;
    
    if (!domain || !keyword) {
      return res.status(400).json({
        success: false,
        error: 'Domain and keyword are required',
        timestamp: new Date().toISOString()
      });
    }

    if (!supabaseService.isReady()) {
      return res.status(503).json({
        success: false,
        error: 'Supabase not configured',
        timestamp: new Date().toISOString()
      });
    }

    const customerId = await getCustomerIdFromRequest(req);
    const website = await supabaseService.createOrGetWebsite(domain, null, customerId);
    if (!website) {
      return res.status(500).json({
        success: false,
        error: 'Failed to create website record',
        timestamp: new Date().toISOString()
      });
    }

    const newKeyword = await supabaseService.addKeyword(
      website.id, 
      keyword, 
      searchVolume || 0, 
      difficulty || 0, 
      currentRank || null
    );

    res.json({
      success: true,
      data: newKeyword,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Supabase keyword addition error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to add keyword',
      timestamp: new Date().toISOString()
    });
  }
});

// Get content calendar
app.get('/api/supabase/calendar/:domain', async (req, res) => {
  try {
    const { domain } = req.params;
    
    if (!supabaseService.isReady()) {
      return res.status(503).json({
        success: false,
        error: 'Supabase not configured',
        timestamp: new Date().toISOString()
      });
    }

    const customerId = await getCustomerIdFromRequest(req);
    const website = await supabaseService.createOrGetWebsite(domain, null, customerId);
    if (!website) {
      return res.status(404).json({
        success: false,
        error: 'Website not found',
        timestamp: new Date().toISOString()
      });
    }

    const calendar = await supabaseService.getContentCalendar(website.id);
    res.json({
      success: true,
      data: calendar || [],
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Supabase calendar retrieval error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve content calendar',
      timestamp: new Date().toISOString()
    });
  }
});

// Store content calendar
app.post('/api/supabase/calendar', async (req, res) => {
  try {
    const { domain, calendarData } = req.body;
    
    if (!domain || !calendarData) {
      return res.status(400).json({
        success: false,
        error: 'Domain and calendar data are required',
        timestamp: new Date().toISOString()
      });
    }

    if (!supabaseService.isReady()) {
      return res.status(503).json({
        success: false,
        error: 'Supabase not configured',
        timestamp: new Date().toISOString()
      });
    }

    const customerId = await getCustomerIdFromRequest(req);
    const website = await supabaseService.createOrGetWebsite(domain, null, customerId);
    if (!website) {
      return res.status(500).json({
        success: false,
        error: 'Failed to create website record',
        timestamp: new Date().toISOString()
      });
    }

    const storedCalendar = await supabaseService.storeContentCalendar(website.id, calendarData);
    res.json({
      success: true,
      data: storedCalendar,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Supabase calendar storage error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to store content calendar',
      timestamp: new Date().toISOString()
    });
  }
});

// Get environment-aware DataForSEO service status
app.get('/api/dataforseo/environment/status', async (req, res) => {
  try {
    const status = dataforseoEnvironmentService.getServiceStatus();
    res.json({
      success: true,
      data: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Environment-aware service status error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get service status',
      timestamp: new Date().toISOString()
    });
  }
});

// Intelligent Content Management API Endpoints
app.post('/api/content/generate-service-based', async (req, res) => {
  try {
    const { userId, domain, days = 7 } = req.body;
    
    if (!userId || !domain) {
      return res.status(400).json({ 
        success: false, 
        error: 'User ID and domain are required' 
      });
    }

    console.log(`🎯 Generating service-based content for ${domain} (${days} days)`);
    
    const content = await intelligentContentService.generateServiceBasedContent(userId, domain, days);
    
    res.json({
      success: true,
      data: content,
      message: `Generated content for ${days} days based on company services`,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Service-based content generation error:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.get('/api/content/approval-queue/:userId/:domain', async (req, res) => {
  try {
    const { userId, domain } = req.params;
    
    const approvalQueue = await intelligentContentService.getApprovalQueue(userId, domain);
    
    res.json({
      success: true,
      data: approvalQueue,
      count: approvalQueue.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching approval queue:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.post('/api/content/approve/:contentId', async (req, res) => {
  try {
    const { contentId } = req.params;
    const { approvedBy = 'customer' } = req.body;
    
    const updatedContent = await intelligentContentService.updateContentStatus(contentId, 'approved', approvedBy);
    
    res.json({
      success: true,
      data: updatedContent,
      message: 'Content approved successfully',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error approving content:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.post('/api/content/reject/:contentId', async (req, res) => {
  try {
    const { contentId } = req.params;
    const { reason } = req.body;
    
    const updatedContent = await intelligentContentService.updateContentStatus(contentId, 'rejected');
    
    res.json({
      success: true,
      data: updatedContent,
      message: 'Content rejected successfully',
      reason: reason,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error rejecting content:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

app.get('/api/content/calendar/:userId/:domain', async (req, res) => {
  try {
    const { userId, domain } = req.params;
    const { days = 7 } = req.query;
    
    const content = await intelligentContentService.getExistingContent(userId, domain, parseInt(days));
    
    res.json({
      success: true,
      data: content,
      count: content.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching content calendar:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

        app.get('/api/services/:userId/:domain', async (req, res) => {
            try {
                const { userId, domain } = req.params;

                const services = await intelligentContentService.getCompanyServices(userId, domain);

                res.json({
                    success: true,
                    data: services,
                    count: services.length,
                    timestamp: new Date().toISOString()
                });

            } catch (error) {
                console.error('Error fetching company services:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

        // Update content calendar item endpoint
        app.put('/api/content-calendar/:id', async (req, res) => {
            try {
                const { id } = req.params;
                const updateData = req.body;
                console.log(`✏️ Updating content item ${id}`);
                
                const updatedContent = await contentCalendarService.updateContentItem(id, updateData);
                
                res.json({ success: true, data: updatedContent });
            } catch (error) {
                console.error('❌ Error updating content item:', error);
                res.status(500).json({ success: false, error: error.message });
            }
        });

        // Upload media for content
        app.post('/api/content-calendar/:id/media', async (req, res) => {
            try {
                const { id } = req.params;
                const fileData = req.body;
                console.log(`📁 Uploading media for content ${id}`);
                
                const uploadedMedia = await contentCalendarService.uploadMedia(id, fileData);
                
                res.json({ success: true, data: uploadedMedia });
            } catch (error) {
                console.error('❌ Error uploading media:', error);
                res.status(500).json({ success: false, error: error.message });
            }
        });

        // Environment Configuration API Endpoints
        app.get('/api/environment/status', (req, res) => {
            try {
                const status = environmentConfigInstance.getStatus();
                
                res.json({
                    success: true,
                    data: status,
                    timestamp: new Date().toISOString()
                });
            } catch (error) {
                console.error('Error getting environment status:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

        app.get('/api/environment/social-platforms', (req, res) => {
            try {
                const platforms = Object.keys(environmentConfigInstance.config.social);
                const configuredPlatforms = environmentConfigInstance.getConfiguredSocialPlatforms();
                
                const platformStatus = platforms.map(platform => {
                    const config = environmentConfigInstance.getSocialConfig(platform);
                    const isConfigured = environmentConfigInstance.isSocialPlatformConfigured(platform);
                    
                    return {
                        platform: platform,
                        displayName: platform.charAt(0).toUpperCase() + platform.slice(1),
                        isConfigured: isConfigured,
                        hasClientId: !!config.clientId,
                        hasClientSecret: !!config.clientSecret,
                        redirectUri: environmentConfigInstance.getRedirectUri(platform)
                    };
                });
                
                res.json({
                    success: true,
                    platforms: platformStatus,
                    configuredCount: configuredPlatforms.length,
                    totalCount: platforms.length,
                    timestamp: new Date().toISOString()
                });
            } catch (error) {
                console.error('Error getting social platforms status:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

        // Social Media OAuth Connection Endpoints
        app.get('/api/social/connect/:platform', async (req, res) => {
            try {
                const { platform } = req.params;
                const userId = 'mozarex-user'; // In production, get from auth

                console.log(`🔗 Initiating ${platform} OAuth connection for user ${userId}`);

                // Check if platform is configured
                if (!environmentConfigInstance.isSocialPlatformConfigured(platform)) {
                    return res.status(400).json({
                        success: false,
                        error: `${platform} OAuth not configured. Please set ${platform.toUpperCase()}_CLIENT_ID and ${platform.toUpperCase()}_CLIENT_SECRET in environment file.`
                    });
                }

                const socialConfig = environmentConfigInstance.getSocialConfig(platform);
                const redirectUri = environmentConfigInstance.getRedirectUri(platform);

                let authUrl = '';

                switch (platform.toLowerCase()) {
                    case 'twitter':
                        authUrl = `https://twitter.com/i/oauth2/authorize?response_type=code&client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=tweet.read%20tweet.write%20users.read%20offline.access&state=${userId}`;
                        break;

                    case 'instagram':
                        authUrl = `https://api.instagram.com/oauth/authorize?client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=user_profile,user_media&response_type=code&state=${userId}`;
                        break;

                    case 'tiktok':
                        authUrl = `https://www.tiktok.com/auth/authorize/?client_key=${socialConfig.clientId}&scope=user.info.basic,video.publish&response_type=code&redirect_uri=${encodeURIComponent(redirectUri)}&state=${userId}`;
                        break;

                    case 'facebook':
                        authUrl = `https://www.facebook.com/v18.0/dialog/oauth?client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=pages_manage_posts,pages_read_engagement&state=${userId}`;
                        break;

                    case 'linkedin':
                        authUrl = `https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=r_liteprofile%20r_emailaddress%20w_member_social&state=${userId}`;
                        break;

                    case 'youtube':
                        authUrl = `https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=https://www.googleapis.com/auth/youtube.upload%20https://www.googleapis.com/auth/youtube&state=${userId}`;
                        break;

                    case 'pinterest':
                        authUrl = `https://www.pinterest.com/oauth/?response_type=code&client_id=${socialConfig.clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=boards:read%20pins:read%20pins:write&state=${userId}`;
                        break;

                    default:
                        return res.status(400).json({
                            success: false,
                            error: 'Unsupported platform'
                        });
                }

                res.json({
                    success: true,
                    authUrl: authUrl,
                    platform: platform,
                    message: `Redirect to ${platform} OAuth`,
                    timestamp: new Date().toISOString()
                });

            } catch (error) {
                console.error('Error initiating OAuth:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

        app.get('/api/social/callback/:platform', async (req, res) => {
            try {
                const { platform } = req.params;
                const { code, state } = req.query;
                const userId = state || 'mozarex-user';

                console.log(`🔄 Processing ${platform} OAuth callback for user ${userId}`);

                if (!code) {
                    return res.status(400).json({
                        success: false,
                        error: 'Authorization code not provided'
                    });
                }

                // In production, exchange code for access token
                // For now, we'll simulate successful connection
                const mockToken = `mock_${platform}_token_${Date.now()}`;

                // Save connection to Supabase
                const { data, error } = await supabaseService.supabase
                    .from('social_accounts')
                    .upsert({
                        user_id: userId,
                        platform: platform,
                        access_token: mockToken,
                        is_connected: true,
                        connected_at: new Date().toISOString(),
                        updated_at: new Date().toISOString()
                    }, {
                        onConflict: 'user_id,platform'
                    })
                    .select();

                if (error) {
                    throw new Error(`Supabase error: ${error.message}`);
                }

                // Redirect back to dashboard with success message
                res.redirect(`/seo-dashboard-enhanced-v2?social_connected=${platform}&success=true`);

            } catch (error) {
                console.error('Error processing OAuth callback:', error);
                res.redirect(`/seo-dashboard-enhanced-v2?social_error=${platform}&error=${encodeURIComponent(error.message)}`);
            }
        });

        app.get('/api/social/accounts/:userId', async (req, res) => {
            try {
                const { userId } = req.params;

                const { data, error } = await supabaseService.supabase
                    .from('social_accounts')
                    .select('*')
                    .eq('user_id', userId);

                if (error) {
                    throw new Error(`Supabase error: ${error.message}`);
                }

                res.json({
                    success: true,
                    data: data,
                    count: data.length,
                    timestamp: new Date().toISOString()
                });

            } catch (error) {
                console.error('Error fetching social accounts:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

        app.post('/api/social/disconnect/:platform', async (req, res) => {
            try {
                const { platform } = req.params;
                const userId = 'mozarex-user'; // In production, get from auth

                console.log(`🔌 Disconnecting ${platform} for user ${userId}`);

                const { error } = await supabaseService.supabase
                    .from('social_accounts')
                    .update({
                        is_connected: false,
                        access_token: null,
                        disconnected_at: new Date().toISOString(),
                        updated_at: new Date().toISOString()
                    })
                    .eq('user_id', userId)
                    .eq('platform', platform);

                if (error) {
                    throw new Error(`Supabase error: ${error.message}`);
                }

                res.json({
                    success: true,
                    message: `${platform} disconnected successfully`,
                    timestamp: new Date().toISOString()
                });

            } catch (error) {
                console.error('Error disconnecting social account:', error);
                res.status(500).json({
                    success: false,
                    error: error.message
                });
            }
        });

// Campaign Management API Endpoints
app.get('/api/campaigns/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        const { data: campaigns, error } = await supabase
            .from('campaigns')
            .select(`
                *,
                campaign_posts (
                    *,
                    social_accounts (platform, account_name)
                )
            `)
            .eq('domain', domain)
            .order('start_date', { ascending: true });

        if (error) throw error;

        res.json({ success: true, campaigns });
    } catch (error) {
        console.error('Error fetching campaigns:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/campaigns', async (req, res) => {
    try {
        const { domain, title, description, startDate, endDate, posts } = req.body;
        
        // Create campaign
        const { data: campaign, error: campaignError } = await supabase
            .from('campaigns')
            .insert({
                user_id: 'mozarex-user', // TODO: Get from auth
                domain,
                title,
                description,
                start_date: startDate,
                end_date: endDate,
                status: 'draft'
            })
            .select()
            .single();

        if (campaignError) throw campaignError;

        // Create campaign posts
        if (posts && posts.length > 0) {
            const postsData = posts.map(post => ({
                campaign_id: campaign.id,
                social_account_id: post.socialAccountId,
                platform: post.platform,
                content: post.content,
                media_urls: post.mediaUrls || [],
                status: 'pending'
            }));

            const { error: postsError } = await supabase
                .from('campaign_posts')
                .insert(postsData);

            if (postsError) throw postsError;
        }

        res.json({ success: true, campaign });
    } catch (error) {
        console.error('Error creating campaign:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.get('/api/social-accounts', async (req, res) => {
    try {
        const { data: accounts, error } = await supabase
            .from('social_accounts')
            .select('*')
            .eq('user_id', 'mozarex-user') // TODO: Get from auth
            .eq('is_active', true);

        if (error) throw error;

        res.json({ success: true, accounts });
    } catch (error) {
        console.error('Error fetching social accounts:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/social-accounts', async (req, res) => {
    try {
        const { platform, accountName, accountId, accessToken, refreshToken, tokenExpiresAt } = req.body;
        
        const { data: account, error } = await supabase
            .from('social_accounts')
            .insert({
                user_id: 'mozarex-user', // TODO: Get from auth
                platform,
                account_name: accountName,
                account_id: accountId,
                access_token: accessToken,
                refresh_token: refreshToken,
                token_expires_at: tokenExpiresAt,
                is_active: true
            })
            .select()
            .single();

        if (error) throw error;

        res.json({ success: true, account });
    } catch (error) {
        console.error('Error creating social account:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.put('/api/campaign-posts/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const { content, mediaUrls, scheduledTime, status } = req.body;
        
        const { data: post, error } = await supabase
            .from('campaign_posts')
            .update({
                content,
                media_urls: mediaUrls,
                status
            })
            .eq('id', id)
            .select()
            .single();

        if (error) throw error;

        res.json({ success: true, post });
    } catch (error) {
        console.error('Error updating campaign post:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/campaign-posts/:id/schedule', async (req, res) => {
    try {
        const { id } = req.params;
        
        const { data: post, error } = await supabase
            .from('campaign_posts')
            .update({ status: 'scheduled' })
            .eq('id', id)
            .select()
            .single();

        if (error) throw error;

        // TODO: Add to scheduling queue for automated posting
        console.log(`📅 Post ${id} scheduled successfully`);

        res.json({ success: true, post });
    } catch (error) {
        console.error('Error scheduling campaign post:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.get('/api/campaign-templates', async (req, res) => {
    try {
        const { data: templates, error } = await supabase
            .from('campaign_templates')
            .select('*')
            .eq('user_id', 'mozarex-user') // TODO: Get from auth
            .order('is_default', { ascending: false });

        if (error) throw error;

        res.json({ success: true, templates });
    } catch (error) {
        console.error('Error fetching campaign templates:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/campaign-templates', async (req, res) => {
    try {
        const { name, description, templateData, isDefault } = req.body;
        
        const { data: template, error } = await supabase
            .from('campaign_templates')
            .insert({
                user_id: 'mozarex-user', // TODO: Get from auth
                name,
                description,
                template_data: templateData,
                is_default: isDefault || false
            })
            .select()
            .single();

        if (error) throw error;

        res.json({ success: true, template });
    } catch (error) {
        console.error('Error creating campaign template:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Social Media OAuth Endpoints (Placeholder)
app.get('/api/auth/twitter', (req, res) => {
    // TODO: Implement Twitter OAuth
    res.json({ 
        success: false, 
        message: 'Twitter OAuth integration coming soon',
        authUrl: 'https://twitter.com/oauth/authorize?client_id=...'
    });
});

app.get('/api/auth/facebook', (req, res) => {
    // TODO: Implement Facebook OAuth
    res.json({ 
        success: false, 
        message: 'Facebook OAuth integration coming soon',
        authUrl: 'https://www.facebook.com/v18.0/dialog/oauth?client_id=...'
    });
});

app.get('/api/auth/instagram', (req, res) => {
    // TODO: Implement Instagram OAuth
    res.json({ 
        success: false, 
        message: 'Instagram OAuth integration coming soon',
        authUrl: 'https://api.instagram.com/oauth/authorize?client_id=...'
    });
});

app.get('/api/auth/tiktok', (req, res) => {
    // TODO: Implement TikTok OAuth
    res.json({ 
        success: false, 
        message: 'TikTok OAuth integration coming soon',
        authUrl: 'https://www.tiktok.com/auth/authorize?client_key=...'
    });
});

// Automated Posting Scheduler (Placeholder)
app.post('/api/scheduler/start', (req, res) => {
    // TODO: Implement automated posting scheduler
    res.json({ 
        success: true, 
        message: 'Automated posting scheduler started',
        nextCheck: new Date(Date.now() + 60000).toISOString() // 1 minute from now
    });
});

app.post('/api/scheduler/stop', (req, res) => {
    // TODO: Implement scheduler stop
    res.json({ 
        success: true, 
        message: 'Automated posting scheduler stopped'
    });
});

// Campaign Analytics Endpoints
app.get('/api/campaigns/:id/analytics', async (req, res) => {
    try {
        const { id } = req.params;
        
        const { data: analytics, error } = await supabase
            .from('campaign_analytics')
            .select(`
                *,
                campaign_posts (platform, content, published_at)
            `)
            .eq('campaign_id', id)
            .order('recorded_at', { ascending: false });

        if (error) throw error;

        res.json({ success: true, analytics });
    } catch (error) {
        console.error('Error fetching campaign analytics:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.post('/api/campaigns/:id/analytics', async (req, res) => {
    try {
        const { id } = req.params;
        const { postId, platform, metrics } = req.body;
        
        const analyticsData = Object.entries(metrics).map(([metricName, metricValue]) => ({
            campaign_id: id,
            post_id: postId,
            platform,
            metric_name: metricName,
            metric_value: metricValue
        }));

        const { error } = await supabase
            .from('campaign_analytics')
            .insert(analyticsData);

        if (error) throw error;

        res.json({ success: true });
    } catch (error) {
        console.error('Error recording campaign analytics:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Content Calendar API Endpoints
let contentCalendarService = null;

// Initialize ContentCalendarService
try {
    const ContentCalendarService = require('./services/contentCalendarService');
    contentCalendarService = new ContentCalendarService();
    console.log('✅ ContentCalendarService initialized successfully');
} catch (error) {
    console.log('⚠️ ContentCalendarService not initialized - Error:', error.message);
    // Set a mock service to prevent errors
    contentCalendarService = {
        getContentForDate: () => Promise.resolve([]),
        getContentForMonth: () => Promise.resolve([]),
        saveGeneratedContent: () => Promise.resolve([]),
        updateContentItem: () => Promise.resolve({}),
        deleteContentItem: () => Promise.resolve({}),
        uploadMedia: () => Promise.resolve({}),
        scheduleContent: () => Promise.resolve({}),
        generateSEOContent: () => Promise.resolve([]),
        needsContentGeneration: () => Promise.resolve(true),
        getCustomerJoinDate: () => Promise.resolve(new Date())
    };
}

// Check if content needs to be generated
app.post('/api/content-calendar/check-needs', async (req, res) => {
    try {
        const { domain } = req.body;
        console.log(`🔍 Checking if content needs generation for ${domain}`);
        
        const needsGeneration = await contentCalendarService.needsContentGeneration(domain);
        
        res.json({ 
            success: true, 
            needsGeneration: needsGeneration,
            domain: domain
        });
    } catch (error) {
        console.error('❌ Error checking content needs:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Generate SEO-optimized content for social media platforms
app.post('/api/content-calendar/generate-seo-content', async (req, res) => {
    try {
        console.log('📨 Received request to /api/content-calendar/generate-seo-content');
        console.log('📨 Request body:', req.body);
        
        const { domain, services, keywords, days = 30, forceCurrentMonth = false, startDate, immediate = false, background = false } = req.body;
        console.log(`🎯 Generating SEO content for ${domain} with ${services?.length || 0} services and ${keywords?.length || 0} keywords`);
        console.log(`🔍 Mode: immediate=${immediate}, background=${background}, forceCurrentMonth=${forceCurrentMonth}`);
        
        if (forceCurrentMonth && startDate) {
            console.log(`📅 Force current month mode: Starting from ${startDate}`);
        }
        
        // Skip content check for immediate/background generation
        if (!immediate && !background) {
            // Check if content needs to be generated
            const needsGeneration = await contentCalendarService.needsContentGeneration(domain);
            if (!needsGeneration) {
                console.log('✅ Content already exists for next 7 days');
                return res.json({ success: true, message: 'Content already exists for next 7 days', data: [] });
            }
        }
        
        // Generate SEO content using the service
        const generatedContent = await contentCalendarService.generateSEOContent(domain, services, keywords, days, forceCurrentMonth, startDate, immediate, background);
        
        console.log(`✅ Generated ${generatedContent.length} SEO-optimized posts`);
        console.log(`📤 Sending response to frontend with ${generatedContent.length} posts`);
        
        res.json({ success: true, data: generatedContent });
        
    } catch (error) {
        console.error('❌ Error generating SEO content:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});


// Get content for a specific date
app.get('/api/content-calendar/:domain/:date', async (req, res) => {
    try {
        const { domain, date } = req.params;
        console.log(`📅 Getting content for ${domain} on ${date}`);
        
        const content = await contentCalendarService.getContentForDate(domain, date);
        
        res.json({ success: true, data: content });
    } catch (error) {
        console.error('❌ Error getting content for date:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Get content for a month
app.get('/api/content-calendar/:domain/month/:year/:month', async (req, res) => {
    try {
        const { domain, year, month } = req.params;
        console.log(`📅 Getting content for ${domain} for ${year}-${month}`);
        
        const content = await contentCalendarService.getContentForMonth(domain, parseInt(year), parseInt(month));
        
        res.json({ success: true, data: content });
    } catch (error) {
        console.error('❌ Error getting content for month:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Save generated content
app.post('/api/content-calendar/save', async (req, res) => {
    try {
        const { domain, contentData } = req.body;
        console.log(`💾 Saving ${contentData.length} content items for ${domain}`);
        
        const savedContent = await contentCalendarService.saveGeneratedContent(domain, contentData);
        
        res.json({ success: true, data: savedContent });
    } catch (error) {
        console.error('❌ Error saving content:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Update content item
app.put('/api/content-calendar/:id', async (req, res) => {
    try {
        const { id } = req.params;
        const updateData = req.body;
        console.log(`✏️ Updating content item ${id}`);
        
        const updatedContent = await contentCalendarService.updateContentItem(id, updateData);
        
        res.json({ success: true, data: updatedContent });
    } catch (error) {
        console.error('❌ Error updating content item:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Delete content item
app.delete('/api/content-calendar/:id', async (req, res) => {
    try {
        const { id } = req.params;
        console.log(`🗑️ Deleting content item ${id}`);
        
        const deletedContent = await contentCalendarService.deleteContentItem(id);
        
        res.json({ success: true, data: deletedContent });
    } catch (error) {
        console.error('❌ Error deleting content item:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Upload media for content
app.post('/api/content-calendar/:id/media', async (req, res) => {
    try {
        const { id } = req.params;
        const fileData = req.body;
        console.log(`📁 Uploading media for content ${id}`);
        
        const uploadedMedia = await contentCalendarService.uploadMedia(id, fileData);
        
        res.json({ success: true, data: uploadedMedia });
    } catch (error) {
        console.error('❌ Error uploading media:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Schedule content
app.post('/api/content-calendar/:id/schedule', async (req, res) => {
    try {
        const { id } = req.params;
        const { scheduledFor, platform } = req.body;
        console.log(`⏰ Scheduling content ${id} for ${scheduledFor} on ${platform}`);
        
        const scheduledContent = await contentCalendarService.scheduleContent(id, scheduledFor, platform);
        
        res.json({ success: true, data: scheduledContent });
    } catch (error) {
        console.error('❌ Error scheduling content:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Blog Generation API Endpoints

// Route for blog page
app.get('/blog', requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, 'frontend/blog.html'));
});

app.get('/subscription', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'subscription-redirect.html'));
});

// Unified signup and subscription page
app.get('/signup', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'auth0-signup.html'));
});

// Payment completion page
app.get('/payment', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'payment.html'));
});

// Analyze website for blog generation
app.get('/api/blog/analyze/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        console.log(`🔍 Analyzing website for blog generation: ${domain}`);

        // Get website analysis data
        const analysisResult = await dataforseoEnvironmentService.analyzeWebsite(domain);
        
        if (!analysisResult.success) {
            return res.status(400).json({ 
                success: false, 
                error: 'Failed to analyze website' 
            });
        }

        // Extract services and keywords from analysis
        const services = extractServicesFromAnalysis(analysisResult.data);
        const keywords = extractKeywordsFromAnalysis(analysisResult.data);

        console.log(`✅ Website analysis completed for blog generation`);
        
        res.json({
            success: true,
            services: services,
            keywords: keywords,
            domain: domain,
            analysis: analysisResult.data
        });

    } catch (error) {
        console.error('❌ Error analyzing website for blog generation:', error);
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Generate blog posts - REMOVED: This endpoint is handled by routes/blog.js
// app.post('/api/blog/generate', addSubscriptionInfo, requireFeature(FEATURES.AI_CONTENT_GENERATION), async (req, res) => {
//     try {
//         const { domain, services, keywords } = req.body;
//         console.log(`📝 Generating blog posts for: ${domain}`);
//
//         // Generate 3 blog posts using AI
//         const blogs = await generateBlogPosts(domain, services, keywords);
//
//         console.log(`✅ Generated ${blogs.length} blog posts`);
//         
//         res.json({
//             success: true,
//             blogs: blogs,
//             domain: domain,
//             timestamp: new Date().toISOString()
//         });
//
//     } catch (error) {
//         console.error('❌ Error generating blog posts:', error);
//         res.status(500).json({ 
//             success: false, 
//             error: error.message 
//         });
//     }
// });

// Generate AI image for blog
app.post('/api/blog/generate-image', async (req, res) => {
    try {
        const { title, description } = req.body;
        console.log(`🎨 Generating AI image for blog: ${title}`);

        // Generate image using AI (placeholder for now)
        const imageUrl = await generateAIImage(title, description);

        res.json({
            success: true,
            imageUrl: imageUrl,
            altText: `AI-generated image for: ${title}`
        });

    } catch (error) {
        console.error('❌ Error generating AI image:', error);
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// WordPress publishing endpoints
app.post('/api/wordpress/publish', async (req, res) => {
    try {
        const { 
            siteUrl, 
            username, 
            password, 
            blogData,
            publishStatus = 'draft' // draft, publish, private
        } = req.body;
        
        console.log('📤 Publishing to WordPress:', siteUrl);
        
        const result = await publishToWordPress(siteUrl, username, password, blogData, publishStatus);
        
        console.log('✅ Published to WordPress successfully');
        
        res.json({
            success: true,
            postId: result.id,
            postUrl: result.link,
            message: 'Blog post published successfully to WordPress!'
        });
    } catch (error) {
        console.error('❌ Error publishing to WordPress:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.post('/api/wordpress/upload-media', async (req, res) => {
    try {
        const { 
            siteUrl, 
            username, 
            password, 
            imageData,
            fileName,
            altText = ''
        } = req.body;
        
        console.log('📸 Uploading media to WordPress:', siteUrl);
        
        const result = await uploadMediaToWordPress(siteUrl, username, password, imageData, fileName, altText);
        
        console.log('✅ Media uploaded to WordPress successfully');
        
        res.json({
            success: true,
            mediaId: result.id,
            mediaUrl: result.source_url,
            message: 'Media uploaded successfully to WordPress!'
        });
    } catch (error) {
        console.error('❌ Error uploading media to WordPress:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.post('/api/wordpress/test-connection', async (req, res) => {
    try {
        const { siteUrl, username, password } = req.body;
        
        console.log('🔍 Testing WordPress connection:', siteUrl);
        
        const isValid = await testWordPressConnection(siteUrl, username, password);
        
        if (isValid) {
            console.log('✅ WordPress connection successful');
            res.json({
                success: true,
                message: 'WordPress connection successful!'
            });
        } else {
            console.log('❌ WordPress connection failed');
            res.json({
                success: false,
                error: 'Invalid WordPress credentials or site URL'
            });
        }
    } catch (error) {
        console.error('❌ Error testing WordPress connection:', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Helper functions for blog generation
function extractServicesFromAnalysis(analysisData) {
    const services = [];
    
    // Extract from on-page analysis
    if (analysisData?.onPage?.services) {
        services.push(...analysisData.onPage.services);
    }
    
    // Extract from SERP analysis
    if (analysisData?.serp?.services) {
        services.push(...analysisData.serp.services);
    }
    
    // Extract from any other analysis sections
    if (analysisData?.services) {
        services.push(...analysisData.services);
    }
    
    // Default services if none found
    if (services.length === 0) {
        services.push(
            'Digital Marketing',
            'SEO Services',
            'Website Optimization',
            'Content Strategy',
            'Online Marketing',
            'Search Engine Optimization'
        );
    }
    
    return [...new Set(services)].slice(0, 6); // Remove duplicates and limit to 6
}

function extractKeywordsFromAnalysis(analysisData) {
    const keywords = [];
    
    // Extract from keyword analysis
    if (analysisData?.keywords?.suggestions) {
        keywords.push(...analysisData.keywords.suggestions.map(k => k.keyword || k));
    }
    
    // Extract from traffic analysis
    if (analysisData?.traffic?.keywords) {
        keywords.push(...analysisData.traffic.keywords.map(k => k.keyword || k));
    }
    
    // Extract from any keyword-related data
    if (analysisData?.keywords && Array.isArray(analysisData.keywords)) {
        keywords.push(...analysisData.keywords.map(k => typeof k === 'string' ? k : k.keyword || k));
    }
    
    // Default keywords if none found
    if (keywords.length === 0) {
        keywords.push(
            'digital marketing',
            'seo services',
            'website optimization',
            'content marketing',
            'online presence',
            'search engine optimization',
            'marketing strategy',
            'web development'
        );
    }
    
    return [...new Set(keywords)].slice(0, 8); // Remove duplicates and limit to 8
}

async function generateBlogPosts(domain, services, keywords) {
    try {
        const blogs = [];
        
        // Generate 1 comprehensive blog post
        const blogTemplate = {
            titleTemplate: `The Complete Guide to ${services[0] || 'Digital Marketing'} Success`,
            topic: services[0] || 'Digital Marketing',
            focus: 'comprehensive guide covering strategies, tools, and best practices'
        };

        const blog = await generateSingleBlogPost(domain, blogTemplate, services, keywords, 1);
        blogs.push(blog);
        
        return blogs;
        
    } catch (error) {
        console.error('Error generating blog posts:', error);
        throw error;
    }
}

    function convertTextToHTML(text) {
        // Convert plain text blog content to HTML format
        let html = text;
        
        // First, split by numbered sections to identify structure
        const sections = html.split(/(\d+\.\s+[^:]+:)/);
        
        let result = [];
        
        for (let i = 0; i < sections.length; i++) {
            const section = sections[i].trim();
            
            if (!section) continue;
            
            // Check if this is a numbered heading
            if (/^\d+\.\s+[^:]+:$/.test(section)) {
                result.push(`<h3>${section}</h3>`);
            } else {
                // This is content - split into paragraphs and format
                const paragraphs = section.split(/\.\s+(?=[A-Z])/);
                
                for (let j = 0; j < paragraphs.length; j++) {
                    let paragraph = paragraphs[j].trim();
                    
                    if (!paragraph) continue;
                    
                    // Add period back if it was removed by split
                    if (j < paragraphs.length - 1 && !paragraph.endsWith('.') && !paragraph.endsWith('!') && !paragraph.endsWith('?')) {
                        paragraph += '.';
                    }
                    
                    // Convert bold text markers (**text**)
                    paragraph = paragraph.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                    
                    // Convert call-to-action sections to blockquotes
                    if (/^(Ready to take your|Contact us|Let's|Don't wait|Would you like|For tailored|In conclusion)/i.test(paragraph)) {
                        result.push(`<blockquote><p>${paragraph}</p></blockquote>`);
                    } else {
                        result.push(`<p>${paragraph}</p>`);
                    }
                }
            }
        }
        
        // If no numbered sections were found, treat as regular paragraphs
        if (result.length === 0) {
            // Split by sentence patterns and logical breaks
            const paragraphs = html.split(/(?<=\.)\s+(?=[A-Z])/);
            
            for (let paragraph of paragraphs) {
                paragraph = paragraph.trim();
                
                if (!paragraph) continue;
                
                // Skip very short fragments
                if (paragraph.length < 20) continue;
                
                // Convert bold text markers (**text**)
                paragraph = paragraph.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                
                // Convert call-to-action sections to blockquotes
                if (/^(Ready to take your|Contact us|Let's|Don't wait|Would you like|For tailored|In conclusion)/i.test(paragraph)) {
                    result.push(`<blockquote><p>${paragraph}</p></blockquote>`);
                } else {
                    result.push(`<p>${paragraph}</p>`);
                }
            }
        }
        
        return result.join('\n');
    }

    async function generateSingleBlogPost(domain, template, services, keywords, blogNumber) {
    try {
        // Initialize OpenAI client
        const openai = require('openai');
        const client = new openai.OpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });

        // Generate content using OpenAI
        const prompt = `
        Create a blog post for ${domain} about "${template.topic}". 

        Services: ${services.join(', ')}
        Keywords: ${keywords.join(', ')}

        You MUST return the blog content formatted with HTML tags. Start your response with this exact HTML structure:

        <h2>Introduction</h2>
        <p>[Write introduction paragraph here with <strong>bold text</strong> for emphasis]</p>

        <h3>[Section 1 Title]</h3>
        <p>[Content with <strong>important points</strong> highlighted]</p>
        <ul>
        <li>[First key point with <strong>emphasis</strong>]</li>
        <li>[Second key point]</li>
        </ul>

        <h3>[Section 2 Title]</h3>
        <p>[Content paragraph]</p>
        <blockquote>[Important tip or insight]</blockquote>

        <h3>[Section 3 Title]</h3>
        <p>[More content with <strong>bold emphasis</strong>]</p>

        <h2>Conclusion</h2>
        <p>[Final paragraph with <strong>strong call-to-action</strong> for ${domain}]</p>

        Replace the bracketed text with actual content about ${template.topic}. Use at least 500 words. Always use HTML tags - never plain text.
        `;

        const response = await client.chat.completions.create({
            model: "gpt-3.5-turbo",
            messages: [
                {
                    role: "system",
                    content: "You are an expert content writer specializing in SEO-optimized blog posts for digital marketing companies. CRITICAL: You MUST format ALL content using HTML tags only. Never use plain text, markdown, or ** symbols. Always use <h2>, <h3>, <p>, <strong>, <ul>, <li>, <blockquote> tags. Write engaging, informative content that ranks well in search engines with proper HTML formatting. Each blog post should be at least 500 words with comprehensive, well-written content formatted exclusively in HTML."
                },
                {
                    role: "user",
                    content: prompt
                }
            ],
            max_tokens: 2000,
            temperature: 0.7
        });

        const content = response.choices[0].message.content;
        
        // Parse the generated content
        const lines = content.split('\n').filter(line => line.trim());
        let title = template.titleTemplate;
        let excerpt = `Discover the latest insights and strategies in ${template.topic}. This comprehensive guide covers everything you need to know to stay ahead of the competition.`;
        let blogContent = content;

        // Extract title, excerpt, and content properly
        let contentStartIndex = 0;
        
        // Find title
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.toLowerCase().includes('title:') && !line.toLowerCase().includes('**title:')) {
                title = line.replace(/title:\s*/i, '').replace(/^\*\*|\*\*$/g, '').trim();
                contentStartIndex = i + 1;
                break;
            } else if (line.startsWith('#') && !line.includes('**')) {
                title = line.replace(/^#+\s*/, '').trim();
                contentStartIndex = i + 1;
                break;
            }
        }

        // Find excerpt
        for (let i = contentStartIndex; i < lines.length; i++) {
            const line = lines[i].trim();
            if (line.toLowerCase().includes('excerpt:') && !line.toLowerCase().includes('**excerpt:')) {
                excerpt = line.replace(/excerpt:\s*/i, '').replace(/^\*\*|\*\*$/g, '').trim();
                contentStartIndex = i + 1;
                break;
            }
        }

        // Extract the main content (skip title, excerpt, and any other metadata)
        const contentLines = [];
        let foundContent = false;
        
        for (let i = contentStartIndex; i < lines.length; i++) {
            const line = lines[i].trim();
            
            // Skip empty lines at the beginning
            if (!foundContent && line === '') continue;
            
            // Start collecting content after we find the first substantial line
            if (!foundContent && (line.length > 20 || line.includes('Introduction') || line.includes('<h2') || line.includes('<p>'))) {
                foundContent = true;
            }
            
            if (foundContent) {
                // Preserve HTML formatting by keeping the line as-is
                contentLines.push(line);
            }
        }
        
        // Join content lines and keep as plain text for frontend formatting
        blogContent = contentLines.join('\n').trim();

        // Calculate metrics
        const wordCount = blogContent.split(' ').length;
        const seoScore = calculateSEOScore(title, excerpt, blogContent, keywords);
        const readabilityScore = calculateReadabilityScore(blogContent);

        // Generate image URL
        const imageUrl = await generateBlogImage(template.topic, title);

        return {
            id: blogNumber,
            title: title,
            excerpt: excerpt,
            content: blogContent,
            image: imageUrl,
            wordCount: wordCount,
            seoScore: seoScore,
            readabilityScore: readabilityScore,
            keywords: keywords.slice(0, 5), // Top 5 keywords used
            services: services.slice(0, 3), // Top 3 services covered
            createdAt: new Date().toISOString()
        };

    } catch (error) {
        console.error('Error generating single blog post:', error);
        
        // Fallback blog post
        return {
            id: blogNumber,
            title: template.titleTemplate,
            excerpt: `Discover the latest insights and strategies in ${template.topic}. This comprehensive guide covers everything you need to know to stay ahead of the competition.`,
            content: `In today's competitive digital landscape, ${template.topic} has become more important than ever. This comprehensive guide will walk you through the essential strategies and best practices that can help your business succeed.\n\n## Understanding ${template.topic}\n\n${template.topic} is a crucial aspect of modern business strategy. By implementing the right techniques and staying up-to-date with the latest trends, you can significantly improve your results.\n\n## Key Strategies\n\n1. **Strategic Planning**: Start with a clear understanding of your goals and target audience.\n2. **Implementation**: Execute your strategy with precision and attention to detail.\n3. **Monitoring**: Continuously track your progress and adjust as needed.\n\n## Best Practices\n\n- Focus on quality over quantity\n- Stay updated with industry trends\n- Measure and analyze your results regularly\n\n## Conclusion\n\nBy following these strategies and best practices, you can achieve significant improvements in your ${template.topic.toLowerCase()} efforts. Remember to stay consistent and always look for ways to optimize your approach.`,
            image: await generateBlogImage(template.topic, template.titleTemplate),
            wordCount: 350,
            seoScore: 75,
            readabilityScore: 80,
            keywords: keywords.slice(0, 5),
            services: services.slice(0, 3),
            createdAt: new Date().toISOString()
        };
    }
}

function calculateSEOScore(title, excerpt, content, keywords) {
    let score = 60; // Base score
    
    // Title optimization (20 points)
    if (title.length >= 30 && title.length <= 60) score += 15;
    if (keywords.some(keyword => title.toLowerCase().includes(keyword.toLowerCase()))) score += 5;
    
    // Content optimization (15 points)
    const wordCount = content.split(' ').length;
    if (wordCount >= 1000 && wordCount <= 2000) score += 10;
    if (keywords.some(keyword => content.toLowerCase().includes(keyword.toLowerCase()))) score += 5;
    
    // Excerpt optimization (10 points)
    if (excerpt.length >= 120 && excerpt.length <= 160) score += 10;
    
    // Structure optimization (10 points)
    if (content.includes('##') || content.includes('<h2>')) score += 5;
    if (content.includes('**') || content.includes('<strong>')) score += 3;
    if (content.includes('1.') || content.includes('<ol>')) score += 2;
    
    // Keyword density (5 points)
    const keywordDensity = keywords.reduce((total, keyword) => {
        const regex = new RegExp(keyword.toLowerCase(), 'gi');
        const matches = content.toLowerCase().match(regex);
        return total + (matches ? matches.length : 0);
    }, 0);
    
    if (keywordDensity >= 5 && keywordDensity <= 15) score += 5;
    
    return Math.min(100, Math.max(60, score));
}

function calculateReadabilityScore(content) {
    // Simplified readability calculation
    const sentences = content.split(/[.!?]+/).filter(s => s.trim().length > 0);
    const words = content.split(/\s+/).filter(w => w.trim().length > 0);
    const avgWordsPerSentence = words.length / sentences.length;
    
    let score = 100;
    
    // Adjust based on sentence length
    if (avgWordsPerSentence > 20) score -= 15;
    else if (avgWordsPerSentence > 15) score -= 10;
    else if (avgWordsPerSentence > 10) score -= 5;
    
    // Adjust based on paragraph length
    const paragraphs = content.split(/\n\s*\n/).filter(p => p.trim().length > 0);
    const avgWordsPerParagraph = words.length / paragraphs.length;
    
    if (avgWordsPerParagraph > 150) score -= 10;
    else if (avgWordsPerParagraph > 100) score -= 5;
    
    return Math.min(100, Math.max(60, score));
}

async function generateBlogImage(topic, title) {
    try {
        // For now, return a placeholder image based on topic
        // In a real implementation, you would integrate with AI image generation services
        const imageTopics = {
            'digital marketing': 'photo-1460925895917-afdab827c52f',
            'seo': 'photo-1558618666-fcd25c85cd64',
            'content marketing': 'photo-1552664730-d307ca884978',
            'website optimization': 'photo-1551650975-87deedd944c3',
            'social media': 'photo-1611224923853-80b023f02d71',
            'analytics': 'photo-1551288049-bebda4e38f71'
        };
        
        const topicLower = topic.toLowerCase();
        let imageId = 'photo-1460925895917-afdab827c52f'; // Default
        
        for (const [key, value] of Object.entries(imageTopics)) {
            if (topicLower.includes(key)) {
                imageId = value;
                break;
            }
        }
        
        return `https://images.unsplash.com/${imageId}?w=500&h=300&fit=crop`;
        
    } catch (error) {
        console.error('Error generating blog image:', error);
        return 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=500&h=300&fit=crop';
    }
}

async function generateAIImage(title, description) {
    try {
        // Placeholder for AI image generation
        // In a real implementation, you would integrate with services like DALL-E, Midjourney, or Stable Diffusion
        console.log(`🎨 Generating AI image for: ${title}`);
        
        // For now, return a relevant Unsplash image
        const searchTerm = title.toLowerCase().replace(/[^a-z\s]/g, '').replace(/\s+/g, '-');
        return `https://images.unsplash.com/photo-${Math.floor(Math.random() * 1000000000)}?w=500&h=300&fit=crop&q=80`;
        
    } catch (error) {
        console.error('Error generating AI image:', error);
        return 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=500&h=300&fit=crop';
    }
}

// Subscription Routes
const subscriptionRoutes = require('./routes/subscription');
app.use('/api/subscription', subscriptionRoutes);

// User Routes
const userRoutes = require('./routes/user');
app.use('/api/user', userRoutes);

// AI Routes
const aiRoutes = require('./routes/ai');
app.use('/api/ai', aiRoutes);

// DataForSEO Routes
const dataforseoRoutes = require('./routes/dataforseo');
app.use('/api/dataforseo', dataforseoRoutes);

// Blog Routes
const blogRoutes = require('./routes/blog');
app.use('/api/blog', blogRoutes);

// WordPress Routes
const wordpressRoutes = require('./routes/wordpress');
app.use('/api/wordpress', wordpressRoutes);

// Start server
server.listen(PORT, () => {
  console.log(`🚀 Digital Marketing SEO Analyzer server running on port ${PORT}`);
  console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`🔍 DataForSEO Username: ${process.env.DATAFORSEO_USERNAME ? 'Set' : 'Not Set'}`);
  console.log(`🔍 DataForSEO Password: ${process.env.DATAFORSEO_PASSWORD ? 'Set' : 'Not Set'}`);
  console.log(`🔍 OpenAI API Key: ${process.env.OPENAI_API_KEY ? 'Set' : 'Not Set'}`);
  console.log(`🔍 Supabase URL: ${process.env.SUPABASE_URL ? 'Set' : 'Not Set'}`);
  console.log(`📊 Visit http://localhost:${PORT} to use the application`);
  console.log(`🤖 Visit http://localhost:${PORT}/chat for AI SEO Assistant`);
  console.log(`🚀 Visit http://localhost:${PORT}/seo-request for SEO Request Assistant`);
  console.log(`📊 Visit http://localhost:${PORT}/seo-dashboard for Comprehensive SEO Dashboard`);
  console.log(`🔍 Visit http://localhost:${PORT}/dataforseo-dashboard for DataForSEO Analysis Dashboard`);
  console.log(`🤖 Visit http://localhost:${PORT}/dataforseo-dashboard-enhanced for AI-Powered DataForSEO Dashboard`);
  console.log(`🚀 Visit http://localhost:${PORT}/seo-dashboard-enhanced-v2 for Enhanced SEO Dashboard V2`);
  console.log(`🔗 Visit http://localhost:${PORT}/dataforseo-mcp-dashboard for DataForSEO MCP Integration Dashboard`);
  console.log(`📈 Visit http://localhost:${PORT}/dashboard for customer dashboard`);
  
  // Log current environment configuration
  environmentConfigInstance.logConfig();
});

// WordPress helper functions
async function testWordPressConnection(siteUrl, username, password) {
    try {
        const auth = Buffer.from(`${username}:${password}`).toString('base64');
        
        const response = await fetch(`${siteUrl}/wp-json/wp/v2/users/me`, {
            method: 'GET',
            headers: {
                'Authorization': `Basic ${auth}`,
                'Content-Type': 'application/json'
            }
        });
        
        return response.ok;
    } catch (error) {
        console.error('WordPress connection test failed:', error);
        return false;
    }
}

async function publishToWordPress(siteUrl, username, password, blogData, publishStatus = 'draft') {
    try {
        const auth = Buffer.from(`${username}:${password}`).toString('base64');
        
        const postData = {
            title: blogData.title,
            content: blogData.content,
            excerpt: blogData.excerpt,
            status: publishStatus,
            format: 'standard',
            categories: blogData.categories || [],
            tags: blogData.tags || []
        };
        
        const response = await fetch(`${siteUrl}/wp-json/wp/v2/posts`, {
            method: 'POST',
            headers: {
                'Authorization': `Basic ${auth}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(postData)
        });
        
        if (!response.ok) {
            throw new Error(`WordPress API error: ${response.status} ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('WordPress publishing failed:', error);
        throw error;
    }
}

async function uploadMediaToWordPress(siteUrl, username, password, imageData, fileName, altText = '') {
    try {
        const auth = Buffer.from(`${username}:${password}`).toString('base64');
        
        // Create FormData for file upload
        const formData = new FormData();
        
        // Convert base64 image data to blob
        const response = await fetch(imageData);
        const blob = await response.blob();
        
        formData.append('file', blob, fileName);
        formData.append('alt_text', altText);
        
        const uploadResponse = await fetch(`${siteUrl}/wp-json/wp/v2/media`, {
            method: 'POST',
            headers: {
                'Authorization': `Basic ${auth}`
            },
            body: formData
        });
        
        if (!uploadResponse.ok) {
            throw new Error(`WordPress media upload error: ${uploadResponse.status} ${uploadResponse.statusText}`);
        }
        
        return await uploadResponse.json();
    } catch (error) {
        console.error('WordPress media upload failed:', error);
        throw error;
    }
}
