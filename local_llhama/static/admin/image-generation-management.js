/**
 * Image Generation Configuration Module
 * Manages ImageGenerationManager settings stored in object_settings.json
 */

let imageGenConfig = null;

/**
 * Load image generation config from server
 */
export async function loadImageGenerationConfig() {
    try {
        const response = await fetch('/settings/image-generation');
        const data = await response.json();

        if (data.status === 'ok') {
            imageGenConfig = data.config;
        } else {
            console.error('Failed to load image generation config:', data.message);
        }
    } catch (error) {
        console.error('Error loading image generation config:', error);
    }
}

/**
 * Populate the GPU device dropdown with options returned by the server
 */
async function populateGpuDropdown() {
    try {
        const response = await fetch('/settings/available-gpus');
        const data = await response.json();

        if (data.status !== 'ok') return;

        const select = document.getElementById('img-cuda-device');
        if (!select) return;

        select.innerHTML = '';
        data.gpus.forEach(gpu => {
            const opt = document.createElement('option');
            opt.value = gpu.id;
            opt.textContent = gpu.name;
            select.appendChild(opt);
        });
    } catch (error) {
        console.error('Error loading GPU list:', error);
    }
}

/**
 * Display image generation configuration in the tab
 */
export async function displayImageGenerationConfig() {
    if (!imageGenConfig) {
        await loadImageGenerationConfig();
    }
    if (!imageGenConfig) return;

    // Populate GPU dropdown before setting value
    await populateGpuDropdown();

    const cfg = imageGenConfig;

    setChecked('img-enabled', cfg.enabled !== false);
    setValue('img-model-id', cfg.model_id || '');
    setValue('img-cache-dir', cfg.cache_dir || '');
    setValue('img-num-steps', cfg.num_steps ?? 4);
    setValue('img-guidance-scale', cfg.guidance_scale ?? 0.0);
    setValue('img-max-seq-len', cfg.max_sequence_length ?? 512);
    setValue('img-output-format', cfg.output_format || 'png');
    setValue('img-cuda-device', cfg.cuda_device || 'cuda:0');
    setChecked('img-keep-loaded', cfg.keep_pipeline_loaded === true);
    setValue('img-min-vram', cfg.keep_pipeline_loaded_min_vram_gb ?? 10.0);

    toggleKeepLoadedSection();
}

/**
 * Save image generation configuration to server
 */
export async function saveImageGenerationConfig() {
    const config = {
        enabled: document.getElementById('img-enabled')?.checked ?? true,
        model_id: document.getElementById('img-model-id')?.value.trim() || '',
        cache_dir: document.getElementById('img-cache-dir')?.value.trim() || '',
        num_steps: parseInt(document.getElementById('img-num-steps')?.value) || 4,
        guidance_scale: parseFloat(document.getElementById('img-guidance-scale')?.value) || 0.0,
        max_sequence_length: parseInt(document.getElementById('img-max-seq-len')?.value) || 512,
        output_format: document.getElementById('img-output-format')?.value || 'png',
        cuda_device: document.getElementById('img-cuda-device')?.value || 'cuda:0',
        keep_pipeline_loaded: document.getElementById('img-keep-loaded')?.checked ?? false,
        keep_pipeline_loaded_min_vram_gb: parseFloat(document.getElementById('img-min-vram')?.value) || 10.0,
    };

    const statusEl = document.getElementById('img-save-status');

    try {
        const response = await fetch('/settings/image-generation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config }),
        });

        const data = await response.json();

        if (data.status === 'ok') {
            imageGenConfig = config;
            showStatus(statusEl, 'Configuration saved. Restart system to apply changes.', 'success');
        } else {
            showStatus(statusEl, 'Save failed: ' + data.message, 'error');
        }
    } catch (error) {
        showStatus(statusEl, 'Save failed: ' + error.message, 'error');
    }
}

// ── Helpers ────────────────────────────────────────────────

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

function setChecked(id, value) {
    const el = document.getElementById(id);
    if (el) el.checked = !!value;
}

function showStatus(el, message, type) {
    if (!el) return;
    el.style.display = 'block';
    el.style.padding = '10px 15px';
    el.style.borderRadius = '4px';
    el.style.fontWeight = '500';

    if (type === 'success') {
        el.style.background = '#d4edda';
        el.style.color = '#155724';
        el.style.border = '1px solid #c3e6cb';
    } else {
        el.style.background = '#f8d7da';
        el.style.color = '#721c24';
        el.style.border = '1px solid #f5c6cb';
    }

    el.textContent = message;
    setTimeout(() => { el.style.display = 'none'; }, 5000);
}

/**
 * Toggle the min-VRAM input visibility based on the keep-loaded checkbox
 * Exposed globally so the HTML onclick can call it
 */
export function toggleKeepLoadedSection() {
    const checkbox = document.getElementById('img-keep-loaded');
    const section = document.getElementById('img-keep-loaded-section');
    if (checkbox && section) {
        section.style.display = checkbox.checked ? 'block' : 'none';
    }
}
