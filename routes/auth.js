const express = require('express');
const passport = require('passport');
const router = express.Router();
const Auth0Service = require('../services/auth0Service');
const axios = require('axios');

// Initialize Auth0 service
const auth0Service = new Auth0Service();

// Auth0 login route (for Universal Login)
router.get('/login', (req, res, next) => {
  const isSignup = req.query.signup === 'true';
  const connection = req.query.connection;
  
  // Store signup mode in session
  if (isSignup) {
    req.session.signupMode = true;
  }
  
  // IMPORTANT: tell Auth0 to show the Signup screen when signup=true
  const authOptions = {
    scope: 'openid email profile',
    ...(isSignup ? { screen_hint: 'signup' } : {})
  };
  
  if (connection) {
    authOptions.connection = connection;
  }
  
  passport.authenticate('auth0', authOptions)(req, res, next);
});

// Form-based login route with Auth0 API validation
router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    
    if (!email || !password) {
      return res.status(400).json({
        success: false,
        message: 'Email and password are required'
      });
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return res.status(400).json({
        success: false,
        message: 'Please enter a valid email address'
      });
    }

    // Validate credentials with Auth0 Authentication API
    try {
      // First try with explicit connection
      let authResponse;
      try {
        authResponse = await axios.post(`https://${process.env.AUTH0_DOMAIN}/oauth/token`, {
          grant_type: 'password',
          username: email,
          password: password,
          audience: process.env.AUTH0_AUDIENCE || `https://${process.env.AUTH0_DOMAIN}/api/v2/`,
          client_id: process.env.AUTH0_CLIENT_ID,
          client_secret: process.env.AUTH0_CLIENT_SECRET,
          scope: 'openid email profile',
          connection: 'Username-Password-Authentication'
        });
      } catch (connectionError) {
        // If connection error, try without explicit connection
        if (connectionError.response?.data?.error === 'server_error' && 
            connectionError.response?.data?.error_description?.includes('default connection')) {
          console.log('Trying without explicit connection...');
          authResponse = await axios.post(`https://${process.env.AUTH0_DOMAIN}/oauth/token`, {
            grant_type: 'password',
            username: email,
            password: password,
            audience: process.env.AUTH0_AUDIENCE || `https://${process.env.AUTH0_DOMAIN}/api/v2/`,
            client_id: process.env.AUTH0_CLIENT_ID,
            client_secret: process.env.AUTH0_CLIENT_SECRET,
            scope: 'openid email profile'
          });
        } else {
          throw connectionError;
        }
      }

      // Get user info from Auth0
      const userInfoResponse = await axios.get(`https://${process.env.AUTH0_DOMAIN}/userinfo`, {
        headers: {
          'Authorization': `Bearer ${authResponse.data.access_token}`
        }
      });

      const auth0User = userInfoResponse.data;
      
      // Check if user exists in our database, create if not
      let user = await auth0Service.getUserByEmail(email);
      if (!user) {
        // Create user in our database
        const { data: newUser, error: createError } = await auth0Service.supabase
          .from('users')
          .insert({
            email: email,
            name: auth0User.name || email,
            auth0_id: auth0User.sub,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .select()
          .single();

        if (createError) {
          console.error('Error creating user in Supabase:', createError);
          return res.status(500).json({
            success: false,
            message: 'Failed to create user account'
          });
        }
        user = newUser;
      } else {
        // Update Auth0 ID if not set
        if (!user.auth0_id) {
          await auth0Service.supabase
            .from('users')
            .update({
              auth0_id: auth0User.sub,
              updated_at: new Date().toISOString()
            })
            .eq('id', user.id);
          user.auth0_id = auth0User.sub;
        }
      }

      // Create session for the user
      req.login(user, (err) => {
        if (err) {
          console.error('Session creation error:', err);
          return res.status(500).json({
            success: false,
            message: 'Failed to create user session'
          });
        }

        res.json({
          success: true,
          message: 'Login successful',
          user: {
            id: user.id,
            email: user.email,
            name: user.name,
            domain: user.domain
          }
        });
      });

    } catch (authError) {
      console.error('Auth0 authentication error:', authError.response?.data || authError.message);
      
      if (authError.response?.status === 401) {
        return res.status(401).json({
          success: false,
          message: 'Invalid email or password'
        });
      } else if (authError.response?.status === 403) {
        return res.status(403).json({
          success: false,
          message: 'Account access denied. Please contact support.'
        });
      } else if (authError.response?.data?.error === 'server_error' && 
                 authError.response?.data?.error_description?.includes('default connection')) {
        return res.status(500).json({
          success: false,
          message: 'Auth0 configuration error. Please enable Resource Owner Password Grant in Auth0 Dashboard.'
        });
      } else if (authError.response?.data?.error === 'unsupported_grant_type') {
        return res.status(500).json({
          success: false,
          message: 'Password grant not enabled. Please enable "Password" grant type in Auth0 Dashboard.'
        });
      } else {
        return res.status(500).json({
          success: false,
          message: 'Authentication service temporarily unavailable'
        });
      }
    }

  } catch (error) {
    console.error('Login error:', error);
    res.status(500).json({
      success: false,
      message: 'An error occurred during login'
    });
  }
});

