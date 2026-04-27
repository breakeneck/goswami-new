/**
 * Goswami.ru - Main JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Search input clear button functionality
    const searchInput = document.getElementById('searchInput');
    const searchClear = document.getElementById('searchClear');
    
    if (searchInput && searchClear) {
        // Show/hide clear button based on input value
        const toggleClearButton = () => {
            if (searchInput.value.length > 0) {
                searchClear.style.display = 'block';
            } else {
                searchClear.style.display = 'none';
            }
        };
        
        // Initial check
        toggleClearButton();
        
        // Listen for input changes
        searchInput.addEventListener('input', toggleClearButton);
        searchInput.addEventListener('focus', toggleClearButton);
        
        // Clear button click handler
        searchClear.addEventListener('click', function() {
            searchInput.value = '';
            searchInput.focus();
            toggleClearButton();
            
            // If on search results page, redirect to home
            if (window.location.pathname === '/search/') {
                window.location.href = '/';
            }
        });
        
        // Handle escape key
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                searchInput.blur();
            }
        });
    }
    
    // Advanced Search Toggle
    const advancedSearchToggle = document.getElementById('advancedSearchToggle');
    const advancedSearch = document.getElementById('advancedSearch');
    
    if (advancedSearchToggle && advancedSearch) {
        // Check if any filters are active
        const urlParams = new URLSearchParams(window.location.search);
        const hasFilters = urlParams.has('location') || urlParams.has('category') || 
                          urlParams.has('scripture') || urlParams.has('date_from') || 
                          urlParams.has('date_to');
        
        // Expand if filters are active
        if (hasFilters) {
            advancedSearch.classList.add('expanded');
        }
        
        advancedSearchToggle.addEventListener('click', function() {
            advancedSearch.classList.toggle('expanded');
        });
    }
    
    // Reset Filters Button
    const resetFiltersBtn = document.getElementById('resetFilters');
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', function() {
            const selects = document.querySelectorAll('.filter-select');
            const inputs = document.querySelectorAll('.filter-input');
            
            selects.forEach(select => select.value = '');
            inputs.forEach(input => input.value = '');
            
            // Submit the form
            document.getElementById('searchForm').submit();
        });
    }
    
    // Mobile burger menu toggle
    const burgerBtn = document.getElementById('burgerBtn');
    const layoutWrapper = document.querySelector('.layout-wrapper');
    
    if (burgerBtn && layoutWrapper) {
        burgerBtn.addEventListener('click', function() {
            layoutWrapper.classList.toggle('side-open');
        });
    }
    
    // Lecture card hover effects enhancement
    const lectureCards = document.querySelectorAll('.lecture-card');
    
    lectureCards.forEach(card => {
        const poster = card.querySelector('.lecture-poster');
        
        if (poster) {
            // Add click handler to navigate to lecture
            poster.addEventListener('click', function() {
                const link = card.querySelector('.lecture-title a');
                if (link) {
                    window.location.href = link.href;
                }
            });
            
            // Make poster clickable
            poster.style.cursor = 'pointer';
        }
    });
    
    // Icon button hover effects
    const iconButtons = document.querySelectorAll('.icon-btn');
    
    iconButtons.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            const svg = this.querySelector('svg');
            if (svg) {
                const paths = svg.querySelectorAll('path, circle');
                paths.forEach(path => {
                    if (path.getAttribute('stroke') === '#2b2b2b') {
                        path.setAttribute('stroke', '#ffa000');
                    }
                });
            }
        });
        
        btn.addEventListener('mouseleave', function() {
            const svg = this.querySelector('svg');
            if (svg) {
                const paths = svg.querySelectorAll('path, circle');
                paths.forEach(path => {
                    if (path.getAttribute('stroke') === '#ffa000') {
                        path.setAttribute('stroke', '#2b2b2b');
                    }
                });
            }
        });
    });
    
    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
    
    // Add loading state for pagination links
    const paginationLinks = document.querySelectorAll('.page-link');
    
    paginationLinks.forEach(link => {
        link.addEventListener('click', function() {
            document.body.classList.add('loading');
        });
    });
    
    // Lazy loading for images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        observer.unobserve(img);
                    }
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }
    
    // Search form submit animation
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', function() {
            document.body.classList.add('loading');
        });
    }
    
    // Keyboard navigation for lecture cards
    lectureCards.forEach((card, index) => {
        card.setAttribute('tabindex', '0');
        
        card.addEventListener('keydown', function(e) {
            const cards = Array.from(lectureCards);
            let nextCard = null;
            
            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    nextCard = cards[index + 1];
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    nextCard = cards[index - 1];
                    break;
                case 'Enter':
                    e.preventDefault();
                    const link = card.querySelector('.lecture-title a');
                    if (link) {
                        window.location.href = link.href;
                    }
                    break;
            }
            
            if (nextCard) {
                nextCard.focus();
                nextCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    });
    
    // Auto-submit on filter change (optional)
    const filterSelects = document.querySelectorAll('.filter-select');
    let autoSubmitTimeout;
    
    filterSelects.forEach(select => {
        select.addEventListener('change', function() {
            // Clear previous timeout
            clearTimeout(autoSubmitTimeout);
            
            // Set new timeout to auto-submit after 500ms
            autoSubmitTimeout = setTimeout(() => {
                if (searchForm) {
                    searchForm.submit();
                }
            }, 500);
        });
    });
    
    // Utility function to format duration
    function formatDuration(seconds) {
        if (!seconds) return '';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
    
    // Utility function to debounce function calls
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Export for use in other scripts
    window.GoswamiUtils = {
        formatDuration,
        debounce
    };
    
    // ============================================
    // Transcript Toggles
    // ============================================
    
    const transcribeToggles = document.querySelectorAll('.transcribe-toggle');
    
    transcribeToggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            const targetId = this.dataset.target;
            const targetElement = document.getElementById(targetId);
            
            if (!targetElement) return;
            
            // Update toggle button states
            transcribeToggles.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Show/hide corresponding content
            document.querySelectorAll('.transcribe-draft, .transcribe-final').forEach(el => {
                el.style.display = 'none';
            });
            targetElement.style.display = 'block';
        });
    });
});
