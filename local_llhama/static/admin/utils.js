/**
 * Utility Functions
 * Common helper functions used across admin panel
 */

/**
 * Format date string to readable format
 */
export function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

/**
 * Escape HTML to prevent XSS
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show error message
 */
export function showError(message) {
    alert('Error: ' + message);
}

/**
 * Show success message
 */
export function showSuccess(message) {
    alert('Success: ' + message);
}

/**
 * Close modal by ID
 */
export function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

/**
 * Close modal when clicking outside
 */
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}
