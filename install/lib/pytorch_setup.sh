#!/bin/bash

# ============================================================================
# PyTorch Setup Module
# Handles PyTorch installation based on GPU type
# ============================================================================

setup_pytorch() {
    local gpu_type="$1"
    
    echo "Preparing to install PyTorch 2.1.2 inside virtualenv..."
    
    # Determine installation type based on detected GPU
    if [[ "$gpu_type" == "nvidia" ]]; then
        echo "NVIDIA GPU detected. Defaulting to CUDA-enabled PyTorch."
        echo "Installing CUDA-enabled PyTorch 2.1.2 with cu121 wheels..."
        echo "(Requires NVIDIA CUDA toolkit 12.1 to be installed)"
        pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cu121 || {
            echo "WARNING: Automatic CUDA PyTorch install failed."
            echo "Please ensure CUDA toolkit is installed or visit:"
            echo "  https://pytorch.org/get-started/locally/"
        }
    elif [[ "$gpu_type" == "amd" ]]; then
        echo "AMD GPU detected. You'll need to install PyTorch with ROCm support."
        echo "Please visit: https://pytorch.org/get-started/locally/"
        echo "Select ROCm for your AMD GPU and install manually."
        read -p "Press Enter to continue..."
    elif [[ "$gpu_type" == "intel" ]]; then
        echo "Intel GPU detected. You'll need to install Intel Extension for PyTorch."
        echo "Please visit: https://intel.github.io/intel-extension-for-pytorch/"
        read -p "Press Enter to continue..."
    elif [[ "$gpu_type" == "cpu" ]]; then
        echo "No GPU detected - installing CPU-only PyTorch."
        echo "PyTorch is required for Whisper speech recognition."
        echo "Installing CPU-only PyTorch 2.1.2..."
        pip install --index-url https://download.pytorch.org/whl/cpu torch==2.1.2 || {
            echo "WARNING: Automatic CPU PyTorch install failed."
            echo "PyTorch is required for speech recognition. Please visit:"
            echo "  https://pytorch.org/get-started/locally/"
        }
    else
        echo "Unknown GPU type. PyTorch is required for Whisper speech recognition."
        echo "Installing CPU-only PyTorch 2.1.2..."
        pip install --index-url https://download.pytorch.org/whl/cpu torch==2.1.2 || {
            echo "WARNING: Automatic CPU PyTorch install failed."
            echo "PyTorch is required for speech recognition. Please visit:"
            echo "  https://pytorch.org/get-started/locally/"
        }
    fi
}
