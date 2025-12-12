#!/bin/bash

# ============================================================================
# Local_LLHAMA Installer
# Version: 0.65 Alpha
# Copyright (c) 2025 Nicola Zanarini
# Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0)
# https://creativecommons.org/licenses/by/4.0/
# ============================================================================

# Track what was installed for cleanup
INSTALLED_PYTHON311="no"
INSTALLED_POSTGRES="no"
INSTALLED_PGVECTOR="no"
INSTALLED_OLLAMA="no"
CREATED_VENV=""
CREATED_DATABASE=""
CREATED_DB_USER=""

# Cleanup function
cleanup_on_failure() {
    local exit_code=$?
    
    # Only run cleanup if there was an error
    if [ $exit_code -ne 0 ]; then
        echo ""
        echo "============================================"
        echo "ERROR: Installation failed!"
        echo "============================================"
        echo ""
        echo "The installation encountered an error."
        echo "Would you like to clean up what was installed?"
        echo ""
        
        # Show what was installed/created
        if [ -n "$CREATED_VENV" ] && [ -d "$CREATED_VENV" ]; then
            echo "  • Virtual environment: $CREATED_VENV"
        fi
        if [ "$INSTALLED_PYTHON311" == "yes" ]; then
            echo "  • Python 3.11 (via apt)"
        fi
        if [ "$INSTALLED_POSTGRES" == "yes" ]; then
            echo "  • PostgreSQL 16 (via apt)"
        fi
        if [ "$INSTALLED_PGVECTOR" == "yes" ]; then
            echo "  • pgvector extension"
        fi
        if [ "$INSTALLED_OLLAMA" == "yes" ]; then
            echo "  • Ollama"
        fi
        if [ -n "$CREATED_DATABASE" ]; then
            echo "  • PostgreSQL database: $CREATED_DATABASE"
        fi
        if [ -n "$CREATED_DB_USER" ]; then
            echo "  • PostgreSQL user: $CREATED_DB_USER"
        fi
        
        echo ""
        read -p "Do you want to clean up installed components? (y/n): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo "Cleaning up..."
            
            # Remove virtual environment
            if [ -n "$CREATED_VENV" ] && [ -d "$CREATED_VENV" ]; then
                read -p "Remove virtual environment '$CREATED_VENV'? (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    rm -rf "$CREATED_VENV"
                    echo "  ✓ Removed virtual environment"
                fi
            fi
            
            # Remove database
            if [ -n "$CREATED_DATABASE" ]; then
                read -p "Remove PostgreSQL database '$CREATED_DATABASE'? (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $CREATED_DATABASE;" 2>/dev/null
                    echo "  ✓ Removed database"
                fi
            fi
            
            # Remove database user
            if [ -n "$CREATED_DB_USER" ]; then
                read -p "Remove PostgreSQL user '$CREATED_DB_USER'? (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    sudo -u postgres psql -c "DROP USER IF EXISTS $CREATED_DB_USER;" 2>/dev/null
                    echo "  ✓ Removed database user"
                fi
            fi
            
            # Remove Python 3.11
            if [ "$INSTALLED_PYTHON311" == "yes" ]; then
                read -p "Remove Python 3.11? (requires sudo) (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    sudo apt-get remove -y python3.11 python3.11-venv python3.11-dev
                    echo "  ✓ Removed Python 3.11"
                fi
            fi
            
            # Remove PostgreSQL
            if [ "$INSTALLED_POSTGRES" == "yes" ]; then
                read -p "Remove PostgreSQL 16? (requires sudo) (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    sudo systemctl stop postgresql
                    sudo apt-get remove -y postgresql-16 postgresql-client-16 postgresql-contrib
                    echo "  ✓ Removed PostgreSQL 16"
                fi
            fi
            
            # Remove Ollama
            if [ "$INSTALLED_OLLAMA" == "yes" ]; then
                read -p "Remove Ollama? (requires sudo) (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    if command -v snap &> /dev/null && snap list ollama &>/dev/null; then
                        sudo snap remove ollama
                    else
                        # Manual removal if installed via script
                        sudo systemctl stop ollama 2>/dev/null
                        sudo systemctl disable ollama 2>/dev/null
                        sudo rm -f /usr/local/bin/ollama
                        sudo rm -f /etc/systemd/system/ollama.service
                        sudo systemctl daemon-reload
                    fi
                    echo "  ✓ Removed Ollama"
                fi
            fi
            
            echo ""
            echo "Cleanup complete."
        else
            echo "Keeping installed components. You can remove them manually later."
        fi
        
        echo ""
        echo "Installation failed. Please fix the error and run the installer again."
        exit $exit_code
    fi
}

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

