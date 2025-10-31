const passport = require('passport');
const Auth0Strategy = require('passport-auth0');
const { createClient } = require('@supabase/supabase-js');

class Auth0Service {
  constructor() {
    this.supabase = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_SERVICE_ROLE_KEY
    );
    
    this.strategy = new Auth0Strategy(
      {
        domain: process.env.AUTH0_DOMAIN,
        clientID: process.env.AUTH0_CLIENT_ID,
        clientSecret: process.env.AUTH0_CLIENT_SECRET,
        callbackURL: process.env.AUTH0_CALLBACK_URL,
        scope: 'openid email profile'
      },
      async (accessToken, refreshToken, extraParams, profile, done) => {
        try {
          console.log('Auth0 profile received:', {
            id: profile.id,
            emails: profile.emails,
            displayName: profile.displayName,
            photos: profile.photos
          });

          // Check if user exists in Supabase
          const { data: existingUser, error: fetchError } = await this.supabase
            .from('users')
            .select('*')
            .eq('auth0_id', profile.id)
            .single();

          if (fetchError && fetchError.code !== 'PGRST116') {
            console.error('Error fetching user:', fetchError);
            return done(fetchError, null);
          }

          if (existingUser) {
            // Update existing user with latest Auth0 data
            const { data: updatedUser, error: updateError } = await this.supabase
              .from('users')
              .update({
                email: profile.emails?.[0]?.value || profile.email || '',
                name: profile.displayName || profile.name || profile.nickname || '',
                picture: profile.photos?.[0]?.value || profile.picture || '',
                updated_at: new Date().toISOString()
              })
              .eq('auth0_id', profile.id)
              .select()
              .single();

            if (updateError) {
              console.error('Error updating user:', updateError);
              return done(updateError, null);
            }

            return done(null, updatedUser);
          } else {
            // Create new user
            const { data: newUser, error: createError } = await this.supabase
              .from('users')
              .insert({
                id: profile.id, // Use Auth0 ID as primary key
                auth0_id: profile.id,
                email: profile.emails?.[0]?.value || profile.email || '',
                name: profile.displayName || profile.name || profile.nickname || '',
                picture: profile.photos?.[0]?.value || profile.picture || '',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
              })
              .select()
              .single();

            if (createError) {
              console.error('Error creating user:', createError);
              return done(createError, null);
            }

            console.log('New user created:', newUser.email);
            return done(null, newUser);
          }
        } catch (error) {
          console.error('Auth0 strategy error:', error);
          return done(error, null);
        }
      }
    );

    // Initialize passport strategy
    passport.use(this.strategy);

    // Serialize user for session
    passport.serializeUser((user, done) => {
      done(null, user.id);
    });

