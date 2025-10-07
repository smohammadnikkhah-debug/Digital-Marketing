/**
 * Environment Configuration Service
 * Handles environment-based configuration for all services
 */

const path = require('path');
const fs = require('fs');

class EnvironmentConfig {
    constructor() {
        this.currentEnvironment = process.env.NODE_ENV || 'development';
        this.config = this.loadEnvironmentConfig();
        this.logCurrentEnvironment();
    }

    loadEnvironmentConfig() {
        // In production (DigitalOcean), environment variables are provided directly by the platform
        // Only load .env file in development
        if (this.currentEnvironment === 'development') {
            const envPath = path.join(process.cwd(), '.env');
            
            if (fs.existsSync(envPath)) {
                require('dotenv').config({ path: envPath });
                console.log('✅ Loaded environment variables from .env file');
            } else {
                console.warn(`⚠️ Environment file .env not found in development, using defaults`);
            }
        } else {
            console.log('✅ Using environment variables from platform (DigitalOcean)');
        }
        
        return {
            environment: this.currentEnvironment,
            isDevelopment: this.currentEnvironment === 'development',
            isProduction: this.currentEnvironment === 'production',
            isSandbox: process.env.ENABLE_SANDBOX_MODE === 'true',
            
            dataforseo: {
                environment: process.env.DATAFORSEO_ENVIRONMENT || 'production',
                baseUrl: process.env.DATAFORSEO_BASE_URL || 'https://api.dataforseo.com/v3',
                username: process.env.DATAFORSEO_USERNAME,
                password: process.env.DATAFORSEO_PASSWORD
            },

            openai: {
                apiKey: process.env.OPENAI_API_KEY,
                model: this.currentEnvironment === 'production' ? 'gpt-4' : 'gpt-3.5-turbo',
                maxTokens: this.currentEnvironment === 'production' ? 4000 : 2000
            },

            supabase: {
                url: process.env.SUPABASE_URL,
                anonKey: process.env.SUPABASE_ANON_KEY,
                serviceRoleKey: process.env.SUPABASE_SERVICE_ROLE_KEY
            },

            social: {
                twitter: {
                    clientId: process.env.TWITTER_CLIENT_ID,
                    clientSecret: process.env.TWITTER_CLIENT_SECRET,
                    redirectUri: process.env.TWITTER_REDIRECT_URI
                },
                instagram: {
                    clientId: process.env.INSTAGRAM_CLIENT_ID,
                    clientSecret: process.env.INSTAGRAM_CLIENT_SECRET,
                    redirectUri: process.env.INSTAGRAM_REDIRECT_URI
                },
                tiktok: {
                    clientId: process.env.TIKTOK_CLIENT_ID,
                    clientSecret: process.env.TIKTOK_CLIENT_SECRET,
                    redirectUri: process.env.TIKTOK_REDIRECT_URI
                },
                facebook: {
                    clientId: process.env.FACEBOOK_CLIENT_ID,
                    clientSecret: process.env.FACEBOOK_CLIENT_SECRET,
                    redirectUri: process.env.FACEBOOK_REDIRECT_URI
                },
                linkedin: {
                    clientId: process.env.LINKEDIN_CLIENT_ID,
                    clientSecret: process.env.LINKEDIN_CLIENT_SECRET,
                    redirectUri: process.env.LINKEDIN_REDIRECT_URI
                },
                youtube: {
                    clientId: process.env.YOUTUBE_CLIENT_ID,
                    clientSecret: process.env.YOUTUBE_CLIENT_SECRET,
                    redirectUri: process.env.YOUTUBE_REDIRECT_URI
                },
                pinterest: {
                    clientId: process.env.PINTEREST_CLIENT_ID,
                    clientSecret: process.env.PINTEREST_CLIENT_SECRET,
                    redirectUri: process.env.PINTEREST_REDIRECT_URI
                }
            },

            server: {
                port: process.env.PORT || 3000,
                enableDebugLogs: process.env.ENABLE_DEBUG_LOGS === 'true',
                logLevel: process.env.LOG_LEVEL || 'info'
            },

            features: {
                enableSandboxMode: process.env.ENABLE_SANDBOX_MODE === 'true',
                enableDemoData: process.env.ENABLE_DEMO_DATA === 'true',
                enableMockResponses: process.env.ENABLE_MOCK_RESPONSES === 'true'
            }
        };
    }