# Detect GPU and VRAM
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

# Preset selection based on VRAM
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

sleep 1

# Determine installation directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Installer is running from: $SCRIPT_DIR"
echo ""

# Check if we're already in a Local_LLHAMA directory
if [[ "$(basename "$SCRIPT_DIR")" == "Local_LLHAMA" ]] || [ -f "$SCRIPT_DIR/local_llhama/Run_System.py" ]; then
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

# Check if Python 3.11 is installed
echo "Checking for Python 3.11 installation..."
if ! command -v python3.11 &> /dev/null
then
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
        fi
    else
        echo "ERROR: Python 3.11 is required. Please install it manually before running this script."
        echo "Install with: sudo apt-get install python3.11 python3.11-venv python3.11-dev"
        exit 1
    fi
else
    echo "Python 3.11 found."
fi

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

# Handle PostgreSQL auto-install or validate existing installation
if [[ "$INSTALL_POSTGRES" == "yes" ]]; then
    echo "Attempting to install PostgreSQL 16 (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y postgresql-16 postgresql-client-16 postgresql-contrib
    if [ $? -ne 0 ]; then
        echo "WARNING: Automatic installation of PostgreSQL 16 failed."
        echo "You can install it manually or re-run the installer after installing PostgreSQL."
    else
        echo "PostgreSQL 16 installation attempted (check with: psql --version)."
        INSTALLED_POSTGRES="yes"
        echo "Enabling and starting PostgreSQL service..."
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
        if [ $? -eq 0 ]; then
            echo "PostgreSQL service enabled and started successfully."
        else
            echo "WARNING: Failed to start PostgreSQL service. Check with: sudo systemctl status postgresql"
        fi
    fi
fi

# Verify PostgreSQL presence (required if user chose not to auto-install or if auto-install failed)
if ! command -v psql &> /dev/null; then
    echo "ERROR: PostgreSQL could not be found." 
    echo "If you declined auto-install, please install PostgreSQL 16 before running this script."
    echo "Install with: sudo apt-get install postgresql-16 postgresql-contrib"
    exit 1
else
    PGVERSION=$(psql --version | awk '{print $NF}' | cut -d. -f1)
    echo "PostgreSQL $PGVERSION found."
fi

# Handle pgvector installation if requested
if [[ "$INSTALL_PGVECTOR" == "yes" ]]; then
    echo "Attempting to install pgvector for PostgreSQL $PGVERSION..."
    # Try apt package first (package names may vary by distribution)
    sudo apt-get update
    if sudo apt-get install -y "postgresql-$PGVERSION-pgvector" 2>/dev/null; then
        echo "pgvector package installed via apt (postgresql-$PGVERSION-pgvector)."
        INSTALLED_PGVECTOR="yes"
    else
        echo "pgvector apt package not available or failed; attempting to build and install from source."
        sudo apt-get install -y git make build-essential "postgresql-server-dev-$PGVERSION"
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to install build dependencies for pgvector. You may need to install them manually."
        else
            TMP_DIR="/tmp/pgvector_build_$$"
            git clone https://github.com/pgvector/pgvector.git "$TMP_DIR"
            if [ $? -ne 0 ]; then
                echo "ERROR: Failed to clone pgvector repository."
            else
                pushd "$TMP_DIR" >/dev/null
                make
                if [ $? -ne 0 ]; then
                    echo "ERROR: make failed for pgvector."
                else
                    sudo make install
                    if [ $? -ne 0 ]; then
                        echo "ERROR: sudo make install failed for pgvector."
                    else
                        echo "pgvector built and installed successfully."
                        INSTALLED_PGVECTOR="yes"
                    fi
                fi
                popd >/dev/null
            fi
        fi
    fi
    echo "Note: You still need to create the extension inside your database with: SQL \"CREATE EXTENSION IF NOT EXISTS vector;\""
