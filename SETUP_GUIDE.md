# AI-Powered Digital Marketing Platform - Setup Guide

## 🚀 Prerequisites & Setup Instructions

### 1. **OpenAI API Key Setup**

#### Step 1: Get OpenAI API Key
1. Visit [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in to your account
3. Go to API Keys section
4. Create a new API key
5. Copy the API key (starts with `sk-`)

#### Step 2: Add to Environment Variables
Add to your `.env` file:
```env
OPENAI_API_KEY=sk-your-actual-api-key-here
OPENAI_MODEL=gpt-4-turbo-preview
```

#### Step 3: API Usage & Costs
- **Cost**: ~$0.01-0.03 per 1K tokens
- **Estimated monthly cost**: $50-200 per active user
- **Rate limiting**: Implemented to control costs
- **Free tier**: $5 credit for new accounts

### 2. **Website Integration Prerequisites**

#### For WordPress Sites:
```env
# WordPress REST API
WORDPRESS_API_URL=https://your-site.com/wp-json/wp/v2/
WORDPRESS_USERNAME=your_username
WORDPRESS_PASSWORD=your_app_password
```

**Setup Steps:**
1. Enable WordPress REST API
2. Create Application Password:
   - Go to Users → Your Profile
   - Scroll to Application Passwords
   - Create new application password
   - Use this password (not your regular password)

#### For Static Sites (FTP/SFTP):
```env
# FTP/SFTP Access
FTP_HOST=your-ftp-host.com
FTP_USERNAME=your_username
FTP_PASSWORD=your_password
FTP_PORT=21
FTP_SECURE=false
```

#### For Custom CMS/Database:
```env
# Database Access
DATABASE_URL=mysql://username:password@host:port/database
# or
DATABASE_URL=postgresql://username:password@host:port/database
```

### 3. **Installation Steps**

#### Step 1: Install Dependencies
```bash
npm install
```

#### Step 2: Update Environment Variables
Create or update `.env` file:
```env
# Server Configuration
PORT=3000
NODE_ENV=development

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4-turbo-preview

# Boostramp Configuration (existing)
BOOSTRAMP_API_KEY=your_boostramp_api_key
BOOSTRAMP_BASE_URL=https://app.boostramp.com/api
DEFAULT_LOCATION_CODE=1

# Security
JWT_SECRET=your-super-secret-jwt-key
RATE_LIMIT_WINDOW=15
RATE_LIMIT_MAX_REQUESTS=100

# Website Integration (choose one)
# WordPress
WORDPRESS_API_URL=https://your-site.com/wp-json/wp/v2/
WORDPRESS_USERNAME=your_username
WORDPRESS_PASSWORD=your_app_password

# FTP/SFTP
FTP_HOST=your-ftp-host.com
FTP_USERNAME=your_username
FTP_PASSWORD=your_password
FTP_PORT=21
FTP_SECURE=false

# Database
DATABASE_URL=your_database_connection_string
```

#### Step 3: Start the Server
```bash
npm start
```

#### Step 4: Access the Application
- **Main SEO Analyzer**: http://localhost:3000
- **AI Chat Assistant**: http://localhost:3000/chat

### 4. **Required Permissions**

#### Website Access Permissions:
- [ ] **Admin Access**: Full website administration rights
- [ ] **File Upload**: Ability to upload/modify files
- [ ] **Database Access**: Read/write permissions (if applicable)
- [ ] **API Access**: REST API access (for WordPress)
- [ ] **SSL Certificate**: Valid SSL certificate for secure connections

#### Security Considerations:
- [ ] **Credential Encryption**: All stored credentials are encrypted
- [ ] **Rate Limiting**: API calls are rate-limited
- [ ] **User Permissions**: Role-based access control
- [ ] **Audit Logging**: All actions are logged
- [ ] **Data Backup**: Regular backup of user data

### 5. **Testing the Setup**

#### Test OpenAI Integration:
```bash
# Test API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello"}]}' \
     https://api.openai.com/v1/chat/completions
```

#### Test Website Integration:
1. Go to http://localhost:3000/chat
2. Enter a website URL in the sidebar
3. Click "Analyze Website"
4. Ask AI questions about the analysis

### 6. **Content Management Capabilities**

#### What the AI Can Do:
- **Analyze** website content and SEO
- **Generate** SEO-optimized content
- **Suggest** improvements and optimizations
- **Create** meta tags, titles, descriptions
- **Optimize** images with alt text
- **Implement** schema markup
- **Update** website content (with proper permissions)

#### Supported Platforms:
- ✅ **WordPress** (via REST API)
- ✅ **Static HTML Sites** (via FTP/SFTP)
- ✅ **Custom CMS** (via database)
- ✅ **E-commerce Platforms** (Shopify, WooCommerce)
- ✅ **Headless CMS** (Strapi, Contentful)

### 7. **Troubleshooting**

#### Common Issues:

**OpenAI API Errors:**
- Check API key validity
- Verify account has sufficient credits
- Check rate limiting settings

**Website Integration Errors:**
- Verify credentials are correct
- Check network connectivity
- Ensure proper permissions

**WebSocket Connection Issues:**
- Check if port 3000 is available
- Verify firewall settings
- Check browser console for errors

### 8. **Next Steps**

1. **Test Basic Functionality**: Ensure all components work
2. **Configure Website Access**: Set up integration with your websites
3. **Customize AI Prompts**: Modify prompts for your specific needs
4. **Set Up User Management**: Implement user authentication
5. **Deploy to Production**: Set up production environment

### 9. **Production Deployment**

#### Environment Variables for Production:
```env
NODE_ENV=production
PORT=3000
OPENAI_API_KEY=your-production-api-key
JWT_SECRET=your-production-jwt-secret
RATE_LIMIT_WINDOW=15
RATE_LIMIT_MAX_REQUESTS=50
```

#### Security Checklist:
- [ ] Use HTTPS in production
- [ ] Set up proper CORS policies
- [ ] Implement rate limiting
- [ ] Use environment variables for secrets
- [ ] Set up monitoring and logging
- [ ] Regular security updates

### 10. **Support & Resources**

- **OpenAI Documentation**: https://platform.openai.com/docs
- **Socket.io Documentation**: https://socket.io/docs/
- **Express.js Documentation**: https://expressjs.com/
- **WordPress REST API**: https://developer.wordpress.org/rest-api/

---

## 🎯 Ready to Start?

1. Get your OpenAI API key
2. Install dependencies: `npm install`
3. Update `.env` file with your credentials
4. Start the server: `npm start`
5. Visit http://localhost:3000/chat to test AI chat
6. Configure website integration as needed

**Your AI-powered digital marketing platform is ready to revolutionize SEO! 🚀**

