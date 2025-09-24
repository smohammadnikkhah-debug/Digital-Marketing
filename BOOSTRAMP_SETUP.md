# Boostramp API Integration Setup

This guide will help you set up the Boostramp API integration for comprehensive SEO analysis.

## Prerequisites

1. **Boostramp Account**: You need an active Boostramp account
2. **API Key**: Generate an API key from your Boostramp dashboard
3. **Node.js**: Ensure you have Node.js installed

## Setup Steps

### 1. Get Your Boostramp API Key

1. Log in to your Boostramp account at [https://app.boostramp.com](https://app.boostramp.com)
2. Navigate to your account settings or API section
3. Generate a new API key
4. Copy the API key for the next step

### 2. Configure Environment Variables

Create a `.env` file in your project root with the following content:

```env
PORT=3000
NODE_ENV=development

# Boostramp API Configuration
BOOSTRAMP_API_KEY=your_actual_api_key_here
BOOSTRAMP_BASE_URL=https://app.boostramp.com/api
DEFAULT_LOCATION_CODE=1
```

**Important**: Replace `your_actual_api_key_here` with your actual Boostramp API key.

### 3. Install Dependencies

Run the following command to install the required dependencies:

```bash
npm install
```

### 4. Test the Integration

1. Start the server:
   ```bash
   npm start
   ```

2. Open your browser and go to `http://localhost:3000`

3. Enter a website URL (e.g., `https://example.com`) and click "Analyze SEO"

4. Check the server console for authentication messages:
   - ✅ `Successfully authenticated with Boostramp API` - Integration working
   - ❌ `Boostramp authentication error` - Check your API key

## API Endpoints Used

The integration uses the following Boostramp API endpoints:

### Authentication
- **Endpoint**: `POST /api/login.php`
- **Purpose**: Authenticate and get session token
- **Parameters**: `api_key`

### Project Management
- **Endpoint**: `POST /api/project.php?func=create`
- **Purpose**: Create a new project for website analysis
- **Parameters**: `token`, `url`, `name`

### On-Page Analysis
- **Endpoint**: `GET /api/page.php?func=getPages`
- **Purpose**: Get detailed on-page SEO metrics
- **Parameters**: `token`, `project_id`

### Backlink Analysis
- **Endpoint**: `GET /api/backlink.php?func=getBacklinks`
- **Purpose**: Get backlink analysis data
- **Parameters**: `token`, `project_id`

### Keyword Research
- **Endpoint**: `GET /api/tools.php?func=getKeywords`
- **Purpose**: Get keyword suggestions
- **Parameters**: `token`, `keyword`, `location_code`

## Features

### Comprehensive Analysis
- **Web Scraping**: Basic SEO elements extraction
- **Boostramp Integration**: Advanced SEO metrics
- **Technical SEO**: Canonical URLs, meta tags, etc.
- **Performance Scoring**: Overall SEO score calculation

### Fallback System
If Boostramp API is unavailable, the system will:
1. Use basic web scraping for analysis
2. Generate recommendations based on scraped data
3. Provide a fallback score calculation

### Real-time Recommendations
The system generates actionable recommendations for:
- Title tag optimization
- Meta description improvements
- Heading structure
- Image alt text
- Technical SEO elements
- Link optimization

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Check if your API key is correct
   - Ensure your Boostramp account is active
   - Verify the API key has proper permissions

2. **Project Creation Failed**
   - Check if the URL is accessible
   - Ensure the URL follows proper format (http:// or https://)
   - Verify your Boostramp account limits

3. **Analysis Timeout**
   - Large websites may take longer to analyze
   - Check your internet connection
   - Verify the target website is accessible

### Debug Mode

To enable debug logging, set the environment variable:
```env
NODE_ENV=development
```

This will show detailed console logs for troubleshooting.

## Security Notes

1. **Never commit your `.env` file** to version control
2. **Keep your API key secure** and don't share it publicly
3. **Use environment variables** for all sensitive configuration
4. **Regularly rotate your API keys** for security

## Support

If you encounter issues:

1. Check the server console for error messages
2. Verify your Boostramp account status
3. Test with a simple URL first (e.g., `https://example.com`)
4. Check the Boostramp API documentation for updates

## Next Steps

Once the basic integration is working, you can:

1. **Customize Analysis**: Modify the analysis parameters
2. **Add More Metrics**: Include additional SEO factors
3. **Implement Caching**: Store analysis results for faster responses
4. **Add User Accounts**: Implement user authentication
5. **Export Reports**: Generate downloadable SEO reports

---

**Need Help?** Check the Boostramp API documentation or contact their support team for API-specific issues.

