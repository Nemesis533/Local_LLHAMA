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
# Install required Python packages
echo "Installing required Python packages..."
pip install --upgrade \
requests \
openai-whisper \
flask \
flask-socketio \
flask-login \
openwakeword \
pyaudio \
sounddevice \
pygame \
piper-tts \
torch \
transformers \
accelerate \
flask-cors \
psutil \
TTS \
librosa \
wave \
python-dotenv \
psycopg2-binary \
asyncpg

echo "All done!"
echo "To activate your virtual environment later, run:"
echo "source $VENV_NAME/bin/activate"
