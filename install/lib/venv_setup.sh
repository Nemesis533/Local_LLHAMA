#!/bin/bash

# ============================================================================
# Virtual Environment Setup Module
# Handles virtual environment creation and package installation
# ============================================================================

setup_venv_and_packages() {
    # Install required system dependencies for Python packages
    echo "Installing system dependencies for Python packages..."
    echo "Checking for portaudio19-dev (required for pyaudio)..."
    
    if ! dpkg -l | grep -q "portaudio19-dev"; then
        echo "Installing portaudio19-dev..."
        sudo apt-get update
        sudo apt-get install -y portaudio19-dev
        
        if [ $? -ne 0 ]; then
            echo "WARNING: Failed to install portaudio19-dev. pyaudio may fail to install."
        else
            echo "portaudio19-dev installed successfully."
        fi
    else
        echo "portaudio19-dev already installed."
    fi
    
    # Prompt the user to enter a name for the virtual environment
    read -p "Enter the name for the new virtual environment: " VENV_NAME
    
    # Confirm environment creation
    echo "Creating virtual environment '$VENV_NAME'..."
    python3.11 -m venv "$VENV_NAME"
    
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        exit 1
    fi
    
    CREATED_VENV="$VENV_NAME"
    export CREATED_VENV
    export VENV_NAME
    echo "Virtual environment '$VENV_NAME' created successfully."
    
    # Activate the virtual environment
    echo "Activating virtual environment '$VENV_NAME'..."
    source "$VENV_NAME/bin/activate"
    
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to activate virtual environment."
        exit 1
    fi
    
    # Upgrade pip inside the virtual environment
    echo "Upgrading pip to the latest version..."
    pip install --upgrade pip
    
    # Install required Python packages from requirements.txt
    echo "Installing required Python packages from requirements.txt..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to install packages from requirements.txt"
            exit 1
        fi
    else
        echo "ERROR: requirements.txt not found in current directory"
        exit 1
    fi
}
