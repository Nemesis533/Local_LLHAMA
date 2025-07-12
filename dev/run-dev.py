"""
@file dev_entrypoint.py
@brief Development entry point for running Local LLHAMA directly from source.

This script sets up the Python path to include the project root, then
invokes the main entry function from the `local_llhama` package.

Usage:
    python dev_entrypoint.py
"""

import os
import sys

# === Path Setup ===

# Add the Local_LLHAMA project root to sys.path for local imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# === Import Main App Entrypoint ===
from local_llhama import main as run_main

def main():
    """
    @brief Launch Local LLHAMA using local source directory for development.

    Sets the base path explicitly so config files and assets are located properly
    when running from a dev environment.
    """
    print("Starting Local LLHAMA in development mode...")  
    
    # Determine the full path to the local_llhama directory
    project_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0]))),
        "local_llhama"
    )

    # Start the main application logic with the project root path
    run_main(project_root)

if __name__ == "__main__":
    main()
