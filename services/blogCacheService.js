const { createClient } = require('@supabase/supabase-js');
const crypto = require('crypto');

class BlogCacheService {
    constructor() {
        this.supabase = createClient(
            process.env.SUPABASE_URL,
            process.env.SUPABASE_SERVICE_ROLE_KEY
        );
    }

    /**
     * Generate a cache key hash from blog generation parameters
     */
    generateCacheKey(params) {
        const { domain, topic, keywords, targetAudience, tone, wordCount, includeImages, seoOptimized } = params;
        
        // Create a normalized string from parameters
        const normalizedParams = {
            domain: domain?.toLowerCase().trim(),
            topic: topic?.toLowerCase().trim(),
            keywords: Array.isArray(keywords) ? keywords.sort().join(',') : keywords,
            targetAudience: targetAudience?.toLowerCase().trim(),
            tone: tone?.toLowerCase().trim(),
            wordCount: parseInt(wordCount) || 500,
            includeImages: Boolean(includeImages),
            seoOptimized: Boolean(seoOptimized)
        };

        // Create hash from normalized parameters
        const paramString = JSON.stringify(normalizedParams);
        return crypto.createHash('sha256').update(paramString).digest('hex');
    }

    /**
     * Check if cached content exists for given parameters
     */
    async getCachedContent(params, userId = null) {
        try {
            const contentHash = this.generateCacheKey(params);
            
            const { data, error } = await this.supabase
                .from('blog_content_cache')
                .select('*')
                .eq('content_hash', contentHash)
                .eq('expires_at', null) // Only get non-expired entries
                .or('expires_at.gt.' + new Date().toISOString())
                .single();

            if (error && error.code !== 'PGRST116') { // PGRST116 = no rows found
                console.error('[BlogCache] Error fetching cached content:', error);
                return null;
            }

            if (data) {
                console.log('[BlogCache] Found cached content for hash:', contentHash);
                return {
                    id: data.id,
                    title: data.title,
                    excerpt: data.excerpt,
                    content: data.content,
                    seoScore: data.seo_score,
                    seoGrade: data.seo_grade,
                    seoAnalysis: data.seo_analysis,
                    wordCount: data.word_count_actual,
                    keywords: data.keywords,
                    targetAudience: data.target_audience,
                    tone: data.tone,
                    includeImages: data.include_images,
                    seoOptimized: data.seo_optimized,
                    createdAt: data.created_at,
                    cached: true
                };
            }

            return null;
        } catch (error) {
            console.error('[BlogCache] Error in getCachedContent:', error);
            return null;
        }
    }

    /**
     * Get the latest blog content for a user and domain
     */
    async getLatestUserContent(userId, domain) {
        try {
            if (!userId) {
                console.log('[BlogCache] No userId provided for getLatestUserContent');
                return null;
            }

            const { data, error } = await this.supabase
                .from('blog_content_cache')
                .select('*')
                .eq('user_id', userId)
                .eq('domain', domain)
                .eq('is_latest', true)
                .eq('expires_at', null) // Only get non-expired entries
                .or('expires_at.gt.' + new Date().toISOString())
                .order('updated_at', { ascending: false })
                .limit(1)
                .single();

            if (error && error.code !== 'PGRST116') { // PGRST116 = no rows found
                console.error('[BlogCache] Error fetching latest user content:', error);
                return null;
            }

            if (data) {
                console.log('[BlogCache] Found latest content for user:', userId, 'domain:', domain);
                return {
                    id: data.id,
                    title: data.title,
                    excerpt: data.excerpt,
                    content: data.content,
                    seoScore: data.seo_score,
                    seoGrade: data.seo_grade,
                    seoAnalysis: data.seo_analysis,
                    wordCount: data.word_count_actual,
                    keywords: data.keywords,
                    targetAudience: data.target_audience,
                    tone: data.tone,
                    includeImages: data.include_images,
                    seoOptimized: data.seo_optimized,
                    createdAt: data.created_at,
                    updatedAt: data.updated_at,
                    cached: true,
                    isLatest: true
                };
            }

            return null;
        } catch (error) {
            console.error('[BlogCache] Error in getLatestUserContent:', error);
            return null;
        }
    }

