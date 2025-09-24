# Digital Marketing SEO Platform

A comprehensive AI-powered SEO analysis and content generation platform.

## 🚀 Quick Start

### 1. **Clone the Repository**
```bash
git clone <your-repo-url>
cd digital-marketing-platform
```

### 2. **Install Dependencies**
```bash
npm install
```

### 3. **Environment Setup**
```bash
# Copy the environment template
cp env.template .env

# Edit the .env file with your actual API keys
nano .env
```

### 4. **Required API Keys**
You'll need to obtain API keys for:
- **OpenAI**: Get your API key from [OpenAI Platform](https://platform.openai.com/)
- **DataForSEO**: Sign up at [DataForSEO](https://dataforseo.com/)
- **Supabase**: Create a project at [Supabase](https://supabase.com/)
- **Auth0**: Set up authentication at [Auth0](https://auth0.com/)

### 5. **Start the Application**
```bash
# Development mode
npm start

# Or directly with Node.js
node server.js
```

## 📁 Project Structure

```
├── frontend/                 # Frontend HTML/CSS/JS files
├── routes/                   # API route handlers
├── services/                 # Business logic services
├── models/                   # Database models
├── images/                   # Static images
├── components/               # Reusable components
├── server.js                 # Main server file
├── package.json              # Dependencies
├── env.template              # Environment template
└── .gitignore               # Git ignore rules
```

## 🔧 Environment Configuration

### Development Environment
- Uses DataForSEO Sandbox API (free)
- Debug logging enabled
- Social connections visible
- Mock responses available

### Production Environment
- Uses DataForSEO Production API
- Optimized logging
- Social connections hidden
- Real API responses only

## 🚀 Deployment

### Quick Deployment (Recommended)
```bash
# On your production server
git clone <your-repo-url>
cd digital-marketing-platform
chmod +x deploy.sh
./deploy.sh
```

### Manual Deployment
1. Set up a VPS (DigitalOcean, Linode, etc.)
2. Install Node.js 18+
3. Install PM2 and Nginx
4. Configure environment variables
5. Set up SSL certificate

See `PRODUCTION_DEPLOYMENT_CHECKLIST.md` for detailed instructions.

## 🛡️ Security Features

- Environment-based feature toggling
- Social connections hidden in production
- Rate limiting and CORS protection
- Secure session management
- SSL/HTTPS support

## 📊 Features

- **SEO Analysis**: Comprehensive website analysis
- **Content Generation**: AI-powered blog and content creation
- **Content Calendar**: Automated social media content planning
- **Keyword Research**: Advanced keyword analysis
- **Competitor Analysis**: Track competitor performance
- **Backlink Analysis**: Monitor backlink profiles
- **Technical SEO**: Identify technical issues

## 🔑 API Endpoints

- `GET /` - Main dashboard
- `GET /blog` - Blog generator
- `GET /seo-tools-content-calendar` - Content calendar
- `POST /api/blog/generate` - Generate blog content
- `POST /api/content-calendar/generate-seo-content` - Generate calendar content

## 📝 License

This project is proprietary software. All rights reserved.

## 🆘 Support

For support and questions, please contact the development team.