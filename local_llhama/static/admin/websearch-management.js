/**
 * Web Search Configuration Module
 * Manages web search settings, API tokens, and allowed websites
 */

import { escapeHtml } from './utils.js';

let webSearchConfig = null;

/**
 * Load web search configuration from server
 */
export async function loadWebSearchConfig() {
    try {
        const response = await fetch('/settings/web-search');
        const data = await response.json();
        
        if (data.status === 'ok') {
            webSearchConfig = data.config;
        } else {
            console.error('Failed to load web search config:', data.message);
        }
    } catch (error) {
        console.error('Error loading web search config:', error);
    }
}

/**
 * Display web search configuration
 */
export function displayWebSearchConfig() {
    if (!webSearchConfig) {
        console.error('No web search config data loaded');
        return;
    }
    
    // Set general settings
    document.getElementById('max-results').value = webSearchConfig.max_results || 3;
    document.getElementById('search-timeout').value = webSearchConfig.timeout || 10;
    
    // Display allowed websites
    displayWebsites();
}

/**
 * Display allowed websites list
 */
export function displayWebsites() {
    const container = document.getElementById('websites-container');
    const websites = webSearchConfig.allowed_websites || [];
    
    if (websites.length === 0) {
        container.innerHTML = '<p style="color: #999; font-style: italic;">No websites configured yet.</p>';
        return;
    }
    
    container.innerHTML = websites.map((site, index) => `
        <div class="website-item" style="background: #f8f9fa; padding: 15px; border-radius: 2px; margin-bottom: 10px; border-left: 4px solid #3498db;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <div style="flex: 1;">
                    <div style="margin-bottom: 8px;">
                        <strong style="color: #2c3e50; font-size: 15px;">${escapeHtml(site.name)}</strong>
                    </div>
                    <div style="margin-bottom: 6px;">
                        <span style="color: #666; font-size: 13px;">URL:</span>
                        <code style="background: white; padding: 2px 6px; border-radius: 1px; font-size: 12px;">${escapeHtml(site.url)}</code>
                    </div>
                    <div style="color: #666; font-size: 13px;">
                        ${escapeHtml(site.description || 'No description')}
                    </div>
                </div>
                <div style="display: flex; gap: 5px; margin-left: 15px;">
                    <button class="btn-small" onclick="window.webSearchManagement.editWebsite(${index})" title="Edit Website">✏️</button>
                    <button class="btn-small" style="background: #e74c3c; color: white;" onclick="window.webSearchManagement.deleteWebsite(${index})" title="Delete Website">🗑️</button>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <label style="color: #666; font-size: 13px; white-space: nowrap;">API Key:</label>
                <input type="password" 
                       id="api-key-${index}" 
                       value="${escapeHtml(site.api_key || '')}" 
                       placeholder="Optional API key for this service" 
                       style="flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 2px; font-size: 13px;"
                       onchange="window.webSearchManagement.updateApiKey(${index}, this.value)">
                <button type="button" 
                        class="btn-small" 
                        onclick="window.webSearchManagement.toggleApiKeyVisibility(${index})" 
                        style="padding: 6px 10px; font-size: 12px;">👁 Show</button>
            </div>
        </div>
    `).join('');
}

/**
 * Add new website
 */
export function addWebsite() {
    const name = prompt('Enter website name (e.g., "Wikipedia"):');
    if (!name) return;
    
    const url = prompt('Enter website URL (e.g., "https://en.wikipedia.org"):');
    if (!url) return;
    
    const description = prompt('Enter description (optional):') || '';
    
    const apiKey = prompt('Enter API key (optional, leave blank if not required):') || '';
    
    if (!webSearchConfig.allowed_websites) {
        webSearchConfig.allowed_websites = [];
    }
    
    const newSite = {
        name: name.trim(),
        url: url.trim(),
        description: description.trim()
    };
    
    if (apiKey.trim()) {
        newSite.api_key = apiKey.trim();
    }
    
    webSearchConfig.allowed_websites.push(newSite);
    
    displayWebsites();
}

/**
 * Edit existing website
 */
export function editWebsite(index) {
    const site = webSearchConfig.allowed_websites[index];
    
    const name = prompt('Enter website name:', site.name);
    if (name === null) return; // User cancelled
    
    const url = prompt('Enter website URL:', site.url);
    if (url === null) return;
    
    const description = prompt('Enter description:', site.description || '');
    if (description === null) return;
    
    const apiKey = prompt('Enter API key (leave blank to remove):', site.api_key || '');
    if (apiKey === null) return;
    
    const updatedSite = {
        name: name.trim(),
        url: url.trim(),
        description: description.trim()
    };
    
    if (apiKey.trim()) {
        updatedSite.api_key = apiKey.trim();
    }
    
    webSearchConfig.allowed_websites[index] = updatedSite;
    
    displayWebsites();
}

/**
 * Delete website
 */
export function deleteWebsite(index) {
    const site = webSearchConfig.allowed_websites[index];
    
    if (confirm(`Delete website "${site.name}"?`)) {
        webSearchConfig.allowed_websites.splice(index, 1);
        displayWebsites();
    }
}

/**
 * Update API key for a website
 */
export function updateApiKey(index, apiKey) {
    if (!webSearchConfig.allowed_websites[index]) return;
    
    if (apiKey && apiKey.trim()) {
        webSearchConfig.allowed_websites[index].api_key = apiKey.trim();
    } else {
        delete webSearchConfig.allowed_websites[index].api_key;
    }
}

/**
 * Toggle API key visibility for a specific website
 */
export function toggleApiKeyVisibility(index) {
    const input = document.getElementById(`api-key-${index}`);
    const button = event.target;
    
    if (input.type === 'password') {
        input.type = 'text';
        button.textContent = '🙈 Hide';
    } else {
        input.type = 'password';
        button.textContent = '👁 Show';
    }
}

/**
 * Toggle password visibility (legacy function - kept for compatibility)
 */
export function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    const button = event.target;
    
    if (input.type === 'password') {
        input.type = 'text';
        button.textContent = '🙈 Hide';
    } else {
        input.type = 'password';
        button.textContent = '👁 Show';
    }
}

/**
 * Save web search configuration to server
 */
export async function saveWebSearchConfig() {
    const statusDiv = document.getElementById('websearch-save-status');
    
    try {
        // Gather current form values
        webSearchConfig.max_results = parseInt(document.getElementById('max-results').value);
        webSearchConfig.timeout = parseInt(document.getElementById('search-timeout').value);
        
        // Send to server
        const response = await fetch('/settings/web-search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                config: webSearchConfig
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            statusDiv.className = 'save-status success';
            statusDiv.textContent = '✓ Web search configuration saved successfully! Changes will take effect on next system restart.';
            statusDiv.style.display = 'block';
            
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 5000);
        } else {
            throw new Error(data.message || 'Failed to save');
        }
        
    } catch (error) {
        statusDiv.className = 'save-status error';
        statusDiv.textContent = '✗ Error saving web search configuration: ' + error.message;
        statusDiv.style.display = 'block';
    }
}
