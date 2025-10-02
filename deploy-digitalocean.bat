@echo off
REM DigitalOcean Deployment Script for Windows
REM This script helps deploy the Digital Marketing SEO Analyzer to DigitalOcean App Platform

echo 🚀 DigitalOcean Deployment Script
echo ==================================

REM Check if doctl is installed
where doctl >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] doctl CLI is not installed. Please install it first:
    echo   Download from: https://docs.digitalocean.com/reference/doctl/how-to/install/
    echo   Or use: winget install DigitalOcean.doctl
    pause
    exit /b 1
)
echo [SUCCESS] doctl CLI is installed

REM Check if user is authenticated
doctl auth list >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Not authenticated with DigitalOcean. Please run:
    echo   doctl auth init
    pause
    exit /b 1
)
echo [SUCCESS] Authenticated with DigitalOcean

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found. Please create it from production.env.example
    echo   copy production.env.example .env
    echo   # Then edit .env with your actual values
    pause
    exit /b 1
)
echo [SUCCESS] .env file found

echo.
echo [INFO] All checks passed. Proceeding with deployment...
echo.

REM Deploy to DigitalOcean App Platform
echo [INFO] Deploying to DigitalOcean App Platform...

REM Check if app exists and deploy/update
doctl apps list | findstr "digital-marketing-seo-analyzer" >nul
if %errorlevel% equ 0 (
    echo [INFO] App exists, updating...
    for /f "tokens=1" %%i in ('doctl apps list --format ID,Name --no-header ^| findstr "digital-marketing-seo-analyzer"') do set APP_ID=%%i
    doctl apps update %APP_ID% --spec .do/app.yaml
) else (
    echo [INFO] Creating new app...
    doctl apps create --spec .do/app.yaml
)

echo [SUCCESS] Deployment initiated

echo.
echo [INFO] Checking deployment status...

REM Get app ID and show status
for /f "tokens=1" %%i in ('doctl apps list --format ID,Name --no-header ^| findstr "digital-marketing-seo-analyzer"') do set APP_ID=%%i

if defined APP_ID (
    echo.
    echo [SUCCESS] App ID: %APP_ID%
    echo.
    doctl apps get %APP_ID%
    echo.
    echo [INFO] To view logs:
    echo   doctl apps logs %APP_ID% --follow
    echo.
    echo [INFO] To view the app:
    echo   doctl apps get %APP_ID% --format DefaultIngress
)

echo.
echo [SUCCESS] Deployment process completed!
echo.
echo [INFO] Next steps:
echo 1. Monitor the deployment in the DigitalOcean dashboard
echo 2. Check the app logs for any issues
echo 3. Test the deployed application
echo 4. Configure custom domain if needed
echo.

pause

