#!/bin/bash

# ============================================================================
# Local_LLHAMA Installer Launcher
# Version: 0.7 Alpha
# Copyright (c) 2025 Nicola Zanarini
# Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)
# https://creativecommons.org/licenses/by/4.0/
# ============================================================================

# This is a simple launcher that calls the modular installer
# The actual installation logic is in the install/ directory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER_PATH="$SCRIPT_DIR/install/install.sh"

# Display header
printf "\n============================================\n"
printf "Local_LLHAMA Installer\n"
printf "Version: 0.7 Alpha\n"
printf "============================================\n\n"

# Check if the modular installer exists
if [ ! -f "$INSTALLER_PATH" ]; then
    echo "ERROR: Modular installer not found at: $INSTALLER_PATH"
    echo ""
    echo "Please ensure you have the complete Local_LLHAMA repository."
    echo "If you cloned the repository, the install/ directory should exist."
    echo ""
    exit 1
fi

# Check if the installer is executable
if [ ! -x "$INSTALLER_PATH" ]; then
    echo "Making installer executable..."
    chmod +x "$INSTALLER_PATH"
fi

# Launch the modular installer
echo "Launching modular installer..."
echo ""
exec bash "$INSTALLER_PATH"
