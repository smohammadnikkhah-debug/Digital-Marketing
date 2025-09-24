const { createClient } = require('@supabase/supabase-js');
const OpenAI = require('openai');

class IntelligentContentService {
    constructor() {
        this.supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );
        
        this.openai = new OpenAI({
            apiKey: process.env.OPENAI_API_KEY
        });
    }

    /**
     * Generate content based on company services and store in Supabase
     */
    async generateServiceBasedContent(userId, domain, days = 7) {
        try {
            console.log(`🎯 Generating service-based content for ${domain} (${days} days)`);
            
        // Get company services
        const services = await this.getCompanyServices(userId, domain);
        console.log('🔍 Services found:', services);
        if (!services || services.length === 0) {
            console.log('⚠️ No company services found, using default services');
            return this.generateDefaultContent(userId, domain, days);
        }

            // Check existing content for the next 7 days
            const existingContent = await this.getExistingContent(userId, domain, days);
            const missingDays = this.findMissingContentDays(existingContent, days);
            
            if (missingDays.length === 0) {
                console.log('✅ All content already exists for the next 7 days');
                return existingContent;
            }

            console.log(`📝 Generating content for ${missingDays.length} missing days:`, missingDays);

            // Generate content for missing days
            const newContent = await this.generateContentForDays(userId, domain, missingDays, services);
            
            // Store in Supabase
            await this.storeContentInSupabase(userId, domain, newContent);
            
            // Log generation
            await this.logContentGeneration(userId, domain, missingDays.length, services);
            
            // Return all content (existing + new)
            const allContent = await this.getExistingContent(userId, domain, days);
            return allContent;

        } catch (error) {
            console.error('❌ Error generating service-based content:', error);
            throw error;
        }
    }

    /**
     * Get company services from Supabase
     */
    async getCompanyServices(userId, domain) {
        try {
            const { data, error } = await this.supabase
                .from('company_services')
                .select('*')
                .eq('user_id', userId)
                .eq('domain', domain)
                .eq('is_active', true);

            if (error) {
                console.error('Error fetching company services:', error);
                // Return default services if table doesn't exist
                return this.getDefaultServices();
            }

            return data || this.getDefaultServices();
        } catch (error) {
            console.error('Error fetching company services:', error);
            return this.getDefaultServices();
        }
    }

    /**
     * Get default company services when database table doesn't exist
     */
    getDefaultServices() {
        return [
            {
                id: 'default-1',
                service_name: 'SEO Optimization',
                service_description: 'Professional SEO services to improve website rankings and organic traffic',
                target_keywords: ['SEO', 'search engine optimization', 'organic traffic', 'keyword research'],
                content_themes: ['SEO tips', 'ranking improvements', 'organic growth', 'search visibility']
            },
            {
                id: 'default-2',
                service_name: 'Digital Marketing',
                service_description: 'Comprehensive digital marketing strategies for business growth',
                target_keywords: ['digital marketing', 'online advertising', 'social media marketing', 'PPC'],
                content_themes: ['marketing strategies', 'advertising tips', 'social media', 'campaign optimization']
            },
            {
                id: 'default-3',
                service_name: 'Website Development',
                service_description: 'Custom website development and optimization services',
                target_keywords: ['website development', 'web design', 'responsive design', 'user experience'],
                content_themes: ['web development', 'design trends', 'user experience', 'website optimization']
            },
            {
                id: 'default-4',
                service_name: 'Content Marketing',
                service_description: 'Strategic content creation and marketing to engage audiences',
                target_keywords: ['content marketing', 'content strategy', 'blog writing', 'content creation'],
                content_themes: ['content strategy', 'writing tips', 'content planning', 'audience engagement']
            }
        ];
    }

    /**
     * Generate default content when no services are available
     */
    async generateDefaultContent(userId, domain, days) {
        console.log('🎯 Generating default content for Mozarex');
        
        const platforms = ['twitter', 'facebook', 'instagram', 'tiktok'];
        const contentArray = [];
        
        for (let day = 1; day <= days; day++) {
            const targetDate = new Date();
            targetDate.setDate(targetDate.getDate() + day - 1);
            
            for (const platform of platforms) {
                const content = this.generatePlatformContent(platform, 'Mozarex', 'Professional SEO and Digital Marketing Services', day);
                
                contentArray.push({
                    user_id: userId,
                    domain: domain,
                    target_date: targetDate.toISOString().split('T')[0],
                    platform: platform,
                    content: content.content,
                    engagement_tip: content.tip,
                    scheduled_time: content.time,
                    status: 'draft'
                });
            }
        }
        
        // Try to store in database, but don't fail if it doesn't work
        await this.storeContentInSupabase(userId, domain, contentArray);
        
        return contentArray;
    }

    /**
     * Get existing content from Supabase
     */
    async getExistingContent(userId, domain, days) {
        try {
            const startDate = new Date();
            const endDate = new Date();
            endDate.setDate(startDate.getDate() + days);

            const { data, error } = await this.supabase
                .from('content_calendar_entries')
                .select('*')
                .eq('user_id', userId)
                .eq('domain', domain)
                .gte('target_date', startDate.toISOString().split('T')[0])
                .lte('target_date', endDate.toISOString().split('T')[0])
                .order('target_date', { ascending: true });

            if (error) {
                console.error('Error fetching existing content:', error);
                return []; // Return empty array if table doesn't exist
            }

            return data || [];
        } catch (error) {
            console.error('Error fetching existing content:', error);
            return [];
        }
    }

    /**
     * Find days that need content generation
     */
    findMissingContentDays(existingContent, days) {
        const missingDays = [];
        const platforms = ['twitter', 'facebook', 'instagram', 'tiktok'];
        
        for (let i = 0; i < days; i++) {
            const date = new Date();
            date.setDate(date.getDate() + i);
            const dateString = date.toISOString().split('T')[0];
            
            // Check if all platforms have content for this day
            const dayContent = existingContent.filter(content => content.target_date === dateString);
            const existingPlatforms = dayContent.map(content => content.platform);
            
            const missingPlatforms = platforms.filter(platform => !existingPlatforms.includes(platform));
            
            if (missingPlatforms.length > 0) {
                missingDays.push({
                    date: dateString,
                    missingPlatforms: missingPlatforms,
                    existingPlatforms: existingPlatforms
                });
            }
        }
        
        return missingDays;
    }

    /**
     * Generate content for specific days using OpenAI
     */
    async generateContentForDays(userId, domain, missingDays, services) {
        const generatedContent = [];
        
        for (const dayInfo of missingDays) {
            console.log(`📅 Generating content for ${dayInfo.date}`);
            
            for (const platform of dayInfo.missingPlatforms) {
                try {
                    const content = await this.generateSingleContent(userId, domain, dayInfo.date, platform, services);
                    generatedContent.push(content);
                } catch (error) {
                    console.error(`Error generating content for ${platform} on ${dayInfo.date}:`, error);
                }
            }
        }
        
        return generatedContent;
    }

    /**
     * Generate content for a single platform/day using OpenAI
     */
    async generateSingleContent(userId, domain, date, platform, services) {
        const serviceInfo = this.selectServiceForDay(services, date);
        const platformContext = this.getPlatformContext(platform);
        
        const prompt = this.buildContentPrompt(domain, serviceInfo, platformContext, date);
        
        console.log(`🤖 Generating ${platform} content for ${date} using service: ${serviceInfo.service_name}`);
        
        const response = await this.openai.chat.completions.create({
            model: 'gpt-3.5-turbo',
            messages: [
                {
                    role: 'system',
                    content: `You are Mozarex AI, an expert content creator for digital marketing agencies. Generate engaging social media content based on the company's services and expertise.`
                },
                {
                    role: 'user',
                    content: prompt
                }
            ],
            max_tokens: 500,
            temperature: 0.7
        });

        const aiResponse = response.choices[0].message.content;
        const parsedContent = this.parseAIResponse(aiResponse, platform);
        
        return {
            user_id: userId,
            domain: domain,
            target_date: date,
            platform: platform,
            content: parsedContent.content,
            engagement_tip: parsedContent.tip,
            scheduled_time: parsedContent.time,
            status: 'draft',
            created_at: new Date().toISOString()
        };
    }

    /**
     * Select appropriate service for the day
     */
    selectServiceForDay(services, date) {
        const dayOfWeek = new Date(date).getDay();
        const serviceIndex = dayOfWeek % services.length;
        return services[serviceIndex];
    }

    /**
     * Get platform-specific context
     */
    getPlatformContext(platform) {
        const contexts = {
            twitter: {
                maxLength: 280,
                style: 'concise, engaging, hashtag-friendly',
                features: 'hashtags, mentions, polls'
            },
            facebook: {
                maxLength: 2000,
                style: 'conversational, informative, community-focused',
                features: 'longer posts, images, videos, events'
            },
            instagram: {
                maxLength: 2200,
                style: 'visual, inspiring, story-driven',
                features: 'images, stories, reels, carousels'
            },
            tiktok: {
                maxLength: 300,
                style: 'trendy, fun, video-focused',
                features: 'short videos, trending sounds, challenges'
            }
        };
        
        return contexts[platform] || contexts.twitter;
    }

    /**
     * Build content generation prompt
     */
    buildContentPrompt(domain, serviceInfo, platformContext, date) {
        return `
Generate social media content for ${domain} based on their service: "${serviceInfo.service_name}"

Service Description: ${serviceInfo.service_description}
Target Keywords: ${serviceInfo.target_keywords.join(', ')}
Content Themes: ${serviceInfo.content_themes.join(', ')}

Platform: ${platformContext.style}
Max Length: ${platformContext.maxLength} characters
Features: ${platformContext.features}

Requirements:
1. Create engaging content that showcases expertise in ${serviceInfo.service_name}
2. Include relevant keywords naturally
3. Add appropriate hashtags (2-3 max)
4. Include a practical tip or insight
5. Make it specific to ${domain}'s services
6. Use a professional but approachable tone

Return ONLY a JSON object with this structure:
{
  "content": "Your social media post content here",
  "tip": "Engagement tip for this platform",
  "time": "10:00 AM"
}

Do not include any other text or explanations.
        `;
    }

    /**
     * Parse AI response and extract content
     */
    parseAIResponse(aiResponse, platform) {
        try {
            // Try to extract JSON from the response
            const jsonMatch = aiResponse.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const parsed = JSON.parse(jsonMatch[0]);
                return {
                    content: parsed.content || 'Content generation failed',
                    tip: parsed.tip || 'Engage with your audience',
                    time: parsed.time || this.getDefaultTime(platform)
                };
            }
        } catch (error) {
            console.error('Error parsing AI response:', error);
        }
        
        // Fallback if JSON parsing fails
        return {
            content: aiResponse.substring(0, 200) + '...',
            tip: 'Engage with your audience',
            time: this.getDefaultTime(platform)
        };
    }

    /**
     * Get default posting time for platform
     */
    getDefaultTime(platform) {
        const times = {
            twitter: '10:00 AM',
            facebook: '2:00 PM',
            instagram: '7:00 PM',
            tiktok: '6:00 PM'
        };
        return times[platform] || '10:00 AM';
    }

    /**
     * Store generated content in Supabase
     */
    async storeContentInSupabase(userId, domain, contentArray) {
        try {
            const { data, error } = await this.supabase
                .from('content_calendar_entries')
                .insert(contentArray);

            if (error) {
                console.error('Error storing content in Supabase:', error);
                console.log('⚠️ Content not stored in database (table may not exist)');
                return contentArray; // Return the content anyway
            }

            console.log(`✅ Stored ${contentArray.length} content entries in Supabase`);
            return data;
        } catch (error) {
            console.error('Error storing content in Supabase:', error);
            console.log('⚠️ Content not stored in database (table may not exist)');
            return contentArray; // Return the content anyway
        }
    }

    /**
     * Log content generation for analytics
     */
    async logContentGeneration(userId, domain, daysGenerated, services) {
        try {
            const logEntry = {
                user_id: userId,
                domain: domain,
                generation_date: new Date().toISOString().split('T')[0],
                days_generated: daysGenerated,
                services_used: services.map(s => s.service_name),
                ai_model: 'gpt-3.5-turbo',
                tokens_used: daysGenerated * 4 * 500, // Estimate
                generation_time_ms: Date.now()
            };

            const { error } = await this.supabase
                .from('content_generation_logs')
                .insert(logEntry);

            if (error) {
                console.error('Error logging content generation:', error);
                console.log('⚠️ Generation log not stored (table may not exist)');
            }
        } catch (error) {
            console.error('Error logging content generation:', error);
            console.log('⚠️ Generation log not stored (table may not exist)');
        }
    }

    /**
     * Update content status (approve/reject)
     */
    async updateContentStatus(contentId, status, approvedBy = null) {
        const updateData = {
            status: status,
            updated_at: new Date().toISOString()
        };

        if (status === 'approved' && approvedBy) {
            updateData.approved_by = approvedBy;
            updateData.approved_at = new Date().toISOString();
        }

        const { data, error } = await this.supabase
            .from('content_calendar_entries')
            .update(updateData)
            .eq('id', contentId)
            .select();

        if (error) {
            console.error('Error updating content status:', error);
            throw error;
        }

        return data[0];
    }

    /**
     * Get content approval queue
     */
    async getApprovalQueue(userId, domain) {
        try {
            const { data, error } = await this.supabase
                .from('content_calendar_entries')
                .select('*')
                .eq('user_id', userId)
                .eq('domain', domain)
                .eq('status', 'draft')
                .order('target_date', { ascending: true });

            if (error) {
                console.error('Error fetching approval queue:', error);
                return []; // Return empty array if table doesn't exist
            }

            return data || [];
        } catch (error) {
            console.error('Error fetching approval queue:', error);
            return [];
        }
    }
}

module.exports = IntelligentContentService;
