#!/bin/bash

# ============================================================================
# Image Generation Setup Module
# Handles optional Stable Diffusion 3.5 image generation configuration.
# Requires a NVIDIA GPU with at least 12 GB VRAM (recommended: 16+ GB).
# ============================================================================

# Minimum VRAM in GB required for comfortable image generation
readonly IMG_GEN_MIN_VRAM=12

# Path to the settings file relative to the install directory
readonly IMG_GEN_SETTINGS_FILE="local_llhama/settings/object_settings.json"

# ---------------------------------------------------------------------------
# _imggen_check_vram
# Evaluates detected VRAM and prints a recommendation / warning.
# Outputs: sets IMG_GEN_VRAM_OK=yes|no
# ---------------------------------------------------------------------------
_imggen_check_vram() {
    IMG_GEN_VRAM_OK="no"

    if [[ "$GPU_TYPE" != "nvidia" ]]; then
        echo "  WARNING: No NVIDIA GPU detected."
        echo "           Image generation requires an NVIDIA GPU with CUDA support."
        echo "           Running on CPU is not supported for Stable Diffusion 3.5."
        return
    fi

    if [ -z "$TOTAL_VRAM" ]; then
        echo "  WARNING: Could not determine VRAM amount."
        echo "           Make sure nvidia-smi is working correctly."
        return
    fi

    local vram_int
    vram_int=$(echo "$TOTAL_VRAM" | awk '{print int($1)}')

    if [ "$vram_int" -ge "$IMG_GEN_MIN_VRAM" ]; then
        IMG_GEN_VRAM_OK="yes"
        echo "  GPU VRAM: ${TOTAL_VRAM} GB  ✓  (minimum ${IMG_GEN_MIN_VRAM} GB required)"
        if [ "$vram_int" -ge 16 ]; then
            echo "  Your GPU has enough VRAM to keep the pipeline loaded between requests,"
            echo "  which speeds up repeated image generation."
        fi
    else
        echo "  WARNING: Your GPU has ${TOTAL_VRAM} GB of VRAM."
        echo "           Stable Diffusion 3.5 Large Turbo requires at least ${IMG_GEN_MIN_VRAM} GB."
        echo "           With less VRAM you may experience:"
        echo "             • Out-of-memory errors during generation"
        echo "             • Very slow generation or system instability"
        echo "           You can still enable the feature if you want to try."
    fi
}

# ---------------------------------------------------------------------------
# _imggen_update_settings
# Patches object_settings.json using Python to stay JSON-safe.
# ---------------------------------------------------------------------------
_imggen_update_settings() {
    local enabled="$1"
    local cache_dir="$2"
    local cuda_device="$3"
    local keep_loaded="$4"

    if [ ! -f "$IMG_GEN_SETTINGS_FILE" ]; then
        echo "  WARNING: Settings file not found: $IMG_GEN_SETTINGS_FILE"
        echo "           You will need to configure image generation manually."
        return 1
    fi

    python3 - "$IMG_GEN_SETTINGS_FILE" "$enabled" "$cache_dir" "$cuda_device" "$keep_loaded" <<'PYEOF'
import sys, json

settings_path, enabled_str, cache_dir, cuda_device, keep_loaded_str = sys.argv[1:]

enabled    = enabled_str    == "true"
keep_loaded = keep_loaded_str == "true"

with open(settings_path, "r", encoding="utf-8") as f:
    data = json.load(f)

section = data.setdefault("ImageGenerationManager", {})

def set_val(section, key, value, vtype):
    if key not in section:
        section[key] = {}
    section[key]["value"] = value
    section[key]["type"]  = vtype

set_val(section, "enabled",                  enabled,     "bool")
set_val(section, "cache_dir",                cache_dir,   "str")
set_val(section, "cuda_device",              cuda_device, "str")
set_val(section, "keep_pipeline_loaded",     keep_loaded, "bool")

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

print(f"  Settings updated in {settings_path}")
PYEOF
}

# ---------------------------------------------------------------------------
# _imggen_configure_hf_token
# Prompts the user for a HuggingFace token and writes it to .env.
# ---------------------------------------------------------------------------
_imggen_configure_hf_token() {
    echo ""
    echo "  --- HuggingFace Authentication ---"
    echo "  Stable Diffusion 3.5 Large Turbo is a gated model."
    echo "  You must have a HuggingFace account and accept the model licence at:"
    echo "    https://huggingface.co/stabilityai/stable-diffusion-3.5-large-turbo"
    echo ""
    echo "  Create a read-access token at:"
    echo "    https://huggingface.co/settings/tokens"
    echo ""
    read -s -p "  Enter your HuggingFace token (leave blank to skip and set HF_TOKEN manually later): " HF_TOKEN_INPUT
    echo

    if [ -n "$HF_TOKEN_INPUT" ]; then
        if [ -f ".env" ]; then
            if grep -q "^HF_TOKEN=" .env; then
                sed -i "s|^HF_TOKEN=.*|HF_TOKEN=$HF_TOKEN_INPUT|" .env
            else
                echo "HF_TOKEN=$HF_TOKEN_INPUT" >> .env
            fi
            echo "  HuggingFace token saved to .env"
        else
            echo "  WARNING: .env file not found. Could not save HF_TOKEN."
            echo "           Add the following line to .env manually:"
            echo "             HF_TOKEN=$HF_TOKEN_INPUT"
        fi
    else
        echo "  Skipped. Remember to set HF_TOKEN in .env before using image generation."
    fi
}

