#!/bin/bash

# ============================================================================
# Local_LLHAMA Installer
# Version: 0.6 Alpha
# 
# Copyright (c) 2025 Nicola Zanarini
# Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)
# https://creativecommons.org/licenses/by/4.0/
# ============================================================================

# Check if Python 3.12 is installed
echo "Checking for Python 3.12 installation..."
if ! command -v python3.12 &> /dev/null
then
    echo "ERROR: Python 3.12 could not be found."
    echo "Please install Python 3.12 before running this script."
    exit 1
else
    echo "Python 3.12 found."
fi

# Check for PostgreSQL installation
echo "Checking for PostgreSQL installation..."
if ! command -v psql &> /dev/null
then
    echo "ERROR: PostgreSQL could not be found."
    echo "Please install PostgreSQL before running this script."
    echo "Install with: sudo apt-get install postgresql postgresql-contrib"
    exit 1
else
    PGVERSION=$(psql --version | awk '{print $NF}' | cut -d. -f1)
    echo "PostgreSQL $PGVERSION found."
    
    # Install pgvector development dependencies only if not already installed
    echo "Checking for PostgreSQL development headers..."
    if ! dpkg -l | grep -q "postgresql-server-dev-$PGVERSION"; then
        echo "Installing PostgreSQL development headers for version $PGVERSION..."
        sudo apt-get update
        sudo apt-get install -y "postgresql-server-dev-$PGVERSION"
        if [ $? -ne 0 ]; then
            echo "WARNING: Failed to install postgresql-server-dev-$PGVERSION"
            echo "pgvector extension may not be available"
        else
            echo "PostgreSQL development headers installed successfully."
        fi
    else
        echo "PostgreSQL development headers already installed."
    fi
fi

# Prompt the user to enter a name for the virtual environment
read -p "Enter the name for the new virtual environment: " VENV_NAME

# Confirm environment creation
echo "Creating virtual environment '$VENV_NAME'..."
python3.12 -m venv "$VENV_NAME"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment."
    exit 1
fi
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

# Check for Ollama installation
echo "Checking for Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "WARNING: Ollama not found."
    echo "Install from: https://ollama.ai"
    read -p "Continue installation anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
else
    echo "Ollama found."
fi

# Create .env file from .env.example if it doesn't exist
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ".env file created. IMPORTANT: Edit .env and configure your settings!"
elif [ ! -f ".env" ]; then
    echo "WARNING: .env.example not found. You'll need to create .env manually."
fi

# Create version info file in the virtual environment
echo "Creating version info file..."
cat > "$VENV_NAME/LOCAL_LLHAMA_VERSION.txt" << EOF
Local_LLHAMA Version Information
================================

Version: 0.6 Alpha
Installation Date: $(date '+%Y-%m-%d %H:%M:%S')

Copyright (c) 2025 Nicola Zanarini
Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)

You are free to:
- Share — copy and redistribute the material in any medium or format
- Adapt — remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:
- Attribution — You must give appropriate credit, provide a link to the license,
  and indicate if changes were made.

Full license: https://creativecommons.org/licenses/by/4.0/

Project Repository: https://github.com/Nemesis533/Local_LLHAMA
EOF

echo "Version info created at: $VENV_NAME/LOCAL_LLHAMA_VERSION.txt"

echo ""
echo "============================================"
echo "Installation complete!"
echo "============================================"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. DATABASE SETUP"
echo "   Follow DATABASE_SETUP.md for detailed instructions, or run:"
echo "   sudo -u postgres psql -c \"CREATE DATABASE llhama;\""
echo "   sudo -u postgres psql -c \"CREATE USER llhama_usr WITH PASSWORD 'your_password';\""
echo "   sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE llhama TO llhama_usr;\""
echo "   psql -U llhama_usr -d llhama -f db_schema_template.sql"
echo ""
echo "2. CONFIGURE ENVIRONMENT"
echo "   Edit .env file and set:"
echo "   - Database credentials (PG_PASSWORD)"
echo "   - Home Assistant URL and token (HA_BASE_URL, HA_TOKEN)"
echo "   - Ollama server IP (OLLAMA_IP)"
echo "   - Secret key (generate with: python -c \"import secrets; print(secrets.token_hex(32))\")"
echo "   - Allowed IP prefixes for web access"
echo ""
echo "3. ACTIVATE ENVIRONMENT"
echo "   source $VENV_NAME/bin/activate"
echo ""
echo "4. START THE SYSTEM"
echo "   python -m local_llhama.Run_System"
echo ""
echo "For detailed documentation, see README.md and DATABASE_SETUP.md"
echo "============================================"
