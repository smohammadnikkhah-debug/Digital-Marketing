const { createClient } = require('@supabase/supabase-js');

class SupabaseService {
  constructor() {
    this.supabase = null;
    this.isConfigured = false;
    this.initialize();
  }

  initialize() {
    try {
      const supabaseUrl = process.env.SUPABASE_URL;
      const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;

      if (!supabaseUrl || !supabaseKey) {
        console.log('⚠️ Supabase credentials not configured, using local storage fallback');
        return;
      }

      this.supabase = createClient(supabaseUrl, supabaseKey);
      this.isConfigured = true;
      console.log('✅ Supabase initialized successfully');
    } catch (error) {
      console.error('❌ Supabase initialization failed:', error.message);
      this.isConfigured = false;
    }
  }

  // Website Management
  async createOrGetWebsite(domain, companyName = null, customerId = null) {
    if (!this.isConfigured) return null;

    try {
      // Check if website already exists for this customer
      const { data: existingWebsite, error: fetchError } = await this.supabase
        .from('websites')
        .select('*')
        .eq('domain', domain)
        .eq('customer_id', customerId)
        .single();

      if (existingWebsite && !fetchError) {
        return existingWebsite;
      }

      // Validate website limit if customerId is provided
      if (customerId) {
        const canAdd = await this.validateWebsiteLimit(customerId);
        if (!canAdd.allowed) {
          console.error('Website limit exceeded for customer:', customerId);
          return { error: 'Website limit exceeded', limit: canAdd.limit, current: canAdd.current };
        }
      }

      // Create new website
      const websiteData = {
        domain: domain,
        company_name: companyName || domain.replace(/^https?:\/\//, '').replace(/^www\./, ''),
        status: 'active',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };

      // Add customer_id if provided
      if (customerId) {
        websiteData.customer_id = customerId;
      }

      const { data: newWebsite, error: createError } = await this.supabase
        .from('websites')
        .insert(websiteData)
        .select()
        .single();

      if (createError) {
        console.error('Error creating website:', createError);
        
        // If it's a unique constraint error, try to get the existing website
        if (createError.code === '23505' && createError.message.includes('domain')) {
          console.log('Website already exists, attempting to retrieve it...');
          
          // Try to get the existing website for this customer
          const { data: existingWebsite, error: fetchError } = await this.supabase
            .from('websites')
            .select('*')
            .eq('domain', domain)
            .eq('customer_id', customerId)
            .single();
            
          if (existingWebsite && !fetchError) {
            console.log('✅ Retrieved existing website for customer');
            return existingWebsite;
          } else {
            console.error('Failed to retrieve existing website:', fetchError);
            return { error: 'Website exists but could not be retrieved', details: createError };
          }
        }
        
        return { error: createError.message, details: createError };
      }

      return newWebsite;
    } catch (error) {
      console.error('Supabase website creation error:', error);
      return null;
    }
  }

  // Validate website limit for a customer
  async validateWebsiteLimit(customerId) {
    try {
      // Get customer with plan information
      const { data: customer, error: customerError } = await this.supabase
        .from('customers')
        .select('plan_id')
        .eq('id', customerId)
        .single();

      if (customerError || !customer) {
        console.error('Error fetching customer:', customerError);
        return { allowed: false, limit: 0, current: 0 };
      }

      // Get current website count for this customer
      const { data: websites, error: websitesError } = await this.supabase
        .from('websites')
        .select('id')
        .eq('customer_id', customerId);

      if (websitesError) {
        console.error('Error fetching websites:', websitesError);
        return { allowed: false, limit: 0, current: 0 };
      }

      const currentCount = websites ? websites.length : 0;

      // Get plan limit
      const planLimits = require('../plan-limits-config');
      const limit = planLimits.getWebsiteLimit(customer.plan_id);

      return {
        allowed: currentCount < limit,
        limit: limit,
        current: currentCount
      };
    } catch (error) {
      console.error('Website limit validation error:', error);
      return { allowed: false, limit: 0, current: 0 };
    }
  }

  // SEO Analysis Storage
  async storeAnalysis(websiteId, analysisData, analysisType = 'comprehensive') {
    if (!this.isConfigured) return null;

    try {
      // First, check if websiteId exists
      if (!websiteId) {
        console.error('Error storing analysis: websiteId is required');
        return null;
      }

      const { data, error } = await this.supabase
        .from('seo_analyses')
        .insert({
          website_id: websiteId,
          analysis_data: analysisData,
          analysis_type: analysisType,
          expires_at: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000) // 14 days from now
        })
        .select()
        .single();

      if (error) {
        console.error('Error storing analysis:', error);
        return null;
      }

      console.log('✅ SEO analysis stored in Supabase');
      return data;
    } catch (error) {
      console.error('Supabase analysis storage error:', error);
      return null;
    }
  }

