#!/bin/bash

# ============================================================================
# Local_LLHAMA Installer
# Version: 0.65 Alpha
# Copyright (c) 2025 Nicola Zanarini
# Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)
# https://creativecommons.org/licenses/by/4.0/
# ============================================================================

# Get the directory where this script is located
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$INSTALLER_DIR/lib"

# Source all library modules
source "$LIB_DIR/cleanup.sh"
source "$LIB_DIR/gpu_detection.sh"
source "$LIB_DIR/python_setup.sh"
source "$LIB_DIR/postgres_setup.sh"
source "$LIB_DIR/venv_setup.sh"
source "$LIB_DIR/pytorch_setup.sh"
source "$LIB_DIR/ollama_setup.sh"
source "$LIB_DIR/database_wizard.sh"
source "$LIB_DIR/env_wizard.sh"
source "$LIB_DIR/service_setup.sh"

# Track what was installed for cleanup
export INSTALLED_PYTHON311="no"
export INSTALLED_POSTGRES="no"
export INSTALLED_PGVECTOR="no"
export INSTALLED_OLLAMA="no"
export CREATED_VENV=""
export CREATED_DATABASE=""
export CREATED_DB_USER=""

# Set up error handling
set -E
trap cleanup_on_failure EXIT

# Intro splash and package disclaimer
printf "\n============================================\n"
printf "Local_LLHAMA Installer\n"
printf "Version: 0.65 Alpha\n"
printf "============================================\n\n"
printf "This installer may install the following system packages:\n\n"
printf "OPTIONAL (you will be asked):\n"
printf "  • Python 3.11 (via deadsnakes PPA)\n"
printf "    - python3.11, python3.11-venv, python3.11-dev\n"
printf "    - software-properties-common\n"
printf "  • PostgreSQL 16\n"
printf "    - postgresql-16, postgresql-client-16, postgresql-contrib\n"
printf "  • pgvector extension\n"
printf "    - postgresql-16-pgvector (or build from source)\n"
printf "    - git, make, build-essential, postgresql-server-dev-16\n"
printf "  • PyTorch 2.1.2 (into virtualenv)\n"
printf "    - torch, torchvision, torchaudio\n"
printf "  • Ollama LLM runtime\n"
printf "    - Installed via official install script\n"
printf "  • PostgreSQL database configuration\n"
printf "    - Database and user creation wizard\n"
printf "  • Systemd service (optional)\n"
printf "    - Auto-start on boot configuration\n\n"
printf "REQUIRED (from requirements.txt):\n"
printf "  • Python packages: Flask, psycopg2, whisper, piper-tts, etc.\n"
printf "  • System dependencies: portaudio19-dev (for pyaudio)\n\n"
printf "NOTE: All system package installations require sudo privileges.\n"
printf "============================================\n\n"
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo
sleep 1

# Determine installation directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installer is running from: $SCRIPT_DIR"
echo ""

# Check if we're in the install/ subdirectory, if so go up one level
if [[ "$(basename "$SCRIPT_DIR")" == "install" ]]; then
    INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
elif [[ "$(basename "$SCRIPT_DIR")" == "Local_LLHAMA" ]] || [ -f "$SCRIPT_DIR/local_llhama/Run_System.py" ]; then
    echo "Detected Local_LLHAMA repository in current location."
    INSTALL_DIR="$SCRIPT_DIR"
else
    echo "This doesn't appear to be a Local_LLHAMA repository."
    read -p "Enter installation directory [~/Local_LLHAMA]: " CUSTOM_DIR
    INSTALL_DIR="${CUSTOM_DIR:-$HOME/Local_LLHAMA}"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        echo "Directory doesn't exist. Please clone the repository first:"
        echo "  git clone https://github.com/Nemesis533/Local_LLHAMA.git $INSTALL_DIR"
        exit 1
    fi
fi

echo "Installation directory: $INSTALL_DIR"
echo ""

# Change to installation directory
cd "$INSTALL_DIR" || exit 1
echo "Working directory: $(pwd)"
echo ""

# Verify required files exist
if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found in $INSTALL_DIR"
    echo "Please ensure you're running this installer from the Local_LLHAMA repository."
    exit 1
fi

# Run GPU detection and preset selection
detect_gpu_and_select_preset

# Setup Python 3.11
setup_python311

# Interactive choices for system components
echo "PostgreSQL, pgvector and PyTorch installation choices"
read -p "Would you like this script to attempt to auto-install PostgreSQL 16? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_POSTGRES="yes"
else
    INSTALL_POSTGRES="no"
fi

read -p "Would you like this script to attempt to auto-install the pgvector extension for PostgreSQL? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_PGVECTOR="yes"
else
    INSTALL_PGVECTOR="no"
fi

read -p "Would you like this script to attempt to auto-install PyTorch 2.1.2 into the created virtualenv? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_TORCH="yes"
else
    INSTALL_TORCH="no"
fi

# Setup PostgreSQL and pgvector
setup_postgres "$INSTALL_POSTGRES" "$INSTALL_PGVECTOR"

# Setup virtual environment and install packages
setup_venv_and_packages

# Setup PyTorch if requested
if [[ "$INSTALL_TORCH" == "yes" ]]; then
    setup_pytorch "$GPU_TYPE"
fi

# Setup Ollama
setup_ollama

# Run database configuration wizard
run_database_wizard

# Apply preset configuration
apply_preset_configuration "$PRESET_FILE"

# Run environment configuration wizard
run_env_wizard

# Create version info file
create_version_info "$VENV_NAME"

# Setup systemd service
setup_systemd_service "$VENV_NAME"

echo ""
echo "============================================"
echo "Installation complete!"
echo "============================================"
echo ""

# Offer to start the system immediately
start_system_prompt "$VENV_NAME"
