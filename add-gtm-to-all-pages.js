const fs = require('fs');
const path = require('path');
const glob = require('glob');

// GTM snippets
const GTM_HEAD = `<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
})(window,document,'script','dataLayer','GTM-K59VFCP8');</script>
<!-- End Google Tag Manager -->`;

const GTM_BODY = `<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-K59VFCP8"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->`;

// Check if GTM is already present in content
function hasGTM(content) {
    return content.includes('GTM-K59VFCP8') || content.includes('googletagmanager.com');
}

// Add GTM to HTML file
function addGTMToFile(filePath) {
    try {
        let content = fs.readFileSync(filePath, 'utf8');
        
        // Skip if GTM already exists
        if (hasGTM(content)) {
            console.log(`⏭️  Skipped (GTM already exists): ${filePath}`);
            return false;
        }
        
        let modified = false;
        
        // Add GTM to <head> (right after <head> tag)
        if (content.includes('<head>') && !content.includes('<!-- Google Tag Manager -->')) {
            content = content.replace(/<head>/i, `<head>\n    ${GTM_HEAD}`);
            modified = true;
        }
        
        // Add GTM to <body> (right after <body> tag)
        if (content.includes('<body') && !content.includes('<!-- Google Tag Manager (noscript) -->')) {
            // Handle both <body> and <body class="...">
            content = content.replace(/<body([^>]*)>/i, `<body$1>\n    ${GTM_BODY}`);
            modified = true;
        }
        
        if (modified) {
            fs.writeFileSync(filePath, content, 'utf8');
            console.log(`✅ Added GTM to: ${filePath}`);
            return true;
        } else {
            console.log(`⚠️  No changes needed: ${filePath}`);
            return false;
        }
        
    } catch (error) {
        console.error(`❌ Error processing ${filePath}:`, error.message);
        return false;
    }
}

// Main function
function addGTMToAllPages() {
    console.log('🚀 Adding Google Tag Manager to all HTML pages...\n');
    
    // Get all HTML files in frontend directory
    const htmlFiles = glob.sync('frontend/**/*.html');
    
    let successCount = 0;
    let skippedCount = 0;
    let errorCount = 0;
    
    htmlFiles.forEach(file => {
        const result = addGTMToFile(file);
        if (result === true) {
            successCount++;
        } else if (result === false && hasGTM(fs.readFileSync(file, 'utf8'))) {
            skippedCount++;
        } else {
            errorCount++;
        }
    });
    
    console.log('\n📊 Summary:');
    console.log(`   ✅ GTM added: ${successCount} files`);
    console.log(`   ⏭️  Already had GTM: ${skippedCount} files`);
    console.log(`   ⚠️  No changes: ${errorCount} files`);
    console.log(`   📁 Total files processed: ${htmlFiles.length}`);
    console.log('\n✨ Done!');
}

// Run the script
addGTMToAllPages();

