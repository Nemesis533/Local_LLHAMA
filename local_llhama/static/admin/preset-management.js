/**
 * Preset Management Module
 * Handles configuration presets, application, and system restart
 */

import { escapeHtml } from './utils.js';

// Store active preset ID and name globally
let activePresetId = null;
let activePresetName = null;

/**
 * Load presets and current configuration
 */
export async function loadPresets() {
    try {
        // Load available presets
        const presetsResponse = await fetch('/presets');
        const presetsData = await presetsResponse.json();
        
        // Load current configuration
        const currentResponse = await fetch('/presets/current');
        const currentData = await currentResponse.json();
        
        console.log('Current config data:', currentData);
        
        if (currentData.status === 'ok') {
            displayCurrentConfig(currentData.current_config);
        }
        
        if (presetsData.status === 'ok') {
            console.log('Active preset ID before display:', activePresetId);
            displayPresets(presetsData.presets);
        }
    } catch (error) {
        console.error('Failed to load presets:', error);
        document.getElementById('presets-container').innerHTML = 
            '<div style="color: #d32f2f; padding: 20px;">Failed to load presets: ' + error.message + '</div>';
    }
}

/**
 * Display current configuration
 */
function displayCurrentConfig(config) {
    const display = document.getElementById('current-config-display');
    activePresetId = config.active_preset || null;
    
    console.log('Config object:', config);
    console.log('Setting activePresetId to:', activePresetId);
    
    display.innerHTML = `
        <div style="display: grid; gap: 10px;">
            ${activePresetId ? `<div style="background: #e8f5e9; padding: 12px; border-radius: 6px; margin-bottom: 8px; border: 2px solid #4caf50;"><strong>Active Preset:</strong> <span style="color: #2e7d32; font-weight: bold; font-size: 16px;" id="active-preset-name">${escapeHtml(activePresetId)}</span></div>` : ''}
            <div><strong>LLM Model:</strong> <span style="color: #1976d2;">${escapeHtml(config.llm_model)}</span></div>
            <div><strong>Whisper Model:</strong> <span style="color: #1976d2;">${escapeHtml(config.whisper_model)}</span></div>
            <div><strong>Languages:</strong> <span style="color: #1976d2;">${config.languages.join(', ')}</span></div>
        </div>
    `;
}

/**
 * Display all presets
 */
