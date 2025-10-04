"""
@file run_dev.py
@brief Development entry point for running Local LLHAMA via Run_System.

This script ensures the project root is in sys.path and invokes
the Run_System module directly for development.

Usage:
    python run_dev.py
"""

import os
import sys
import runpy

# === Path Setup ===
# Add the project root (one level up from dev/) to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Debugging info
print("sys.path:", sys.path)
print("Project root contents:", os.listdir(project_root))

# === Launch the target module ===
if __name__ == "__main__":
    print("Starting Local LLHAMA via Run_System (development mode)...")
    runpy.run_module("local_llhama.Run_System", run_name="__main__")