fi

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

# If user requested, attempt to install PyTorch 2.1.2 inside the virtualenv
if [[ "$INSTALL_TORCH" == "yes" ]]; then
    echo "Preparing to install PyTorch 2.1.2 inside virtualenv..."
    
    # Determine installation type based on detected GPU
    if [[ "$GPU_TYPE" == "nvidia" ]]; then
        echo "NVIDIA GPU detected. Defaulting to CUDA-enabled PyTorch."
        echo "Installing CUDA-enabled PyTorch 2.1.2 with cu121 wheels..."
        echo "(Requires NVIDIA CUDA toolkit 12.1 to be installed)"
        pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cu121 || {
            echo "WARNING: Automatic CUDA PyTorch install failed."
            echo "Please ensure CUDA toolkit is installed or visit:"
            echo "  https://pytorch.org/get-started/locally/"
        }
    elif [[ "$GPU_TYPE" == "amd" ]]; then
        echo "AMD GPU detected. You'll need to install PyTorch with ROCm support."
        echo "Please visit: https://pytorch.org/get-started/locally/"
        echo "Select ROCm for your AMD GPU and install manually."
        read -p "Press Enter to continue..."
    elif [[ "$GPU_TYPE" == "intel" ]]; then
        echo "Intel GPU detected. You'll need to install Intel Extension for PyTorch."
        echo "Please visit: https://intel.github.io/intel-extension-for-pytorch/"
        read -p "Press Enter to continue..."
    elif [[ "$GPU_TYPE" == "cpu" ]]; then
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
fi

# Check for Ollama installation
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
                echo "Ollama installed successfully via snap."
            else
                echo "Snap installation failed. Trying alternative method..."
                curl -fsSL https://ollama.com/install.sh | sh
                if [ $? -ne 0 ]; then
                    echo "WARNING: Ollama installation failed. You can install it manually:"
                    echo "  sudo snap install ollama"
                    echo "  OR visit: https://ollama.ai"
                else
                    INSTALLED_OLLAMA="yes"
                    echo "Ollama installed successfully."
                fi
            fi
        else
            # Fallback to curl script if snap not available
            echo "Snap not available. Using official install script..."
            curl -fsSL https://ollama.com/install.sh | sh
            if [ $? -ne 0 ]; then
                echo "WARNING: Ollama installation failed. Install manually:"
                echo "  Install snap: sudo apt install snapd"
                echo "  Then: sudo snap install ollama"
                echo "  OR visit: https://ollama.ai"
            else
                INSTALLED_OLLAMA="yes"
                echo "Ollama installed successfully."
            fi
        fi
    else
        echo "Skipping Ollama installation. You can install it later:"
        echo "  sudo snap install ollama"
        echo "  OR visit: https://ollama.ai"
    fi
else
    echo "Ollama found."
fi

