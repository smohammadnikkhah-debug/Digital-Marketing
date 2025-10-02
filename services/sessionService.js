const jwt = require('jsonwebtoken');
const auth0Service = require('./auth0Service');

class SessionService {
  constructor() {
    this.jwtSecret = process.env.JWT_SECRET || 'your-secret-key-change-in-production';
    this.sessionExpiry = '24h'; // 24 hours
  }

  /**
   * Create a JWT token for a user session
   * @param {Object} user - User object from database
   * @returns {string} JWT token
   */
  createToken(user) {
    const payload = {
      userId: user.id,
      email: user.email,
      name: user.name,
      domain: user.domain,
      auth0Id: user.auth0_id,
      iat: Math.floor(Date.now() / 1000)
    };

    return jwt.sign(payload, this.jwtSecret, { 
      expiresIn: this.sessionExpiry,
      issuer: 'mozarex-app'
    });
  }

  /**
   * Verify and decode a JWT token
   * @param {string} token - JWT token
   * @returns {Object|null} Decoded token payload or null if invalid
   */
  verifyToken(token) {
    try {
      return jwt.verify(token, this.jwtSecret);
    } catch (error) {
      console.error('JWT verification failed:', error.message);
      return null;
    }
  }

  /**
   * Extract token from request headers
   * @param {Object} req - Express request object
   * @returns {string|null} Token or null if not found
   */
  extractToken(req) {
    // Check Authorization header
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Bearer ')) {
      return authHeader.substring(7);
    }

    // Check cookies
    if (req.cookies && req.cookies.authToken) {
      return req.cookies.authToken;
    }

    // Check query parameter (for testing)
    if (req.query.token) {
      return req.query.token;
    }

    return null;
  }

  /**
   * Middleware to authenticate requests
   * @param {Object} req - Express request object
   * @param {Object} res - Express response object
   * @param {Function} next - Next middleware function
   */
  async authenticate(req, res, next) {
    try {
      const token = this.extractToken(req);
      
      if (!token) {
        return res.status(401).json({ 
          authenticated: false, 
          error: 'No authentication token provided' 
        });
      }

      const decoded = this.verifyToken(token);
      
      if (!decoded) {
        return res.status(401).json({ 
          authenticated: false, 
          error: 'Invalid or expired token' 
        });
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
    } catch (error) {
      console.error('Authentication middleware error:', error);
      res.status(500).json({ 
        authenticated: false, 
        error: 'Authentication error' 
      });
    }
  }

  /**
   * Optional authentication middleware (doesn't fail if no token)
   * @param {Object} req - Express request object
   * @param {Object} res - Express response object
   * @param {Function} next - Next middleware function
   */
  async optionalAuthenticate(req, res, next) {
    try {
      const token = this.extractToken(req);
      
      if (token) {
        const decoded = this.verifyToken(token);
        
        if (decoded) {
          req.user = {
            id: decoded.userId,
            email: decoded.email,
            name: decoded.name,
            domain: decoded.domain,
            auth0Id: decoded.auth0Id
          };
        }
      }

      next();
    } catch (error) {
      console.error('Optional authentication middleware error:', error);
      next(); // Continue even if authentication fails
    }
  }

  /**
   * Get current user from token
   * @param {string} token - JWT token
   * @returns {Object|null} User object or null
   */
  async getCurrentUser(token) {
    try {
      const decoded = this.verifyToken(token);
      
      if (!decoded) {
        return null;
      }

      // Get fresh user data from database
      const user = await auth0Service.getUserById(decoded.userId);
      
      return user;
    } catch (error) {
      console.error('Get current user error:', error);
      return null;
    }
  }

  /**
   * Refresh user session with fresh data
   * @param {string} token - Current JWT token
   * @returns {Object|null} New token or null if refresh fails
   */
  async refreshSession(token) {
    try {
      const decoded = this.verifyToken(token);
      
      if (!decoded) {
        return null;
      }

      // Get fresh user data
      const user = await auth0Service.getUserById(decoded.userId);
      
      if (!user) {
        return null;
      }

      // Create new token with fresh data
      return this.createToken(user);
    } catch (error) {
      console.error('Refresh session error:', error);
      return null;
    }
  }
}

module.exports = new SessionService();
