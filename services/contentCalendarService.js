const { createClient } = require('@supabase/supabase-js');

class ContentCalendarService {
    constructor() {
        this.supabase = null;
        this.useLocalStorage = false;
        this.init();
    }

    async init() {
        try {
            if (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY) {
                this.supabase = createClient(
                    process.env.SUPABASE_URL,
                    process.env.SUPABASE_SERVICE_ROLE_KEY
                );
                console.log('✅ ContentCalendarService initialized with Supabase');
                
                // Test Supabase connection
                await this.testSupabaseConnection();
            } else {
                console.log('⚠️ ContentCalendarService using localStorage fallback');
                this.useLocalStorage = true;
            }
        } catch (error) {
            console.error('❌ ContentCalendarService initialization error:', error);
            this.useLocalStorage = true;
        }
    }

    async testSupabaseConnection() {
        try {
            // Test with a simple query
            const { data, error } = await this.supabase
                .from('content_calendar')
                .select('id')
                .limit(1);
            
            if (error && error.code === 'PGRST116') {
                console.log('⚠️ content_calendar table does not exist, falling back to localStorage');
                this.useLocalStorage = true;
            } else if (error) {
                console.log('⚠️ Supabase connection issue, falling back to localStorage:', error.message);
                this.useLocalStorage = true;
            } else {
                console.log('✅ Supabase connection working correctly');
            }
        } catch (error) {
            console.log('⚠️ Supabase test failed, falling back to localStorage:', error.message);
            this.useLocalStorage = true;
        }
    }

    async waitForInitialization() {
        let attempts = 0;
        while (!this.supabase && !this.useLocalStorage && attempts < 10) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
    }

