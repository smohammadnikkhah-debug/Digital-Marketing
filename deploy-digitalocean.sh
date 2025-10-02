#!/bin/bash

# DigitalOcean Deployment Script
# This script helps deploy the Digital Marketing SEO Analyzer to DigitalOcean App Platform

set -e

echo "🚀 DigitalOcean Deployment Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if doctl is installed
check_doctl() {
    if ! command -v doctl &> /dev/null; then
        print_error "doctl CLI is not installed. Please install it first:"
        echo "  macOS: brew install doctl"
        echo "  Linux: https://docs.digitalocean.com/reference/doctl/how-to/install/"
        echo "  Windows: https://docs.digitalocean.com/reference/doctl/how-to/install/"
        exit 1
    fi
    print_success "doctl CLI is installed"
}

# Check if user is authenticated
check_auth() {
    if ! doctl auth list &> /dev/null; then
        print_error "Not authenticated with DigitalOcean. Please run:"
        echo "  doctl auth init"
        exit 1
    fi
    print_success "Authenticated with DigitalOcean"
}

# Check if .env file exists
check_env() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Please create it from production.env.example"
        echo "  cp production.env.example .env"
        echo "  # Then edit .env with your actual values"
        exit 1
    fi
    print_success ".env file found"
}

# Validate required environment variables
validate_env() {
    print_status "Validating environment variables..."
    
    required_vars=(
        "NODE_ENV"
        "DATAFORSEO_USERNAME"
        "DATAFORSEO_PASSWORD"
        "OPENAI_API_KEY"
        "SUPABASE_URL"
        "SUPABASE_ANON_KEY"
        "STRIPE_SECRET_KEY"
        "STRIPE_PUBLISHABLE_KEY"
        "AUTH0_DOMAIN"
        "AUTH0_CLIENT_ID"
        "AUTH0_CLIENT_SECRET"
        "AUTH0_SESSION_SECRET"
        "JWT_SECRET"
    )
    
    missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=$" .env || grep -q "^${var}=your_" .env; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        print_error "Missing or invalid environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        echo ""
        echo "Please update your .env file with valid values."
        exit 1
    fi
    
    print_success "Environment variables validated"
}

# Deploy to DigitalOcean App Platform
deploy_app() {
    print_status "Deploying to DigitalOcean App Platform..."
    
    # Check if app exists
    if doctl apps list | grep -q "digital-marketing-seo-analyzer"; then
        print_status "App exists, updating..."
        doctl apps update $(doctl apps list --format ID,Name --no-header | grep "digital-marketing-seo-analyzer" | awk '{print $1}') --spec .do/app.yaml
    else
        print_status "Creating new app..."
        doctl apps create --spec .do/app.yaml
    fi
    
    print_success "Deployment initiated"
}

# Show deployment status
show_status() {
    print_status "Checking deployment status..."
    
    app_id=$(doctl apps list --format ID,Name --no-header | grep "digital-marketing-seo-analyzer" | awk '{print $1}')
    
    if [ -n "$app_id" ]; then
        echo ""
        print_success "App ID: $app_id"
        echo ""
        doctl apps get $app_id
        echo ""
        print_status "To view logs:"
        echo "  doctl apps logs $app_id --follow"
        echo ""
        print_status "To view the app:"
        echo "  doctl apps get $app_id --format DefaultIngress"
    fi
}

# Main execution
main() {
    echo ""
    print_status "Starting deployment process..."
    echo ""
    
    check_doctl
    check_auth
    check_env
    validate_env
    
    echo ""
    print_status "All checks passed. Proceeding with deployment..."
    echo ""
    
    deploy_app
    show_status
    
    echo ""
    print_success "Deployment process completed!"
    echo ""
    print_status "Next steps:"
    echo "1. Monitor the deployment in the DigitalOcean dashboard"
    echo "2. Check the app logs for any issues"
    echo "3. Test the deployed application"
    echo "4. Configure custom domain if needed"
    echo ""
}

# Run main function
main "$@"

