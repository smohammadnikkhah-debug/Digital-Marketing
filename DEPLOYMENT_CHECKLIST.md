# DigitalOcean Deployment Checklist

## Pre-Deployment Checklist

### ✅ Environment Setup
- [ ] DigitalOcean account created
- [ ] doctl CLI installed and authenticated
- [ ] GitHub repository accessible
- [ ] All required API keys obtained

### ✅ Code Preparation
- [ ] Code committed to GitHub repository
- [ ] All dependencies listed in `package.json`
- [ ] No hardcoded local paths or URLs
- [ ] Production environment variables configured

### ✅ Configuration Files
- [ ] `.do/app.yaml` created and configured
- [ ] `Dockerfile` created
- [ ] `.dockerignore` configured
- [ ] `production.env.example` created

### ✅ Environment Variables
- [ ] `NODE_ENV=production` set
- [ ] `PORT=3000` configured
- [ ] DataForSEO credentials configured
- [ ] OpenAI API key configured
- [ ] Supabase credentials configured
- [ ] Stripe keys configured
- [ ] Auth0 credentials configured
- [ ] JWT_SECRET set
- [ ] All social media API keys configured (optional)

## Deployment Process

### Step 1: Install doctl CLI
```bash
# Windows
winget install DigitalOcean.doctl

# macOS
brew install doctl

# Linux
wget https://github.com/digitalocean/doctl/releases/download/v1.94.0/doctl-1.94.0-linux-amd64.tar.gz
tar xf doctl-1.94.0-linux-amd64.tar.gz
sudo mv doctl /usr/local/bin
```

### Step 2: Authenticate
```bash
doctl auth init
```

### Step 3: Prepare Environment
```bash
# Copy and configure environment variables
cp production.env.example .env
# Edit .env with your actual values

# Fix any null values
node fix-production-env.js
```

### Step 4: Deploy
```bash
# Windows
deploy-digitalocean.bat

# Linux/macOS
./deploy-digitalocean.sh
```

### Step 5: Monitor
```bash
# Check app status
doctl apps list

# View logs
doctl apps logs <APP_ID> --follow

# Get app URL
doctl apps get <APP_ID> --format DefaultIngress
```

## Post-Deployment Checklist

### ✅ Application Testing
- [ ] App is accessible via provided URL
- [ ] Authentication flow works
- [ ] Dashboard loads correctly
- [ ] SEO analysis features work
- [ ] Payment processing works
- [ ] All API integrations functional

### ✅ Performance & Security
- [ ] HTTPS enabled (automatic with DigitalOcean)
- [ ] Health checks passing
- [ ] No sensitive data in logs
- [ ] Environment variables properly set
- [ ] Database connections working

### ✅ Monitoring Setup
- [ ] App monitoring configured
- [ ] Log aggregation set up
- [ ] Error tracking configured
- [ ] Performance monitoring enabled

## Troubleshooting

### Common Issues

#### 1. Authentication Errors
```bash
# Re-authenticate
doctl auth init
```

#### 2. Environment Variable Issues
```bash
# Check environment variables
doctl apps get <APP_ID> --format Env

# Update environment variables
doctl apps update <APP_ID> --spec .do/app.yaml
```

#### 3. Build Failures
```bash
# Check build logs
doctl apps logs <APP_ID> --type build

# Verify dependencies
npm install
```

#### 4. Runtime Errors
```bash
# Check runtime logs
doctl apps logs <APP_ID> --type run

# Check app status
doctl apps get <APP_ID>
```

### Debugging Commands

```bash
# List all apps
doctl apps list

# Get detailed app info
doctl apps get <APP_ID>

# View all logs
doctl apps logs <APP_ID> --follow

# View specific log types
doctl apps logs <APP_ID> --type build
doctl apps logs <APP_ID> --type run
doctl apps logs <APP_ID> --type deploy

# Update app configuration
doctl apps update <APP_ID> --spec .do/app.yaml

# Delete app (if needed)
doctl apps delete <APP_ID>
```

## Cost Optimization

### Resource Sizing
- **Basic XXS**: 0.25 vCPU, 512MB RAM - $5/month (testing)
- **Basic S**: 1 vCPU, 1GB RAM - $12/month (small production)
- **Basic M**: 2 vCPU, 2GB RAM - $24/month (medium production)

### Scaling Options
- **Horizontal Scaling**: Increase instance count
- **Vertical Scaling**: Increase instance size
- **Auto-scaling**: Configure based on metrics

## Security Best Practices

### Environment Security
- [ ] No secrets in code
- [ ] Environment variables encrypted
- [ ] API keys rotated regularly
- [ ] Access logs monitored

### Application Security
- [ ] HTTPS enforced
- [ ] CORS properly configured
- [ ] Input validation implemented
- [ ] SQL injection prevention
- [ ] XSS protection enabled

### Infrastructure Security
- [ ] Firewall rules configured
- [ ] Network security groups set
- [ ] Regular security updates
- [ ] Backup strategy implemented

## Maintenance

### Regular Tasks
- [ ] Monitor application performance
- [ ] Check for security updates
- [ ] Review and rotate API keys
- [ ] Monitor costs and usage
- [ ] Backup database regularly

### Update Process
1. Test changes locally
2. Commit to GitHub
3. Deploy to staging (if available)
4. Deploy to production
5. Monitor for issues
6. Rollback if necessary

## Support Resources

### Documentation
- [DigitalOcean App Platform Docs](https://docs.digitalocean.com/products/app-platform/)
- [doctl CLI Reference](https://docs.digitalocean.com/reference/doctl/)
- [Node.js Deployment Guide](https://docs.digitalocean.com/products/app-platform/how-to/deploy-nodejs-app/)

### Community
- [DigitalOcean Community](https://www.digitalocean.com/community)
- [Stack Overflow](https://stackoverflow.com/questions/tagged/digitalocean)
- [GitHub Issues](https://github.com/digitalocean/doctl/issues)

### Support
- [DigitalOcean Support](https://cloud.digitalocean.com/support)
- [Status Page](https://status.digitalocean.com/)

## Emergency Procedures

### App Down
1. Check DigitalOcean status page
2. Review application logs
3. Check environment variables
4. Verify database connectivity
5. Contact support if needed

### Data Loss
1. Check backup availability
2. Restore from latest backup
3. Verify data integrity
4. Update backup procedures

### Security Incident
1. Immediately rotate all API keys
2. Review access logs
3. Check for unauthorized access
4. Update security measures
5. Notify relevant parties

## Success Metrics

### Performance Metrics
- [ ] Response time < 2 seconds
- [ ] Uptime > 99.9%
- [ ] Error rate < 0.1%
- [ ] CPU usage < 80%
- [ ] Memory usage < 80%

### Business Metrics
- [ ] User registration working
- [ ] Payment processing successful
- [ ] SEO analysis functional
- [ ] Dashboard accessible
- [ ] API endpoints responding

## Final Verification

Before considering deployment complete:

- [ ] All checklist items completed
- [ ] Application fully functional
- [ ] Performance metrics met
- [ ] Security measures in place
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Team trained on deployment process

---

**Deployment Date**: ___________
**Deployed By**: ___________
**App URL**: ___________
**App ID**: ___________
**Notes**: ___________

