# Local_LLHAMA Modular Installer

This directory contains the modular installer for Local_LLHAMA, broken down into manageable components.

## Structure

```
install/
├── install.sh              # Main orchestrator script
└── lib/                    # Library modules
    ├── cleanup.sh          # Cleanup and error handling
    ├── gpu_detection.sh    # GPU detection and preset selection
    ├── python_setup.sh     # Python 3.11 installation
    ├── postgres_setup.sh   # PostgreSQL and pgvector setup
    ├── venv_setup.sh       # Virtual environment creation
    ├── pytorch_setup.sh    # PyTorch installation
    ├── ollama_setup.sh     # Ollama installation
    ├── database_wizard.sh  # Database configuration wizard
    ├── env_wizard.sh       # Environment configuration wizard
    └── service_setup.sh    # Systemd service setup
```

## Usage

Run the installer from the repository root:

```bash
bash install/install.sh
```

Or make it executable and run directly:

```bash
chmod +x install/install.sh
./install/install.sh
```

## Module Overview

### Core Modules

- **cleanup.sh** - Handles cleanup on installation failure, tracks what was installed
- **gpu_detection.sh** - Detects GPU type, VRAM, and offers appropriate presets
- **python_setup.sh** - Installs Python 3.11 via deadsnakes PPA if needed
- **postgres_setup.sh** - Installs PostgreSQL 16 and pgvector extension
- **venv_setup.sh** - Creates virtual environment and installs Python packages
- **pytorch_setup.sh** - Installs appropriate PyTorch version based on GPU
- **ollama_setup.sh** - Installs Ollama via snap or official script

### Configuration Modules

- **database_wizard.sh** - Interactive PostgreSQL database setup
- **env_wizard.sh** - Interactive .env file configuration
- **service_setup.sh** - Systemd service creation and startup options

## Features

- **Modular Design**: Each component in its own file for easy maintenance
- **Error Handling**: Automatic cleanup on failure with user confirmation
- **State Tracking**: Tracks installations for proper cleanup
- **Reusable**: Functions can be called independently or as part of the main flow

## Maintenance

To modify a specific feature, edit the corresponding module in `lib/`. The main `install.sh` script coordinates the overall installation flow.
