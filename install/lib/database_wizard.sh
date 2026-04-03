#!/bin/bash

# ============================================================================
# Database Wizard Module
# Interactive PostgreSQL database configuration
# ============================================================================

run_database_wizard() {
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
            configure_database "$DB_NAME" "$DB_USER" "$DB_PASSWORD"
        fi
    fi
}

configure_database() {
    local db_name="$1"
    local db_user="$2"
    local db_password="$3"
    
    echo ""
    echo "Creating database and user..."
    
    # Create database
    sudo -u postgres psql -c "CREATE DATABASE $db_name;" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Database '$db_name' created successfully."
        CREATED_DATABASE="$db_name"
        export CREATED_DATABASE
    else
        echo "NOTE: Database '$db_name' may already exist or creation failed."
    fi
    
    # Create user with password
    sudo -u postgres psql -c "CREATE USER $db_user WITH PASSWORD '$db_password';" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "User '$db_user' created successfully."
        CREATED_DB_USER="$db_user"
        export CREATED_DB_USER
    else
        echo "NOTE: User '$db_user' may already exist. Updating password..."
        sudo -u postgres psql -c "ALTER USER $db_user WITH PASSWORD '$db_password';"
    fi
    
    # Grant privileges
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $db_name TO $db_user;"
    echo "Privileges granted to '$db_user' on database '$db_name'."
    
    # Grant schema privileges (PostgreSQL 15+)
    sudo -u postgres psql -d "$db_name" -c "GRANT ALL ON SCHEMA public TO $db_user;" 2>/dev/null
    
    # Enable pgvector extension if available
    echo "Attempting to enable pgvector extension..."
    sudo -u postgres psql -d "$db_name" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null
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
            PGPASSWORD="$db_password" psql -h localhost -U "$db_user" -d "$db_name" -f init_database.sql
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
            sed -i "s/^PG_DATABASE=.*/PG_DATABASE=$db_name/" .env
            sed -i "s/^PG_USER=.*/PG_USER=$db_user/" .env
            sed -i "s/^PG_PASSWORD=.*/PG_PASSWORD=$db_password/" .env
            
            echo ".env file updated with database credentials."
        fi
    fi
    
    echo ""
    echo "Database configuration complete!"
    echo "Database: $db_name"
    echo "User: $db_user"
    echo "Connection string: postgresql://$db_user:****@localhost:5432/$db_name"
    
    # Export for use in env_wizard
    export DB_NAME="$db_name"
    export DB_USER="$db_user"
    export DB_PASSWORD="$db_password"
}
