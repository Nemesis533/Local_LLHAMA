#!/bin/bash

# ============================================================================
# Python Setup Module
# Handles Python 3.11 installation and verification
# ============================================================================

setup_python311() {
    echo "Checking for Python 3.11 installation..."
    
    if ! command -v python3.11 &> /dev/null; then
        echo "WARNING: Python 3.11 could not be found."
        read -p "Would you like this script to attempt to auto-install Python 3.11? (y/n): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Attempting to install Python 3.11 (requires sudo)..."
            echo "Adding deadsnakes PPA for Python 3.11..."
            sudo apt-get update
            sudo apt-get install -y software-properties-common
            sudo add-apt-repository -y ppa:deadsnakes/ppa
            sudo apt-get update
            echo "Installing Python 3.11 and required packages..."
            sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
            
            if [ $? -ne 0 ]; then
                echo "ERROR: Failed to install Python 3.11."
                echo "Please install it manually before running this script."
                exit 1
            else
                echo "Python 3.11 installed successfully."
                INSTALLED_PYTHON311="yes"
                export INSTALLED_PYTHON311
            fi
        else
            echo "ERROR: Python 3.11 is required. Please install it manually before running this script."
            echo "Install with: sudo apt-get install python3.11 python3.11-venv python3.11-dev"
            exit 1
        fi
    else
        echo "Python 3.11 found."
    fi
}
