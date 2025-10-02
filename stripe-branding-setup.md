# Stripe Checkout Branding Setup

To match your website's color scheme in Stripe Checkout, you need to configure the branding in your Stripe Dashboard.

## Website Color Scheme
Based on your trial-signup page, your brand colors are:
- **Primary Gradient**: `#667eea` to `#764ba2` (Purple-Blue)
- **Success Color**: `#10b981` (Green)
- **Background**: `#0f172a` to `#1e293b` (Dark Blue-Gray)
- **Text**: `#f1f5f9` (Light Gray)

## Stripe Dashboard Configuration

### 1. Access Stripe Dashboard
1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. Navigate to **Settings** → **Branding**

### 2. Configure Brand Colors
Set the following colors in your Stripe Dashboard:

**Primary Color**: `#667eea`
- This will be used for buttons and primary elements

**Accent Color**: `#10b981` 
- This will be used for success states and highlights

### 3. Upload Logo (Optional)
- Upload your company logo
- Recommended size: 128x128px
- Format: PNG with transparent background

### 4. Customize Checkout Appearance
In **Settings** → **Checkout**:
- Enable "Show billing address"
- Enable "Show shipping address" (if needed)
- Set default country to your primary market

### 5. Test the Changes
After making changes:
1. Create a test checkout session
2. Verify the colors match your website
3. Test on both desktop and mobile

## Alternative: Custom Checkout Page
If you want full control over styling, you can:
1. Use Stripe Elements to build a custom checkout form
2. Style it to match your website exactly
3. Handle the payment flow on your own domain

## Current Implementation
The current code includes:
- Custom submit message for trial signup
- Metadata tracking for trial sessions
- 7-day trial period configuration

The visual branding will be applied through the Stripe Dashboard settings above.