// Google login route
router.get('/google', (req, res) => {
  const authOptions = {
    scope: 'openid email profile',
    connection: 'google-oauth2'
  };
  
  passport.authenticate('auth0', authOptions)(req, res);
});

// Password reset route
router.get('/reset-password', (req, res) => {
  const email = req.query.email;
  
  if (!email) {
    return res.redirect('/login?error=email_required');
  }

  // Redirect to Auth0 password reset with email pre-filled
  const resetURL = `https://${process.env.AUTH0_DOMAIN}/v2/change_password?` +
    `client_id=${process.env.AUTH0_CLIENT_ID}&` +
    `email=${encodeURIComponent(email)}&` +
    `connection=Username-Password-Authentication`;

  res.redirect(resetURL);
});

// Auth0 callback route - removed Passport.js implementation
// Now handled by server.js directly

// Logout route
router.get('/logout', (req, res) => {
  // Clear the session cookie
  res.clearCookie('authToken');
  
  // Clear session data
  if (req.session) {
    req.session.destroy();
  }
  
  // Prepare Auth0 domain (handle both with and without https://)
  let auth0Domain = process.env.AUTH0_DOMAIN || 'login.mozarex.com';
  if (auth0Domain.startsWith('https://')) {
    auth0Domain = auth0Domain.replace('https://', '');
  }
  if (auth0Domain.startsWith('http://')) {
    auth0Domain = auth0Domain.replace('http://', '');
  }
  
  // Set return URL (where user goes after logout)
  // This should be your app's homepage, not the Auth0 logout endpoint
  const returnToURL = process.env.AUTH0_LOGOUT_REDIRECT || 'https://mozarex.com';
  
  // Build Auth0 logout URL
  const logoutURL = `https://${auth0Domain}/v2/logout?` +
    `returnTo=${encodeURIComponent(returnToURL)}&` +
    `client_id=${process.env.AUTH0_CLIENT_ID}`;
  
  console.log('🚪 Logging out, redirecting to:', logoutURL);
  
  res.redirect(logoutURL);
});

// Get current user info
router.get('/user', async (req, res) => {
  try {
    const sessionService = require('../services/sessionService');
    const token = sessionService.extractToken(req);
    
    if (!token) {
      return res.json({
        authenticated: false,
        user: null
      });
    }

    const decoded = sessionService.verifyToken(token);
    
    if (!decoded) {
      return res.json({
        authenticated: false,
        user: null
      });
    }

    // Get fresh user data from database
    const user = await auth0Service.getUserById(decoded.userId);
    
    if (!user) {
      return res.json({
        authenticated: false,
        user: null
      });
    }

    // Get customer data if customer_id exists
    let customerData = null;
    if (user.customer_id) {
      customerData = await auth0Service.getCustomerById(user.customer_id);
    }

    res.json({
      authenticated: true,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        domain: user.domain,
        company: customerData?.company_name || user.company || '',
        business_description: customerData?.business_description || user.business_description || '',
        plan: user.plan || customerData?.plan_id || 'basic',
        customer_id: user.customer_id
      }
    });
  } catch (error) {
    console.error('Error getting user info:', error);
    res.status(500).json({
      authenticated: false,
      user: null,
      error: 'Failed to get user info'
    });
  }
});

