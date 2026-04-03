#!/bin/bash

# ============================================================================
# GPU Detection Module
# Detects GPU type and VRAM, then offers preset selection
# ============================================================================

detect_gpu_and_select_preset() {
    echo ""
    echo "============================================"
    echo "GPU Detection"
    echo "============================================"
    
    if command -v nvidia-smi &> /dev/null; then
        echo "NVIDIA GPU detected. Checking VRAM..."
        GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$GPU_INFO" ]; then
            echo "$GPU_INFO" | while IFS=',' read -r gpu_name vram_mb; do
                vram_gb=$(awk "BEGIN {printf \"%.1f\", $vram_mb/1024}")
                echo "  • GPU: $(echo $gpu_name | xargs)"
                echo "    VRAM: ${vram_gb} GB"
            done
            TOTAL_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{sum+=$1} END {printf "%.1f", sum/1024}')
            echo ""
            echo "Total VRAM available: ${TOTAL_VRAM} GB"
            GPU_TYPE="nvidia"
        else
            echo "WARNING: nvidia-smi found but failed to query GPU information."
            GPU_TYPE="unknown"
        fi
    elif command -v rocm-smi &> /dev/null; then
        echo "AMD GPU detected (ROCm)."
        echo "Note: AMD GPU support requires PyTorch built with ROCm."
        GPU_TYPE="amd"
    elif command -v intel_gpu_top &> /dev/null; then
        echo "Intel GPU detected."
        echo "Note: Intel GPU support requires Intel Extension for PyTorch."
        GPU_TYPE="intel"
    else
        echo "WARNING: No GPU detected or GPU utilities (nvidia-smi, rocm-smi, intel_gpu_top) not found."
        echo ""
        echo "The system will run in CPU-only mode, which means:"
        echo "  • Speech recognition (Whisper) will be SLOWER"
        echo "  • LLM inference (Ollama) will be SLOWER"
        echo "  • Text-to-speech (Piper) will work normally (CPU is fine)"
        echo ""
        echo "If you have an NVIDIA GPU, install drivers and nvidia-smi first."
        echo "If you have an AMD GPU, install ROCm utilities."
        echo "If you have an Intel GPU, install Intel GPU tools."
        echo ""
        read -p "Continue with CPU-only installation? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Installation cancelled by user."
            trap - EXIT  # Disable cleanup trap for user cancellation
            exit 0
        fi
        echo "Proceeding with CPU-only installation..."
        GPU_TYPE="cpu"
    fi
    
    echo "============================================"
    echo ""
    
    # Export GPU_TYPE for other modules
    export GPU_TYPE
    export TOTAL_VRAM
    
    # Preset selection based on VRAM
    select_preset
    
    sleep 1
}

