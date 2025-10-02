const { createClient } = require('@supabase/supabase-js');

class DatabaseService {
  constructor() {
    this.supabase = null;
    this.memoryStorage = {}; // In-memory storage for fallback
    this.useLocalStorage = false; // Default to false, will be set by initializeDatabase
    this.initializeDatabase();
  }

  async initializeDatabase() {
    try {
      // Supabase configuration
      const supabaseUrl = process.env.SUPABASE_URL || 'https://your-project.supabase.co';
      const supabaseKey = process.env.SUPABASE_ANON_KEY || 'your-anon-key';
      
      if (supabaseUrl === 'https://your-project.supabase.co' || supabaseKey === 'your-anon-key') {
        console.log('⚠️ Supabase not configured, using local storage fallback');
        this.useLocalStorage = true;
        return;
      }

      this.supabase = createClient(supabaseUrl, supabaseKey);
      
      // Test if the users table exists
      const { error } = await this.supabase
        .from('users')
        .select('id')
        .limit(1);
      
      if (error && error.code === 'PGRST205') {
        console.log('⚠️ Users table not found in Supabase, using local storage fallback');
        this.useLocalStorage = true;
        return;
      }
      
      this.useLocalStorage = false;
      console.log('✅ Supabase database connected');
    } catch (error) {
      console.error('❌ Database initialization failed:', error);
      this.useLocalStorage = true;
    }
  }

  async waitForInitialization() {
    // Wait for initialization to complete
    let attempts = 0;
    while (this.useLocalStorage === false && this.supabase === null && attempts < 10) {
      await new Promise(resolve => setTimeout(resolve, 100));
      attempts++;
    }
  }

  async saveUserData(userData) {
    await this.waitForInitialization();
    
    try {
      if (this.useLocalStorage) {
        return this.saveToLocalStorage(userData);
      }

      // Get authenticated user's customer_id from JWT token
      let customerId = null;
      
      if (userData.req) {
        const sessionService = require('./sessionService');
        const token = sessionService.extractToken(userData.req);
        
        if (token) {
          const decoded = sessionService.verifyToken(token);
          if (decoded && decoded.userId) {
            // Get user from database to get customer_id
            const auth0Service = require('./auth0Service');
            const auth0 = new auth0Service();
            const user = await auth0.getUserById(decoded.userId);
            if (user && user.customer_id) {
              customerId = user.customer_id;
            }
          }
        }
      }

      // Use SupabaseService to create/get website with customer_id
      const supabaseService = require('./supabaseService');
      const website = await supabaseService.createOrGetWebsite(
        userData.domain, 
        userData.businessDescription, 
        customerId
      );

      if (website && website.error) {
        return { success: false, error: website.error };
      }

      return { success: true, data: website };
    } catch (error) {
      console.error('Save user data error:', error);
      
      // Fall back to local storage on any error
      console.log('⚠️ Database error, falling back to local storage');
      return this.saveToLocalStorage(userData);
    }
  }

  async getUserData(domain) {
    await this.waitForInitialization();
    
    try {
      if (this.useLocalStorage) {
        return this.getFromLocalStorage(domain);
      }

      const userId = this.generateUserId(domain);
      
      const { data, error } = await this.supabase
        .from('users')
        .select('*')
        .eq('domain', domain)
        .single();

      if (error) {
        console.error('Database get error:', error);
        
        // If the error is about missing table, fall back to local storage
        if (error.code === 'PGRST205' || error.message.includes('Could not find the table')) {
          console.log('⚠️ Users table not found, falling back to local storage');
          return this.getFromLocalStorage(domain);
        }
        
        return { success: false, error: error.message };
      }

      if (!data) {
        return { success: false, error: 'User not found' };
      }

      // Convert back to userData format
      const userData = {
        domain: data.domain,
        businessDescription: data.business_description,
        integrations: data.integrations,
        analysisData: data.analysis_data
      };

      return { success: true, data: userData };
    } catch (error) {
      console.error('Get user data error:', error);
      
      // Fall back to local storage on any error
      console.log('⚠️ Database error, falling back to local storage');
      return this.getFromLocalStorage(domain);
    }
  }

  async getAllUsers() {
    try {
      if (this.useLocalStorage) {
        return this.getAllFromLocalStorage();
      }

      const { data, error } = await this.supabase
        .from('users')
        .select('*')
        .order('updated_at', { ascending: false });

      if (error) {
        console.error('Database get all error:', error);
        
        // If the error is about missing table, fall back to local storage
        if (error.code === 'PGRST205' || error.message.includes('Could not find the table')) {
          console.log('⚠️ Users table not found, falling back to local storage');
          return this.getAllFromLocalStorage();
        }
        
        return { success: false, error: error.message };
      }

      return { success: true, data: data };
    } catch (error) {
      console.error('Get all users error:', error);
      
      // Fall back to local storage on any error
      console.log('⚠️ Database error, falling back to local storage');
      return this.getAllFromLocalStorage();
    }
  }

  // Local storage fallback methods
  saveToLocalStorage(userData) {
    try {
      const userId = this.generateUserId(userData.domain);
      const userRecord = {
        id: userId,
        domain: userData.domain,
        business_description: userData.businessDescription,
        integrations: userData.integrations,
        analysis_data: userData.analysisData,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      // Save to in-memory storage
      this.memoryStorage[userId] = userRecord;
      
      return { success: true, data: [userRecord] };
    } catch (error) {
      console.error('Local storage save error:', error);
      return { success: false, error: error.message };
    }
  }

  getFromLocalStorage(domain) {
    try {
      const userId = this.generateUserId(domain);
      const userRecord = this.memoryStorage[userId];

      if (!userRecord) {
        return { success: false, error: 'User not found' };
      }

      // Convert back to userData format
      const userData = {
        domain: userRecord.domain,
        businessDescription: userRecord.business_description,
        integrations: userRecord.integrations,
        analysisData: userRecord.analysis_data
      };

      return { success: true, data: userData };
    } catch (error) {
      console.error('Local storage get error:', error);
      return { success: false, error: error.message };
    }
  }

  getAllFromLocalStorage() {
    try {
      const users = Object.values(this.memoryStorage);
      
      return { success: true, data: users };
    } catch (error) {
      console.error('Local storage get all error:', error);
      return { success: false, error: error.message };
    }
  }

  generateUserId(domain) {
    // Simple hash function to generate consistent user ID
    let hash = 0;
    for (let i = 0; i < domain.length; i++) {
      const char = domain.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash).toString();
  }

  // Database schema creation (for Supabase setup)
  getDatabaseSchema() {
    return `
      -- Create users table
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        domain TEXT NOT NULL UNIQUE,
        business_description TEXT,
        integrations JSONB DEFAULT '{}',
        analysis_data JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      );

      -- Create index on domain for faster lookups
      CREATE INDEX IF NOT EXISTS idx_users_domain ON users(domain);

      -- Create index on updated_at for sorting
      CREATE INDEX IF NOT EXISTS idx_users_updated_at ON users(updated_at);

      -- Enable Row Level Security (RLS)
      ALTER TABLE users ENABLE ROW LEVEL SECURITY;

      -- Create policy for public access (adjust as needed for your security requirements)
      CREATE POLICY "Allow public access" ON users FOR ALL USING (true);
    `;
  }
}

module.exports = new DatabaseService();
