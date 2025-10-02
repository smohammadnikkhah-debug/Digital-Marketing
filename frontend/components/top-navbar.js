// Reusable Top Navbar JavaScript Functions

// Load user data to display actual user name
async function loadUserData() {
    try {
        console.log('👤 Loading user data...');
        const storedUserData = localStorage.getItem('userData');
        if (storedUserData) {
            const userData = JSON.parse(storedUserData);
            updateUserName(userData.name || userData.email || 'User');
            return;
        }
        const response = await fetch('/auth/user', {
            credentials: 'include' // Include cookies for JWT session
        });
        console.log('📡 User API response status:', response.status);
        if (response.ok) {
            const userData = await response.json();
            console.log('📡 User API response data:', userData);
            if (userData.authenticated && userData.user) {
                const displayName = userData.user.name || userData.user.email || 'User';
                updateUserName(displayName);
                localStorage.setItem('userData', JSON.stringify(userData.user));
                console.log('✅ User name updated to:', displayName);
            } else {
                console.log('⚠️ User not authenticated, keeping default name');
            }
        } else if (response.status === 401) {
            console.log('⚠️ User not authenticated (401), keeping default name');
            updateUserName('User');
        } else {
            console.log('⚠️ User API request failed with status:', response.status);
            updateUserName('User');
        }
    } catch (error) {
        console.error('❌ Error loading user data:', error);
        updateUserName('User');
    }
}

// Update user name in navbar
function updateUserName(name) {
    const userNameElements = document.querySelectorAll('.user-name');
    userNameElements.forEach(element => {
        element.textContent = name;
    });
    
    // Update user avatar with first letter
    const userAvatars = document.querySelectorAll('.user-avatar');
    userAvatars.forEach(avatar => {
        avatar.textContent = name.charAt(0).toUpperCase();
    });
    
    // Update dropdown header - check both possible selectors
    const dropdownHeader = document.querySelector('.user-dropdown h4') || 
                          document.querySelector('.user-details h4');
    if (dropdownHeader) {
        dropdownHeader.textContent = name;
    }
    
    console.log('✅ User name updated to:', name);
}

// User dropdown functionality with dynamic positioning
function showUserDropdown() {
    const dropdown = document.getElementById('userDropdown');
    const userMenu = document.querySelector('.user-menu');
    
    if (!dropdown || !userMenu) return;
    
    const rect = userMenu.getBoundingClientRect();
    
    dropdown.style.position = 'fixed';
    dropdown.style.top = (rect.bottom + 5) + 'px';
    dropdown.style.right = (window.innerWidth - rect.right) + 'px';
    dropdown.style.zIndex = '2147483647';
    
    dropdown.classList.add('show');
}

function hideUserDropdown() {
    const dropdown = document.getElementById('userDropdown');
    if (dropdown) {
        dropdown.classList.remove('show');
    }
}

// Logout functionality
function logout() {
    if (confirm('Are you sure you want to logout?')) {
        window.location.href = '/auth/logout';
    }
}

// Set current page title in breadcrumb
function setCurrentPageTitle(title) {
    const currentPageElement = document.getElementById('currentPage');
    if (currentPageElement) {
        currentPageElement.textContent = title;
    }
}

// Setup scroll handler for navbar background
function setupScrollHandler() {
    const topHeader = document.querySelector('.top-header');
    if (!topHeader) return;
    
    window.addEventListener('scroll', function() {
        if (window.scrollY > 50) {
            topHeader.classList.add('scrolled');
        } else {
            topHeader.classList.remove('scrolled');
        }
    });
}

// Initialize top navbar
function initializeTopNavbar() {
    console.log('🔧 Initializing top navbar...');
    loadUserData();
    setupScrollHandler();
    
    // Add click outside to close dropdown
    document.addEventListener('click', function(event) {
        const userMenu = document.querySelector('.user-menu');
        const dropdown = document.getElementById('userDropdown');
        
        if (userMenu && dropdown && !userMenu.contains(event.target)) {
            hideUserDropdown();
        }
    });
    
    console.log('✅ Top navbar initialized');
}