select_preset() {
    if [[ "$GPU_TYPE" == "nvidia" ]] && [ -n "$TOTAL_VRAM" ]; then
        echo "============================================"
        echo "Configuration Preset Selection"
        echo "============================================"
        echo ""
        echo "Based on your GPU VRAM (${TOTAL_VRAM} GB), choose a preset:"
        echo ""
        
        # Check VRAM and show warning if needed
        VRAM_INT=$(echo "$TOTAL_VRAM" | awk '{print int($1)}')
        if [ "$VRAM_INT" -le 6 ]; then
            echo "WARNING: Low VRAM detected (${TOTAL_VRAM} GB)"
            echo "    The system requires ~6GB VRAM minimum to run."
            echo "    For best experience, run Ollama separately on:"
            echo "      • CPU (slower)"
            echo "      • Another GPU"
            echo "      • Remote server (remember to update OLLAMA_IP in .env)"
            echo ""
        fi
        
        # Show all presets with recommendations
        echo "Available Presets:"
        echo ""
        echo "1) English-Only Small (8GB VRAM)"
        echo "   • Lightweight, English-only"
        echo "   • Best for: Home automation focus"
        echo "   • Model: qwen3:8b, Whisper: small"
        if [ "$VRAM_INT" -ge 8 ]; then
            echo "   [Recommended for your GPU]"
        fi
        echo ""
        
        echo "2) English-Only Large (16GB VRAM)"
        echo "   • High-quality English responses"
        echo "   • Best for: General purpose use"
        echo "   • Model: gpt-oss:20b, Whisper: small"
        if [ "$VRAM_INT" -ge 16 ] && [ "$VRAM_INT" -lt 24 ]; then
            echo "   [Recommended for your GPU]"
        fi
        echo ""
        
        echo "3) Multi-Lingual Small (16GB VRAM)"
        echo "   • 6 languages: EN, FR, DE, IT, ES, RU"
        echo "   • Best for: Multilingual home"
        echo "   • Model: qwen3:14b, Whisper: turbo"
        if [ "$VRAM_INT" -ge 16 ] && [ "$VRAM_INT" -lt 24 ]; then
            echo "   [Recommended for your GPU]"
        fi
        echo ""
        
        echo "4) Multi-Lingual Large (24GB VRAM)"
        echo "   • 6 languages: EN, FR, DE, IT, ES, RU"
        echo "   • Best for: Maximum performance"
        echo "   • Model: gpt-oss:20b, Whisper: turbo"
        if [ "$VRAM_INT" -ge 24 ]; then
            echo "   [Recommended for your GPU]"
        fi
        echo ""
        
        echo "5) Skip preset selection (manual configuration)"
        echo ""
        
        # Get user choice
        while true; do
            read -p "Select preset (1-5): " PRESET_CHOICE
            case $PRESET_CHOICE in
                1)
                    PRESET_FILE="english_only_small"
                    echo "Selected: English-Only Small"
                    break
                    ;;
                2)
                    PRESET_FILE="english_only_large"
                    echo "Selected: English-Only Large"
                    if [ "$VRAM_INT" -lt 16 ]; then
                        echo "WARNING: This preset requires 16GB VRAM. Consider running Ollama separately."
                    fi
                    break
                    ;;
                3)
                    PRESET_FILE="multi_lingual_small"
                    echo "Selected: Multi-Lingual Small"
                    if [ "$VRAM_INT" -lt 16 ]; then
                        echo "WARNING: This preset requires 16GB VRAM. Consider running Ollama separately."
                    fi
                    break
                    ;;
                4)
                    PRESET_FILE="multi_lingual_large"
                    echo "Selected: Multi-Lingual Large"
                    if [ "$VRAM_INT" -lt 24 ]; then
                        echo "WARNING: This preset requires 24GB VRAM. Consider running Ollama separately."
                    fi
                    break
                    ;;
                5)
                    PRESET_FILE=""
                    echo "Skipping preset selection. You'll need to configure manually."
                    break
                    ;;
                *)
                    echo "Invalid choice. Please enter 1-5."
                    ;;
            esac
        done
        echo ""
        echo "============================================"
        echo ""
    elif [[ "$GPU_TYPE" == "cpu" ]]; then
        echo "============================================"
        echo "Configuration Preset Selection"
        echo "============================================"
        echo ""
        echo "WARNING: CPU-only mode detected"
        echo "    The English-Only Small preset will be used by default."
        echo "    You should run Ollama separately for better performance:"
        echo "      • On another machine with a GPU"
        echo "      • Remember to update OLLAMA_IP in .env to point to Ollama server"
        echo ""
        PRESET_FILE="english_only_small"
        echo "============================================"
        echo ""
    else
        echo "WARNING: Non-NVIDIA GPU or no VRAM detection available."
        echo "    Skipping preset selection. Manual configuration required."
        echo ""
        PRESET_FILE=""
    fi
    
    # Export PRESET_FILE for other modules
    export PRESET_FILE
}

apply_preset_configuration() {
    local preset_file="$1"
    
    if [ -n "$preset_file" ]; then
        echo ""
        echo "============================================"
        echo "Applying Configuration Preset"
        echo "============================================"
        echo ""
        
        PRESET_PATH="local_llhama/settings/presets/${preset_file}.json"
        if [ -f "$PRESET_PATH" ]; then
            echo "Applying preset: $preset_file"
            echo "Using preset_manager.py to configure system..."
            
            # Run preset manager to apply the preset
            python preset_manager.py apply "$preset_file"
            if [ $? -eq 0 ]; then
                echo "Preset applied successfully!"
                echo ""
                echo "Note: Ollama models will be downloaded on first use."
                echo "      This may take several minutes depending on model size."
            else
                echo "WARNING: Failed to apply preset automatically."
                echo "   You can apply it manually later with:"
                echo "   python preset_manager.py apply $preset_file"
            fi
        else
            echo "WARNING: Preset file not found: $PRESET_PATH"
            echo "   Manual configuration required."
        fi
        echo ""
        echo "============================================"
        echo ""
    fi
}
