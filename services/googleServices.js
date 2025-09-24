const { google } = require('googleapis');
const { OAuth2Client } = require('google-auth-library');
require('dotenv').config();

class GoogleServices {
  constructor() {
    this.oauth2Client = new OAuth2Client(
      process.env.GOOGLE_CLIENT_ID,
      process.env.GOOGLE_CLIENT_SECRET,
      process.env.GOOGLE_REDIRECT_URI || 'http://localhost:3000/auth/google/callback'
    );
    
    this.scopes = [
      'https://www.googleapis.com/auth/webmasters.readonly',
      'https://www.googleapis.com/auth/business.manage'
    ];
  }

  /**
   * Generate Google OAuth URL for authentication
   */
  getAuthUrl() {
    return this.oauth2Client.generateAuthUrl({
      access_type: 'offline',
      scope: this.scopes,
      prompt: 'consent'
    });
  }

  /**
   * Exchange authorization code for tokens
   */
  async getTokensFromCode(code) {
    try {
      const { tokens } = await this.oauth2Client.getToken(code);
      this.oauth2Client.setCredentials(tokens);
      return tokens;
    } catch (error) {
      console.error('Error getting tokens:', error);
      throw error;
    }
  }

  /**
   * Set credentials for API calls
   */
  setCredentials(tokens) {
    this.oauth2Client.setCredentials(tokens);
  }

  /**
   * Get Google Search Console data
   */
  async getSearchConsoleData(propertyUrl, startDate, endDate) {
    try {
      const searchconsole = google.searchconsole({ version: 'v1', auth: this.oauth2Client });
      
      // Get search analytics data
      const searchAnalytics = await searchconsole.searchanalytics.query({
        siteUrl: propertyUrl,
        requestBody: {
          startDate: startDate,
          endDate: endDate,
          dimensions: ['query', 'page', 'country', 'device'],
          rowLimit: 1000,
          startRow: 0
        }
      });

      // Get sitemaps
      const sitemaps = await searchconsole.sitemaps.list({
        siteUrl: propertyUrl
      });

      // Get URL inspection data (sample)
      const urlInspection = await searchconsole.urlInspection.index.inspect({
        requestBody: {
          inspectionUrl: propertyUrl,
          siteUrl: propertyUrl
        }
      });

      return {
        success: true,
        data: {
          searchAnalytics: searchAnalytics.data,
          sitemaps: sitemaps.data,
          urlInspection: urlInspection.data,
          propertyUrl: propertyUrl
        }
      };
    } catch (error) {
      console.error('Google Search Console API error:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get Google Business Profile data
   */
  async getBusinessProfileData(accountId) {
    try {
      const mybusiness = google.mybusinessaccountmanagement({ version: 'v1', auth: this.oauth2Client });
      
      // Get business accounts
      const accounts = await mybusiness.accounts.list();
      
      // Get business information
      const businessInfo = await mybusiness.accounts.get({
        name: `accounts/${accountId}`
      });

      // Get reviews (if available)
      const reviews = await mybusiness.accounts.locations.reviews.list({
        name: `accounts/${accountId}/locations`
      });

      return {
        success: true,
        data: {
          accounts: accounts.data,
          businessInfo: businessInfo.data,
          reviews: reviews.data,
          accountId: accountId
        }
      };
    } catch (error) {
      console.error('Google Business Profile API error:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get list of verified properties in Search Console
   */
  async getSearchConsoleProperties() {
    try {
      const searchconsole = google.searchconsole({ version: 'v1', auth: this.oauth2Client });
      const response = await searchconsole.sites.list();
      
      return {
        success: true,
        data: response.data.siteEntry || []
      };
    } catch (error) {
      console.error('Error getting Search Console properties:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Get list of business accounts
   */
  async getBusinessAccounts() {
    try {
      const mybusiness = google.mybusinessaccountmanagement({ version: 'v1', auth: this.oauth2Client });
      const response = await mybusiness.accounts.list();
      
      return {
        success: true,
        data: response.data.accounts || []
      };
    } catch (error) {
      console.error('Error getting business accounts:', error);
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Refresh access token if needed
   */
  async refreshToken(refreshToken) {
    try {
      this.oauth2Client.setCredentials({
        refresh_token: refreshToken
      });
      
      const { credentials } = await this.oauth2Client.refreshAccessToken();
      return credentials;
    } catch (error) {
      console.error('Error refreshing token:', error);
      throw error;
    }
  }
}

module.exports = GoogleServices;






