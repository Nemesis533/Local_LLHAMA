#!/bin/bash

# ============================================================================
# Cleanup Module
# Handles cleanup on installation failure
# ============================================================================

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
