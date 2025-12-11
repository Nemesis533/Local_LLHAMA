# Database Setup Guide

Local_LLHAMA uses PostgreSQL for storing user accounts, chat conversations, calendar events, and message embeddings for semantic search.

## Prerequisites

1. **PostgreSQL 14+** must be installed
2. **pgvector extension** for semantic search (optional but recommended)
3. Python environment with required packages (psycopg2, asyncpg, python-dotenv)

## Quick Setup

The easiest way to initialize the database:

```bash
# 1. Create the database (if it doesn't exist)
createdb -U postgres llhama

# 2. Create the user and grant permissions (as postgres superuser)
psql -U postgres -d llhama -c "CREATE USER llhama_usr WITH PASSWORD 'your_secure_password';"
psql -U postgres -d llhama -f setup_permissions.sql

# 3. Run the initialization script
python3 setup_database.py
```

This will create all tables and insert a default admin user.

## Manual Setup

If you prefer to run the SQL directly:

```bash
psql -U llhama_usr -d llhama -f init_database.sql
```

## Database Schema

### Tables

#### `users`
Stores user accounts with authentication and role-based permissions.
- `id`: Primary key (auto-increment)
- `username`: Unique username
- `password_hash`: Bcrypt password hash
- `is_admin`: Admin privileges flag
- `is_active`: Account active status
- `can_access_dashboard`: Dashboard access permission
- `can_access_chat`: Chat interface access permission
- `must_change_password`: Force password change on next login

#### `conversations`
Stores chat conversation threads (one per user).
- `id`: UUID primary key
- `user_id`: Foreign key to users
- `title`: Conversation title (optional)
- `created_at`: Creation timestamp

#### `messages`
Individual messages within conversations.
- `id`: UUID primary key
- `conversation_id`: Foreign key to conversations
- `role`: Message role ('user', 'assistant', 'system')
- `content`: Message text
- `created_at`: Creation timestamp

#### `message_embeddings`
Vector embeddings for semantic search (requires pgvector).
- `message_id`: Foreign key to messages
- `vector`: 768-dimensional vector embedding

#### `events`
Calendar events, reminders, and tasks.
- `id`: Primary key (auto-increment)
- `user_id`: Foreign key to users
- `title`: Event title
- `description`: Event description
- `event_type`: 'reminder', 'task', or 'event'
- `due_datetime`: When the event is due
- `repeat_pattern`: 'none', 'daily', 'weekly', 'monthly', 'yearly'
- `is_completed`: Completion status
- `is_active`: Active status
- `notification_minutes_before`: Notification timing

## Default Admin User

After initialization, a default admin account is created:
- **Username**: `admin`
- **Password**: `admin123`

⚠️ **IMPORTANT**: Change this password immediately after first login!

## Environment Configuration

Ensure your `.env` file contains the PostgreSQL credentials:

```env
PG_HOST=localhost
PG_PORT=5432
PG_USER=llhama_usr
PG_PASSWORD=your_secure_password
PG_DATABASE=llhama
```

## Reset Database

To completely reset the database (⚠️ **WARNING: ALL DATA WILL BE LOST**):

```bash
python3 setup_database.py --reset
```

Or manually:
```bash
psql -U llhama_usr -d llhama -f init_database.sql
```

The SQL script automatically drops existing tables before recreating them.

## Backup and Restore

### Export Schema and Admin User

```bash
python3 db_schema_export.py
```

This creates `db_schema.json` with:
- Complete table schema
- All constraints and indexes
- Admin user backup (with password hash)

### Restore from Schema

```bash
python3 db_schema_import.py db_schema.json
```

This will:
1. Drop all existing tables
2. Recreate tables from schema
3. Restore admin user(s)

⚠️ **WARNING**: This destroys all existing data!

## Troubleshooting

### Permission Denied Errors

If you get permission errors, run the permissions script:

```bash
psql -U postgres -d llhama -f setup_permissions.sql
```

### pgvector Extension Missing

If message embeddings fail, install pgvector:

```bash
# Ubuntu/Debian
sudo apt install postgresql-14-pgvector

# Or compile from source
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

Then enable it:
```sql
CREATE EXTENSION vector;
```

### Connection Issues

Check if PostgreSQL is running:
```bash
sudo systemctl status postgresql
```

Test connection:
```bash
psql -U llhama_usr -d llhama -c "SELECT version();"
```

## Migration from SQLite (Future)

If you were previously using SQLite for events, a migration script will be provided to import existing data into PostgreSQL.

## Files Reference

- `init_database.sql` - Main SQL schema (version controlled)
- `setup_database.py` - Python setup script with validation
- `setup_permissions.sql` - PostgreSQL permissions configuration
- `db_schema_export.py` - Export current schema to JSON
- `db_schema_import.py` - Import schema from JSON
- `db_schema.json` - Exported schema (not version controlled)
