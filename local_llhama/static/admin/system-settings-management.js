/**
 * System Settings Management Module
 * Dynamically generates and manages system settings UI from JSON structure
 */

let systemSettingsData = {};
let availableGpus = [];

/**
 * Load available GPUs from server
 */
async function loadAvailableGpus() {
    try {
        const response = await fetch('/settings/available-gpus');
        const data = await response.json();
        
        if (data.status === 'ok') {
            availableGpus = data.gpus;
            return true;
        } else {
            console.error('Failed to load available GPUs:', data.message);
            return false;
        }
    } catch (error) {
        console.error('Failed to load available GPUs:', error.message);
        return false;
    }
}

/**
 * Load system settings from server
 */
export async function loadSystemSettings() {
    try {
        const response = await fetch('/settings/system-settings');
        const data = await response.json();
        
        if (data.status === 'ok') {
            systemSettingsData = data.settings;
            return true;
        } else {
            showError('Failed to load system settings: ' + data.message);
            return false;
        }
    } catch (error) {
        showError('Failed to load system settings: ' + error.message);
        return false;
    }
}

/**
 * Display system settings by dynamically building the UI
 */
export async function displaySystemSettings() {
    // Load data if not already loaded
    if (Object.keys(systemSettingsData).length === 0) {
        const loaded = await loadSystemSettings();
        if (!loaded) return;
    }
    
    // Load available GPUs
    await loadAvailableGpus();
    
    // Build dynamic UI
    const container = document.getElementById('dynamic-system-settings');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Define section display names
    const sectionTitles = {
        'safety': 'Safety & Content Moderation',
        'chat': 'Chat & Conversations',
        'hardware': 'Hardware Configuration',
        'home_assistant': 'Home Assistant Configuration'
    };
    
    // Render each category
    for (const [categoryKey, categoryData] of Object.entries(systemSettingsData)) {
        if (typeof categoryData !== 'object') continue;
        
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'settings-section';
        
        const title = document.createElement('h3');
        title.textContent = sectionTitles[categoryKey] || categoryKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        sectionDiv.appendChild(title);
        
        // Render each setting in the category
        for (const [settingKey, settingData] of Object.entries(categoryData)) {
            if (settingKey === 'description' || typeof settingData !== 'object' || !settingData.hasOwnProperty('value')) continue;
            
            const settingDiv = createSettingElement(categoryKey, settingKey, settingData);
            if (settingDiv) {
                sectionDiv.appendChild(settingDiv);
            }
        }
        
        container.appendChild(sectionDiv);
    }
}

/**
 * Create a setting UI element based on its type
 */
