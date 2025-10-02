# DigitalOcean Deployment Guide

This guide will help you deploy the Digital Marketing SEO Analyzer to DigitalOcean App Platform.

## Prerequisites

1. **DigitalOcean Account**: Sign up at [digitalocean.com](https://digitalocean.com)
2. **doctl CLI**: Install the DigitalOcean command-line tool
3. **GitHub Repository**: Your code should be in a GitHub repository
4. **Environment Variables**: All required API keys and secrets

## Step 1: Install doctl CLI

### Windows
```bash
# Using winget
winget install DigitalOcean.doctl

# Or download from: https://github.com/digitalocean/doctl/releases
```

### macOS
```bash
brew install doctl
```

### Linux
```bash
# Download and install
wget https://github.com/digitalocean/doctl/releases/download/v1.94.0/doctl-1.94.0-linux-amd64.tar.gz
tar xf doctl-1.94.0-linux-amd64.tar.gz
sudo mv doctl /usr/local/bin
```

## Step 2: Authenticate with DigitalOcean

```bash
doctl auth init
```

Enter your DigitalOcean API token when prompted. You can generate one at: https://cloud.digitalocean.com/account/api/tokens

## Step 3: Prepare Environment Variables

1. Copy the example environment file:
```bash
cp production.env.example .env
```

2. Edit `.env` with your actual values:
```bash
# Required variables
NODE_ENV=production
DATAFORSEO_USERNAME=your_actual_username
DATAFORSEO_PASSWORD=your_actual_password
OPENAI_API_KEY=your_actual_openai_key
SUPABASE_URL=your_actual_supabase_url
SUPABASE_ANON_KEY=your_actual_supabase_key
STRIPE_SECRET_KEY=your_actual_stripe_key
AUTH0_DOMAIN=your_actual_auth0_domain
AUTH0_CLIENT_ID=your_actual_auth0_client_id
AUTH0_CLIENT_SECRET=your_actual_auth0_client_secret
# ... and all other required variables
```

## Step 4: Deploy to DigitalOcean

### Option A: Using the deployment script (Recommended)

**Windows:**
```bash
deploy-digitalocean.bat
```

**Linux/macOS:**
```bash
./deploy-digitalocean.sh
```

### Option B: Manual deployment

1. **Create the app:**
```bash
doctl apps create --spec .do/app.yaml
```

2. **Update existing app:**
```bash
doctl apps update <APP_ID> --spec .do/app.yaml
```

## Step 5: Monitor Deployment

1. **Check app status:**
```bash
doctl apps list
doctl apps get <APP_ID>
```

2. **View logs:**
```bash
doctl apps logs <APP_ID> --follow
```

3. **Get app URL:**
```bash
doctl apps get <APP_ID> --format DefaultIngress
```

## Step 6: Configure Custom Domain (Optional)

1. In the DigitalOcean dashboard, go to your app
2. Navigate to Settings > Domains
3. Add your custom domain
4. Update your DNS records as instructed

## Configuration Files

### `.do/app.yaml`
This file defines your app configuration for DigitalOcean App Platform:
- Service configuration
- Environment variables
- Health checks
- Scaling settings

### `Dockerfile`
Container configuration for your application:
- Node.js 18 base image
- Security best practices
- Health checks
- Non-root user

### `production.env.example`
Template for production environment variables

## Environment Variables Reference

### Required Variables
- `NODE_ENV`: Set to "production"
- `DATAFORSEO_USERNAME`: Your DataForSEO username
- `DATAFORSEO_PASSWORD`: Your DataForSEO password
- `OPENAI_API_KEY`: Your OpenAI API key
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_ANON_KEY`: Your Supabase anonymous key
- `STRIPE_SECRET_KEY`: Your Stripe secret key
- `STRIPE_PUBLISHABLE_KEY`: Your Stripe publishable key
- `AUTH0_DOMAIN`: Your Auth0 domain
- `AUTH0_CLIENT_ID`: Your Auth0 client ID
- `AUTH0_CLIENT_SECRET`: Your Auth0 client secret
- `AUTH0_SESSION_SECRET`: Random secret for sessions
- `JWT_SECRET`: Random secret for JWT tokens

### Optional Variables
- Social media API keys (Google, Facebook, Twitter, etc.)
- `SENDGRID_API_KEY`: For email functionality
- `GOOGLE_PLACES_API_KEY`: For location services

## Troubleshooting

### Common Issues

1. **Authentication Error**
   ```bash
   doctl auth init
   ```

2. **Environment Variables Not Set**
   - Check your `.env` file
   - Ensure all required variables are set
   - Verify no placeholder values remain

3. **Build Failures**
   - Check the build logs: `doctl apps logs <APP_ID>`
   - Verify all dependencies are in `package.json`
   - Check for any missing files

4. **App Not Starting**
   - Check runtime logs: `doctl apps logs <APP_ID> --follow`
   - Verify the `PORT` environment variable is set
   - Check if the app is listening on the correct port

### Getting Help

1. **DigitalOcean Documentation**: https://docs.digitalocean.com/products/app-platform/
2. **doctl CLI Reference**: https://docs.digitalocean.com/reference/doctl/
3. **Community Support**: https://www.digitalocean.com/community

## Cost Estimation

### Basic Plan (Recommended for testing)
- **Instance**: Basic XXS (0.25 vCPU, 512MB RAM)
- **Cost**: ~$5/month
- **Suitable for**: Development and testing

### Production Plan
- **Instance**: Basic S (1 vCPU, 1GB RAM)
- **Cost**: ~$12/month
- **Suitable for**: Small to medium traffic

### High Traffic Plan
- **Instance**: Basic M (2 vCPU, 2GB RAM)
- **Cost**: ~$24/month
- **Suitable for**: High traffic applications

## Security Considerations

1. **Environment Variables**: Never commit `.env` files to version control
2. **API Keys**: Use strong, unique API keys
3. **HTTPS**: DigitalOcean App Platform provides HTTPS by default
4. **Updates**: Keep dependencies updated for security patches

## Monitoring and Maintenance

1. **Health Checks**: Monitor app health through DigitalOcean dashboard
2. **Logs**: Regularly check application logs
3. **Updates**: Deploy updates regularly
4. **Backups**: Ensure your database (Supabase) has proper backups

## Next Steps After Deployment

1. **Test the Application**: Verify all features work correctly
2. **Configure Monitoring**: Set up alerts for downtime
3. **Performance Optimization**: Monitor and optimize as needed
4. **SSL Certificate**: Configure custom domain with SSL
5. **CDN**: Consider adding a CDN for better performance

## Support

If you encounter issues during deployment:

1. Check the troubleshooting section above
2. Review DigitalOcean documentation
3. Check application logs
4. Verify all environment variables are correctly set
5. Ensure your GitHub repository is accessible

For additional help, refer to the DigitalOcean community forums or support documentation.