# Optional: Database setup wizard
echo ""
read -p "Would you like to configure the PostgreSQL database now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "============================================"
    echo "Database Configuration Wizard"
    echo "============================================"
    echo ""
    
    # Get database details
    read -p "Enter database name [llhama]: " DB_NAME
    DB_NAME=${DB_NAME:-llhama}
    
    read -p "Enter database username [llhama_usr]: " DB_USER
    DB_USER=${DB_USER:-llhama_usr}
    
    read -s -p "Enter database password: " DB_PASSWORD
    echo
    read -s -p "Confirm database password: " DB_PASSWORD_CONFIRM
    echo
    
    if [[ "$DB_PASSWORD" != "$DB_PASSWORD_CONFIRM" ]]; then
        echo "ERROR: Passwords do not match. Skipping database configuration."
        echo "You can configure the database manually later using DATABASE_SETUP.md"
    else
        echo ""
        echo "Creating database and user..."
        
        # Create database
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME;" 2>/dev/null
        if [ $? -eq 0 ]; then
            CREATED_DATABASE="$DB_NAME"
        else
            echo "NOTE: Database '$DB_NAME' may already exist or creation failed."
        fi
        
        # Create user with password
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "User '$DB_USER' created successfully."
            CREATED_DB_USER="$DB_USER
            echo "User '$DB_USER' created successfully."
        else
            echo "NOTE: User '$DB_USER' may already exist. Updating password..."
            sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
        fi
        
        # Grant privileges
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
        echo "Privileges granted to '$DB_USER' on database '$DB_NAME'."
        
        # Grant schema privileges (PostgreSQL 15+)
        sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;" 2>/dev/null
        
        # Enable pgvector extension if available
        echo "Attempting to enable pgvector extension..."
        sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "pgvector extension enabled successfully."
        else
            echo "NOTE: pgvector extension not available. Install it first if you need vector support."
        fi
        
        # Check for SQL schema files
        if [ -f "init_database.sql" ]; then
            echo ""
            read -p "Would you like to apply the database schema (init_database.sql)? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f init_database.sql
                if [ $? -eq 0 ]; then
                    echo "Database schema applied successfully."
                else
                    echo "WARNING: Failed to apply database schema. You may need to apply it manually."
                fi
            fi
        fi
        
        # Update .env file if it exists
        if [ -f ".env" ]; then
            echo ""
            read -p "Would you like to update the .env file with these database credentials? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                # Backup .env
                cp .env .env.backup
                echo "Backed up .env to .env.backup"
                
                # Update database settings in .env
                sed -i "s/^PG_HOST=.*/PG_HOST=localhost/" .env
                sed -i "s/^PG_PORT=.*/PG_PORT=5432/" .env
                sed -i "s/^PG_DATABASE=.*/PG_DATABASE=$DB_NAME/" .env
                sed -i "s/^PG_USER=.*/PG_USER=$DB_USER/" .env
                sed -i "s/^PG_PASSWORD=.*/PG_PASSWORD=$DB_PASSWORD/" .env
                
                echo ".env file updated with database credentials."
            fi
        fi
        
        echo ""
        echo "Database configuration complete!"
        echo "Database: $DB_NAME"
        echo "User: $DB_USER"
        echo "Connection string: postgresql://$DB_USER:****@localhost:5432/$DB_NAME"
    fi
fi

# Apply selected preset if one was chosen
if [ -n "$PRESET_FILE" ]; then
    echo ""
    echo "============================================"
    echo "Applying Configuration Preset"
    echo "============================================"
    echo ""
    
    PRESET_PATH="local_llhama/settings/presets/${PRESET_FILE}.json"
    if [ -f "$PRESET_PATH" ]; then
        echo "Applying preset: $PRESET_FILE"
        echo "Using preset_manager.py to configure system..."
        
        # Run preset manager to apply the preset
        python preset_manager.py apply "$PRESET_FILE"
        if [ $? -eq 0 ]; then
            echo "Preset applied successfully!"
            echo ""
            echo "Note: Ollama models will be downloaded on first use."
            echo "      This may take several minutes depending on model size."
        else
            echo "WARNING: Failed to apply preset automatically."
            echo "   You can apply it manually later with:"
            echo "   python preset_manager.py apply $PRESET_FILE"
        fi
    else
        echo "WARNING: Preset file not found: $PRESET_PATH"
        echo "   Manual configuration required."
    fi
    echo ""
    echo "============================================"
    echo ""
