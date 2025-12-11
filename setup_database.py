#!/usr/bin/env python3
"""
Database Setup Script

Initializes the PostgreSQL database for Local_LLHAMA using the SQL schema.
This script can be run during initial setup or to reset the database.

Usage:
    python3 setup_database.py [--reset]
    
Options:
    --reset     Drop all existing tables and recreate (WARNING: DATA LOSS!)

Requirements:
    - PostgreSQL must be installed and running
    - .env file must exist with PG_* credentials
    - Database must already be created (e.g., createdb llhama)
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env file."""
    load_dotenv()
    return {
        "host": os.getenv("PG_HOST", "localhost"),
        "port": int(os.getenv("PG_PORT", 5432)),
        "user": os.getenv("PG_USER", "llhama_usr"),
        "password": os.getenv("PG_PASSWORD"),
        "database": os.getenv("PG_DATABASE", "llhama"),
    }


def check_postgres_connection(env_vars):
    """Test PostgreSQL connection."""
    try:
        # Use pg_isready to check if server is running
        result = subprocess.run(
            ["pg_isready", "-h", env_vars["host"], "-p", str(env_vars["port"])],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"✗ PostgreSQL server is not ready: {result.stderr}")
            return False
        
        print(f"✓ PostgreSQL server is running at {env_vars['host']}:{env_vars['port']}")
        return True
        
    except FileNotFoundError:
        print("✗ pg_isready command not found. Is PostgreSQL installed?")
        return False


def check_database_exists(env_vars):
    """Check if the database exists."""
    try:
        result = subprocess.run(
            [
                "psql",
                "-h", env_vars["host"],
                "-p", str(env_vars["port"]),
                "-U", env_vars["user"],
                "-lqt"
            ],
            env={**os.environ, "PGPASSWORD": env_vars["password"]},
            capture_output=True,
            text=True,
        )
        
        databases = [line.split("|")[0].strip() for line in result.stdout.split("\n")]
        exists = env_vars["database"] in databases
        
        if exists:
            print(f"✓ Database '{env_vars['database']}' exists")
        else:
            print(f"✗ Database '{env_vars['database']}' does not exist")
            print(f"\nTo create it, run:")
            print(f"  createdb -h {env_vars['host']} -p {env_vars['port']} -U {env_vars['user']} {env_vars['database']}")
        
        return exists
        
    except Exception as e:
        print(f"✗ Error checking database: {e}")
        return False


def run_sql_file(env_vars, sql_file):
    """Execute SQL file using psql."""
    try:
        print(f"\nExecuting {sql_file}...")
        result = subprocess.run(
            [
                "psql",
                "-h", env_vars["host"],
                "-p", str(env_vars["port"]),
                "-U", env_vars["user"],
                "-d", env_vars["database"],
                "-f", sql_file,
            ],
            env={**os.environ, "PGPASSWORD": env_vars["password"]},
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print(f"✗ Error executing SQL file:")
            print(result.stderr)
            return False
        
        print(result.stdout)
        return True
        
    except Exception as e:
        print(f"✗ Error running SQL file: {e}")
        return False


def main():
    """Main setup function."""
    print("=" * 60)
    print("Local_LLHAMA Database Setup")
    print("=" * 60)
    
    # Check for reset flag
    reset_mode = "--reset" in sys.argv
    if reset_mode:
        print("\n⚠️  RESET MODE: All existing data will be deleted!")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Setup cancelled.")
            sys.exit(0)
    
    # Load environment variables
    print("\nLoading configuration from .env...")
    env_vars = load_env()
    
    if not env_vars["password"]:
        print("✗ PG_PASSWORD not found in .env file")
        sys.exit(1)
    
    print(f"✓ Configuration loaded")
    print(f"  Database: {env_vars['database']}")
    print(f"  User: {env_vars['user']}")
    print(f"  Host: {env_vars['host']}:{env_vars['port']}")
    
    # Check PostgreSQL connection
    print("\nChecking PostgreSQL server...")
    if not check_postgres_connection(env_vars):
        sys.exit(1)
    
    # Check if database exists
    print("\nChecking database...")
    if not check_database_exists(env_vars):
        sys.exit(1)
    
    # Find SQL initialization file
    sql_file = Path(__file__).parent / "init_database.sql"
    if not sql_file.exists():
        print(f"\n✗ SQL file not found: {sql_file}")
        sys.exit(1)
    
    print(f"\n✓ Found initialization script: {sql_file.name}")
    
    # Run SQL initialization
    print("\nInitializing database schema...")
    if not run_sql_file(env_vars, str(sql_file)):
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ Database setup complete!")
    print("=" * 60)
    print("\nDefault admin credentials:")
    print("  Username: admin")
    print("  Password: admin123")
    print("\n⚠️  IMPORTANT: Change the admin password after first login!")
    print("=" * 60)


if __name__ == "__main__":
    main()
