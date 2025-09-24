const express = require('express');
const router = express.Router();
const axios = require('axios');
const Auth0Service = require('../services/auth0Service');

const auth0Service = new Auth0Service();

// Update user profile
router.put('/profile', async (req, res) => {
    try {
        const { name, email, company } = req.body;
        
        if (!name || !email) {
            return res.status(400).json({
                success: false,
                message: 'Name and email are required'
            });
        }

        // Check if user is authenticated
        if (!req.isAuthenticated()) {
            return res.status(401).json({
                success: false,
                message: 'User not authenticated'
            });
        }

        const user = req.user;

        // Get current user data to check for changes
        const { data: currentUser, error: fetchError } = await auth0Service.supabase
            .from('users')
            .select('email, auth0_id')
            .eq('id', user.id)
            .single();

        if (fetchError || !currentUser) {
            console.error('Error fetching current user for profile update:', fetchError);
            return res.status(500).json({
                success: false,
                message: 'Failed to fetch user data'
            });
        }

        // Update user in Supabase
        const { data: updatedUser, error: updateError } = await auth0Service.supabase
            .from('users')
            .update({
                name: name,
                email: email,
                company: company || null,
                updated_at: new Date().toISOString()
            })
            .eq('id', user.id)
            .select()
            .single();

        if (updateError) {
            console.error('Error updating user profile:', updateError);
            return res.status(500).json({
                success: false,
                message: 'Failed to update profile'
            });
        }

        // Update user in Auth0 if email or name changed
        if ((email !== currentUser.email || name !== user.name) && currentUser.auth0_id) {
            try {
                const managementToken = await getAuth0ManagementToken();
                await updateAuth0User(managementToken, currentUser.auth0_id, {
                    email: email,
                    name: name
                });
            } catch (auth0Error) {
                console.error('Error updating Auth0 user:', auth0Error);
                // Continue even if Auth0 update fails
            }
        }

        res.json({
            success: true,
            message: 'Profile updated successfully',
            user: updatedUser
        });

    } catch (error) {
        console.error('Profile update error:', error);
        res.status(500).json({
            success: false,
            message: 'Internal server error'
        });
    }
});

// Update user password
router.put('/password', async (req, res) => {
    try {
        const { currentPassword, newPassword } = req.body;
        
        if (!currentPassword || !newPassword) {
            return res.status(400).json({
                success: false,
                message: 'Current password and new password are required'
            });
        }

        if (newPassword.length < 8) {
            return res.status(400).json({
                success: false,
                message: 'New password must be at least 8 characters long'
            });
        }

        // Check if user is authenticated
        if (!req.isAuthenticated()) {
            return res.status(401).json({
                success: false,
                message: 'User not authenticated'
            });
        }

        const user = req.user;

        // Get user's Auth0 ID from database
        const { data: userData, error: fetchError } = await auth0Service.supabase
            .from('users')
            .select('auth0_id')
            .eq('id', user.id)
            .single();

        if (fetchError || !userData || !userData.auth0_id) {
            console.error('Error fetching user Auth0 ID for password update:', fetchError);
            return res.status(500).json({
                success: false,
                message: 'Failed to retrieve user information'
            });
        }

        // Update password in Auth0
        try {
            const managementToken = await getAuth0ManagementToken();
            await updateAuth0UserPassword(managementToken, userData.auth0_id, newPassword);
            
            res.json({
                success: true,
                message: 'Password updated successfully'
            });
        } catch (auth0Error) {
            console.error('Error updating Auth0 password:', auth0Error);
            
            // Check if it's an authorization error
            if (auth0Error.response && auth0Error.response.data && 
                auth0Error.response.data.error === 'access_denied') {
                return res.status(403).json({
                    success: false,
                    message: 'Client is not authorized to access Auth0 Management API. Please contact support to configure Auth0 client grants.'
                });
            }
            
            res.status(500).json({
                success: false,
                message: 'Failed to update password'
            });
        }

    } catch (error) {
        console.error('Password update error:', error);
        res.status(500).json({
            success: false,
            message: 'Internal server error'
        });
    }
});

// Get Auth0 Management API access token
async function getAuth0ManagementToken() {
    try {
        const response = await axios.post(`https://${process.env.AUTH0_DOMAIN}/oauth/token`, {
            client_id: process.env.AUTH0_CLIENT_ID,
            client_secret: process.env.AUTH0_CLIENT_SECRET,
            audience: `https://${process.env.AUTH0_DOMAIN}/api/v2/`,
            grant_type: 'client_credentials'
        });
        
        return response.data.access_token;
    } catch (error) {
        console.error('Error getting Auth0 management token:', error);
        throw new Error('Failed to authenticate with Auth0 Management API');
    }
}

// Update user in Auth0 using Management API
async function updateAuth0User(accessToken, userId, userData) {
    try {
        const response = await axios.patch(
            `https://${process.env.AUTH0_DOMAIN}/api/v2/users/${userId}`,
            userData,
            {
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Content-Type': 'application/json'
                }
            }
        );
        
        return response.data;
    } catch (error) {
        console.error('Error updating Auth0 user:', error);
        throw error;
    }
}

// Update user password in Auth0 using Management API
async function updateAuth0UserPassword(accessToken, userId, newPassword) {
    try {
        const response = await axios.patch(
            `https://${process.env.AUTH0_DOMAIN}/api/v2/users/${userId}`,
            {
                password: newPassword,
                connection: 'Username-Password-Authentication'
            },
            {
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Content-Type': 'application/json'
                }
            }
        );
        
        return response.data;
    } catch (error) {
        console.error('Error updating Auth0 password:', error);
        throw error;
    }
}

module.exports = router;