fi

# Create .env file from .env.example if it doesn't exist
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ".env file created."
elif [ ! -f ".env" ]; then
    echo "WARNING: .env.example not found. You'll need to create .env manually."
fi

# Optional: Environment configuration wizard
if [ -f ".env" ]; then
    echo ""
    read -p "Would you like to configure the .env file now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "============================================"
        echo "Environment Configuration Wizard"
        echo "============================================"
        echo ""
        
        # Backup .env if not already backed up
        if [ ! -f ".env.backup" ]; then
            cp .env .env.backup
            echo "Backed up .env to .env.backup"
            echo ""
        fi
        
        # Home Assistant Configuration
        echo "--- Home Assistant Configuration ---"
        read -p "Enter Home Assistant URL [http://homeassistant.local:8123]: " HA_URL
        HA_URL=${HA_URL:-http://homeassistant.local:8123}
        
        read -p "Enter Home Assistant Long-Lived Access Token: " HA_TOKEN
        
        # Ollama Configuration
        echo ""
        echo "--- Ollama Configuration ---"
        read -p "Enter Ollama server IP:PORT [localhost:11434]: " OLLAMA_SERVER
        OLLAMA_SERVER=${OLLAMA_SERVER:-localhost:11434}
        
        # Web Security Configuration
        echo ""
        echo "--- Web Security Configuration ---"
        echo "Enter allowed IP prefixes for web access (comma-separated)"
        read -p "Example: 192.168.1.,127.0.0.1 [127.0.0.1]: " ALLOWED_IPS
        ALLOWED_IPS=${ALLOWED_IPS:-127.0.0.1}
        
        # Generate secret key
        echo ""
        echo "Generating secret key..."
        if command -v python3.11 &> /dev/null; then
            SECRET_KEY=$(python3.11 -c "import secrets; print(secrets.token_hex(32))")
        elif command -v python3 &> /dev/null; then
            SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        else
            SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || echo "CHANGE_ME_$(date +%s)")
        fi
        echo "Secret key generated."
        
        # Admin Credentials
        echo ""
        echo "--- Admin Credentials ---"
        read -p "Enter admin username [admin]: " ADMIN_USER
        ADMIN_USER=${ADMIN_USER:-admin}
        
        read -s -p "Enter admin password: " ADMIN_PASS
        echo
        read -s -p "Confirm admin password: " ADMIN_PASS_CONFIRM
        echo
        
        if [[ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]]; then
            echo "ERROR: Passwords do not match. Using default password 'changeme123'."
            echo "IMPORTANT: Change this password after first login!"
            ADMIN_PASS="changeme123"
        fi
        
        # Database Configuration (if already set up)
        echo ""
        echo "--- Database Configuration ---"
        if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ] && [ -n "$DB_PASSWORD" ]; then
            echo "Using database configuration from previous step:"
            echo "  Database: $DB_NAME"
            echo "  User: $DB_USER"
            PG_HOST="localhost"
            PG_PORT="5432"
        else
            read -p "Enter PostgreSQL host [localhost]: " PG_HOST
            PG_HOST=${PG_HOST:-localhost}
            
            read -p "Enter PostgreSQL port [5432]: " PG_PORT
            PG_PORT=${PG_PORT:-5432}
            
            read -p "Enter PostgreSQL database name [llhama]: " DB_NAME
            DB_NAME=${DB_NAME:-llhama}
            
            read -p "Enter PostgreSQL username [llhama_usr]: " DB_USER
            DB_USER=${DB_USER:-llhama_usr}
            
            read -s -p "Enter PostgreSQL password: " DB_PASSWORD
            echo
        fi
        
        # Apply settings to .env
        echo ""
        echo "Applying configuration to .env file..."
        
        sed -i "s|^HA_BASE_URL=.*|HA_BASE_URL=$HA_URL|" .env
        sed -i "s|^HA_TOKEN=.*|HA_TOKEN=$HA_TOKEN|" .env
        sed -i "s|^OLLAMA_IP=.*|OLLAMA_IP=$OLLAMA_SERVER|" .env
        sed -i "s|^ALLOWED_IP_PREFIXES=.*|ALLOWED_IP_PREFIXES=$ALLOWED_IPS|" .env
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
        sed -i "s|^DEFAULT_ADMIN_USERNAME=.*|DEFAULT_ADMIN_USERNAME=$ADMIN_USER|" .env
        sed -i "s|^DEFAULT_ADMIN_PASSWORD=.*|DEFAULT_ADMIN_PASSWORD=$ADMIN_PASS|" .env
        sed -i "s|^PG_HOST=.*|PG_HOST=$PG_HOST|" .env
        sed -i "s|^PG_PORT=.*|PG_PORT=$PG_PORT|" .env
        sed -i "s|^PG_DATABASE=.*|PG_DATABASE=$DB_NAME|" .env
        sed -i "s|^PG_USER=.*|PG_USER=$DB_USER|" .env
        sed -i "s|^PG_PASSWORD=.*|PG_PASSWORD=$DB_PASSWORD|" .env
        
        echo ""
        echo "Environment configuration complete!"
        echo "IMPORTANT: Review .env and configure your settings!"
        echo "NOTE: Change admin password after first login for security!"
    else
        echo "IMPORTANT: Edit .env and configure your settings before starting the system!"
    fi
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

