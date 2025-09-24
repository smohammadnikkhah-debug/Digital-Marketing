const mongoose = require('mongoose');

// User Schema
const userSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  name: { type: String, required: true },
  company: { type: String },
  plan: { 
    type: String, 
    enum: ['free', 'basic', 'pro', 'business', 'enterprise'],
    default: 'free'
  },
  subscription: {
    status: { type: String, enum: ['active', 'cancelled', 'expired', 'trial'], default: 'trial' },
    startDate: { type: Date, default: Date.now },
    endDate: { type: Date },
    trialEndDate: { type: Date, default: () => new Date(Date.now() + 14 * 24 * 60 * 60 * 1000) },
    stripeCustomerId: { type: String },
    stripeSubscriptionId: { type: String }
  },
  usage: {
    websites: { type: Number, default: 0 },
    chatMessages: { type: Number, default: 0 },
    seoAnalyses: { type: Number, default: 0 },
    contentRequests: { type: Number, default: 0 },
    lastResetDate: { type: Date, default: Date.now }
  },
  limits: {
    websites: { type: Number, default: 1 },
    chatMessages: { type: Number, default: 10 },
    seoAnalyses: { type: Number, default: 1 },
    contentRequests: { type: Number, default: 0 }
  },
  websites: [{
    url: { type: String, required: true },
    name: { type: String },
    addedDate: { type: Date, default: Date.now },
    lastAnalysis: { type: Date },
    analysisCount: { type: Number, default: 0 }
  }],
  teamMembers: [{
    email: { type: String },
    role: { type: String, enum: ['admin', 'editor', 'viewer'], default: 'viewer' },
    addedDate: { type: Date, default: Date.now }
  }],
  settings: {
    notifications: { type: Boolean, default: true },
    emailReports: { type: Boolean, default: true },
    autoAnalysis: { type: Boolean, default: false }
  },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now }
});

// Plan limits configuration
const PLAN_LIMITS = {
  free: {
    websites: 1,
    chatMessages: 10,
    seoAnalyses: 1,
    contentRequests: 0,
    price: 0,
    features: ['Basic SEO Analysis', 'Limited Chat', 'Community Support']
  },
  basic: {
    websites: 1,
    chatMessages: 50,
    seoAnalyses: 5,
    contentRequests: 2,
    price: 49,
    features: ['1 Website', '50 AI Chat Messages', '5 Deep SEO Analyses', '2 Content Writing Requests', 'Manual Updates', 'Email Support']
  },
  pro: {
    websites: 3,
    chatMessages: 200,
    seoAnalyses: 15,
    contentRequests: 10,
    price: 99,
    features: ['3 Websites', '200 AI Chat Messages', '15 Deep SEO Analyses', '10 Content Writing Requests', 'Automated Updates', 'API Access', 'Priority Support', 'White-label Reports']
  },
  business: {
    websites: -1, // Unlimited
    chatMessages: -1, // Unlimited
    seoAnalyses: -1, // Unlimited
    contentRequests: -1, // Unlimited
    price: 199,
    features: ['Unlimited Websites', 'Unlimited AI Chat', 'Unlimited SEO Analyses', 'Unlimited Content Writing', 'Full Automation', 'Team Collaboration', 'Advanced Analytics', 'Custom Integrations', 'Dedicated Support']
  },
  enterprise: {
    websites: -1,
    chatMessages: -1,
    seoAnalyses: -1,
    contentRequests: -1,
    price: 499,
    features: ['Everything in Business', 'Unlimited Team Members', 'Custom AI Training', 'On-premise Deployment', 'SLA Guarantees', 'Dedicated Support Team', 'Custom Development']
  }
};

// User methods
userSchema.methods.checkUsageLimit = function(feature) {
  const planLimits = PLAN_LIMITS[this.plan];
  const limit = planLimits[feature];
  
  if (limit === -1) return true; // Unlimited
  
  const currentUsage = this.usage[feature];
  return currentUsage < limit;
};

userSchema.methods.incrementUsage = function(feature) {
  if (this.checkUsageLimit(feature)) {
    this.usage[feature]++;
    return true;
  }
  return false;
};

userSchema.methods.resetMonthlyUsage = function() {
  const now = new Date();
  const lastReset = new Date(this.usage.lastResetDate);
  
  // Check if it's a new month
  if (now.getMonth() !== lastReset.getMonth() || now.getFullYear() !== lastReset.getFullYear()) {
    this.usage.chatMessages = 0;
    this.usage.seoAnalyses = 0;
    this.usage.contentRequests = 0;
    this.usage.lastResetDate = now;
    return true;
  }
  return false;
};

userSchema.methods.upgradePlan = function(newPlan) {
  if (PLAN_LIMITS[newPlan]) {
    this.plan = newPlan;
    this.limits = { ...PLAN_LIMITS[newPlan] };
    this.updatedAt = new Date();
    return true;
  }
  return false;
};

userSchema.methods.addWebsite = function(url, name) {
  if (this.checkUsageLimit('websites')) {
    this.websites.push({ url, name });
    this.usage.websites++;
    return true;
  }
  return false;
};

userSchema.methods.removeWebsite = function(url) {
  const index = this.websites.findIndex(site => site.url === url);
  if (index !== -1) {
    this.websites.splice(index, 1);
    this.usage.websites--;
    return true;
  }
  return false;
};

userSchema.methods.addTeamMember = function(email, role = 'viewer') {
  if (this.plan === 'business' || this.plan === 'enterprise') {
    this.teamMembers.push({ email, role });
    return true;
  }
  return false;
};

userSchema.methods.removeTeamMember = function(email) {
  const index = this.teamMembers.findIndex(member => member.email === email);
  if (index !== -1) {
    this.teamMembers.splice(index, 1);
    return true;
  }
  return false;
};

userSchema.methods.getPlanInfo = function() {
  return PLAN_LIMITS[this.plan];
};

userSchema.methods.getUsageStats = function() {
  const planLimits = PLAN_LIMITS[this.plan];
  return {
    websites: {
      used: this.usage.websites,
      limit: planLimits.websites,
      unlimited: planLimits.websites === -1
    },
    chatMessages: {
      used: this.usage.chatMessages,
      limit: planLimits.chatMessages,
      unlimited: planLimits.chatMessages === -1
    },
    seoAnalyses: {
      used: this.usage.seoAnalyses,
      limit: planLimits.seoAnalyses,
      unlimited: planLimits.seoAnalyses === -1
    },
    contentRequests: {
      used: this.usage.contentRequests,
      limit: planLimits.contentRequests,
      unlimited: planLimits.contentRequests === -1
    }
  };
};

// Static methods
userSchema.statics.getPlanLimits = function(plan) {
  return PLAN_LIMITS[plan] || null;
};

userSchema.statics.getAllPlans = function() {
  return PLAN_LIMITS;
};

userSchema.statics.createUser = function(userData) {
  const user = new this(userData);
  user.limits = { ...PLAN_LIMITS[user.plan] };
  return user;
};

module.exports = mongoose.model('User', userSchema);