    getDefaultConfig() {
        return {
            environment: 'production',
            isDevelopment: false,
            isProduction: true,
            isSandbox: false,
            dataforseo: {
                environment: 'production',
                baseUrl: 'https://api.dataforseo.com/v3',
                username: null,
                password: null
            },
            openai: {
                apiKey: null,
                model: 'gpt-3.5-turbo',
                maxTokens: 2000
            },
            supabase: {
                url: null,
                anonKey: null,
                serviceRoleKey: null
            },
            social: {
                twitter: { clientId: null, clientSecret: null, redirectUri: null },
                instagram: { clientId: null, clientSecret: null, redirectUri: null },
                tiktok: { clientId: null, clientSecret: null, redirectUri: null },
                facebook: { clientId: null, clientSecret: null, redirectUri: null },
                linkedin: { clientId: null, clientSecret: null, redirectUri: null },
                youtube: { clientId: null, clientSecret: null, redirectUri: null },
                pinterest: { clientId: null, clientSecret: null, redirectUri: null }
            },
            server: {
                port: 3000,
                enableDebugLogs: true,
                logLevel: 'debug'
            },
            features: {
                enableSandboxMode: false,
                enableDemoData: false,
                enableMockResponses: false
            }
        };
    }

    logCurrentEnvironment() {
        console.log('\n🌍 Environment Configuration Loaded:');
        console.log(`   Environment: ${this.config.environment}`);
        console.log(`   DataForSEO: ${this.config.dataforseo.environment} (${this.config.dataforseo.baseUrl})`);
        console.log(`   OpenAI Model: ${this.config.openai.model}`);
        console.log(`   Sandbox Mode: ${this.config.isSandbox ? '✅ Enabled' : '❌ Disabled'}`);
        console.log(`   Debug Logs: ${this.config.server.enableDebugLogs ? '✅ Enabled' : '❌ Disabled'}`);
        
        const socialPlatforms = Object.keys(this.config.social);
        const configuredPlatforms = socialPlatforms.filter(platform => 
            this.config.social[platform].clientId && 
            this.config.social[platform].clientId !== `dev_${platform}_client_id` &&
            this.config.social[platform].clientId !== `prod_${platform}_client_id`
        );
        
        console.log(`   Social Platforms: ${configuredPlatforms.length}/${socialPlatforms.length} configured`);
        if (configuredPlatforms.length > 0) {
            console.log(`   Configured: ${configuredPlatforms.join(', ')}`);
        }
        console.log('');
    }

    getServiceConfig(serviceName) {
        return this.config[serviceName] || null;
    }

    getSocialConfig(platform) {
        return this.config.social[platform] || null;
    }

    isSocialPlatformConfigured(platform) {
        const config = this.getSocialConfig(platform);
        return config && config.clientId && config.clientSecret && 
               !config.clientId.includes('_client_id');
    }

    getConfiguredSocialPlatforms() {
        const platforms = Object.keys(this.config.social);
        return platforms.filter(platform => this.isSocialPlatformConfigured(platform));
    }

    getRedirectUri(platform) {
        const config = this.getSocialConfig(platform);
        if (!config || !config.redirectUri) {
            return null;
        }
        
        if (this.config.isDevelopment) {
            return config.redirectUri.replace('https://yourdomain.com', 'http://localhost:3000');
        }
        
        return config.redirectUri;
    }

    getDataForSEOConfig() {
        return {
            environment: this.config.dataforseo.environment,
            baseUrl: this.config.dataforseo.baseUrl,  // Fixed: was baseURL, should be baseUrl
            username: this.config.dataforseo.username,
            password: this.config.dataforseo.password
        };
    }

    getEnvironmentInfo() {
        return {
            environment: this.config.environment,
            isDevelopment: this.config.isDevelopment,
            isProduction: this.config.isProduction,
            isSandbox: this.config.isSandbox,
            configuredSocialPlatforms: this.getConfiguredSocialPlatforms(),
            dataforseoEnvironment: this.config.dataforseo.environment,
            openaiModel: this.config.openai.model
        };
    }

