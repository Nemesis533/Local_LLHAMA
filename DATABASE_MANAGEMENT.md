# Database Schema Management

This directory contains scripts to manage the Local LLHAMA database schema and backup/restore functionality.

## Files

- **db_schema_export.py** - Exports the current database schema to JSON format
- **db_schema_import.py** - Restores database schema from JSON (clears all data except admin users)
- **db_schema.json** - The exported schema file (created by export script)

## Quick Start

### 1. Export Current Schema

```bash
python3 db_schema_export.py
```

This will:
- Connect to PostgreSQL using credentials from `.env`
- Extract all table schemas, columns, constraints, and indexes
- Backup all admin user(s) with their credentials
- Save everything to `db_schema.json`

**Output:**
```
✓ Exported 7 tables
✓ Found 1 admin user(s)
✓ Schema exported to db_schema.json
```

### 2. Restore Schema (Fresh Database)

```bash
python3 db_schema_import.py
```

This will:
- Load the schema from `db_schema.json`
- **WARNING:** Drop all existing tables (DATA LOSS)
- Recreate all tables from schema
- Restore the admin user(s)

**Confirmation Required:**
```
WARNING: This will DELETE ALL DATA and recreate tables!
Type 'yes' to proceed:
```

To use a different schema file:
```bash
python3 db_schema_import.py path/to/schema.json
```

## Environment Variables Required

The scripts read from `.env`:

```
PG_HOST=localhost
PG_PORT=5432
PG_USER=llhama_usr
PG_PASSWORD=your_password
PG_DATABASE=llhama
```

If these are not set, defaults are used (localhost:5432, llhama_usr, llhama).

## What Gets Backed Up

### Schema
- Table definitions (columns, data types, defaults)
- Constraints (primary keys, unique constraints, foreign keys)
- Indexes

### Data
- All admin users (with password hashes)
- Admin user permissions and settings
- Account creation timestamps

### What Gets Deleted
- All regular users (non-admin)
- All conversations and messages
- All events and calendar entries
- All audit logs
- All other application data

## Common Workflows

### Scenario 1: Clean Database Reset (Keep Admin)

```bash
# Step 1: Export current schema (with admin user)
python3 db_schema_export.py

# Step 2: Restore clean database (drops everything except admin)
python3 db_schema_import.py
```

### Scenario 2: Migrate Database

```bash
# On source system:
python3 db_schema_export.py
# Copy db_schema.json to new system

# On target system:
python3 db_schema_import.py db_schema.json
```

### Scenario 3: Multiple Database Versions

```bash
# Keep different schema versions
cp db_schema.json db_schema_backup_2025-12-07.json
```

Then restore any version:
```bash
python3 db_schema_import.py db_schema_backup_2025-12-07.json
```

## Integration with Installation Script

The `local_LLM_installer.sh` can be extended to automatically initialize the database:

```bash
# After installing dependencies, initialize database:
if [ -f "db_schema.json" ]; then
    echo "Initializing database schema..."
    python3 db_schema_import.py
fi
```

## JSON Schema Format

The exported `db_schema.json` has this structure:

```json
{
  "export_date": "2025-12-07T12:00:00.000000",
  "database": "llhama",
  "version": "1.0",
  "schema": {
    "users": {
      "columns": [...],
      "constraints": [...],
      "indexes": [...]
    },
    "conversations": {...},
    ...
  },
  "admin_users": [
    {
      "username": "admin",
      "password_hash": "...",
      "created_at": "2025-01-01T00:00:00",
      ...
    }
  ]
}
```

## Troubleshooting

### Connection Failed

```
ERROR: PostgreSQL could not be connected
```

Check:
1. PostgreSQL is running: `sudo systemctl status postgresql`
2. Credentials in `.env` are correct
3. Database exists: `psql -h localhost -U llhama_usr -l`

### Permission Denied

```
ERROR: permission denied for schema public
```

Make sure the PostgreSQL user has permissions:
```bash
sudo -u postgres psql -c "GRANT ALL ON SCHEMA public TO llhama_usr;"
```

### JSON Parse Error

```
ERROR: Invalid JSON in db_schema.json
```

Check if file is corrupted. Regenerate with `db_schema_export.py`

## Safety Notes

⚠️ **WARNING:** The import script is destructive!
- It will DROP ALL TABLES (with CASCADE)
- All non-admin user data will be deleted
- This cannot be undone

Always backup `db_schema.json` before running import!

## Support

For issues, check:
1. Database connectivity
2. `.env` file configuration
3. PostgreSQL server status
4. User permissions