# ---------------------------------------------------------------------------
# setup_image_generation  (public entry point called from install.sh)
# ---------------------------------------------------------------------------
setup_image_generation() {
    echo ""
    echo "============================================"
    echo "Image Generation Setup (Stable Diffusion 3.5)"
    echo "============================================"
    echo ""
    echo "Local_LLHAMA includes optional AI image generation powered by"
    echo "Stable Diffusion 3.5 Large Turbo (NF4 quantised)."
    echo ""
    echo "Hardware requirements:"
    echo "  • NVIDIA GPU with CUDA support"
    echo "  • At least 12 GB VRAM  (16+ GB recommended)"
    echo "  • ~14 GB of disk space for model weights"
    echo ""
    echo "Additional Python packages installed regardless of your choice"
    echo "(already in requirements.txt):"
    echo "  diffusers, transformers, accelerate, bitsandbytes"
    echo ""

    # VRAM check and advisory
    _imggen_check_vram

    echo ""

    # Ask user
    read -p "Would you like to enable image generation? (y/n): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Image generation will be DISABLED."
        _imggen_update_settings "false" "/mnt/fast_storage/diffusers" "cuda:0" "false"
        echo ""
        echo "You can enable it later by editing:"
        echo "  $IMG_GEN_SETTINGS_FILE"
        echo "  Set  ImageGenerationManager > enabled > value  to  true"
        echo ""
        return 0
    fi

    # -----------------------------------------------------------------------
    # User said yes — gather configuration
    # -----------------------------------------------------------------------

    echo ""
    echo "--- Model Cache Directory ---"
    echo "Model weights (~14 GB) will be downloaded here on first use."
    echo "Use a path on a fast drive with sufficient free space."
    read -p "  Enter cache directory [/mnt/fast_storage/diffusers]: " IMGGEN_CACHE_DIR
    IMGGEN_CACHE_DIR="${IMGGEN_CACHE_DIR:-/mnt/fast_storage/diffusers}"

    # Create the directory if necessary
    if [ ! -d "$IMGGEN_CACHE_DIR" ]; then
        echo "  Directory does not exist — creating: $IMGGEN_CACHE_DIR"
        mkdir -p "$IMGGEN_CACHE_DIR" 2>/dev/null || {
            echo "  WARNING: Could not create $IMGGEN_CACHE_DIR"
            echo "           You may need to create it manually or run with sudo."
        }
    else
        echo "  Directory exists: $IMGGEN_CACHE_DIR"
    fi

    echo ""
    echo "--- CUDA Device ---"
    echo "Which GPU should run image generation?"
    read -p "  Enter CUDA device [cuda:0]: " IMGGEN_CUDA_DEVICE
    IMGGEN_CUDA_DEVICE="${IMGGEN_CUDA_DEVICE:-cuda:0}"

    # Keep-pipeline option only makes sense with enough VRAM
    IMGGEN_KEEP_LOADED="false"
    if [[ "$IMG_GEN_VRAM_OK" == "yes" ]]; then
        local vram_int
        vram_int=$(echo "$TOTAL_VRAM" | awk '{print int($1)}')
        if [ "$vram_int" -ge 16 ]; then
            echo ""
            echo "--- Pipeline Persistence ---"
            echo "With ${TOTAL_VRAM} GB of VRAM you can keep the SD pipeline resident"
            echo "after each generation to speed up subsequent requests."
            echo "Note: this reduces VRAM available to the LLM."
            read -p "  Keep pipeline loaded between requests? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                IMGGEN_KEEP_LOADED="true"
            fi
        fi
    fi

    # HuggingFace token
    _imggen_configure_hf_token

    # Apply settings
    echo ""
    echo "  Updating $IMG_GEN_SETTINGS_FILE ..."
    _imggen_update_settings "true" "$IMGGEN_CACHE_DIR" "$IMGGEN_CUDA_DEVICE" "$IMGGEN_KEEP_LOADED"

    echo ""
    echo "Image generation enabled and configured."
    echo ""
    echo "IMPORTANT: The model weights are NOT downloaded now."
    echo "           They will be downloaded automatically (~14 GB) on the first"
    echo "           image generation request after the system starts."
    echo ""
    echo "  cache_dir   : $IMGGEN_CACHE_DIR"
    echo "  cuda_device : $IMGGEN_CUDA_DEVICE"
    echo "  keep loaded : $IMGGEN_KEEP_LOADED"
    echo ""
    sleep 1
}
