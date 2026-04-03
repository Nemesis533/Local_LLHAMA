#!/bin/bash

# ============================================================================
# Environment Wizard Module
# Interactive .env file configuration
# ============================================================================

run_env_wizard() {
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
            configure_env_file
        else
            echo "IMPORTANT: Edit .env and configure your settings before starting the system!"
        fi
    fi
}

configure_env_file() {
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
}