# Optional: Create systemd service
echo ""
read -p "Would you like to create a systemd service to run Local_LLHAMA on boot? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    CURRENT_USER=$(whoami)
    WORKING_DIR=$(pwd)
    VENV_PYTHON="$WORKING_DIR/$VENV_NAME/bin/python"
    
    echo "Creating systemd service file..."
    SERVICE_FILE="/tmp/local-llhama.service"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Local LLHAMA - Local LLM Home Assistant
After=network.target postgresql.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$WORKING_DIR
Environment="PATH=$WORKING_DIR/$VENV_NAME/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PYTHON -m local_llhama.Run_System
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    echo "Installing systemd service (requires sudo)..."
    sudo cp "$SERVICE_FILE" /etc/systemd/system/local-llhama.service
    sudo systemctl daemon-reload
    
    read -p "Would you like to enable the service to start on boot? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl enable local-llhama.service
        echo "Service enabled. It will start automatically on boot."
    else
        echo "Service installed but not enabled. Enable it later with: sudo systemctl enable local-llhama.service"
    fi
    
    read -p "Would you like to start the service now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl start local-llhama.service
        if [ $? -eq 0 ]; then
            echo "Service started successfully."
            echo "Check status with: sudo systemctl status local-llhama"
        else
            echo "WARNING: Failed to start service. Check logs with: sudo journalctl -u local-llhama -n 50"
        fi
    fi
    
    echo ""
    echo "Service management commands:"
    echo "  Start:   sudo systemctl start local-llhama"
    echo "  Stop:    sudo systemctl stop local-llhama"
    echo "  Status:  sudo systemctl status local-llhama"
    echo "  Logs:    sudo journalctl -u local-llhama -f"
    echo "  Enable:  sudo systemctl enable local-llhama"
    echo "  Disable: sudo systemctl disable local-llhama"
    echo ""
fi

echo ""
echo "============================================"
echo "Installation complete!"
echo "============================================"
echo ""

