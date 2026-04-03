#!/bin/bash

# ============================================================================
# Service Setup Module
# Handles systemd service creation and management
# ============================================================================

create_version_info() {
    local venv_name="$1"
    
    echo "Creating version info file..."
    cat > "$venv_name/LOCAL_LLHAMA_VERSION.txt" << EOF
Local_LLHAMA Version Information
================================

Version: 0.7 Alpha
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
    
    echo "Version info created at: $venv_name/LOCAL_LLHAMA_VERSION.txt"
}

setup_systemd_service() {
    local venv_name="$1"
    
    echo ""
    read -p "Would you like to create a systemd service to run Local_LLHAMA on boot? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        CURRENT_USER=$(whoami)
        WORKING_DIR=$(pwd)
        VENV_PYTHON="$WORKING_DIR/$venv_name/bin/python"
        
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
Environment="PATH=$WORKING_DIR/$venv_name/bin:/usr/local/bin:/usr/bin:/bin"
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
}

start_system_prompt() {
    local venv_name="$1"
    
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
        sed -i "s|__VENV_NAME__|$venv_name|g" "$STARTUP_SCRIPT"
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
        echo "   source $venv_name/bin/activate"
        echo ""
        echo "2. START THE SYSTEM"
        echo "   python -m local_llhama.Run_System"
        echo ""
        echo "3. ACCESS WEB INTERFACE"
        echo "   Open your browser to: http://localhost:5000"
        echo ""
        echo "Or run this single command to start everything:"
        echo "   source $venv_name/bin/activate && python -m local_llhama.Run_System"
        echo ""
        echo "For detailed documentation, see README.md and DATABASE_SETUP.md"
        echo "============================================"
        
        # Disable trap since installation completed successfully
        trap - EXIT
    fi
}