// Update user domain
router.post('/user/domain', async (req, res) => {
  try {
    const sessionService = require('../services/sessionService');
    const token = sessionService.extractToken(req);
    
    if (!token) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    const decoded = sessionService.verifyToken(token);
    
    if (!decoded) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    const { domain } = req.body;

    if (!domain) {
      return res.status(400).json({ error: 'Domain is required' });
    }

    // Update user domain in database
    const result = await auth0Service.updateUserDomain(decoded.userId, domain);
    
    if (result) {
      res.json({ success: true, message: 'Domain updated successfully' });
    } else {
      res.status(500).json({ error: 'Failed to update domain' });
    }
  } catch (error) {
    console.error('Update domain error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Update user business description
router.post('/user/business', async (req, res) => {
  try {
    const sessionService = require('../services/sessionService');
    const token = sessionService.extractToken(req);
    
    if (!token) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    const decoded = sessionService.verifyToken(token);
    
    if (!decoded) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    const { business_description } = req.body;
    
    if (!business_description) {
      return res.status(400).json({ error: 'Business description is required' });
    }

    // Update user business description in database
    const result = await auth0Service.updateUserBusinessDescription(decoded.userId, business_description);
    
    if (result) {
      res.json({ success: true, message: 'Business description updated successfully' });
    } else {
      res.status(500).json({ error: 'Failed to update business description' });
    }
  } catch (error) {
    console.error('Update business description error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Check authentication status
router.get('/status', async (req, res) => {
  try {
    const sessionService = require('../services/sessionService');
    const token = sessionService.extractToken(req);
    
    if (!token) {
      return res.json({
        authenticated: false,
        user: null
      });
    }

    const decoded = sessionService.verifyToken(token);
    
    if (!decoded) {
      return res.json({
        authenticated: false,
        user: null
      });
    }

    res.json({
      authenticated: true,
      user: {
        id: decoded.userId,
        email: decoded.email,
        name: decoded.name,
        domain: decoded.domain
      }
    });
  } catch (error) {
    console.error('Auth status check error:', error);
    res.json({
      authenticated: false,
      user: null
    });
  }
});

// Create user account using Auth0 Management API
router.post('/signup', async (req, res) => {
  try {
    const { fullName, email, password, plan } = req.body;
    
    if (!fullName || !email || !password) {
      return res.status(400).json({
        success: false,
        error: 'Full name, email, and password are required'
      });
    }
    
    // Validate plan selection (now accepts Stripe product IDs)
    const validPlans = ['basic', 'pro', 'business']; // Keep legacy support
    const selectedPlan = plan || 'basic'; // Default to basic if no plan specified
    
    // For now, we'll store the plan as-is (could be Stripe product ID or legacy plan name)
    // TODO: Add validation for Stripe product IDs if needed
    
    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return res.status(400).json({
        success: false,
        error: 'Please enter a valid email address'
      });
    }
    
    // Validate password strength
    if (password.length < 8) {
      return res.status(400).json({
        success: false,
        error: 'Password must be at least 8 characters long'
      });
    }
    
    // Check if user already exists in our database
    const existingUser = await auth0Service.getUserByEmail(email);
    if (existingUser) {
      return res.status(400).json({
        success: false,
        error: 'An account with this email already exists'
      });
    }
    
    // Get Auth0 Management API access token
    const managementToken = await getAuth0ManagementToken();
    
    // Create user in Auth0 using Management API
    const auth0User = await createAuth0User(managementToken, {
      email: email,
      password: password,
      name: fullName,
      connection: 'Username-Password-Authentication',
      email_verified: false
    });
    
        // Create customer record first
        const customer = await auth0Service.createCustomer({
          email: email,
          name: fullName
        }, selectedPlan);

        if (!customer) {
          console.error('Failed to create customer record');
          return res.status(500).json({
            success: false,
            error: 'Failed to create customer account'
          });
        }

        // Create user in our Supabase database
        const { data: newUser, error: createError } = await auth0Service.supabase
          .from('users')
          .insert({
            id: auth0User.user_id, // Use Auth0 user ID as primary key
            email: email,
            name: fullName,
            auth0_id: auth0User.user_id,
            customer_id: customer.id, // Link user to customer
            plan: selectedPlan,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .select()
          .single();
    
    if (createError) {
      console.error('Error creating user in Supabase:', createError);
      console.error('Auth0 user created:', auth0User);
      console.error('Attempted user data:', {
        id: auth0User.user_id,
        email: email,
        name: fullName,
        auth0_id: auth0User.user_id
      });
      return res.status(500).json({
        success: false,
        error: 'Failed to create user account',
        details: createError.message
      });
    }
    
    res.json({
      success: true,
      user: {
        id: newUser.id,
        email: newUser.email,
        name: newUser.name,
        auth0_id: newUser.auth0_id,
        plan: selectedPlan // Return the selected plan from request
      },
      message: 'Account created successfully. Welcome to Mozarex AI!'
    });
    
  } catch (error) {
    console.error('Signup error:', error);
    console.error('Error stack:', error.stack);
    
    // Handle specific Auth0 errors
    if (error.response && error.response.data) {
      const auth0Error = error.response.data;
      console.error('Auth0 error details:', auth0Error);
      
      // Handle user already exists error (409 Conflict)
      if (error.response.status === 409 && auth0Error.message === 'The user already exists.') {
        return res.status(400).json({
          success: false,
          error: 'An account with this email already exists'
        });
      }
      
      // Handle other Auth0 errors
      if (auth0Error.code === 'user_exists') {
        return res.status(400).json({
          success: false,
          error: 'An account with this email already exists'
        });
      }
    }
    
    res.status(500).json({
      success: false,
      error: 'Internal server error',
      details: error.message
    });
  }
});

// Get Auth0 Management API access token
async function getAuth0ManagementToken() {
  try {
    const response = await axios.post(`https://${process.env.AUTH0_DOMAIN}/oauth/token`, {
      client_id: process.env.AUTH0_CLIENT_ID,
      client_secret: process.env.AUTH0_CLIENT_SECRET,
      audience: `https://${process.env.AUTH0_DOMAIN}/api/v2/`,
      grant_type: 'client_credentials'
    });
    
    return response.data.access_token;
  } catch (error) {
    console.error('Error getting Auth0 management token:', error);
    throw new Error('Failed to authenticate with Auth0 Management API');
  }
}

// Create user in Auth0 using Management API
async function createAuth0User(accessToken, userData) {
  try {
    const response = await axios.post(
      `https://${process.env.AUTH0_DOMAIN}/api/v2/users`,
      userData,
      {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      }
    );
    
    return response.data;
  } catch (error) {
    console.error('Error creating Auth0 user:', error);
    throw error;
  }
}

module.exports = router;