# Offer to start the system immediately
read -p "Would you like to start Local_LLHAMA now and open the chat page in your browser? (takes ~40s to start) (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting Local_LLHAMA..."
    echo "NOTE: The system takes approximately 40 seconds to fully start up."
    echo "The browser will open automatically when ready."
    echo "Press Ctrl+C in the terminal to stop the system when done."
    echo ""
    sleep 2
    
    # Detect default port (5000 is typical for Flask)
    WEB_PORT=5000
    CHAT_URL="http://localhost:$WEB_PORT"
    
    # Create a startup script
    STARTUP_SCRIPT="/tmp/start_llhama_$$.sh"
    cat > "$STARTUP_SCRIPT" << 'STARTUP_EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_NAME="__VENV_NAME__"
CHAT_URL="__CHAT_URL__"

# Activate venv and start system
cd "__WORKING_DIR__" || exit 1
source "$VENV_NAME/bin/activate"

# Function to show progress bar
show_progress() {
    local duration=40
    local elapsed=0
    local bar_length=50
    
    echo ""
    echo "Waiting for system to start (40 seconds)..."
    
    while [ $elapsed -lt $duration ]; do
        # Calculate progress
        local progress=$((elapsed * 100 / duration))
        local filled=$((elapsed * bar_length / duration))
        local empty=$((bar_length - filled))
        
        # Build progress bar
        local bar="["
        for ((i=0; i<filled; i++)); do bar="${bar}#"; done
        for ((i=0; i<empty; i++)); do bar="${bar}-"; done
        bar="${bar}]"
        
        # Display progress
        printf "\r%s %d%% (%ds/%ds)" "$bar" "$progress" "$elapsed" "$duration"
        
        sleep 1
        elapsed=$((elapsed + 1))
    done
    
    printf "\r%s %d%% (%ds/%ds)\n" "[##################################################]" "100" "$duration" "$duration"
    echo "Opening browser..."
    echo ""
    echo "============================================"
    echo "Local_LLHAMA is ready!"
    echo "============================================"
    echo "Chat interface: $CHAT_URL"
    echo "Press Ctrl+C in this terminal to stop the system"
    echo "============================================"
    echo ""
}

# Open browser with progress bar (in background)
(show_progress && (xdg-open "$CHAT_URL" 2>/dev/null || sensible-browser "$CHAT_URL" 2>/dev/null || echo "Please open $CHAT_URL in your browser")) &

# Start the system
echo "Starting Local_LLHAMA..."
echo "Chat interface will be available at: $CHAT_URL"
echo "Press Ctrl+C to stop"
python -m local_llhama.Run_System
STARTUP_EOF
    
    # Replace placeholders
    sed -i "s|__VENV_NAME__|$VENV_NAME|g" "$STARTUP_SCRIPT"
    sed -i "s|__WORKING_DIR__|$(pwd)|g" "$STARTUP_SCRIPT"
    sed -i "s|__CHAT_URL__|$CHAT_URL|g" "$STARTUP_SCRIPT"
    
    chmod +x "$STARTUP_SCRIPT"
    # Disable trap before exec since installation was successful
    trap - EXIT
    exec bash "$STARTUP_SCRIPT"
else
    echo ""
    echo "NEXT STEPS:"
    echo ""
    echo "1. ACTIVATE ENVIRONMENT"
    echo "   source $VENV_NAME/bin/activate"
    echo ""
    echo "2. START THE SYSTEM"
    echo "   python -m local_llhama.Run_System"
    echo ""
    echo "3. ACCESS WEB INTERFACE"
    echo "   Open your browser to: http://localhost:5000"
    echo ""
    echo "Or run this single command to start everything:"
    echo "   source $VENV_NAME/bin/activate && python -m local_llhama.Run_System"
    echo ""
    echo "For detailed documentation, see README.md and DATABASE_SETUP.md"
    echo "============================================"
    
    # Disable trap since installation completed successfully
    trap - EXIT
    echo "For detailed documentation, see README.md and DATABASE_SETUP.md"
    echo "============================================"
fi