    // Check if content needs to be generated
    async needsContentGeneration(domain) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return true; // Always generate for localStorage
            }

            const today = new Date();
            const nextTenDays = new Date(today.getTime() + 10 * 24 * 60 * 60 * 1000);
            
            // Check if we have content for the next 10 days
            const contentCount = await this.getContentCountForDateRange(domain, today, nextTenDays);
            
            return contentCount < 10; // Need at least 10 days of content
            
        } catch (error) {
            console.error('Error checking content needs:', error);
            return true; // Default to generating content
        }
    }

    // Get content count for date range
    async getContentCountForDateRange(domain, startDate, endDate) {
        try {
            if (this.useLocalStorage) {
                return 0; // Mock for localStorage
            }

            const { count, error } = await this.supabase
                .from('content_calendar')
                .select('*', { count: 'exact', head: true })
                .eq('domain', domain)
                .gte('target_date', startDate.toISOString().split('T')[0])
                .lte('target_date', endDate.toISOString().split('T')[0]);
            
            if (error) {
                console.error('Error getting content count:', error);
                return 0;
            }
            
            return count || 0;
            
        } catch (error) {
            console.error('Error getting content count:', error);
            return 0;
        }
    }

    // Get content for a specific date
    async getContentForDate(domain, date) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return this.getFromLocalStorage(domain, date);
            }

            console.log(`🔍 Fetching content for domain: ${domain}, date: ${date}`);

            // First get the website_id
            const websiteId = await this.getWebsiteId(domain);
            if (!websiteId) {
                console.error(`❌ Could not find website_id for domain: ${domain}`);
                return [];
            }

            const { data, error } = await this.supabase
                .from('content_calendar')
                .select('*')
                .eq('website_id', websiteId)
                .eq('target_date', date)
                .order('created_at', { ascending: true });
            
            if (error) {
                console.error('❌ Error getting content for date:', error);
                return [];
            }
            
            console.log(`✅ Found ${data?.length || 0} content items for ${domain} on ${date}`);
            return data || [];
            
        } catch (error) {
            console.error('❌ Error getting content for date:', error);
            return [];
        }
    }

    // Get content for a month
    async getContentForMonth(domain, year, month) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return this.getFromLocalStorage(domain, `${year}-${month.toString().padStart(2, '0')}`);
            }

            const startDate = `${year}-${month.toString().padStart(2, '0')}-01`;
            const endDate = `${year}-${month.toString().padStart(2, '0')}-31`;
            
            const { data, error } = await this.supabase
                .from('content_calendar')
                .select('*')
                .eq('domain', domain)
                .gte('target_date', startDate)
                .lte('target_date', endDate)
                .order('target_date', { ascending: true });
            
            if (error) {
                console.error('Error getting content for month:', error);
                return [];
            }
            
            return data || [];
            
        } catch (error) {
            console.error('Error getting content for month:', error);
            return [];
        }
    }

    // Save generated content
    async saveGeneratedContent(domain, contentData) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return this.saveToLocalStorage(domain, contentData);
            }

            console.log(`💾 Saving ${contentData.length} content items for domain: ${domain}`);

            // First get the website_id
            const websiteId = await this.getWebsiteId(domain);
            if (!websiteId) {
                console.error(`❌ Could not find website_id for domain: ${domain}`);
                return [];
            }

            // Prepare data for insertion
            const insertData = contentData.map(item => ({
                website_id: websiteId, // Use website_id instead of domain
                target_date: item.target_date,
                platform: item.platform,
                title: item.title || '',
                content: item.content,
                description: item.description || '',
                hashtags: item.hashtags || [],
                seo_keywords: item.seo_keywords || [],
                call_to_action: item.call_to_action || '',
                engagement_tip: item.engagement_tip || '',
                status: 'draft'
            }));

            console.log(`📝 Prepared ${insertData.length} items for insertion with website_id: ${websiteId}`);

            const { data, error } = await this.supabase
                .from('content_calendar')
                .insert(insertData)
                .select();
            
            if (error) {
                console.error('❌ Error saving content:', error);
                return [];
            }
            
            console.log(`✅ Successfully saved ${data?.length || 0} content items to Supabase`);
            return data || [];
            
        } catch (error) {
            console.error('❌ Error saving content:', error);
            return [];
        }
    }

    // Update content item
    async updateContentItem(id, updateData) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return this.updateInLocalStorage(id, updateData);
            }

            const { data, error } = await this.supabase
                .from('content_calendar')
                .update(updateData)
                .eq('id', id)
                .select()
                .single();
            
            if (error) {
                console.error('Error updating content item:', error);
                return null;
            }
            
            return data;
            
        } catch (error) {
            console.error('Error updating content item:', error);
            return null;
        }
    }

    // Delete content item
    async deleteContentItem(id) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return this.deleteFromLocalStorage(id);
            }

            const { data, error } = await this.supabase
                .from('content_calendar')
                .delete()
                .eq('id', id)
                .select()
                .single();
            
            if (error) {
                console.error('Error deleting content item:', error);
                return null;
            }
            
            return data;
            
        } catch (error) {
            console.error('Error deleting content item:', error);
            return null;
        }
    }

    // Upload media for content
    async uploadMedia(id, fileData) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return { success: true, message: 'Media upload simulated for localStorage' };
            }

            // This would handle file upload to Supabase Storage
            // For now, return success
            return { success: true, message: 'Media upload not implemented yet' };
            
        } catch (error) {
            console.error('Error uploading media:', error);
            return { success: false, error: error.message };
        }
    }

    // Schedule content
    async scheduleContent(id, scheduledFor, platform) {
        await this.waitForInitialization();
        
        try {
            if (this.useLocalStorage) {
                return { success: true, message: 'Content scheduling simulated for localStorage' };
            }

            const { data, error } = await this.supabase
                .from('content_calendar')
                .update({ 
                    status: 'scheduled',
                    updated_at: new Date().toISOString()
                })
                .eq('id', id)
                .select()
                .single();
            
            if (error) {
                console.error('Error scheduling content:', error);
                return { success: false, error: error.message };
            }
            
            return { success: true, data: data };
            
        } catch (error) {
            console.error('Error scheduling content:', error);
            return { success: false, error: error.message };
        }
    }

    // Generate SEO content using OpenAI
    async generateSEOContent(domain, services, keywords, days = 30, forceCurrentMonth = false, startDate, immediate = false, background = false) {
        await this.waitForInitialization();
        
        try {
            console.log(`🎯 Generating SEO content for ${domain}`);
            console.log(`📊 Services: ${services?.length || 0}, Keywords: ${keywords?.length || 0}`);
            console.log(`📅 Days: ${days}, Immediate: ${immediate}, Background: ${background}`);
            
            // First, validate that the domain exists in the websites table
            const isValidDomain = await this.validateDomain(domain);
            if (!isValidDomain) {
                console.error(`❌ Domain ${domain} is not valid or not found in websites table`);
                return [];
            }
            
            // Get customer join date
            const joinDate = await this.getCustomerJoinDate(domain);
            const today = new Date();
            
            // Calculate actual start date
            let actualStartDate;
            if (startDate) {
                // Use the provided startDate (for immediate/background generation)
                actualStartDate = new Date(startDate);
                console.log(`📅 Using provided startDate: ${startDate} → ${actualStartDate.toISOString().split('T')[0]}`);
            } else if (forceCurrentMonth) {
                actualStartDate = new Date(startDate);
                console.log(`📅 Using forceCurrentMonth startDate: ${startDate} → ${actualStartDate.toISOString().split('T')[0]}`);
            } else {
                // Default to join date or today, whichever is later
                actualStartDate = new Date(joinDate);
                if (actualStartDate < today) {
                    actualStartDate = today;
                }
                console.log(`📅 Using default startDate: joinDate=${joinDate}, today=${today.toISOString().split('T')[0]} → ${actualStartDate.toISOString().split('T')[0]}`);
            }
            
            // Calculate end date
            const endDate = new Date(actualStartDate);
            endDate.setDate(endDate.getDate() + days);
            
            console.log(`📅 Generating content from ${actualStartDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]}`);
            
            // Read existing content first, then generate missing content
            const allContent = [];
            const platforms = ['twitter', 'instagram', 'tiktok'];
            const newlyGeneratedContent = [];
            
            for (let d = new Date(actualStartDate); d < endDate; d.setDate(d.getDate() + 1)) {
                const currentDate = new Date(d);
                const dateStr = currentDate.toISOString().split('T')[0];
                
                console.log(`🔍 Checking existing content for ${dateStr}...`);
                
                // First, try to read existing content from Supabase
                const existingContent = await this.getContentForDate(domain, dateStr);
                
                if (existingContent && existingContent.length > 0) {
                    console.log(`✅ Found ${existingContent.length} existing content items for ${dateStr}`);
                    // Add existing content to our result
                    existingContent.forEach(item => {
                        allContent.push({
                            target_date: item.target_date,
                            platform: item.platform,
                            title: item.title,
                            content: item.content,
                            description: item.description,
                            hashtags: item.hashtags,
                            seo_keywords: item.seo_keywords,
                            call_to_action: item.call_to_action,
                            engagement_tip: item.engagement_tip
                        });
                    });
                } else {
                    console.log(`❌ No existing content found for ${dateStr}, generating new content...`);
                    
                    // Generate new content for each platform
                    for (const platform of platforms) {
                        try {
                            const content = await this.generateContentForPlatform(domain, platform, dateStr, services, keywords);
                            if (content) {
                                const newContentItem = {
                                    target_date: dateStr,
                                    platform: platform,
                                    title: content.title,
                                    content: content.content,
                                    description: content.description,
                                    hashtags: content.hashtags,
                                    seo_keywords: content.seo_keywords,
                                    call_to_action: content.call_to_action || 'Contact us for more information',
                                    engagement_tip: content.engagement_tip || 'Engage with your audience'
                                };
                                
                                allContent.push(newContentItem);
                                newlyGeneratedContent.push(newContentItem);
                                console.log(`✅ Generated new content for ${platform} on ${dateStr}`);
                            }
                        } catch (error) {
                            console.error(`Error generating content for ${platform} on ${dateStr}:`, error);
                        }
                    }
                }
            }
            
            console.log(`📊 Total content items: ${allContent.length} (existing + newly generated)`);
            
            // Save any newly generated content to Supabase
            if (newlyGeneratedContent.length > 0) {
                console.log(`💾 Saving ${newlyGeneratedContent.length} newly generated content items to Supabase`);
                await this.saveGeneratedContent(domain, newlyGeneratedContent);
            } else {
                console.log(`✅ All content already exists in Supabase, no new content to save`);
            }
            
            return allContent;
            
        } catch (error) {
            console.error('Error generating SEO content:', error);
            return [];
        }
    }

    // Generate content for specific platform
    async generateContentForPlatform(domain, platform, date, services, keywords) {
        try {
            const openai = require('openai');
            const client = new openai.OpenAI({
                apiKey: process.env.OPENAI_API_KEY
            });

            const serviceText = services && services.length > 0 ? services.join(', ') : 'digital marketing services';
            const keywordText = keywords && keywords.length > 0 ? keywords.join(', ') : 'SEO, digital marketing';

            const prompt = `Generate SEO-optimized social media content for ${platform} for a business website (${domain}) that offers ${serviceText}. 

Target keywords: ${keywordText}
Date: ${date}
Platform: ${platform}

Requirements:
- Create engaging, platform-specific content
- Include relevant hashtags (3-5 hashtags)
- Optimize for SEO with target keywords
- Keep it authentic and valuable
- Platform-specific formatting (${platform} style)

IMPORTANT: Return ONLY valid JSON without any markdown formatting, code blocks, or additional text. Just the raw JSON object:

{
  "title": "Engaging title",
  "content": "Main content text",
  "description": "Brief description",
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3"],
  "seo_keywords": ["keyword1", "keyword2"]
}`;

            const response = await client.chat.completions.create({
                model: "gpt-3.5-turbo",
                messages: [
                    {
                        role: "system",
                        content: "You are an expert social media content creator specializing in SEO-optimized posts. Create engaging, platform-specific content that drives engagement and improves SEO. CRITICAL: Always return ONLY valid JSON without any markdown formatting, code blocks, or additional text."
                    },
                    {
                        role: "user",
                        content: prompt
                    }
                ],
                max_tokens: 500,
                temperature: 0.7
            });

            const content = response.choices[0].message.content;
            
            // Clean up the response - remove markdown code blocks if present
            let cleanContent = content.trim();
            if (cleanContent.startsWith('```json')) {
                cleanContent = cleanContent.replace(/^```json\s*/, '').replace(/\s*```$/, '');
            } else if (cleanContent.startsWith('```')) {
                cleanContent = cleanContent.replace(/^```\s*/, '').replace(/\s*```$/, '');
            }
            
            return JSON.parse(cleanContent);
            
        } catch (error) {
            console.error(`Error generating content for ${platform}:`, error);
            return null;
        }
    }

    // Get website_id from domain
    async getWebsiteId(domain) {
        try {
            if (this.useLocalStorage) {
                return 'mock-website-id'; // Mock ID for localStorage
            }

            console.log(`🔍 Getting website_id for domain: ${domain}`);

            const { data, error } = await this.supabase
                .from('websites')
                .select('id, customer_id')
                .eq('domain', domain)
                .single();
            
            if (error) {
                console.error(`❌ Domain ${domain} not found in websites table:`, error);
                return null;
            }
            
            console.log(`✅ Found website_id: ${data.id} for domain: ${domain}`);
            return data.id;
            
        } catch (error) {
            console.error(`❌ Error getting website_id for domain ${domain}:`, error);
            return null;
        }
    }

    // Validate domain exists in websites table
    async validateDomain(domain) {
        try {
            if (this.useLocalStorage) {
                return true; // Assume valid for localStorage
            }

            console.log(`🔍 Validating domain: ${domain}`);

            const { data, error } = await this.supabase
                .from('websites')
                .select('id')
                .eq('domain', domain)
                .single();
            
            if (error) {
                console.error(`❌ Domain ${domain} not found in websites table:`, error);
                return false;
            }
            
            console.log(`✅ Domain ${domain} validated successfully`);
            return true;
            
        } catch (error) {
            console.error(`❌ Error validating domain ${domain}:`, error);
            return false;
        }
    }

    // Get customer join date (from website creation date)
    async getCustomerJoinDate(domain) {
        try {
            if (this.useLocalStorage) {
                return new Date(); // Fallback to current date
            }

            console.log(`📅 Getting join date for domain: ${domain}`);

            const { data, error } = await this.supabase
                .from('websites')
                .select('created_at')
                .eq('domain', domain)
                .single();
            
            if (error || !data) {
                console.log('❌ No website data found, using current date');
                return new Date();
            }
            
            console.log(`✅ Join date for ${domain}: ${data.created_at}`);
            return new Date(data.created_at);
            
        } catch (error) {
            console.error('❌ Error getting customer join date:', error);
            return new Date();
        }
    }

    // LocalStorage fallback methods
    getFromLocalStorage(domain, date) {
        try {
            const key = `content_calendar_${domain}`;
            const data = JSON.parse(localStorage.getItem(key) || '{}');
            return data[date] || [];
        } catch (error) {
            return [];
        }
    }

    saveToLocalStorage(domain, contentData) {
        try {
            const key = `content_calendar_${domain}`;
            const existingData = JSON.parse(localStorage.getItem(key) || '{}');
            
            contentData.forEach(item => {
                if (!existingData[item.date]) {
                    existingData[item.date] = [];
                }
                existingData[item.date].push(item);
            });
            
            localStorage.setItem(key, JSON.stringify(existingData));
            return contentData;
        } catch (error) {
            console.error('Error saving to localStorage:', error);
            return [];
        }
    }

    updateInLocalStorage(id, updateData) {
        // Mock implementation for localStorage
        return { id, ...updateData };
    }

    deleteFromLocalStorage(id) {
        // Mock implementation for localStorage
        return { id };
    }
}

module.exports = ContentCalendarService;
