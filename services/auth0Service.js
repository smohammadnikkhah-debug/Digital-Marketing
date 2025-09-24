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

  // Get user by email
  async getUserByEmail(email) {
    try {
      const { data: user, error } = await this.supabase
        .from('users')
        .select('*')
        .eq('email', email)
        .single();

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
          trial_user: true, // Flag to indicate this is a trial user
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
          trial_user: false, // Remove trial flag
          updated_at: new Date().toISOString()
        })
        .eq('email', email)
        .eq('trial_user', true) // Only update trial users
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
