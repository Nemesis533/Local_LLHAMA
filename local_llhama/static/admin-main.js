/**
 * Admin Panel Main Entry Point
 * Coordinates all admin panel modules
 */

// Import all modules
import * as utils from './admin/utils.js';
import * as userManagement from './admin/user-management.js';
import * as languageManagement from './admin/language-management.js';
import * as promptManagement from './admin/prompt-management.js';
import * as webSearchManagement from './admin/websearch-management.js';
import * as presetManagement from './admin/preset-management.js';
import * as modelManagement from './admin/model-management.js';
import * as systemSettingsManagement from './admin/system-settings-management.js';

// Expose modules to global window object for onclick handlers in HTML
window.userManagement = userManagement;
window.languageManagement = languageManagement;
window.promptManagement = promptManagement;
window.webSearchManagement = webSearchManagement;
window.presetManagement = presetManagement;
window.modelManagement = modelManagement;
window.systemSettingsManagement = systemSettingsManagement;

// Also expose individual functions at top level for legacy compatibility
window.closeModal = utils.closeModal;
window.showCreateUserModal = userManagement.showCreateUserModal;
window.editPermissions = userManagement.editPermissions;
window.resetPassword = userManagement.resetPassword;
window.deleteUser = userManagement.deleteUser;
window.addLanguageMapping = languageManagement.addLanguageMapping;
window.saveLanguageModels = languageManagement.saveLanguageModels;
window.displayPrompts = promptManagement.displayPrompts;
window.savePrompts = promptManagement.savePrompts;
window.addWebsite = webSearchManagement.addWebsite;
window.saveWebSearchConfig = webSearchManagement.saveWebSearchConfig;
window.togglePasswordVisibility = webSearchManagement.togglePasswordVisibility;
window.updateApiKey = webSearchManagement.updateApiKey;
window.toggleApiKeyVisibility = webSearchManagement.toggleApiKeyVisibility;
window.restartSystem = presetManagement.restartSystem;
window.applyPreset = presetManagement.applyPreset;
window.saveModelConfig = modelManagement.saveModelConfig;
window.saveSystemSettings = systemSettingsManagement.saveSystemSettings;

/**
 * Tab Management
 */
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
        tab.style.display = 'none';
    });
    
    // Remove active class from all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    const selectedTab = document.getElementById(tabName + '-tab');
    if (selectedTab) {
        selectedTab.classList.add('active');
        selectedTab.style.display = 'block';
    }
    
    // Activate the clicked button
    const buttons = document.querySelectorAll('.tab-button');
    buttons.forEach(btn => {
        const btnText = btn.textContent.toLowerCase();
        if ((tabName === 'users' && btnText.includes('user')) ||
            (tabName === 'languages' && btnText.includes('language')) ||
            (tabName === 'prompts' && btnText.includes('prompt')) ||
            (tabName === 'websearch' && btnText.includes('web')) ||
            (tabName === 'presets' && btnText.includes('preset')) ||
            (tabName === 'model' && btnText.includes('model')) ||
            (tabName === 'system-settings' && btnText.includes('system'))) {
            btn.classList.add('active');
        }
    });
    
    // Refresh data when switching tabs
    if (tabName === 'languages') {
        languageManagement.displayLanguageMappings();
    }
    
    if (tabName === 'prompts') {
        promptManagement.displayPrompts();
    }
    
    if (tabName === 'websearch') {
        webSearchManagement.displayWebSearchConfig();
    }
    
    if (tabName === 'presets') {
        presetManagement.loadPresets();
    }
    
    if (tabName === 'model') {
        modelManagement.displayModelConfig();
    }
    
    if (tabName === 'system-settings') {
        systemSettingsManagement.displaySystemSettings();
    }
}

// Expose switchTab globally
window.switchTab = switchTab;

// Logout handler
window.handleLogout = async function() {
    try {
        const response = await fetch('/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            window.location.href = '/login';
        } else {
            alert('Logout failed. Please try again.');
        }
    } catch (error) {
        console.error('Logout error:', error);
        alert('Logout failed. Please try again.');
    }
};

/**
 * Initialize on page load
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize user management
    userManagement.initUserManagement();
    
    // Load initial data
    userManagement.loadUsers();
    languageManagement.loadLanguageSettings();
    promptManagement.loadPromptsData();
    webSearchManagement.loadWebSearchConfig();
    modelManagement.loadModelConfig();
    systemSettingsManagement.loadSystemSettings();
    
    // Check if coming from restart action
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('restarting') === 'true') {
        // Switch to model tab
        const targetTab = urlParams.get('tab') || 'model';
        setTimeout(() => {
            switchTab(targetTab);
            // Wait a moment for tab to render, then scroll to log box
            setTimeout(() => {
                const logBox = document.getElementById('model-log-box');
                if (logBox) {
                    logBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Add restart notification to log
                    const restartMsg = document.createElement('div');
                    restartMsg.style.cssText = 'color: #2196F3; font-weight: bold; margin: 5px 0; padding: 8px; background: #E3F2FD; border-radius: 4px;';
                    restartMsg.textContent = '🔄 System restart initiated... Monitoring progress below.';
                    logBox.insertBefore(restartMsg, logBox.firstChild);
                }
            }, 300);
        }, 500);
        // Clean up URL
        window.history.replaceState({}, document.title, '/admin');
    }
});
