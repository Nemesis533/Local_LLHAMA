#!/usr/bin/env python3
"""
Database Management Script for Local LLHAMA

Provides options to:
- View database statistics
- Clean/delete data from the PostgreSQL database
- Backup database to SQL file
- Restore database from SQL file
- Initialize/reset database structure
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Database configuration - will be loaded from environment/config
DB_CONFIG = {
    "host": "localhost",
    "user": "your_user",  # Will be loaded from config
    "password": "your_password",  # Will be loaded from config
    "dbname": "local_llhama",
    "port": 5432,
}


def load_db_config():
    """Load database configuration from environment or config files."""
    try:
        # Try to load from setup_database.py if it exists
        try:
            from setup_database import get_db_config

            config = get_db_config()
            DB_CONFIG.update(config)
            return True
        except ImportError:
            pass

        # Try to load from .env file
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key == "DB_HOST":
                            DB_CONFIG["host"] = value
                        elif key == "DB_USER":
                            DB_CONFIG["user"] = value
                        elif key == "DB_PASSWORD":
                            DB_CONFIG["password"] = value
                        elif key == "DB_NAME":
                            DB_CONFIG["dbname"] = value
                        elif key == "DB_PORT":
                            DB_CONFIG["port"] = int(value)
            return True
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
        return False


class DBManager:
    """Database management utility for Local LLHAMA."""

    def __init__(self):
        """Initialize database connection."""
        load_db_config()
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor()
        self.db_name = DB_CONFIG.get("dbname", "local_llhama")
        self.db_host = DB_CONFIG.get("host", "localhost")
        self.db_port = DB_CONFIG.get("port", 5432)
        self.db_user = DB_CONFIG.get("user", "postgres")

    def show_statistics(self):
        """Display current database statistics."""
        print("\n" + "=" * 70)
        print("DATABASE STATISTICS")
        print("=" * 70)

        # Count users
        self.cursor.execute("SELECT COUNT(*) FROM users")
        users_count = self.cursor.fetchone()[0]
        print(f"Users: {users_count}")

        # Count conversations
        self.cursor.execute("SELECT COUNT(*) FROM conversations")
        conversations_count = self.cursor.fetchone()[0]
        print(f"Conversations: {conversations_count}")

        # Count messages
        self.cursor.execute("SELECT COUNT(*) FROM messages")
        messages_count = self.cursor.fetchone()[0]
        print(f"Messages: {messages_count}")

        # Count calendar events
        self.cursor.execute("SELECT COUNT(*) FROM calendar_events")
        events_count = self.cursor.fetchone()[0]
        print(f"Calendar Events: {events_count}")

        # List users with their conversation/message counts
        self.cursor.execute(
            """
            SELECT u.id, u.username, 
                   COUNT(DISTINCT c.id) as conv_count,
                   COUNT(m.id) as msg_count
            FROM users u
            LEFT JOIN conversations c ON u.id = c.user_id
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY u.id, u.username
            ORDER BY u.id
        """
        )
        users = self.cursor.fetchall()
        if users:
            print(f"\nUsers Details:")
            for user_id, username, conv_count, msg_count in users:
                print(
                    f"  - {username} (ID: {user_id}): {conv_count} conversations, {msg_count} messages"
                )

        # Database size
        self.cursor.execute(
            f"""
            SELECT pg_size_pretty(pg_database_size('{self.db_name}'))
        """
        )
        db_size = self.cursor.fetchone()[0]
        print(f"\nDatabase Size: {db_size}")

        print("=" * 70 + "\n")

    def delete_all_conversations(self):
        """Delete all conversations and messages (keeps users and calendar)."""
        confirm = input(
            "\n⚠️  WARNING: This will delete ALL conversations and messages!\n"
            "Users and calendar events will be preserved.\n"
            "Type 'DELETE CONVERSATIONS' to confirm: "
        )
        if confirm != "DELETE CONVERSATIONS":
            print("❌ Deletion cancelled.")
            return

        try:
            # Delete messages first (foreign key constraint)
            self.cursor.execute("DELETE FROM messages")
            messages_deleted = self.cursor.rowcount

            # Delete conversations
            self.cursor.execute("DELETE FROM conversations")
            conversations_deleted = self.cursor.rowcount

            self.conn.commit()
            print(
                f"\n✅ Deleted {conversations_deleted} conversations and {messages_deleted} messages"
            )

        except Exception as e:
            self.conn.rollback()
            print(f"\n❌ Error deleting data: {e}")

    def delete_all_data(self):
        """Delete ALL data from all tables."""
        confirm = input(
            "\n⚠️  DANGER: This will delete ALL data from the database!\n"
            "This includes users, conversations, messages, and calendar events.\n"
            "Type 'DELETE ALL DATA' to confirm: "
        )
        if confirm != "DELETE ALL DATA":
            print("❌ Deletion cancelled.")
            return

        try:
            # Delete in correct order due to foreign key constraints
            self.cursor.execute("DELETE FROM messages")
            messages_deleted = self.cursor.rowcount

            self.cursor.execute("DELETE FROM conversations")
            conversations_deleted = self.cursor.rowcount

            self.cursor.execute("DELETE FROM calendar_events")
            events_deleted = self.cursor.rowcount

            # Don't delete from users table to preserve authentication
            # If you want to delete users too, uncomment:
            # self.cursor.execute("DELETE FROM users WHERE id > 1")  # Keep admin
            # users_deleted = self.cursor.rowcount

            self.conn.commit()
            print(
                f"\n✅ Deleted:\n"
                f"  - {messages_deleted} messages\n"
                f"  - {conversations_deleted} conversations\n"
                f"  - {events_deleted} calendar events"
            )

        except Exception as e:
            self.conn.rollback()
            print(f"\n❌ Error deleting data: {e}")

    def delete_user_data(self, username: str):
        """Delete all data for a specific user."""
        # First check if user exists
        self.cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = self.cursor.fetchone()

        if not user:
            print(f"\n❌ User not found: {username}")
            return

        user_id = user[0]

        # Count what will be deleted
        self.cursor.execute(
            "SELECT COUNT(*) FROM conversations WHERE user_id = %s", (user_id,)
        )
        conv_count = self.cursor.fetchone()[0]

        self.cursor.execute(
            """
            SELECT COUNT(*) FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.user_id = %s
        """,
            (user_id,),
        )
        msg_count = self.cursor.fetchone()[0]

        if conv_count == 0 and msg_count == 0:
            print(f"\n❌ No data found for user: {username}")
            return

        confirm = input(
            f"\n⚠️  This will delete {conv_count} conversations and {msg_count} messages for user '{username}'.\n"
            f"Confirm? (yes/no): "
        )
        if confirm.lower() != "yes":
            print("❌ Deletion cancelled.")
            return

        try:
            # Delete messages through conversations
            self.cursor.execute(
                """
                DELETE FROM messages 
                WHERE conversation_id IN (
                    SELECT id FROM conversations WHERE user_id = %s
                )
            """,
                (user_id,),
            )
            messages_deleted = self.cursor.rowcount

            # Delete conversations
            self.cursor.execute(
                "DELETE FROM conversations WHERE user_id = %s", (user_id,)
            )
            conversations_deleted = self.cursor.rowcount

            # Delete calendar events
            self.cursor.execute(
                "DELETE FROM calendar_events WHERE user_id = %s", (user_id,)
            )
            events_deleted = self.cursor.rowcount

            self.conn.commit()
            print(
                f"\n✅ Deleted for user '{username}':\n"
                f"  - {conversations_deleted} conversations\n"
                f"  - {messages_deleted} messages\n"
                f"  - {events_deleted} calendar events"
            )

        except Exception as e:
            self.conn.rollback()
            print(f"\n❌ Error deleting data: {e}")

    def delete_old_conversations(self, days: int = 30):
        """Delete conversations older than specified days."""
        confirm = input(
            f"\n⚠️  This will delete conversations older than {days} days.\n"
            f"Confirm? (yes/no): "
        )
        if confirm.lower() != "yes":
            print("❌ Deletion cancelled.")
            return

        try:
            # Delete old messages first
            self.cursor.execute(
                """
                DELETE FROM messages 
                WHERE conversation_id IN (
                    SELECT id FROM conversations 
                    WHERE created_at < NOW() - INTERVAL '%s days'
                )
            """,
                (days,),
            )
            messages_deleted = self.cursor.rowcount

            # Delete old conversations
            self.cursor.execute(
                """
                DELETE FROM conversations 
                WHERE created_at < NOW() - INTERVAL '%s days'
            """,
                (days,),
            )
            conversations_deleted = self.cursor.rowcount

            self.conn.commit()
            print(
                f"\n✅ Deleted {conversations_deleted} conversations and {messages_deleted} messages older than {days} days"
            )

        except Exception as e:
            self.conn.rollback()
            print(f"\n❌ Error deleting old conversations: {e}")

    def backup_database(self, output_file: Optional[str] = None):
        """
        Backup database to SQL file using pg_dump.

        @param output_file Optional output file path. If None, generates timestamped filename.
        """
        if output_file is None:
            backup_dir = Path(__file__).parent.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = backup_dir / f"local_llhama_backup_{timestamp}.sql"

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n📦 Backing up database to: {output_path.absolute()}")

        try:
            cmd = [
                "pg_dump",
                "-h",
                str(self.db_host),
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-F",
                "p",  # Plain text format
                "--no-owner",
                "--no-acl",
                "-f",
                str(output_path.absolute()),
            ]

            env = {"PGPASSWORD": DB_CONFIG.get("password", "")}

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**subprocess.os.environ, **env},
            )

            if result.returncode == 0:
                file_size = output_path.stat().st_size / 1024 / 1024  # MB
                print(f"✅ Database backed up successfully! ({file_size:.2f} MB)")
                print(f"   File: {output_path.absolute()}")
                return str(output_path)
            else:
                print(f"❌ Error backing up database:")
                print(f"   {result.stderr}")
                return None

        except FileNotFoundError:
            print(
                "❌ pg_dump command not found. Make sure PostgreSQL client tools are installed."
            )
            return None
        except Exception as e:
            print(f"❌ Error during backup: {e}")
            return None

    def restore_database(self, input_file: str):
        """
        Restore database from SQL file using psql.

        @param input_file Path to SQL backup file
        """
        input_path = Path(input_file)

        if not input_path.exists():
            print(f"❌ File not found: {input_path}")
            return

        self.show_statistics()

        confirm = input(
            f"\n⚠️  WARNING: This will overwrite current database data!\n"
            f"Restoring from: {input_path.absolute()}\n"
            f"Type 'RESTORE' to confirm: "
        )

        if confirm != "RESTORE":
            print("❌ Restore cancelled.")
            return

        print(f"\n📥 Restoring database from: {input_path.absolute()}")

        try:
            cmd = [
                "psql",
                "-h",
                str(self.db_host),
                "-p",
                str(self.db_port),
                "-U",
                self.db_user,
                "-d",
                self.db_name,
                "-f",
                str(input_path.absolute()),
            ]

            env = {"PGPASSWORD": DB_CONFIG.get("password", "")}

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**subprocess.os.environ, **env},
            )

            if result.returncode == 0:
                print("✅ Database restored successfully!")
                print("\nNew database state:")
                self.show_statistics()
            else:
                print(f"❌ Error restoring database:")
                print(f"   {result.stderr}")

        except FileNotFoundError:
            print(
                "❌ psql command not found. Make sure PostgreSQL client tools are installed."
            )
        except Exception as e:
            print(f"❌ Error during restore: {e}")

    def vacuum_database(self):
        """Run VACUUM ANALYZE to optimize database."""
        print("\n🧹 Running VACUUM ANALYZE to optimize database...")

        try:
            # Close current connection and create one with autocommit
            self.cursor.close()
            self.conn.close()

            self.conn = psycopg2.connect(**DB_CONFIG)
            self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor = self.conn.cursor()

            self.cursor.execute("VACUUM ANALYZE")
            print("✅ Database optimized successfully!")

            # Reconnect normally
            self.cursor.close()
            self.conn.close()
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()

        except Exception as e:
            print(f"❌ Error during vacuum: {e}")

    def reset_database(self):
        """Drop and recreate all tables (nuclear option)."""
        confirm = input(
            "\n⚠️  NUCLEAR OPTION: This will DROP all tables and recreate them!\n"
            f"All data will be lost permanently!\n"
            "Type 'RESET DATABASE' to confirm: "
        )
        if confirm != "RESET DATABASE":
            print("❌ Reset cancelled.")
            return

        print("\n🔄 Resetting database...")

        try:
            # Run the setup_database.py script
            setup_script = Path(__file__).parent.parent / "setup_database.py"
            if setup_script.exists():
                import subprocess

                result = subprocess.run(
                    [sys.executable, str(setup_script)], capture_output=True, text=True
                )
                if result.returncode == 0:
                    print("✅ Database reset successfully!")
                else:
                    print(f"❌ Error resetting database:")
                    print(result.stderr)
            else:
                print(f"❌ setup_database.py not found at {setup_script}")

        except Exception as e:
            print(f"❌ Error during reset: {e}")

    def close(self):
        """Close database connection."""
        self.cursor.close()
        self.conn.close()


def print_menu():
    """Print the main menu."""
    print("\n" + "=" * 70)
    print("LOCAL LLHAMA DATABASE MANAGER")
    print("=" * 70)
    print("1.  Show database statistics")
    print("2.  Delete all conversations (keep users & calendar)")
    print("3.  Delete ALL data (nuclear option)")
    print("4.  Delete data for specific user")
    print("5.  Delete old conversations (by age)")
    print("6.  Backup database to SQL file")
    print("7.  Restore database from SQL file")
    print("8.  Optimize database (VACUUM)")
    print("9.  Reset database (drop & recreate tables)")
    print("10. Exit")
    print("=" * 70)


def main():
    """Main interactive loop."""
    try:
        manager = DBManager()
        print(f"\n✅ Connected to database: {manager.db_name}@{manager.db_host}")

        while True:
            print_menu()
            choice = input("\nSelect option (1-10): ").strip()

            if choice == "1":
                manager.show_statistics()

            elif choice == "2":
                manager.delete_all_conversations()

            elif choice == "3":
                manager.delete_all_data()

            elif choice == "4":
                manager.show_statistics()
                username = input("\nEnter username: ").strip()
                if username:
                    manager.delete_user_data(username)

            elif choice == "5":
                days = input("\nDelete conversations older than (days) [30]: ").strip()
                days = int(days) if days else 30
                manager.delete_old_conversations(days)

            elif choice == "6":
                output_file = input(
                    "\nEnter output file path (press Enter for auto): "
                ).strip()
                if not output_file:
                    output_file = None
                manager.backup_database(output_file)

            elif choice == "7":
                input_file = input("\nEnter SQL backup file path: ").strip()
                if input_file:
                    manager.restore_database(input_file)
                else:
                    print("❌ No file path provided.")

            elif choice == "8":
                manager.vacuum_database()

            elif choice == "9":
                manager.reset_database()

            elif choice == "10":
                print("\n✅ Exiting...")
                break

            else:
                print("\n❌ Invalid option. Please select 1-10.")

        manager.close()

    except psycopg2.OperationalError as e:
        print(f"\n❌ Database connection error: {e}")
        print("Make sure PostgreSQL is running and credentials in .env are correct.")
        sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n✅ Interrupted by user. Exiting...")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
