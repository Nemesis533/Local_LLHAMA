/**
 * Prompt Management Module
 * Handles LLM prompt templates and their configuration
 */

import { escapeHtml, showError } from './utils.js';

let promptsData = {};

/**
 * Load prompts data from server
 */
export async function loadPromptsData() {
    try {
        const response = await fetch('/settings/prompts');
        const data = await response.json();
        
        if (data.status === 'ok') {
            promptsData = data.prompts;
            return true;
        } else {
            showError('Failed to load prompts: ' + data.message);
            return false;
        }
    } catch (error) {
        showError('Failed to load prompts: ' + error.message);
        return false;
    }
}

/**
 * Display all prompts in editor
 */
export async function displayPrompts() {
    // Load data if not already loaded
    if (Object.keys(promptsData).length === 0) {
        const loaded = await loadPromptsData();
        if (!loaded) return;
    }
    
    const container = document.getElementById('prompts-container');
    
    if (Object.keys(promptsData).length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">No prompts configured.</p>';
        return;
    }
    
    // Define which prompts need template variables
    const templateVarPrompts = ['smart_home_prompt_template'];
    
    container.innerHTML = Object.entries(promptsData).map(([promptKey, promptConfig]) => {
        const description = promptConfig.description || 'No description available';
        const value = promptConfig.value || '';
        const displayName = promptKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        // Check if this prompt needs template variables
        const needsTemplateVars = templateVarPrompts.includes(promptKey);
        
        let templateVarSection = '';
        if (needsTemplateVars) {
            templateVarSection = `
                <div class="template-var-info">
                    <strong>Template Variables:</strong> This prompt requires specific template variables. 
                    Use the buttons below to insert them at your cursor position.
                </div>
                <div class="template-variables">
                    <button class="template-var-btn" onclick="window.promptManagement.insertTemplateVariable('${promptKey}', '{devices_context}')">
                        Insert {devices_context}
                    </button>
                    <button class="template-var-btn" onclick="window.promptManagement.insertTemplateVariable('${promptKey}', '{simple_functions_context}')">
                        Insert {simple_functions_context}
                    </button>
                </div>
            `;
        }
        
        return `
            <div class="prompt-editor">
                <div class="prompt-header" onclick="window.promptManagement.togglePromptBody('${promptKey}')">
                    <span>${displayName}</span>
                    <span id="toggle-icon-${promptKey}">▶</span>
                </div>
                <div id="prompt-body-${promptKey}" class="prompt-body" style="display: none;">
                    <div class="prompt-description">${escapeHtml(description)}</div>
                    
                    <label for="prompt-desc-${promptKey}">Description:</label>
                    <input type="text" id="prompt-desc-${promptKey}" 
                           value="${escapeHtml(description)}"
                           onchange="window.promptManagement.updatePromptDescription('${promptKey}', this.value)">
                    
                    ${templateVarSection}
                    
                    <label for="prompt-value-${promptKey}">Prompt Content:</label>
                    <textarea id="prompt-value-${promptKey}" 
                              onchange="window.promptManagement.updatePromptValue('${promptKey}', this.value)"
                    >${escapeHtml(value)}</textarea>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Toggle prompt body visibility
 */
export function togglePromptBody(promptKey) {
    const body = document.getElementById(`prompt-body-${promptKey}`);
    const icon = document.getElementById(`toggle-icon-${promptKey}`);
    
    if (body.style.display === 'none') {
        body.style.display = 'block';
        icon.textContent = '▼';
    } else {
        body.style.display = 'none';
        icon.textContent = '▶';
    }
}

/**
 * Update prompt description
 */
export function updatePromptDescription(promptKey, newDescription) {
    if (promptsData[promptKey]) {
        promptsData[promptKey].description = newDescription;
    }
}

/**
 * Update prompt value
 */
export function updatePromptValue(promptKey, newValue) {
    if (promptsData[promptKey]) {
        promptsData[promptKey].value = newValue;
    }
}

/**
 * Insert template variable at cursor position
 */
export function insertTemplateVariable(promptKey, variable) {
    const textarea = document.getElementById(`prompt-value-${promptKey}`);
    
    if (!textarea) return;
    
    // Get cursor position
    const startPos = textarea.selectionStart;
    const endPos = textarea.selectionEnd;
    const currentValue = textarea.value;
    
    // Insert the variable at cursor position
    const newValue = currentValue.substring(0, startPos) + variable + currentValue.substring(endPos);
    
    // Update textarea
    textarea.value = newValue;
    
    // Update the data
    updatePromptValue(promptKey, newValue);
    
    // Set cursor position after inserted text
    const newCursorPos = startPos + variable.length;
    textarea.focus();
    textarea.setSelectionRange(newCursorPos, newCursorPos);
    
    // Visual feedback
    textarea.style.background = '#e8f4f8';
    setTimeout(() => {
        textarea.style.background = 'white';
    }, 200);
}

/**
 * Save prompts to server
 */
export async function savePrompts() {
    const statusDiv = document.getElementById('prompts-save-status');
    
    try {
        const response = await fetch('/settings/prompts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompts: promptsData
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            statusDiv.className = 'save-status success';
            statusDiv.textContent = '✓ Prompts saved successfully! Changes will take effect on next system restart.';
            statusDiv.style.display = 'block';
            
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 5000);
        } else {
            throw new Error(data.message || 'Failed to save');
        }
        
    } catch (error) {
        statusDiv.className = 'save-status error';
        statusDiv.textContent = '✗ Error saving prompts: ' + error.message;
        statusDiv.style.display = 'block';
    }
}