    // Deserialize user from session
    passport.deserializeUser(async (id, done) => {
      try {
        const { data: user, error } = await this.supabase
          .from('users')
          .select('*')
          .eq('id', id)
          .single();

        if (error) {
          console.error('Error deserializing user:', error);
          return done(error, null);
        }

        done(null, user);
      } catch (error) {
        console.error('Deserialize user error:', error);
        done(error, null);
      }
    });
  }

  // Get user by Auth0 ID
  async getUserByAuth0Id(auth0Id) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .select('*')
        .eq('auth0_id', auth0Id)
        .single();

      if (error) {
        console.error('Error fetching user by Auth0 ID:', error);
        return null;
      }

      return user;
    } catch (error) {
      console.error('Get user by Auth0 ID error:', error);
      return null;
    }
  }

  // Update user domain
  async updateUserDomain(userId, domain) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .update({
          domain: domain,
          updated_at: new Date().toISOString()
        })
        .eq('id', userId)
        .select()
        .single();

      if (error) {
        console.error('Error updating user domain:', error);
        return null;
      }

      return user;
    } catch (error) {
      console.error('Update user domain error:', error);
      return null;
    }
  }

  // Update user business description
  async updateUserBusinessDescription(userId, business_description) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .update({
          business_description: business_description,
          updated_at: new Date().toISOString()
        })
        .eq('id', userId)
        .select()
        .single();

      if (error) {
        console.error('Error updating user business description:', error);
        return null;
      }

      return user;
    } catch (error) {
      console.error('Update user business description error:', error);
      return null;
    }
  }

  // Get user by email
  async getUserByEmail(email) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .select('*')
        .eq('email', email)
        .maybeSingle(); // Use maybeSingle() instead of single() to handle 0 rows gracefully

      if (error) {
        console.error('Error fetching user by email:', error);
        return null;
      }

      return user;
    } catch (error) {
      console.error('Get user by email error:', error);
      return null;
    }
  }

  // Get user by ID
  async getUserById(userId) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .select('*')
        .eq('id', userId)
        .maybeSingle();

      if (error) {
        console.error('Error fetching user by ID:', error);
        return null;
      }

      return user;
    } catch (error) {
      console.error('Get user by ID error:', error);
      return null;
    }
  }

  // Create Supabase user (used by server.js callback)
  async createSupabaseUser(userData) {
    try {
      const userRecord = {
        id: userData.id,
        auth0_id: userData.id,
        email: userData.email,
        name: userData.name,
        picture: userData.picture,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      // Add customer_id if provided
      if (userData.customer_id) {
        userRecord.customer_id = userData.customer_id;
      }

      const { data: newUser, error } = await this.supabase
        .from('users')
        .insert(userRecord)
        .select()
        .single();

      if (error) {
        console.error('Error creating Supabase user:', error);
        return null;
      }

      return newUser;
    } catch (error) {
      console.error('Create Supabase user error:', error);
      return null;
    }
  }

  // Create customer record with plan information
  async createCustomer(userData, planId = 'basic') {
    try {
      console.log('Creating customer record for:', userData.email, 'with plan:', planId);
      
      // Calculate plan_limit based on plan_id
      // basic/starter plans = 1 website, professional = 3 websites
      let planLimit = 1; // Default to 1
      
      if (planId) {
        const planIdLower = planId.toLowerCase();
        if (planIdLower.includes('professional') || planIdLower.includes('pro') || 
            planId.includes('price_1SB8gW') || planId.includes('price_1S9kCw')) {
          planLimit = 3;
        } else if (planIdLower.includes('basic') || planIdLower.includes('starter') ||
                   planId.includes('price_1SB8Iy') || planId.includes('price_1S9k6k')) {
          planLimit = 1;
        }
      }
      
      console.log('Setting plan_limit to:', planLimit, 'for plan:', planId);
      
      const { data: newCustomer, error } = await this.supabase
        .from('customers')
        .insert({
          company_name: userData.name || userData.email.split('@')[0],
          contact_email: userData.email,
          business_description: null,
          industry: null,
          plan_id: planId,
          plan_limit: planLimit,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
        .select()
        .single();

      if (error) {
        console.error('Error creating customer:', error);
        return null;
      }

      console.log('Customer created successfully:', newCustomer.id, 'with plan_limit:', planLimit);
      return newCustomer;
    } catch (error) {
      console.error('Create customer error:', error);
      return null;
    }
  }

  // Get customer by email
  async getCustomerByEmail(email) {
    try {
      const { data: customer, error } = await this.supabase
        .from('customers')
        .select('*')
        .eq('contact_email', email)
        .maybeSingle();

      if (error) {
        console.error('Error fetching customer by email:', error);
        return null;
      }

      return customer;
    } catch (error) {
      console.error('Get customer by email error:', error);
      return null;
    }
  }

  // Get customer by ID
  async getCustomerById(customerId) {
    try {
      const { data: customer, error } = await this.supabase
        .from('customers')
        .select('*')
        .eq('id', customerId)
        .maybeSingle();

      if (error) {
        console.error('Error fetching customer by ID:', error);
        return null;
      }

      return customer;
    } catch (error) {
      console.error('Get customer by ID error:', error);
      return null;
    }
  }

  // Check if user has used trial before
  async hasUsedTrial(email) {
    try {
      const { data: customer, error } = await this.supabase
        .from('customers')
        .select('trial_used')
        .eq('contact_email', email)
        .maybeSingle();

      if (error) {
        console.error('Error checking trial usage:', error);
        return false; // Default to allowing trial if we can't check
      }

      return customer ? customer.trial_used === true : false;
    } catch (error) {
      console.error('Trial usage check error:', error);
      return false;
    }
  }

  // Mark trial as used for a customer
  async markTrialAsUsed(customerId) {
    try {
      const { error } = await this.supabase
        .from('customers')
        .update({ 
          trial_used: true,
          updated_at: new Date().toISOString()
        })
        .eq('id', customerId);

      if (error) {
        console.error('Error marking trial as used:', error);
        return false;
      }

      return true;
    } catch (error) {
      console.error('Mark trial as used error:', error);
      return false;
    }
  }

  // Create Auth0 user account for trial customer
  async createTrialUserAccount(email, name, stripeCustomerId) {
    try {
      console.log('🔧 Creating Auth0 user account for trial customer:', email);
      
      // Check if user already exists
      const existingUser = await this.getUserByEmail(email);
      if (existingUser) {
        console.log('✅ User already exists:', existingUser.email);
        return existingUser;
      }

      // Create new user in Supabase (this will be linked to Auth0 when they login)
      const { data: newUser, error: createError } = await this.supabase
        .from('users')
        .insert({
          email: email,
          name: name,
          stripe_customer_id: stripeCustomerId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
        .select()
        .single();

      if (createError) {
        console.error('❌ Error creating trial user:', createError);
        return null;
      }

      console.log('✅ Trial user account created:', newUser.email);
      return newUser;
    } catch (error) {
      console.error('❌ Create trial user account error:', error);
      return null;
    }
  }

  // Link existing trial user with Auth0 ID after login
  async linkTrialUserWithAuth0(email, auth0Id) {
    try {
      console.log('🔗 Linking trial user with Auth0 ID:', email);
      
      const { data: updatedUser, error: updateError } = await this.supabase
        .from('users')
        .update({
          auth0_id: auth0Id,
          updated_at: new Date().toISOString()
        })
        .eq('email', email)
        .select()
        .single();

      if (updateError) {
        console.error('❌ Error linking trial user with Auth0:', updateError);
        return null;
      }

      console.log('✅ Trial user linked with Auth0:', updatedUser.email);
      return updatedUser;
    } catch (error) {
      console.error('❌ Link trial user with Auth0 error:', error);
      return null;
    }
  }
}

module.exports = Auth0Service;
