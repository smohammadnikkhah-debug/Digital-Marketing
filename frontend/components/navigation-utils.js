// Navigation Utilities
// Handles environment-based feature visibility

function hideSocialConnectionsInProduction() {
    // Check if we're in production environment
    const isProduction = window.location.hostname !== 'localhost' && 
                        window.location.hostname !== '127.0.0.1' && 
                        !window.location.hostname.includes('dev') &&
                        !window.location.hostname.includes('test');
    
    if (isProduction) {
        // Hide the social connections link specifically
        const socialConnectionsLink = document.querySelector('a[href="/seo-tools-social-connections"]');
        if (socialConnectionsLink) {
            socialConnectionsLink.style.display = 'none';
        }
        
        // Hide the entire Connections section if it only contains social connections
        const connectionsSection = document.querySelector('.nav-section');
        if (connectionsSection) {
            const connectionsTitle = connectionsSection.querySelector('.nav-section-title');
            if (connectionsTitle && connectionsTitle.textContent.trim() === 'Connections') {
                const navItems = connectionsSection.querySelectorAll('.nav-item');
                let visibleItems = 0;
                
                navItems.forEach(item => {
                    if (item.style.display !== 'none') {
                        visibleItems++;
                    }
                });
                
                // If no visible items in Connections section, hide the entire section
                if (visibleItems === 0) {
                    connectionsSection.style.display = 'none';
                }
            }
        }
    }
}

function initializeNavigation() {
    // Hide social connections in production
    hideSocialConnectionsInProduction();
    
    // Add any other navigation-related initialization here
}

// Auto-initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeNavigation);
