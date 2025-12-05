// Dashboard JavaScript

// Auto-refresh dashboard every 30 seconds
const AUTO_REFRESH_INTERVAL = 30000; // 30 seconds

let refreshTimer = null;

function startAutoRefresh() {
    refreshTimer = setInterval(() => {
        console.log('Auto-refreshing dashboard...');
        location.reload();
    }, AUTO_REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Dashboard loaded');
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Add click handlers for table rows
    const tableRows = document.querySelectorAll('.data-table tbody tr');
    tableRows.forEach(row => {
        row.style.cursor = 'default';
    });
    
    // Format timestamps for better readability
    formatTimestamps();
    
    // Add tooltips
    addTooltips();
});

// Stop auto-refresh when page is hidden (save resources)
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopAutoRefresh();
        console.log('Page hidden, stopping auto-refresh');
    } else {
        startAutoRefresh();
        console.log('Page visible, starting auto-refresh');
    }
});

// Format timestamps to relative time
function formatTimestamps() {
    const timestamps = document.querySelectorAll('[data-timestamp]');
    timestamps.forEach(elem => {
        const timestamp = new Date(elem.dataset.timestamp);
        const relative = getRelativeTime(timestamp);
        elem.title = elem.textContent;
        elem.textContent = relative;
    });
}

// Get relative time string
function getRelativeTime(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000); // seconds
    
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// Add tooltips
function addTooltips() {
    const badges = document.querySelectorAll('.badge');
    badges.forEach(badge => {
        if (!badge.title) {
            badge.title = badge.textContent;
        }
    });
}

// Smooth scroll animation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
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

// Add visual feedback for stat cards
const statCards = document.querySelectorAll('.stat-card');
statCards.forEach(card => {
    card.addEventListener('mouseenter', () => {
        card.style.transform = 'translateY(-8px)';
    });
    
    card.addEventListener('mouseleave', () => {
        card.style.transform = 'translateY(0)';
    });
});

console.log('Dashboard JavaScript initialized');
