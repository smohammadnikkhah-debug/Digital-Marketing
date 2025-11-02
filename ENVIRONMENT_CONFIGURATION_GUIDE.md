# 🔧 Environment Configuration System

## 📋 **Overview**

A comprehensive environment management system that allows easy switching between **Development** (Sandbox) and **Production** (DataForSEO API) environments.

---

## 🎯 **Key Features**

### ✅ **Environment Separation**
- **Development**: Uses DataForSEO Sandbox API (Free)
- **Production**: Uses DataForSEO Production API (Paid)
- **Easy Switching**: Runtime environment switching via API or CLI

### ✅ **Configuration Management**
- Environment-specific configuration files
- Runtime environment switching
- Centralized configuration service
- Environment-aware services

---

## 📁 **File Structure**

```
├── env.development          # Development environment config
├── env.production           # Production environment config
├── env-manager.js           # CLI environment manager
├── services/
│   ├── environmentConfig.js        # Environment configuration service
│   └── dataforseoEnvironmentService.js  # Environment-aware DataForSEO service
└── server.js               # Updated with environment endpoints
```

---

## 🔧 **Environment Configurations**

### **Development Environment (`env.development`)**
```bash
NODE_ENV=development
DATAFORSEO_ENVIRONMENT=sandbox
DATAFORSEO_BASE_URL=https://sandbox.dataforseo.com/v3
ENABLE_SANDBOX_MODE=true
ENABLE_DEMO_DATA=true
ENABLE_DEBUG_LOGS=true
```

### **Production Environment (`env.production`)**
```bash
NODE_ENV=production
DATAFORSEO_ENVIRONMENT=production
DATAFORSEO_BASE_URL=https://api.dataforseo.com/v3
ENABLE_SANDBOX_MODE=false
ENABLE_DEMO_DATA=false
ENABLE_DEBUG_LOGS=false
```

---

## 🚀 **Usage Methods**

### **1. CLI Environment Manager**

```bash
# Switch to development (sandbox)
npm run env:dev
# or
node env-manager.js dev

# Switch to production
npm run env:prod
# or
node env-manager.js prod

# Check current status
npm run env:status
# or
node env-manager.js status

# List available environments
npm run env:list
# or
node env-manager.js list
```

### **2. API Endpoints**

```bash
# Get current environment status
GET /api/environment/status

# Switch to development
POST /api/environment/switch/development

# Switch to production
POST /api/environment/switch/production

# Force sandbox mode
POST /api/environment/force/sandbox

# Force production mode
POST /api/environment/force/production
```

### **3. Environment-Aware Analysis**

```bash
# Use environment-aware analysis endpoint
POST /api/dataforseo/environment/analyze-website
{
  "url": "https://example.com"
}

# Get environment-aware service status
GET /api/dataforseo/environment/status
```

---

## 🧪 **Testing Results**

### **✅ Environment Switching**
```bash
# Development → Production
POST /api/environment/switch/production
Response: "Switched to production environment (Production API)"

# Production → Development  
POST /api/environment/switch/development
Response: "Switched to development environment (Sandbox mode)"
```

### **✅ Environment Status**
```bash
GET /api/environment/status
Response: {
  "currentEnvironment": "development",
  "dataForSEOEnvironment": "sandbox",
  "baseURL": "https://sandbox.dataforseo.com/v3",
  "isSandbox": true,
  "isProduction": false
}
```

### **✅ Environment-Aware Analysis**
```bash
POST /api/dataforseo/environment/analyze-website
Response: {
  "success": true,
  "analysis": {
    "environment": "sandbox",
    "url": "https://google.com",
    "timestamp": "2025-09-15T00:17:17.408Z"
  }
}
```

---

## 📊 **Environment Comparison**

| Feature | Development | Production |
|---------|-------------|------------|
| **DataForSEO API** | Sandbox (Free) | Production (Paid) |
| **Base URL** | `sandbox.dataforseo.com/v3` | `api.dataforseo.com/v3` |
| **Debug Logs** | ✅ Enabled | ❌ Disabled |
| **Demo Data** | ✅ Available | ❌ Disabled |
| **Mock Responses** | ✅ Available | ❌ Disabled |
| **Cost** | 🆓 Free | 💰 Paid |
| **Use Case** | Testing & Development | Production Deployment |

---

## 🔄 **Switching Workflows**

### **Development Workflow**
```bash
# 1. Switch to development
npm run env:dev

# 2. Start server
npm start

# 3. Test with sandbox API
curl -X POST http://localhost:3000/api/dataforseo/environment/analyze-website \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### **Production Workflow**
```bash
# 1. Switch to production
npm run env:prod

# 2. Start server
npm start

# 3. Use production API
curl -X POST http://localhost:3000/api/dataforseo/environment/analyze-website \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### **Runtime Switching**
```bash
# Switch environments without restarting server
curl -X POST http://localhost:3000/api/environment/switch/production
curl -X POST http://localhost:3000/api/environment/switch/development
```

---

## 🎯 **Benefits**

### **💰 Cost Management**
- **Development**: Free sandbox testing
- **Production**: Pay only for production usage
- **Easy Testing**: No API costs during development

### **🚀 Development Efficiency**
- **Quick Switching**: Change environments instantly
- **Consistent Configuration**: Centralized environment management
- **Debug Support**: Development-specific logging and features

### **🔒 Production Safety**
- **Environment Isolation**: Clear separation between dev/prod
- **Configuration Validation**: Automatic environment validation
- **Runtime Control**: Switch environments without restarts

---

## 📝 **Integration Points**

### **Services Updated**
- ✅ `environmentConfig.js` - Core configuration service
- ✅ `dataforseoEnvironmentService.js` - Environment-aware DataForSEO service
- ✅ `server.js` - Environment management endpoints

### **Frontend Integration**
- ✅ Onboarding flow uses environment-aware endpoints
- ✅ Dashboard supports environment switching
- ✅ All analysis endpoints respect environment configuration

### **CLI Tools**
- ✅ `env-manager.js` - Command-line environment management
- ✅ NPM scripts for easy environment switching
- ✅ Status checking and validation

---

## 🎉 **Ready to Use!**

The environment configuration system is now **fully operational** and provides:

1. **🆓 Free Development**: Use sandbox API for testing
2. **💰 Production Ready**: Switch to production API when needed
3. **🔄 Easy Switching**: Change environments via CLI or API
4. **📊 Full Visibility**: Monitor environment status and configuration
5. **🚀 Seamless Integration**: All services respect environment settings

### **Quick Start**
```bash
# Development (Sandbox)
npm run start:dev

# Production (API)
npm run start:prod

# Check status
npm run env:status
```

---

*Generated on: ${new Date().toISOString()}*
*Environment System Version: 1.0.0*