    /**
     * Store generated content in cache
     */
    async storeCachedContent(params, blogContent, userId = null, isLatest = false) {
        try {
            const contentHash = this.generateCacheKey(params);
            
            // If this is the latest content, mark all previous content as not latest
            if (isLatest && userId) {
                await this.supabase
                    .from('blog_content_cache')
                    .update({ is_latest: false })
                    .eq('user_id', userId)
                    .eq('domain', params.domain);
            }
            
            const cacheData = {
                user_id: userId,
                domain: params.domain,
                topic: params.topic,
                keywords: Array.isArray(params.keywords) ? params.keywords : [params.keywords],
                target_audience: params.targetAudience,
                tone: params.tone,
                word_count: params.wordCount,
                include_images: params.includeImages,
                seo_optimized: params.seoOptimized,
                content_hash: contentHash,
                title: blogContent.title,
                excerpt: blogContent.excerpt,
                content: blogContent.content,
                seo_score: blogContent.seoScore,
                seo_grade: blogContent.seoGrade,
                seo_analysis: blogContent.seoAnalysis,
                word_count_actual: blogContent.wordCount,
                is_latest: isLatest,
                expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() // 30 days from now
            };

            const { data, error } = await this.supabase
                .from('blog_content_cache')
                .upsert(cacheData, { 
                    onConflict: 'content_hash',
                    ignoreDuplicates: false 
                })
                .select()
                .single();

            if (error) {
                console.error('[BlogCache] Error storing cached content:', error);
                return false;
            }

            console.log('[BlogCache] Stored cached content with hash:', contentHash, 'isLatest:', isLatest);
            return true;
        } catch (error) {
            console.error('[BlogCache] Error in storeCachedContent:', error);
            return false;
        }
    }

    /**
     * Update existing blog content (for regeneration)
     */
    async updateExistingContent(contentId, blogContent) {
        try {
            const { data, error } = await this.supabase
                .from('blog_content_cache')
                .update({
                    title: blogContent.title,
                    excerpt: blogContent.excerpt,
                    content: blogContent.content,
                    seo_score: blogContent.seoScore,
                    seo_grade: blogContent.seoGrade,
                    seo_analysis: blogContent.seoAnalysis,
                    word_count_actual: blogContent.wordCount,
                    updated_at: new Date().toISOString(),
                    expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() // Reset expiration
                })
                .eq('id', contentId)
                .select()
                .single();

            if (error) {
                console.error('[BlogCache] Error updating existing content:', error);
                return false;
            }

            console.log('[BlogCache] Updated existing content with ID:', contentId);
            return true;
        } catch (error) {
            console.error('[BlogCache] Error in updateExistingContent:', error);
            return false;
        }
    }

    /**
     * Invalidate cache entry (delete it)
     */
    async invalidateCache(params) {
        try {
            const contentHash = this.generateCacheKey(params);
            
            const { error } = await this.supabase
                .from('blog_content_cache')
                .delete()
                .eq('content_hash', contentHash);

            if (error) {
                console.error('[BlogCache] Error invalidating cache:', error);
                return false;
            }

            console.log('[BlogCache] Invalidated cache for hash:', contentHash);
            return true;
        } catch (error) {
            console.error('[BlogCache] Error in invalidateCache:', error);
            return false;
        }
    }

    /**
     * Clean up expired cache entries
     */
    async cleanupExpiredCache() {
        try {
            const { error } = await this.supabase
                .rpc('cleanup_expired_blog_cache');

            if (error) {
                console.error('[BlogCache] Error cleaning up expired cache:', error);
                return false;
            }

            console.log('[BlogCache] Cleaned up expired cache entries');
            return true;
        } catch (error) {
            console.error('[BlogCache] Error in cleanupExpiredCache:', error);
            return false;
        }
    }

    /**
     * Get cache statistics
     */
    async getCacheStats() {
        try {
            const { data, error } = await this.supabase
                .from('blog_content_cache')
                .select('id, created_at, expires_at');

            if (error) {
                console.error('[BlogCache] Error getting cache stats:', error);
                return null;
            }

            const now = new Date();
            const total = data.length;
            const expired = data.filter(item => new Date(item.expires_at) < now).length;
            const active = total - expired;

            return {
                total,
                active,
                expired,
                lastCleanup: now.toISOString()
            };
        } catch (error) {
            console.error('[BlogCache] Error in getCacheStats:', error);
            return null;
        }
    }
}

module.exports = BlogCacheService;