    validateConfig() {
        const errors = [];
        const warnings = [];

        if (!this.config.dataforseo.username || !this.config.dataforseo.password) {
            if (this.currentEnvironment === 'production') {
                errors.push('⚠️ DataForSEO credentials not configured. Please set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD in DigitalOcean App Platform environment variables');
            } else {
                errors.push('DataForSEO credentials not configured. Please set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD');
            }
        }

        if (!this.config.openai.apiKey) {
            if (this.currentEnvironment === 'production') {
                errors.push('⚠️ OpenAI API key not configured. Please set OPENAI_API_KEY in DigitalOcean App Platform environment variables');
            } else {
                errors.push('OpenAI API key not configured');
            }
        }

        if (!this.config.supabase.url || !this.config.supabase.anonKey) {
            if (this.currentEnvironment === 'production') {
                errors.push('⚠️ Supabase configuration not complete. Please set SUPABASE_URL and SUPABASE_ANON_KEY in DigitalOcean App Platform environment variables');
            } else {
                errors.push('Supabase configuration not complete');
            }
        }

        const socialPlatforms = Object.keys(this.config.social);
        socialPlatforms.forEach(platform => {
            const config = this.config.social[platform];
            if (!config.clientId || !config.clientSecret) {
                warnings.push(`${platform} OAuth not configured`);
            }
        });

        return { errors, warnings };
    }

    logConfig() {
        console.log('\n🌍 Environment Configuration Summary:');
        console.log(`   Environment: ${this.config.environment}`);
        console.log(`   DataForSEO: ${this.config.dataforseo.environment} (${this.config.dataforseo.baseUrl})`);
        console.log(`   OpenAI Model: ${this.config.openai.model}`);
        console.log(`   Sandbox Mode: ${this.config.isSandbox ? '✅ Enabled' : '❌ Disabled'}`);
        console.log(`   Debug Logs: ${this.config.isDevelopment ? '✅ Enabled' : '❌ Disabled'}`);
        
        const configuredPlatforms = this.getConfiguredSocialPlatforms();
        console.log(`   Social Platforms: ${configuredPlatforms.length}/7 configured`);
        
        if (configuredPlatforms.length > 0) {
            console.log(`   Configured: ${configuredPlatforms.join(', ')}`);
        }
        
        console.log('');
    }

    getStatus() {
        return {
            environment: this.config.environment,
            isDevelopment: this.config.isDevelopment,
            isProduction: this.config.isProduction,
            isSandbox: this.config.isSandbox,
            dataforseo: {
                environment: this.config.dataforseo.environment,
                baseUrl: this.config.dataforseo.baseUrl,
                configured: !!(this.config.dataforseo.username && this.config.dataforseo.password)
            },
            openai: {
                model: this.config.openai.model,
                configured: !!this.config.openai.apiKey
            },
            supabase: {
                configured: !!(this.config.supabase.url && this.config.supabase.anonKey)
            },
            social: {
                configuredPlatforms: this.getConfiguredSocialPlatforms(),
                totalPlatforms: Object.keys(this.config.social).length
            },
            features: {
                enableSandboxMode: this.config.features.enableSandboxMode,
                enableDemoData: this.config.features.enableDemoData,
                enableMockResponses: this.config.features.enableMockResponses
            }
        };
    }

    switchToDevelopment() {
        this.currentEnvironment = 'development';
        this.config = this.loadEnvironmentConfig();
        console.log('🔄 Switched to development environment');
    }

    switchToProduction() {
        this.currentEnvironment = 'production';
        this.config = this.loadEnvironmentConfig();
        console.log('🔄 Switched to production environment');
    }

    forceSandboxMode() {
        this.config.dataforseo.environment = 'sandbox';
        this.config.dataforseo.baseUrl = 'https://sandbox.dataforseo.com/v3';
        this.config.isSandbox = true;
        console.log('🔄 Forced sandbox mode');
    }

    forceProductionMode() {
        this.config.dataforseo.environment = 'production';
        this.config.dataforseo.baseUrl = 'https://api.dataforseo.com/v3';
        this.config.isSandbox = false;
        console.log('🔄 Forced production mode');
    }

    getDataForSEOConfig() {
        return this.config.dataforseo;
    }

    getOpenAIConfig() {
        return this.config.openai;
    }

    getSupabaseConfig() {
        return this.config.supabase;
    }

    getSocialConfig() {
        return this.config.social;
    }

    getFeaturesConfig() {
        return this.config.features;
    }
}

module.exports = EnvironmentConfig;