function displayPresets(presets) {
    const container = document.getElementById('presets-container');
    
    // Add "Create New Preset" card
    const createCard = `
        <div class="preset-card create-new" onclick="window.presetManagement.showCreatePresetModal()">
            <div class="create-icon">◈</div>
            <div class="create-text">Create New Preset</div>
        </div>
    `;
    
    if (presets.length === 0) {
        container.innerHTML = createCard + '<div style="padding: 20px; text-align: center; color: #666;">No presets available</div>';
        return;
    }
    
    // Sort presets alphabetically by name
    const sortedPresets = presets.sort((a, b) => a.name.localeCompare(b.name));
    
    container.innerHTML = createCard + sortedPresets.map(preset => {
        const isActive = activePresetId && activePresetId === preset.id;
        const req = preset.requirements || {};
        
        console.log(`Preset ${preset.id}: isActive=${isActive}, activePresetId=${activePresetId}`);
        
        // Store active preset name for display
        if (isActive) {
            activePresetName = preset.name;
            // Update the active preset name in current config if element exists
            setTimeout(() => {
                const nameEl = document.getElementById('active-preset-name');
                if (nameEl) {
                    nameEl.textContent = preset.name;
                }
            }, 100);
        }
        
        return `
            <div class="preset-card ${isActive ? 'active' : ''}" data-preset-id="${escapeHtml(preset.id)}">
                <h3>${escapeHtml(preset.name)}</h3>
                <div class="preset-description">${escapeHtml(preset.description)}</div>
                
                <div class="preset-specs">
                    <div class="preset-spec-item">
                        <span class="preset-spec-label">LLM Model:</span>
                        <span class="preset-spec-value" id="llm-${escapeHtml(preset.id)}">Loading...</span>
                    </div>
                    <div class="preset-spec-item">
                        <span class="preset-spec-label">Whisper:</span>
                        <span class="preset-spec-value" id="whisper-${escapeHtml(preset.id)}">Loading...</span>
                    </div>
                    <div class="preset-spec-item">
                        <span class="preset-spec-label">Languages:</span>
                        <span class="preset-spec-value" id="lang-${escapeHtml(preset.id)}">Loading...</span>
                    </div>
                </div>
                
                ${req.gpu_count || req.vram_per_gpu ? `
                <div class="preset-requirements">
                    <strong>Requirements:</strong>
                    ${req.gpu_count ? `<div>• GPUs: ${req.gpu_count}</div>` : ''}
                    ${req.vram_per_gpu ? `<div>• VRAM: ${req.vram_per_gpu} per GPU</div>` : ''}
                </div>
                ` : '<div style="min-height: 70px;"></div>'}
                
                <div class="preset-buttons-container">
                    <button class="preset-details-toggle" onclick="window.presetManagement.togglePresetDetails('${escapeHtml(preset.id)}')">
                        <span>◈ VIEW ALL SETTINGS</span>
                        <span class="toggle-icon">▼</span>
                    </button>
                    
                    <div class="preset-details-content" id="details-${escapeHtml(preset.id)}">
                        <div class="preset-settings-section" id="settings-${escapeHtml(preset.id)}">
                            <h4 style="color: #000;">◧ Configuration Details</h4>
                            <div>Loading settings...</div>
                        </div>
                    </div>
                    
                    <button class="preset-apply-btn" onclick="window.presetManagement.applyPreset('${escapeHtml(preset.id)}', '${escapeHtml(preset.name)}')" ${isActive ? 'disabled' : ''}>
                        ${isActive ? 'Currently Active' : 'Apply This Preset'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
    // Load detailed info for each preset
    presets.forEach(preset => {
        loadPresetDetails(preset.id);
    });
}

/**
 * Load detailed preset information
 */
async function loadPresetDetails(presetId) {
    try {
        const response = await fetch(`/presets/${presetId}`);
        const data = await response.json();
        
        if (data.status === 'ok' && data.preset) {
            const summary = data.preset.settings_summary;
            document.getElementById(`llm-${presetId}`).textContent = summary.llm_model;
            document.getElementById(`whisper-${presetId}`).textContent = summary.whisper_model;
            document.getElementById(`lang-${presetId}`).textContent = summary.languages.join(', ');
        }
    } catch (error) {
        console.error(`Failed to load details for preset ${presetId}:`, error);
    }
}

/**
 * Toggle preset details expansion
 */
export function togglePresetDetails(presetId) {
    const content = document.getElementById(`details-${presetId}`);
    const toggle = content.previousElementSibling;
    
    if (content.classList.contains('expanded')) {
        // Close the dropdown
        content.classList.remove('expanded');
        toggle.classList.remove('expanded');
        // Remove click listener
        document.removeEventListener('click', content._closeHandler);
        content.removeEventListener('click', content._stopPropagation);
    } else {
        // Close any other open dropdowns first
        document.querySelectorAll('.preset-details-content.expanded').forEach(el => {
            el.classList.remove('expanded');
            el.previousElementSibling.classList.remove('expanded');
            document.removeEventListener('click', el._closeHandler);
            el.removeEventListener('click', el._stopPropagation);
        });
        
        // Open this dropdown
        content.classList.add('expanded');
        toggle.classList.add('expanded');
        
        // Load full settings if not already loaded
        loadFullPresetSettings(presetId);
        
        // Add click handlers to close dropdown
        setTimeout(() => {
            const closeHandler = (e) => {
                // Close if clicking outside the dropdown or on the toggle button
                if (!content.contains(e.target) || toggle.contains(e.target)) {
                    content.classList.remove('expanded');
                    toggle.classList.remove('expanded');
                    document.removeEventListener('click', closeHandler);
                    content.removeEventListener('click', stopPropagation);
                }
            };
            
            const stopPropagation = (e) => {
                e.stopPropagation();
            };
            
            // Store handlers for cleanup
            content._closeHandler = closeHandler;
            content._stopPropagation = stopPropagation;
            
            document.addEventListener('click', closeHandler);
            content.addEventListener('click', stopPropagation);
        }, 10);
    }
}

/**
 * Load and display all settings for a preset
 */
async function loadFullPresetSettings(presetId) {
    const container = document.getElementById(`settings-${presetId}`);
    
    // Check if already loaded
    if (container.dataset.loaded === 'true') {
        return;
    }
    
    try {
        const response = await fetch(`/presets/${presetId}`);
        const data = await response.json();
        
        if (data.status !== 'ok' || !data.preset) {
            container.innerHTML = '<div style="color: var(--color-danger);">Failed to load settings</div>';
            return;
        }
        
        const preset = data.preset;
        const settings = preset.settings || {};
        
        let html = '<h4 style="color: #000;">◧ Configuration Details</h4>';
        
        // Iterate through each settings section
        for (const [sectionName, sectionSettings] of Object.entries(settings)) {
            html += `<div style="margin-bottom: var(--space-md);">`;
            html += `<div style="font-weight: bold; color: #000; margin-bottom: var(--space-xs); text-transform: uppercase; font-size: var(--font-size-xs); letter-spacing: 0.5px;">${escapeHtml(sectionName)}</div>`;
            
            for (const [key, config] of Object.entries(sectionSettings)) {
                const value = config.value;
                const type = config.type;
                
                // Format the value based on type
                let displayValue;
                if (type === 'dict' || type === 'list') {
                    displayValue = JSON.stringify(value, null, 2);
                } else {
                    displayValue = String(value);
                }
                
                html += `
                    <div class="preset-setting-item">
                        <span class="preset-setting-label">${escapeHtml(key)}</span>
                        <span class="preset-setting-value">${escapeHtml(displayValue)}</span>
                    </div>
                `;
            }
            
            html += `</div>`;
        }
        
        container.innerHTML = html;
        container.dataset.loaded = 'true';
        
    } catch (error) {
        console.error(`Failed to load full settings for preset ${presetId}:`, error);
        container.innerHTML = '<div style="color: var(--color-danger);">Error loading settings</div>';
    }
}

/**
 * Apply a preset
 */
export async function applyPreset(presetId, presetName) {
    if (!confirm(`Apply preset "${presetName}"?\n\nYou will need to restart the system for changes to take effect.\n\nContinue?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/presets/${presetId}/apply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            alert(`✅ Success!\n\n${data.message}\n\nPlease restart the Local LLHAMA system to apply these changes.`);
            // Reload presets and current config to show the active state
            await loadPresets();
        } else {
            alert(`❌ Error: ${data.message}`);
        }
    } catch (error) {
        alert(`❌ Failed to apply preset: ${error.message}`);
    }
}

