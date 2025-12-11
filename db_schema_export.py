#!/usr/bin/env python3
"""
Database Schema Export Script

Exports the current PostgreSQL database schema to JSON format, preserving admin user data.
Can be used to recreate the database structure cleanly while keeping essential user data.

Usage:
    python3 db_schema_export.py

The script will:
1. Connect to PostgreSQL using credentials from .env
2. Extract all table schemas and constraints
3. Backup the admin user(s)
4. Save everything to db_schema.json
"""

import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2 import extras


def load_env():
    """Load environment variables from .env file."""
    load_dotenv()
    return {
        'host': os.getenv("PG_HOST", "localhost"),
        'port': int(os.getenv("PG_PORT", 5432)),
        'user': os.getenv("PG_USER", "llhama_usr"),
        'password': os.getenv("PG_PASSWORD"),
        'database': os.getenv("PG_DATABASE", "llhama")
    }


def get_table_schema(conn, table_name):
    """Extract schema for a specific table."""
    with conn.cursor(cursor_factory=extras.DictCursor) as cur:
        # Get column definitions
        cur.execute(f"""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = cur.fetchall()
        
        # Get constraints (primary key, unique, foreign key)
        cur.execute(f"""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = %s
        """, (table_name,))
        constraints = cur.fetchall()
        
        # Get indexes
        cur.execute(f"""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s
        """, (table_name,))
        indexes = cur.fetchall()
        
        return {
            'columns': [dict(col) for col in columns],
            'constraints': [dict(c) for c in constraints],
            'indexes': [dict(idx) for idx in indexes]
        }


def get_admin_users(conn):
    """Get all admin users from the database."""
    with conn.cursor(cursor_factory=extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, username, password_hash, created_at, is_admin, 
                   is_active, can_access_dashboard, can_access_chat, must_change_password
            FROM users
            WHERE is_admin = true
            ORDER BY created_at ASC
        """)
        admins = cur.fetchall()
        return [dict(admin) for admin in admins]


def export_schema(conn):
    """Export complete database schema."""
    with conn.cursor() as cur:
        # Get all table names
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]
    
    schema = {}
    for table_name in tables:
        schema[table_name] = get_table_schema(conn, table_name)
    
    return schema


def main():
    """Main export function."""
    print("=" * 60)
    print("Database Schema Export")
    print("=" * 60)
    
    # Load environment
    env_vars = load_env()
    
    if not env_vars['password']:
        print("ERROR: PG_PASSWORD not found in .env file")
        sys.exit(1)
    
    print(f"Connecting to PostgreSQL at {env_vars['host']}:{env_vars['port']}/{env_vars['database']}...")
    
    try:
        conn = psycopg2.connect(
            host=env_vars['host'],
            port=env_vars['port'],
            user=env_vars['user'],
            password=env_vars['password'],
            database=env_vars['database']
        )
        print("✓ Connected successfully")
        
        # Export schema
        print("\nExporting database schema...")
        schema = export_schema(conn)
        print(f"✓ Exported {len(schema)} tables")
        
        # Get admin users
        print("Backing up admin user(s)...")
        admins = get_admin_users(conn)
        print(f"✓ Found {len(admins)} admin user(s)")
        
        # Convert datetime objects to strings
        for admin in admins:
            if 'created_at' in admin and admin['created_at']:
                admin['created_at'] = admin['created_at'].isoformat()
        
        # Create export document
        export_data = {
            'export_date': datetime.now().isoformat(),
            'database': env_vars['database'],
            'version': '1.0',
            'schema': schema,
            'admin_users': admins,
            'notes': 'This file contains the database schema and admin user(s). Use db_schema_import.py to restore.'
        }
        
        # Save to file
        output_file = 'db_schema.json'
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"\n✓ Schema exported to {output_file}")
        print(f"\nSummary:")
        print(f"  - Tables: {len(schema)}")
        print(f"  - Admin users backed up: {len(admins)}")
        if admins:
            print(f"  - Admin usernames: {', '.join([a['username'] for a in admins])}")
        
        conn.close()
        
    except psycopg2.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
