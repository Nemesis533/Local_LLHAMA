#!/bin/bash

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
# Install required Python packages
echo "Installing required Python packages..."
pip install --upgrade \
requests \
openai-whisper \
flask \
flask_socketio \
openwakeword \
pyaudio \
sounddevice \
pygame \
piper-tts \

# Install required Python packages
echo "Installing required packages: torch, transformers, accelerate, flask, flask-cors, psutil, requests, TTS"
pip install torch transformers accelerate flask flask-cors psutil requests TTS

echo "All done!"
echo "To activate your virtual environment later, run:"
echo "source $VENV_NAME/bin/activate"
