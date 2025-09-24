# Auth0 Integration Setup Guide

## Overview
This guide will help you complete the Auth0 integration for your Mozarex SEO Dashboard. The integration includes user authentication, signup/login, and user data storage in Supabase.

## Files Created/Modified

### New Files Created:
1. `services/auth0Service.js` - Auth0 service for user management
2. `routes/auth.js` - Auth0 authentication routes
3. `frontend/login.html` - Modern login/signup page
4. `frontend/onboarding-auth0.html` - Auth0-integrated onboarding flow

### Modified Files:
1. `package.json` - Added Auth0 dependencies
2. `env.development` - Added Auth0 configuration variables
3. `supabase-schema.sql` - Updated users table with Auth0 fields
4. `server.js` - Added Auth0 middleware and routes

## Required Auth0 Configuration

### 1. Create Auth0 Application
1. Go to [Auth0 Dashboard](https://manage.auth0.com/)
2. Create a new "Single Page Application"
3. Note down your Domain, Client ID, and Client Secret

### 2. Configure Auth0 Application Settings
Set these URLs in your Auth0 application settings:
- **Allowed Callback URLs**: `http://localhost:3000/auth/callback`
- **Allowed Logout URLs**: `http://localhost:3000`
- **Allowed Web Origins**: `http://localhost:3000`
- **Allowed Origins (CORS)**: `http://localhost:3000`

### 3. Update Environment Variables
Replace the placeholder values in `env.development` with your Auth0 credentials:

```env
# Auth0 Configuration (Development)
AUTH0_DOMAIN=your-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id-here
AUTH0_CLIENT_SECRET=your-client-secret-here
AUTH0_CALLBACK_URL=http://localhost:3000/auth/callback
AUTH0_LOGOUT_URL=http://localhost:3000
AUTH0_SESSION_SECRET=your-super-secret-session-key-change-this-in-production
```

**Important**: Change the `AUTH0_SESSION_SECRET` to a strong, random string in production.

## Database Schema Update

The Supabase users table has been updated to include Auth0 integration fields:

```sql
-- Updated users table with Auth0 fields
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  auth0_id TEXT UNIQUE, -- Auth0 user ID
  email TEXT UNIQUE,
  name TEXT,
  picture TEXT,
  domain TEXT UNIQUE,
  business_description TEXT,
  integrations JSONB DEFAULT '{}',
  analysis_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

Run the updated `supabase-schema.sql` in your Supabase SQL editor to apply these changes.

## How the Auth0 Flow Works

### 1. User Authentication Flow
1. User visits `/` → redirects to `/login` if not authenticated
2. User clicks "Sign in with Auth0" → redirects to Auth0 login
3. Auth0 handles authentication → redirects back to `/auth/callback`
4. Server creates/updates user in Supabase database
5. User is redirected to `/onboarding` (if no domain) or `/dashboard` (if domain exists)

### 2. User Data Storage
- Auth0 user profile data is automatically stored in Supabase
- User can complete onboarding by adding domain and business description
- All user data is linked via Auth0 ID for future sessions

### 3. Protected Routes
These routes now require authentication:
- `/dashboard` - Main dashboard
- `/onboarding` - Onboarding flow
- All API endpoints can be protected by adding `requireAuth` middleware

## Testing the Integration

### 1. Start the Server
```bash
npm start
```

### 2. Test Authentication Flow
1. Visit `http://localhost:3000`
2. Should redirect to login page
3. Click "Sign in with Auth0"
4. Complete Auth0 authentication
5. Should redirect to onboarding or dashboard

### 3. Test User Data Storage
1. Complete the onboarding flow
2. Check Supabase users table for new user record
3. Verify Auth0 ID, email, and other fields are populated

## API Endpoints

### Authentication Endpoints
- `GET /auth/login` - Initiate Auth0 login
- `GET /auth/callback` - Auth0 callback handler
- `GET /auth/logout` - Logout and redirect to Auth0 logout
- `GET /auth/user` - Get current user data
- `GET /auth/status` - Check authentication status

### User Management Endpoints
- `POST /auth/user/domain` - Update user domain
- `POST /auth/user/business` - Update business description

## Security Features

### 1. Session Management
- Secure session storage with configurable expiration
- CSRF protection through session middleware
- Secure cookies in production environment

### 2. Database Security
- Row Level Security (RLS) enabled on all tables
- Service role access for server operations
- Auth0 ID used for user identification

### 3. Route Protection
- Authentication middleware for protected routes
- Automatic redirects for unauthenticated users
- Session-based user state management

## Production Deployment

### 1. Environment Variables
Update these for production:
```env
NODE_ENV=production
AUTH0_CALLBACK_URL=https://yourdomain.com/auth/callback
AUTH0_LOGOUT_URL=https://yourdomain.com
AUTH0_SESSION_SECRET=use-a-very-strong-random-string-here
```

### 2. Auth0 Application Settings
Update your Auth0 application with production URLs:
- **Allowed Callback URLs**: `https://yourdomain.com/auth/callback`
- **Allowed Logout URLs**: `https://yourdomain.com`
- **Allowed Web Origins**: `https://yourdomain.com`

### 3. Security Considerations
- Use HTTPS in production
- Set secure session cookies
- Implement rate limiting on auth endpoints
- Monitor authentication logs

## Troubleshooting

### Common Issues
1. **"Invalid callback URL"** - Check Auth0 application settings
2. **"Session not found"** - Verify session secret configuration
3. **"User not created in database"** - Check Supabase connection and permissions
4. **"Redirect loop"** - Verify authentication middleware setup

### Debug Mode
Enable debug logs by setting:
```env
LOG_LEVEL=debug
ENABLE_DEBUG_LOGS=true
```

## Next Steps

1. **Provide your Auth0 credentials** to complete the integration
2. **Test the authentication flow** thoroughly
3. **Update production environment** when ready to deploy
4. **Customize the UI** to match your branding preferences

The Auth0 integration is now complete and ready for testing once you provide the Auth0 application credentials!
