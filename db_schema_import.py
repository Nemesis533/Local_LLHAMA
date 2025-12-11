#!/usr/bin/env python3
"""
Database Schema Import Script

Recreates PostgreSQL database tables from JSON schema export.
Clears all data except restores admin user(s) from backup.

Usage:
    python3 db_schema_import.py [schema_file]

Default schema file: db_schema.json

The script will:
1. Connect to PostgreSQL using credentials from .env
2. Drop all existing tables (WARNING: DATA LOSS)
3. Recreate tables from schema
4. Restore admin user(s) from backup
"""

import json
import os
import sys
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


def generate_create_table_sql(table_name, schema):
    """Generate CREATE TABLE statement from schema."""
    columns = schema.get('columns', [])
    constraints = schema.get('constraints', [])
    
    col_defs = []
    
    # Add column definitions
    for col in columns:
        col_def = f"{col['column_name']} {col['data_type']}"
        
        # Add constraints
        if col['column_default']:
            col_def += f" DEFAULT {col['column_default']}"
        
        if col['is_nullable'] == 'NO':
            col_def += " NOT NULL"
        else:
            col_def += " NULL"
        
        col_defs.append(col_def)
    
    # Add primary key constraints
    for constraint in constraints:
        if constraint['constraint_type'] == 'PRIMARY KEY':
            pk_col = constraint['column_name']
            col_defs.append(f"PRIMARY KEY ({pk_col})")
            break
    
    # Add unique constraints
    for constraint in constraints:
        if constraint['constraint_type'] == 'UNIQUE':
            unique_col = constraint['column_name']
            col_defs.append(f"UNIQUE ({unique_col})")
    
    # Add foreign key constraints
    for constraint in constraints:
        if constraint['constraint_type'] == 'FOREIGN KEY':
            # Try to extract from constraint info
            pass  # Will be handled by existing constraints in DB
    
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
    sql += ",\n".join(f"  {col}" for col in col_defs)
    sql += "\n);"
    
    return sql


def recreate_tables(conn, schema_data):
    """Recreate all tables from schema."""
    schema = schema_data['schema']
    
    with conn.cursor() as cur:
        # Drop all tables first (in reverse order for dependencies)
        print("\nDropping existing tables...")
        cur.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename DESC
        """)
        tables_to_drop = [row[0] for row in cur.fetchall()]
        
        for table in tables_to_drop:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                print(f"  ✓ Dropped {table}")
            except psycopg2.Error as e:
                print(f"  ✗ Failed to drop {table}: {e}")
        
        conn.commit()
        
        # Recreate tables
        print("\nRecreating tables...")
        
        # Define table creation order (for dependencies)
        table_order = ['users', 'conversations', 'messages', 'message_embeddings', 
                       'events', 'calendar_events', 'audit_logs']
        
        # Add any tables not in the predefined order
        all_tables = list(schema.keys())
        for table in all_tables:
            if table not in table_order:
                table_order.append(table)
        
        for table_name in table_order:
            if table_name not in schema:
                continue
                
            try:
                sql = generate_create_table_sql(table_name, schema[table_name])
                cur.execute(sql)
                print(f"  ✓ Created {table_name}")
            except psycopg2.Error as e:
                print(f"  ✗ Failed to create {table_name}: {e}")
        
        conn.commit()


def restore_admin_users(conn, admin_users):
    """Restore admin user(s) to the database."""
    if not admin_users:
        print("\nNo admin users to restore")
        return
    
    print(f"\nRestoring {len(admin_users)} admin user(s)...")
    
    with conn.cursor() as cur:
        for admin in admin_users:
            try:
                cur.execute("""
                    INSERT INTO users 
                    (username, password_hash, created_at, is_admin, is_active, 
                     can_access_dashboard, can_access_chat, must_change_password)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    admin['username'],
                    admin['password_hash'],
                    admin.get('created_at'),
                    admin.get('is_admin', True),
                    admin.get('is_active', True),
                    admin.get('can_access_dashboard', True),
                    admin.get('can_access_chat', True),
                    admin.get('must_change_password', False)
                ))
                print(f"  ✓ Restored admin user: {admin['username']}")
            except psycopg2.Error as e:
                print(f"  ✗ Failed to restore {admin['username']}: {e}")
        
        conn.commit()


def main():
    """Main import function."""
    schema_file = sys.argv[1] if len(sys.argv) > 1 else 'db_schema.json'
    
    print("=" * 60)
    print("Database Schema Import")
    print("=" * 60)
    print(f"\nUsing schema file: {schema_file}")
    
    # Check if schema file exists
    if not os.path.exists(schema_file):
        print(f"ERROR: Schema file '{schema_file}' not found")
        print("Run db_schema_export.py first to create it")
        sys.exit(1)
    
    # Load schema
    print("Loading schema...")
    try:
        with open(schema_file, 'r') as f:
            schema_data = json.load(f)
        print("✓ Schema loaded")
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {schema_file}: {e}")
        sys.exit(1)
    
    # Load environment
    env_vars = load_env()
    
    if not env_vars['password']:
        print("ERROR: PG_PASSWORD not found in .env file")
        sys.exit(1)
    
    print(f"Connecting to PostgreSQL at {env_vars['host']}:{env_vars['port']}/{env_vars['database']}...")
    
    # Confirm before proceeding
    print("\n" + "!" * 60)
    print("WARNING: This will DELETE ALL DATA and recreate tables!")
    print("!" * 60)
    response = input("\nType 'yes' to proceed: ").strip().lower()
    
    if response != 'yes':
        print("Cancelled.")
        sys.exit(0)
    
    try:
        conn = psycopg2.connect(
            host=env_vars['host'],
            port=env_vars['port'],
            user=env_vars['user'],
            password=env_vars['password'],
            database=env_vars['database']
        )
        print("✓ Connected successfully\n")
        
        # Recreate tables
        recreate_tables(conn, schema_data)
        
        # Restore admin users
        admin_users = schema_data.get('admin_users', [])
        restore_admin_users(conn, admin_users)
        
        print("\n" + "=" * 60)
        print("✓ Database schema recreation complete!")
        print("=" * 60)
        print(f"\nRestored {len(admin_users)} admin user(s)")
        if admin_users:
            print(f"Admin usernames: {', '.join([a['username'] for a in admin_users])}")
        
        conn.close()
        
    except psycopg2.Error as e:
        print(f"\n✗ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
