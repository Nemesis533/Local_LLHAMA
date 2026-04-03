#!/bin/bash

# ============================================================================
# PostgreSQL Setup Module
# Handles PostgreSQL 16 and pgvector extension installation
# ============================================================================

setup_postgres() {
    local install_postgres="$1"
    local install_pgvector="$2"
    
    # Handle PostgreSQL auto-install or validate existing installation
    if [[ "$install_postgres" == "yes" ]]; then
        echo "Attempting to install PostgreSQL 16 (requires sudo)..."
        sudo apt-get update
        sudo apt-get install -y postgresql-16 postgresql-client-16 postgresql-contrib
        
        if [ $? -ne 0 ]; then
            echo "WARNING: Automatic installation of PostgreSQL 16 failed."
            echo "You can install it manually or re-run the installer after installing PostgreSQL."
        else
            echo "PostgreSQL 16 installation attempted (check with: psql --version)."
            INSTALLED_POSTGRES="yes"
            export INSTALLED_POSTGRES
            
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
    
    # Verify PostgreSQL presence
    if ! command -v psql &> /dev/null; then
        echo "ERROR: PostgreSQL could not be found." 
        echo "If you declined auto-install, please install PostgreSQL 16 before running this script."
        echo "Install with: sudo apt-get install postgresql-16 postgresql-contrib"
        exit 1
    else
        PGVERSION=$(psql --version | awk '{print $NF}' | cut -d. -f1)
        echo "PostgreSQL $PGVERSION found."
        export PGVERSION
    fi
    
    # Handle pgvector installation if requested
    if [[ "$install_pgvector" == "yes" ]]; then
        install_pgvector_extension "$PGVERSION"
    fi
}

install_pgvector_extension() {
    local pgversion="$1"
    
    echo "Attempting to install pgvector for PostgreSQL $pgversion..."
    
    # Try apt package first (package names may vary by distribution)
    sudo apt-get update
    if sudo apt-get install -y "postgresql-$pgversion-pgvector" 2>/dev/null; then
        echo "pgvector package installed via apt (postgresql-$pgversion-pgvector)."
        INSTALLED_PGVECTOR="yes"
        export INSTALLED_PGVECTOR
    else
        echo "pgvector apt package not available or failed; attempting to build and install from source."
        sudo apt-get install -y git make build-essential "postgresql-server-dev-$pgversion"
        
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
                        export INSTALLED_PGVECTOR
                    fi
                fi
                popd >/dev/null
            fi
        fi
    fi
    
    echo "Note: You still need to create the extension inside your database with: SQL \"CREATE EXTENSION IF NOT EXISTS vector;\""
}
