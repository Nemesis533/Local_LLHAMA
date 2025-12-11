/**
 * Language Management Module
 * Handles TTS language-to-voice-model mappings
 */

import { escapeHtml, showError } from './utils.js';

let languageModels = {};
let availableVoices = [];

/**
 * Load language settings and available voices
 */
export async function loadLanguageSettings() {
    try {
        // Load current language models
        const modelsResponse = await fetch('/settings/language-models');
        const modelsData = await modelsResponse.json();
        
        if (modelsData.status === 'ok') {
            languageModels = modelsData.language_models;
        }
        
        // Load available voice files
        const voicesResponse = await fetch('/settings/available-voices');
        const voicesData = await voicesResponse.json();
        
        if (voicesData.status === 'ok') {
            availableVoices = voicesData.voices;
        }
        
        displayLanguageMappings();
        
    } catch (error) {
        showError('Failed to load language settings: ' + error.message);
    }
}

/**
 * Display language mappings
 */
export function displayLanguageMappings() {
    const container = document.getElementById('language-mappings-container');
    
    if (Object.keys(languageModels).length === 0) {
        container.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">No language mappings configured. Click "Add Language" to create one.</p>';
        return;
    }
    
    container.innerHTML = Object.entries(languageModels).map(([langCode, modelFile]) => `
        <div class="language-mapping" data-lang="${escapeHtml(langCode)}">
            <label style="font-weight: 500; min-width: 100px;">Language Code:</label>
            <input type="text" value="${escapeHtml(langCode)}" 
                   onchange="window.languageManagement.updateLanguageCode('${escapeHtml(langCode)}', this.value)"
                   placeholder="e.g., en, fr, de">
            
            <label style="font-weight: 500;">Voice Model:</label>
            <select onchange="window.languageManagement.updateLanguageModel('${escapeHtml(langCode)}', this.value)">
                ${availableVoices.map(voice => `
                    <option value="${escapeHtml(voice)}" ${voice === modelFile ? 'selected' : ''}>
                        ${escapeHtml(voice)}
                    </option>
                `).join('')}
            </select>
            
            <button class="btn-small btn-danger" onclick="window.languageManagement.removeLanguageMapping('${escapeHtml(langCode)}')">
                ✕ Remove
            </button>
        </div>
    `).join('');
}

/**
 * Add new language mapping
 */
export function addLanguageMapping() {
    if (availableVoices.length === 0) {
        showError('No voice models available. Please add .onnx files to the piper_voices directory.');
        return;
    }
    
    // Find a new language code that doesn't exist
    let newLangCode = 'new';
    let counter = 1;
    while (languageModels[newLangCode]) {
        newLangCode = 'new' + counter;
        counter++;
    }
    
    languageModels[newLangCode] = availableVoices[0];
    displayLanguageMappings();
}

/**
 * Update language code
 */
export function updateLanguageCode(oldCode, newCode) {
    newCode = newCode.trim().toLowerCase();
    
    if (!newCode) {
        showError('Language code cannot be empty');
        displayLanguageMappings();
        return;
    }
    
    if (newCode !== oldCode && languageModels[newCode]) {
        showError('Language code "' + newCode + '" already exists');
        displayLanguageMappings();
        return;
    }
    
    if (newCode !== oldCode) {
        languageModels[newCode] = languageModels[oldCode];
        delete languageModels[oldCode];
        displayLanguageMappings();
    }
}

/**
 * Update language model
 */
export function updateLanguageModel(langCode, modelFile) {
    languageModels[langCode] = modelFile;
}

/**
 * Remove language mapping
 */
export function removeLanguageMapping(langCode) {
    if (confirm('Are you sure you want to remove the mapping for "' + langCode + '"?')) {
        delete languageModels[langCode];
        displayLanguageMappings();
    }
}

/**
 * Save language models to server
 */
export async function saveLanguageModels() {
    const statusDiv = document.getElementById('language-save-status');
    
    try {
        const response = await fetch('/settings/language-models', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                language_models: languageModels
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            statusDiv.className = 'save-status success';
            statusDiv.textContent = '✓ Language models saved successfully! Changes will take effect on next system restart.';
            statusDiv.style.display = 'block';
            
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 5000);
        } else {
            throw new Error(data.message || 'Failed to save');
        }
        
    } catch (error) {
        statusDiv.className = 'save-status error';
        statusDiv.textContent = '✗ Error saving language models: ' + error.message;
        statusDiv.style.display = 'block';
    }
}
