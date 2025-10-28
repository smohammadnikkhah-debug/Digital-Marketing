const express = require('express');
const router = express.Router();

// WordPress connection test endpoint
router.post('/test-connection', async (req, res) => {
    try {
        const { siteUrl, username, password } = req.body;

        if (!siteUrl || !username || !password) {
            return res.status(400).json({
                success: false,
                error: 'All WordPress credentials are required'
            });
        }

        // Test WordPress connection (mock implementation)
        // In real implementation, this would make an API call to WordPress
        console.log('[WordPress] Testing connection to:', siteUrl);

        // Simulate connection test
        const isValidConnection = await testWordPressConnection(siteUrl, username, password);

        if (isValidConnection) {
            res.json({
                success: true,
                message: 'Connection successful'
            });
        } else {
            res.json({
                success: false,
                error: 'Invalid credentials or site URL'
            });
        }

    } catch (error) {
        console.error('[WordPress] Connection test error:', error);
        res.status(500).json({
            success: false,
            error: 'Connection test failed',
            message: error.message
        });
    }
});

// WordPress publish endpoint
router.post('/publish', async (req, res) => {
    try {
        const { 
            siteUrl, 
            username, 
            password, 
            title, 
            content, 
            excerpt, 
            publishStatus 
        } = req.body;

        if (!siteUrl || !username || !password || !title || !content) {
            return res.status(400).json({
                success: false,
                error: 'All required fields must be provided'
            });
        }

        console.log('[WordPress] Publishing blog:', title);

        // Publish to WordPress (mock implementation)
        const publishResult = await publishToWordPress({
            siteUrl,
            username,
            password,
            title,
            content,
            excerpt: excerpt || '',
            status: publishStatus || 'draft'
        });

        if (publishResult.success) {
            res.json({
                success: true,
                message: 'Blog published successfully',
                postUrl: publishResult.postUrl,
                postId: publishResult.postId
            });
        } else {
            res.json({
                success: false,
                error: publishResult.error
            });
        }

    } catch (error) {
        console.error('[WordPress] Publishing error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to publish blog',
            message: error.message
        });
    }
});

// Test WordPress connection (Mock)
async function testWordPressConnection(siteUrl, username, password) {
    // Simulate API call delay
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Mock validation - in real implementation, this would make an actual API call
    const isValidUrl = siteUrl.includes('wordpress') || siteUrl.includes('.com') || siteUrl.includes('.org');
    const isValidUsername = username.length >= 3;
    const isValidPassword = password.length >= 8;
    
    return isValidUrl && isValidUsername && isValidPassword;
}

// Publish to WordPress (Mock)
async function publishToWordPress(params) {
    const { siteUrl, username, password, title, content, excerpt, status } = params;
    
    // Simulate API call delay
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Mock successful publishing
    const postId = Math.floor(Math.random() * 10000) + 1000;
    const postUrl = `${siteUrl}/post/${postId}`;
    
    return {
        success: true,
        postId: postId,
        postUrl: postUrl,
        message: 'Blog published successfully'
    };
}

module.exports = router;




