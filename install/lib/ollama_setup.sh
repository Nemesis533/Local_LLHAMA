#!/bin/bash

# ============================================================================
# Ollama Setup Module
# Handles Ollama installation via snap or official script
# ============================================================================

setup_ollama() {
    echo "Checking for Ollama installation..."
    
    if ! command -v ollama &> /dev/null; then
        echo "WARNING: Ollama not found."
        read -p "Would you like to install Ollama automatically? (y/n): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Installing Ollama..."
            
            # Try snap first (recommended method)
            if command -v snap &> /dev/null; then
                echo "Installing Ollama via snap..."
                sudo snap install ollama
                
                if [ $? -eq 0 ]; then
                    INSTALLED_OLLAMA="yes"
                    export INSTALLED_OLLAMA
                    echo "Ollama installed successfully via snap."
                else
                    echo "Snap installation failed. Trying alternative method..."
                    install_ollama_via_script
                fi
            else
                # Fallback to curl script if snap not available
                echo "Snap not available. Using official install script..."
                install_ollama_via_script
            fi
        else
            echo "Skipping Ollama installation. You can install it later:"
            echo "  sudo snap install ollama"
            echo "  OR visit: https://ollama.ai"
        fi
    else
        echo "Ollama found."
    fi
}

install_ollama_via_script() {
    curl -fsSL https://ollama.com/install.sh | sh
    
    if [ $? -ne 0 ]; then
        echo "WARNING: Ollama installation failed. Install manually:"
        echo "  Install snap: sudo apt install snapd"
        echo "  Then: sudo snap install ollama"
        echo "  OR visit: https://ollama.ai"
    else
        INSTALLED_OLLAMA="yes"
        export INSTALLED_OLLAMA
        echo "Ollama installed successfully."
    fi
}