/**
 * Restart the system
 */
export async function restartSystem() {
    if (!confirm('Are you sure you want to restart the Local LLHAMA system?\n\nYou will be redirected to the Model tab where you can monitor the restart progress.')) {
        return;
    }
    
    try {
        // Redirect to admin model tab immediately with restart parameter
        window.location.href = '/admin?restarting=true&tab=model';
        
        // Send restart command (will execute even as page is redirecting)
        fetch('/restart-system', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'restart' })
        }).catch(err => console.error('Restart request failed:', err));
        
    } catch (error) {
        alert(`❌ Failed to initiate restart: ${error.message}`);
    }
}

/**
 * Show modal for creating a new preset
 */
export function showCreatePresetModal() {
    const modal = document.getElementById('create-preset-modal');
    if (!modal) {
        createPresetModal();
    }
    document.getElementById('create-preset-modal').style.display = 'flex';
}

/**
 * Close the create preset modal
 */
export function closeCreatePresetModal() {
    document.getElementById('create-preset-modal').style.display = 'none';
}

/**
 * Create the modal HTML structure
 */
function createPresetModal() {
    const modalHTML = `
        <div id="create-preset-modal" class="modal" style="display: none;">
            <div class="modal-content" style="max-width: 800px; max-height: 90vh; overflow-y: auto;">
                <span class="close-modal" onclick="window.presetManagement.closeCreatePresetModal()">&times;</span>
                <h2>◈ CREATE NEW PRESET</h2>
                
                <form id="create-preset-form" onsubmit="window.presetManagement.submitCreatePreset(event)">
                    <div class="preset-form-section">
                        <h4>▣ BASIC INFORMATION</h4>
                        <label for="preset-id">Preset ID (lowercase, no spaces)</label>
                        <input type="text" id="preset-id" pattern="[a-z0-9_]+" required placeholder="e.g., my_custom_preset">
                        
                        <label for="preset-name">Preset Name</label>
                        <input type="text" id="preset-name" required placeholder="e.g., My Custom Preset">
                        
                        <label for="preset-description">Description</label>
                        <textarea id="preset-description" rows="3" required placeholder="Describe this preset configuration..."></textarea>
                    </div>
                    
                    <div class="preset-form-section">
                        <h4>▣ LLM CONFIGURATION</h4>
                        <label for="ollama-model">Ollama Model</label>
                        <input type="text" id="ollama-model" required placeholder="e.g., qwen3:14b">
                        
                        <label for="ollama-embedding">Embedding Model</label>
                        <input type="text" id="ollama-embedding" required placeholder="e.g., embeddinggemma">
                        
                        <label for="allow-internet">
                            <input type="checkbox" id="allow-internet" checked>
                            Allow Internet Searches
                        </label>
                    </div>
                    
                    <div class="preset-form-section">
                        <h4>▣ AUDIO CONFIGURATION</h4>
                        <label for="whisper-model">Whisper Model</label>
                        <select id="whisper-model" required>
                            <option value="turbo">Turbo (Best Performance)</option>
                            <option value="large">Large (Best Accuracy)</option>
                            <option value="medium" selected>Medium (Balanced)</option>
                            <option value="small">Small (Low VRAM)</option>
                            <option value="base">Base (Minimal)</option>
                            <option value="tiny">Tiny (Ultra Light)</option>
                        </select>
                    </div>
                    
                    <div class="preset-form-section">
                        <h4>▣ CHAT HANDLER SETTINGS</h4>
                        <label for="max-tokens">Max Tokens</label>
                        <input type="number" id="max-tokens" required value="4096" min="512" max="32768">
                        
                        <label for="default-context-words">Default Context Words</label>
                        <input type="number" id="default-context-words" required value="400" min="50" max="2000">
                        
                        <label for="min-context-words">Minimum Context Words</label>
                        <input type="number" id="min-context-words" required value="100" min="50" max="1000">
                        
                        <label for="context-reduction">Context Reduction Factor</label>
                        <input type="number" id="context-reduction" required value="0.7" min="0.1" max="0.9" step="0.1">
                        
                        <label for="context-management-mode">Context Management Mode</label>
                        <select id="context-management-mode" required>
                            <option value="truncate" selected>Truncate (Simple cut-off)</option>
                            <option value="summarize">Summarize (AI-generated summary)</option>
                        </select>
                        
                        <label for="context-summarization-model">Summarization Model</label>
                        <select id="context-summarization-model" required>
                            <option value="decision" selected>Decision Model (faster)</option>
                            <option value="main">Main Model (higher quality)</option>
                            <option value="auto">Auto (prefer decision model)</option>
                        </select>
                        
                        <label for="context-summary-target-words">Summary Target Words</label>
                        <input type="number" id="context-summary-target-words" required value="150" min="50" max="500">
                    </div>
                    
                    <div class="preset-form-section">
                        <h4>▣ REQUIREMENTS</h4>
                        <label for="gpu-count">GPU Count</label>
                        <input type="number" id="gpu-count" min="1" value="1">
                        
                        <label for="vram-per-gpu">VRAM per GPU</label>
                        <input type="text" id="vram-per-gpu" placeholder="e.g., 16GB">
                    </div>
                    
                    <div style="display: flex; gap: var(--space-md); margin-top: var(--space-xl);">
                        <button type="submit" class="btn-save" style="flex: 1;">■ CREATE PRESET</button>
                        <button type="button" class="btn-cancel" onclick="window.presetManagement.closeCreatePresetModal()" style="flex: 1;">✕ CANCEL</button>
                    </div>
                </form>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Submit the create preset form
 */
export async function submitCreatePreset(event) {
    event.preventDefault();
    
    const presetData = {
        id: document.getElementById('preset-id').value.trim(),
        name: document.getElementById('preset-name').value.trim(),
        description: document.getElementById('preset-description').value.trim(),
        requirements: {
            gpu_count: parseInt(document.getElementById('gpu-count').value) || 1,
            vram_per_gpu: document.getElementById('vram-per-gpu').value.trim() || "16GB"
        },
        settings: {
            SettingLoaderClass: {
                ollama_model: {
                    value: document.getElementById('ollama-model').value.trim(),
                    type: "str"
                },
                ollama_embedding_model: {
                    value: document.getElementById('ollama-embedding').value.trim(),
                    type: "str"
                },
                allow_internet_searches: {
                    value: document.getElementById('allow-internet').checked,
                    type: "bool"
                }
            },
            AudioTranscriptionClass: {
                whisper_model: {
                    value: document.getElementById('whisper-model').value,
                    type: "str"
                }
            },
            ChatHandler: {
                max_tokens: {
                    value: parseInt(document.getElementById('max-tokens').value),
                    type: "int"
                },
                default_context_words: {
                    value: parseInt(document.getElementById('default-context-words').value),
                    type: "int"
                },
                min_context_words: {
                    value: parseInt(document.getElementById('min-context-words').value),
                    type: "int"
                },
                context_reduction_factor: {
                    value: parseFloat(document.getElementById('context-reduction').value),
                    type: "float"
                },
                context_management_mode: {
                    value: document.getElementById('context-management-mode').value,
                    type: "str"
                },
                context_summarization_model: {
                    value: document.getElementById('context-summarization-model').value,
                    type: "str"
                },
                context_summary_target_words: {
                    value: parseInt(document.getElementById('context-summary-target-words').value),
                    type: "int"
                }
            },
            TextToSpeech: {
                language_models: {
                    value: {
                        en: "en_US-amy-medium.onnx"
                    },
                    type: "dict"
                }
            }
        }
    };
    
    try {
        const response = await fetch('/presets', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(presetData)
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            alert(`✅ Success!\n\nPreset "${presetData.name}" created successfully.`);
            closeCreatePresetModal();
            // Reload presets to show the new one
            await loadPresets();
        } else {
            alert(`❌ Error: ${data.message}`);
        }
    } catch (error) {
        alert(`❌ Failed to create preset: ${error.message}`);
    }
}
