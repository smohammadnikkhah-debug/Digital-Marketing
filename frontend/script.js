/**
 * MOZAREX — PRODUCTION INTERACTION & ANALYTICS SCRIPT
 * Web, App & AI Development Studio
 */

document.addEventListener('DOMContentLoaded', function() {
  initHeaderScroll();
  initMobileNav();
  initConsultationModal();
  initSmoothScroll();
  initAnalyticsTracking();
});

/**
 * Header background adjustment on scroll
 */
function initHeaderScroll() {
  const header = document.querySelector('.site-header');
  if (!header) return;

  const handleScroll = () => {
    if (window.scrollY > 20) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();
}

/**
 * Mobile Navigation Drawer Toggle
 */
function initMobileNav() {
  const toggleBtn = document.querySelector('.mobile-nav-toggle');
  const mainNav = document.querySelector('.main-nav');
  if (!toggleBtn || !mainNav) return;

  toggleBtn.addEventListener('click', () => {
    const isExpanded = mainNav.classList.toggle('active');
    toggleBtn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    const icon = toggleBtn.querySelector('i') || toggleBtn;
    if (isExpanded) {
      toggleBtn.innerHTML = '✕';
    } else {
      toggleBtn.innerHTML = '☰';
    }
  });

  // Close nav on click outside or item click
  document.addEventListener('click', (e) => {
    if (mainNav.classList.contains('active') && !mainNav.contains(e.target) && !toggleBtn.contains(e.target)) {
      mainNav.classList.remove('active');
      toggleBtn.setAttribute('aria-expanded', 'false');
      toggleBtn.innerHTML = '☰';
    }
  });

  mainNav.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      mainNav.classList.remove('active');
      toggleBtn.setAttribute('aria-expanded', 'false');
      toggleBtn.innerHTML = '☰';
    });
  });
}

/**
 * Consultation Modal Handling
 */
function initConsultationModal() {
  const modal = document.getElementById('consultationModal');
  const openButtons = document.querySelectorAll('[data-open-consultation]');
  const closeButtons = document.querySelectorAll('[data-close-consultation]');
  const form = document.getElementById('consultationForm');
  const feedback = document.getElementById('formFeedback');

  if (!modal) return;

  const openModal = (source = 'direct') => {
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';

    // Push analytics event
    trackEvent('consultation_modal_open', { source: source });

    const firstInput = modal.querySelector('input, select, textarea');
    if (firstInput) firstInput.focus();
  };

  const closeModal = () => {
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  };

  openButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const source = btn.getAttribute('data-source') || 'cta_button';
      openModal(source);
    });
  });

  closeButtons.forEach(btn => {
    btn.addEventListener('click', closeModal);
  });

  // Close on backdrop click
  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeModal();
    }
  });

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.classList.contains('active')) {
      closeModal();
    }
  });

  // Form submission
  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();

      const name = document.getElementById('consultName').value.trim();
      const email = document.getElementById('consultEmail').value.trim();
      const phone = document.getElementById('consultPhone') ? document.getElementById('consultPhone').value.trim() : '';
      const service = document.getElementById('consultService').value;
      const budget = document.getElementById('consultBudget') ? document.getElementById('consultBudget').value : '';
      const message = document.getElementById('consultMessage').value.trim();

      // Dispatch GTM Analytics Event
      trackEvent('consultation_form_submit', {
        name_provided: !!name,
        service_type: service,
        budget_range: budget
      });

      // Show user feedback
      if (feedback) {
        feedback.className = 'form-feedback success';
        feedback.textContent = 'Thank you! Preparing your consultation request...';
        feedback.style.display = 'block';
      }

      // Compose mailto fallback
      const subject = encodeURIComponent(`Mozarex Consultation Request - ${service} (${name})`);
      const body = encodeURIComponent(
        `Hello Mozarex Team,\n\n` +
        `I would like to request a free consultation regarding a project:\n\n` +
        `Client Name: ${name}\n` +
        `Email: ${email}\n` +
        `Phone: ${phone || 'Not provided'}\n` +
        `Service Interest: ${service}\n` +
        `Estimated Budget: ${budget || 'To be discussed'}\n\n` +
        `Project Summary:\n${message}\n\n` +
        `Please reach out to discuss next steps.\n\n` +
        `Best regards,\n${name}`
      );

      setTimeout(() => {
        window.location.href = `mailto:info@mozarex.com?subject=${subject}&body=${body}`;
        if (feedback) {
          feedback.textContent = 'Redirecting to your email client to send to info@mozarex.com. We look forward to talking soon!';
        }
      }, 1000);
    });
  }
}

/**
 * Smooth scrolling for in-page anchors
 */
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const href = this.getAttribute('href');
      if (href === '#' || href === '#!') return;
      
      const targetElement = document.querySelector(href);
      if (targetElement) {
        e.preventDefault();
        const headerHeight = 80;
        const targetPos = targetElement.getBoundingClientRect().top + window.pageYOffset - headerHeight;
        
        window.scrollTo({
          top: targetPos,
          behavior: 'smooth'
        });
      }
    });
  });
}

/**
 * Analytics Tracking Helper (DataLayer & GTM Safe)
 */
function trackEvent(eventName, eventParams = {}) {
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({
    event: eventName,
    ...eventParams,
    timestamp: new Date().toISOString()
  });
}

function initAnalyticsTracking() {
  // Track $1,490 Offer Clicks
  document.querySelectorAll('[data-track="offer_1490"]').forEach(el => {
    el.addEventListener('click', () => {
      trackEvent('offer_1490_click', { section: 'website_development_offer' });
    });
  });

  // Track Service Clicks
  document.querySelectorAll('[data-track="service_card"]').forEach(el => {
    el.addEventListener('click', () => {
      const serviceName = el.getAttribute('data-service-name') || 'unknown';
      trackEvent('service_card_click', { service: serviceName });
    });
  });

  // Track App Clicks
  document.querySelectorAll('[data-track="app_product"]').forEach(el => {
    el.addEventListener('click', () => {
      const appName = el.getAttribute('data-app-name') || 'unknown';
      trackEvent('app_product_click', { app: appName });
    });
  });
}

// Global helper for opening modal anywhere
window.openConsultationModal = function(source = 'global') {
  const modal = document.getElementById('consultationModal');
  if (modal) {
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    trackEvent('consultation_modal_open', { source });
  }
};