function createSettingElement(categoryKey, settingKey, settingData) {
    const settingDiv = document.createElement('div');
    settingDiv.className = 'setting-item';
    
    const value = settingData.value;
    const description = settingData.description || '';
    const settingId = `${categoryKey}-${settingKey}`;
    
    // Determine input type based on value type
    if (typeof value === 'boolean') {
        // Checkbox for boolean
        const label = document.createElement('label');
        label.className = 'toggle-label';
        
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = settingId;
        input.checked = value;
        input.onchange = () => updateSetting(categoryKey, settingKey, input.checked);
        
        const span = document.createElement('span');
        span.className = 'toggle-text';
        span.textContent = settingKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        label.appendChild(input);
        label.appendChild(span);
        settingDiv.appendChild(label);
        
    } else if (typeof value === 'number') {
        // Number input
        const label = document.createElement('label');
        label.htmlFor = settingId;
        label.textContent = settingKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) + ':';
        settingDiv.appendChild(label);
        
        const input = document.createElement('input');
        input.type = 'number';
        input.id = settingId;
        input.value = value;
        input.min = value >= 1 ? 1 : 0;
        input.max = value > 50 ? 1000 : 100;
        input.onchange = () => updateSetting(categoryKey, settingKey, parseInt(input.value, 10));
        settingDiv.appendChild(input);
        
    } else if (typeof value === 'string') {
        const label = document.createElement('label');
        label.htmlFor = settingId;
        label.textContent = settingKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) + ':';
        settingDiv.appendChild(label);
        
        // Special case: cuda_device gets dropdown
        if (settingKey === 'cuda_device') {
            const select = document.createElement('select');
            select.id = settingId;
            
            availableGpus.forEach(gpu => {
                const option = document.createElement('option');
                option.value = gpu.id;
                option.textContent = gpu.name;
                select.appendChild(option);
            });
            
            select.value = value;
            select.onchange = () => updateSetting(categoryKey, settingKey, select.value);
            settingDiv.appendChild(select);
        } else {
            // Regular text input
            const input = document.createElement('input');
            input.type = 'text';
            input.id = settingId;
            input.value = value;
            input.onchange = () => updateSetting(categoryKey, settingKey, input.value);
            settingDiv.appendChild(input);
        }
        
    } else if (Array.isArray(value)) {
        // Textarea for arrays
        const label = document.createElement('label');
        label.htmlFor = settingId;
        label.textContent = settingKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) + ':';
        settingDiv.appendChild(label);
        
        const textarea = document.createElement('textarea');
        textarea.id = settingId;
        textarea.rows = 3;
        textarea.style.width = '100%';
        textarea.value = value.join(', ');
        textarea.onchange = () => {
            const arrayValue = textarea.value.split(',').map(s => s.trim()).filter(s => s);
            updateSetting(categoryKey, settingKey, arrayValue);
        };
        settingDiv.appendChild(textarea);
        
    } else if (typeof value === 'object' && value !== null) {
        // Textarea for objects (convert to comma-separated values)
        const label = document.createElement('label');
        label.htmlFor = settingId;
        label.textContent = settingKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) + ':';
        settingDiv.appendChild(label);
        
        const textarea = document.createElement('textarea');
        textarea.id = settingId;
        textarea.rows = 3;
        textarea.style.width = '100%';
        textarea.value = Object.values(value).join(', ');
        textarea.onchange = () => {
            // For exclusion_dict, convert comma-separated to object
            const values = textarea.value.split(',').map(s => s.trim()).filter(s => s);
            const objValue = {};
            values.forEach((v, i) => {
                objValue[`exclude_name${i + 1}`] = v;
            });
            updateSetting(categoryKey, settingKey, objValue);
        };
        settingDiv.appendChild(textarea);
    }
    
    // Add description
    if (description) {
        const descP = document.createElement('p');
        descP.className = 'setting-description';
        descP.textContent = description;
        settingDiv.appendChild(descP);
    }
    
    return settingDiv;
}

/**
 * Update a setting value in the data structure
 */
function updateSetting(categoryKey, settingKey, value) {
    if (!systemSettingsData[categoryKey]) {
        systemSettingsData[categoryKey] = {};
    }
    
    if (!systemSettingsData[categoryKey][settingKey]) {
        systemSettingsData[categoryKey][settingKey] = {};
    }
    
    systemSettingsData[categoryKey][settingKey].value = value;
    console.log(`Updated ${categoryKey}.${settingKey}:`, value);
}

/**
 * Save system settings to server
 */
export async function saveSystemSettings() {
    try {
        const response = await fetch('/settings/system-settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                settings: systemSettingsData
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            showSuccess('System settings saved successfully');
        } else {
            showError('Failed to save system settings: ' + data.message);
        }
    } catch (error) {
        showError('Failed to save system settings: ' + error.message);
    }
}

/**
 * Show error message
 */
function showError(message) {
    const statusDiv = document.getElementById('system-settings-save-status');
    if (statusDiv) {
        statusDiv.textContent = message;
        statusDiv.style.color = 'red';
        statusDiv.style.display = 'block';
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 5000);
    }
}

/**
 * Show success message
 */
function showSuccess(message) {
    const statusDiv = document.getElementById('system-settings-save-status');
    if (statusDiv) {
        statusDiv.textContent = message;
        statusDiv.style.color = 'green';
        statusDiv.style.display = 'block';
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 3000);
    }
}

// Export functions for global access
window.systemSettingsManagement = {
    displaySystemSettings,
    saveSystemSettings,
    loadSystemSettings
};
