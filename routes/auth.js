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
  
  const authOptions = {
    scope: 'openid email profile'
  };
  
  // Add connection parameter if specified (e.g., google-oauth2)
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
            trial_user: false,
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

// Auth0 callback route
router.get('/callback', 
  passport.authenticate('auth0', { failureRedirect: '/login' }),
  async (req, res) => {
    try {
      // User is now authenticated and stored in session
      const user = req.user;
      const isSignup = req.session.signupMode;
      
      console.log('User authenticated:', user.email, 'Signup mode:', isSignup);
      
      // Check if this is a trial user linking their Auth0 account
      if (user.trial_user) {
        console.log('🔗 Linking trial user with Auth0 ID:', user.email);
        await auth0Service.linkTrialUserWithAuth0(user.email, user.auth0_id);
      }
      
      // Clear signup mode from session
      if (isSignup) {
        req.session.signupMode = false;
      }
      
      // Redirect based on user status and signup mode
      if (isSignup && !user.domain) {
        // New user signup - redirect to plan selection
        res.redirect('/subscription?signup=success');
      } else if (user.domain) {
        // Existing user with domain - go to dashboard
        res.redirect('/dashboard');
      } else {
        // Existing user without domain - go to onboarding
        res.redirect('/onboarding');
      }
    } catch (error) {
      console.error('Auth callback error:', error);
      res.redirect('/login?error=auth_failed');
    }
  }
);

// Logout route
router.get('/logout', (req, res) => {
  req.logout((err) => {
    if (err) {
      console.error('Logout error:', err);
      return res.redirect('/login?error=logout_failed');
    }
    
    // Redirect to Auth0 logout
    const logoutURL = `https://${process.env.AUTH0_DOMAIN}/v2/logout?` +
      `returnTo=${encodeURIComponent(process.env.AUTH0_LOGOUT_URL)}&` +
      `client_id=${process.env.AUTH0_CLIENT_ID}`;
    
    res.redirect(logoutURL);
  });
});

// Get current user info
router.get('/user', (req, res) => {
  if (req.isAuthenticated()) {
    res.json({
      authenticated: true,
      user: {
        id: req.user.id,
        email: req.user.email,
        name: req.user.name,
        picture: req.user.picture,
        domain: req.user.domain,
        business_description: req.user.business_description,
        integrations: req.user.integrations
      }
    });
  } else {
    res.json({
      authenticated: false,
      user: null
    });
  }
});

// Update user domain
router.post('/user/domain', async (req, res) => {
  try {
    if (!req.isAuthenticated()) {
      return res.status(401).json({ error: 'Not authenticated' });
    }

    const { domain } = req.body;
    
    if (!domain) {
      return res.status(400).json({ error: 'Domain is required' });
    }

    // Update user domain (multiple users can use same domain)
    const updatedUser = await auth0Service.updateUserDomain(req.user.id, domain);
    
    if (!updatedUser) {
      return res.status(500).json({ error: 'Failed to update domain' });
    }

    // Update session user
    req.user.domain = domain;

    res.json({
      success: true,
      user: updatedUser,
      message: 'Domain saved successfully!'
    });
  } catch (error) {
    console.error('Update domain error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Update user business description
router.post('/user/business', async (req, res) => {
  try {
    if (!req.isAuthenticated()) {
      return res.status(401).json({ error: 'Not authenticated' });
    }

    const { business_description } = req.body;
    
    if (!business_description) {
      return res.status(400).json({ error: 'Business description is required' });
    }

    // Update user business description
    const { data: updatedUser, error } = await auth0Service.supabase
      .from('users')
      .update({
        business_description: business_description,
        updated_at: new Date().toISOString()
      })
      .eq('id', req.user.id)
      .select()
      .single();

    if (error) {
      console.error('Error updating business description:', error);
      return res.status(500).json({ error: 'Failed to update business description' });
    }

    // Update session user
    req.user.business_description = business_description;

    res.json({
      success: true,
      user: updatedUser
    });
  } catch (error) {
    console.error('Update business description error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Check authentication status
router.get('/status', (req, res) => {
  res.json({
    authenticated: req.isAuthenticated(),
    user: req.isAuthenticated() ? {
      id: req.user.id,
      email: req.user.email,
      name: req.user.name,
      domain: req.user.domain
    } : null
  });
});

// Create user account using Auth0 Management API
router.post('/signup', async (req, res) => {
  try {
    const { fullName, email, password } = req.body;
    
    if (!fullName || !email || !password) {
      return res.status(400).json({
        success: false,
        error: 'Full name, email, and password are required'
      });
    }
    
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
    
        // Create user in our Supabase database
        const { data: newUser, error: createError } = await auth0Service.supabase
          .from('users')
          .insert({
            email: email,
            name: fullName,
            auth0_id: auth0User.user_id,
            trial_user: false,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          })
          .select()
          .single();
    
    if (createError) {
      console.error('Error creating user in Supabase:', createError);
      return res.status(500).json({
        success: false,
        error: 'Failed to create user account'
      });
    }
    
    res.json({
      success: true,
      user: {
        id: newUser.id,
        email: newUser.email,
        name: newUser.name,
        auth0_id: newUser.auth0_id
      },
      message: 'Account created successfully. You can now select a plan.'
    });
    
  } catch (error) {
    console.error('Signup error:', error);
    
    // Handle specific Auth0 errors
    if (error.response && error.response.data) {
      const auth0Error = error.response.data;
      if (auth0Error.code === 'user_exists') {
        return res.status(400).json({
          success: false,
          error: 'An account with this email already exists'
        });
      }
    }
    
    res.status(500).json({
      success: false,
      error: 'Internal server error'
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