  // SEO Analysis Retrieval
  async getAnalysis(websiteId, analysisType = 'comprehensive') {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('seo_analyses')
        .select('*')
        .eq('website_id', websiteId)
        .eq('analysis_type', analysisType)
        .gt('expires_at', new Date().toISOString())
        .order('created_at', { ascending: false })
        .limit(1)
        .single();

      if (error) {
        // No cached analysis found
        return null;
      }

      console.log('✅ Retrieved cached SEO analysis from Supabase');
      return data;
    } catch (error) {
      console.error('Supabase analysis retrieval error:', error);
      return null;
    }
  }

  // Get analysis data by domain
  async getAnalysisData(domain, customerId = null) {
    if (!this.isConfigured) return null;

    try {
      // First get the website ID for this domain and customer
      let query = this.supabase
        .from('websites')
        .select('id')
        .eq('domain', domain);
      
      if (customerId) {
        query = query.eq('customer_id', customerId);
      }
      
      const { data: website, error: websiteError } = await query.single();

      if (websiteError || !website) {
        console.log('No website found for domain:', domain, 'customer:', customerId);
        return null;
      }

      // Get the latest analysis for this website
      const { data, error } = await this.supabase
        .from('seo_analyses')
        .select('analysis_data')
        .eq('website_id', website.id)
        .order('created_at', { ascending: false })
        .limit(1)
        .single();

      if (error) {
        console.log('No analysis data found for domain:', domain);
        return null;
      }

      console.log('✅ Retrieved analysis data for domain:', domain);
      return data.analysis_data;
    } catch (error) {
      console.error('Error getting analysis data by domain:', error);
      return null;
    }
  }

  // Get all websites for a customer
  async getCustomerWebsites(customerId) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('websites')
        .select('*')
        .eq('customer_id', customerId)
        .order('created_at', { ascending: false });

      if (error) {
        console.error('Error fetching customer websites:', error);
        return null;
      }

      return data || [];
    } catch (error) {
      console.error('Error getting customer websites:', error);
      return null;
    }
  }

  // Get analysis data for all customer websites
  async getCustomerAnalysisData(customerId) {
    if (!this.isConfigured) return null;

    try {
      // Get all websites for this customer
      const websites = await this.getCustomerWebsites(customerId);
      if (!websites || websites.length === 0) {
        return [];
      }

      // Get analysis data for each website
      const analysisData = [];
      for (const website of websites) {
        const analysis = await this.getAnalysisData(website.domain, customerId);
        if (analysis) {
          analysisData.push({
            website: website,
            analysis: analysis
          });
        }
      }

      return analysisData;
    } catch (error) {
      console.error('Error getting customer analysis data:', error);
      return null;
    }
  }

  // Keyword Management
  async storeKeywords(websiteId, keywords) {
    if (!this.isConfigured) return null;

    try {
      // First, check if websiteId exists
      if (!websiteId) {
        console.error('Error storing keywords: websiteId is required');
        return null;
      }

      // First, delete existing keywords for this website
      await this.supabase
        .from('keywords')
        .delete()
        .eq('website_id', websiteId);

      // Insert new keywords
      const keywordData = keywords.map(keyword => ({
        website_id: websiteId,
        keyword: keyword.keyword,
        search_volume: keyword.search_volume || 0,
        difficulty: keyword.difficulty || 0,
        current_rank: keyword.current_rank || null,
        optimization_notes: keyword.optimization_notes || null
      }));

      const { data, error } = await this.supabase
        .from('keywords')
        .insert(keywordData)
        .select();

      if (error) {
        console.error('Error storing keywords:', error);
        return null;
      }

      console.log(`✅ Stored ${keywords.length} keywords in Supabase`);
      return data;
    } catch (error) {
      console.error('Supabase keyword storage error:', error);
      return null;
    }
  }

  async getKeywords(websiteId) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('keywords')
        .select('*')
        .eq('website_id', websiteId)
        .order('search_volume', { ascending: false });

      if (error) {
        console.error('Error retrieving keywords:', error);
        return null;
      }

      return data;
    } catch (error) {
      console.error('Supabase keyword retrieval error:', error);
      return null;
    }
  }

  async addKeyword(websiteId, keyword, searchVolume = 0, difficulty = 0, currentRank = null) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('keywords')
        .insert({
          website_id: websiteId,
          keyword: keyword,
          search_volume: searchVolume,
          difficulty: difficulty,
          current_rank: currentRank
        })
        .select()
        .single();

      if (error) {
        console.error('Error adding keyword:', error);
        return null;
      }

      console.log(`✅ Added keyword "${keyword}" to Supabase`);
      return data;
    } catch (error) {
      console.error('Supabase keyword addition error:', error);
      return null;
    }
  }

  // Content Calendar Management
  async storeContentCalendar(websiteId, calendarData) {
    if (!this.isConfigured) return null;

    try {
      // First, delete existing calendar entries for this website
      await this.supabase
        .from('content_calendar')
        .delete()
        .eq('website_id', websiteId);

      // Insert new calendar entries
      const calendarEntries = [];
      for (const [date, content] of Object.entries(calendarData)) {
        for (const [platform, ideas] of Object.entries(content)) {
          calendarEntries.push({
            website_id: websiteId,
            content_type: platform,
            target_date: date,
            content_ideas: Array.isArray(ideas) ? ideas.join('\n') : ideas,
            status: 'planned'
          });
        }
      }

      const { data, error } = await this.supabase
        .from('content_calendar')
        .insert(calendarEntries)
        .select();

      if (error) {
        console.error('Error storing content calendar:', error);
        return null;
      }

      console.log(`✅ Stored ${calendarEntries.length} content calendar entries in Supabase`);
      return data;
    } catch (error) {
      console.error('Supabase content calendar storage error:', error);
      return null;
    }
  }

  async getContentCalendar(websiteId) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('content_calendar')
        .select('*')
        .eq('website_id', websiteId)
        .gte('target_date', new Date().toISOString().split('T')[0])
        .order('target_date', { ascending: true });

      if (error) {
        console.error('Error retrieving content calendar:', error);
        return null;
      }

      return data;
    } catch (error) {
      console.error('Supabase content calendar retrieval error:', error);
      return null;
    }
  }

  // Chat History Management
  async storeChatMessage(websiteId, userMessage, aiResponse) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('chat_history')
        .insert({
          website_id: websiteId,
          user_message: userMessage,
          ai_response: aiResponse
        })
        .select()
        .single();

      if (error) {
        console.error('Error storing chat message:', error);
        return null;
      }

      return data;
    } catch (error) {
      console.error('Supabase chat storage error:', error);
      return null;
    }
  }

  async getChatHistory(websiteId, limit = 50) {
    if (!this.isConfigured) return null;

    try {
      const { data, error } = await this.supabase
        .from('chat_history')
        .select('*')
        .eq('website_id', websiteId)
        .order('created_at', { ascending: false })
        .limit(limit);

      if (error) {
        console.error('Error retrieving chat history:', error);
        return null;
      }

      return data;
    } catch (error) {
      console.error('Supabase chat history retrieval error:', error);
      return null;
    }
  }

  // Utility Methods
  isReady() {
    return this.isConfigured && this.supabase !== null;
  }

  async testConnection() {
    if (!this.isConfigured) {
      return { success: false, error: 'Supabase not configured' };
    }

    try {
      const { data, error } = await this.supabase
        .from('websites')
        .select('count')
        .limit(1);

      if (error) {
        return { success: false, error: error.message };
      }

      return { success: true, message: 'Supabase connection successful' };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
}

module.exports = new SupabaseService();
