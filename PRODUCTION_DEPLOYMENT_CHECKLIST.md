# Production Deployment Checklist

## 🚀 Pre-Deployment Setup

### 1. **Environment Configuration**
- [ ] Copy `env.production` to `.env` on server
- [ ] Update all API keys to production values
- [ ] Set `NODE_ENV=production`
- [ ] Configure production database URL
- [ ] Update Auth0 settings for production domain

### 2. **Domain & SSL Configuration**
- [ ] Point domain DNS to server IP
- [ ] Configure SSL certificate (Let's Encrypt)
- [ ] Update Auth0 callback URLs
- [ ] Update Supabase allowed origins

### 3. **Database Setup**
- [ ] Set up production PostgreSQL database
- [ ] Run database migrations
- [ ] Configure Supabase production project
- [ ] Test database connections

### 4. **Service Configuration**

#### **Auth0 Production Setup:**
- [ ] Create production Auth0 application
- [ ] Update callback URLs: `https://yourdomain.com/auth/callback`
- [ ] Update logout URLs: `https://yourdomain.com`
- [ ] Update allowed origins

#### **Supabase Production Setup:**
- [ ] Create production Supabase project
- [ ] Update allowed origins in Supabase dashboard
- [ ] Configure RLS policies
- [ ] Test database connections

#### **OpenAI Configuration:**
- [ ] Use production OpenAI API key
- [ ] Set appropriate rate limits
- [ ] Monitor usage and costs

#### **DataForSEO Configuration:**
- [ ] Switch from sandbox to production API
- [ ] Update base URL to production
- [ ] Monitor API usage

### 5. **Security Configuration**
- [ ] Set strong session secrets
- [ ] Configure CORS properly
- [ ] Set up rate limiting
- [ ] Enable HTTPS only
- [ ] Configure security headers

### 6. **Performance Optimization**
- [ ] Enable gzip compression
- [ ] Set up CDN (optional)
- [ ] Configure caching headers
- [ ] Optimize static assets

## 🔧 Server Configuration

### **Nginx Configuration:**
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

### **PM2 Configuration:**
```json
{
  "apps": [{
    "name": "seo-platform",
    "script": "server.js",
    "instances": "max",
    "exec_mode": "cluster",
    "env": {
      "NODE_ENV": "production",
      "PORT": 3000
    },
    "error_file": "./logs/err.log",
    "out_file": "./logs/out.log",
    "log_file": "./logs/combined.log",
    "time": true
  }]
}
```

## 📊 Monitoring & Maintenance

### **Monitoring Setup:**
- [ ] Set up PM2 monitoring
- [ ] Configure log rotation
- [ ] Set up uptime monitoring
- [ ] Monitor server resources
- [ ] Set up error tracking (Sentry)

### **Backup Strategy:**
- [ ] Database backups
- [ ] Code repository backups
- [ ] Environment configuration backups
- [ ] SSL certificate backups

### **Update Process:**
- [ ] Test updates in staging environment
- [ ] Use blue-green deployment
- [ ] Have rollback plan ready
- [ ] Monitor after deployment

## 🚨 Troubleshooting

### **Common Issues:**
1. **Port conflicts**: Ensure port 3000 is available
2. **Permission issues**: Check file permissions
3. **Environment variables**: Verify all required vars are set
4. **Database connections**: Test database connectivity
5. **SSL issues**: Check certificate validity

### **Debug Commands:**
```bash
# Check PM2 status
pm2 status

# View logs
pm2 logs seo-platform

# Restart application
pm2 restart seo-platform

# Check Nginx status
sudo systemctl status nginx

# Test Nginx configuration
sudo nginx -t
```

## 📈 Performance Tips

1. **Enable compression** in Nginx
2. **Use PM2 cluster mode** for multiple processes
3. **Set up Redis** for session storage (optional)
4. **Use CDN** for static assets
5. **Monitor memory usage** and optimize accordingly

## 🔐 Security Checklist

- [ ] Regular security updates
- [ ] Firewall configuration
- [ ] SSH key authentication only
- [ ] Regular backups
- [ ] Monitor access logs
- [ ] Use strong passwords/keys
- [ ] Enable fail2ban for brute force protection
