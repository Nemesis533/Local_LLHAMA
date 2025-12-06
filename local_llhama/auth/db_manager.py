"""
Database Manager for SQLite-based authentication.
Handles user database operations and schema management.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

from ..Shared_Logger import LogLevel


class User:
    """Simple User model for authentication."""
    
    def __init__(self, user_id, username, password_hash, created_at, last_login, is_active=True, 
                 is_admin=False, can_access_dashboard=True, can_access_chat=True, must_change_password=False):
        self.class_prefix_message = "[USER]"
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self.created_at = created_at
        self.last_login = last_login
        self.is_active = is_active
        self.is_admin = is_admin
        self.can_access_dashboard = can_access_dashboard
        self.can_access_chat = can_access_chat
        self.must_change_password = must_change_password
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)


class DatabaseManager:
    """
    Manages SQLite database for user authentication.
    Provides methods for user CRUD operations.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize database manager.
        
        @param db_path: Path to SQLite database file. If None, uses default location.
        """
        self.class_prefix_message = "[DB_Manager]"
        if db_path is None:
            base_path = Path(__file__).parent.parent
            data_dir = base_path / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = data_dir / "users.db"
        
        self.db_path = str(db_path)
        self._init_database()
    
    def _get_connection(self):
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """Initialize database schema and create default admin user if needed."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create users table with new columns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                is_admin BOOLEAN DEFAULT 0,
                can_access_dashboard BOOLEAN DEFAULT 1,
                can_access_chat BOOLEAN DEFAULT 1,
                must_change_password BOOLEAN DEFAULT 0
            )
        ''')
        
        # Check if new columns exist, add them if not (migration)
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'is_admin' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Added is_admin column to users table")
        
        if 'can_access_dashboard' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN can_access_dashboard BOOLEAN DEFAULT 1')
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Added can_access_dashboard column to users table")
        
        if 'can_access_chat' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN can_access_chat BOOLEAN DEFAULT 1')
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Added can_access_chat column to users table")
        
        if 'must_change_password' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0')
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Added must_change_password column to users table")
        
        conn.commit()
        
        # Check if admin user exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
        admin_exists = cursor.fetchone()[0] > 0
        
        if not admin_exists:
            # Create default admin user from environment or use default
            load_dotenv()
            default_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'changeme123')
            
            # Validate password meets requirements
            if len(default_password) < 8:
                print(f"{self.class_prefix_message}WARNING: DEFAULT_ADMIN_PASSWORD too short, using 'changeme123'")
                default_password = 'changeme123'
            
            password_hash = generate_password_hash(default_password, method='pbkdf2:sha256')
            
            cursor.execute(
                'INSERT INTO users (username, password_hash, is_admin, can_access_dashboard, can_access_chat) VALUES (?, ?, ?, ?, ?)',
                ('admin', password_hash, True, True, True)
            )
            conn.commit()
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Created default admin user with password: {default_password}")
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Please change the default password after first login!")
        else:
            # Ensure existing admin has is_admin flag set
            cursor.execute('UPDATE users SET is_admin = 1 WHERE username = ?', ('admin',))
            conn.commit()
        
        conn.close()
    
    def get_user_by_username(self, username):
        """
        Retrieve user by username.
        
        @param username: Username to look up.
        @return: User object if found, None otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '
            'FROM users WHERE username = ?',
            (username,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                last_login=row['last_login'],
                is_active=bool(row['is_active']),
                is_admin=bool(row['is_admin']),
                can_access_dashboard=bool(row['can_access_dashboard']),
                can_access_chat=bool(row['can_access_chat']),
                must_change_password=bool(row['must_change_password'])
            )
        return None
    
    def get_user_by_id(self, user_id):
        """
        Retrieve user by ID.
        
        @param user_id: User ID to look up.
        @return: User object if found, None otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '
            'FROM users WHERE id = ?',
            (user_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                last_login=row['last_login'],
                is_active=bool(row['is_active']),
                is_admin=bool(row['is_admin']),
                can_access_dashboard=bool(row['can_access_dashboard']),
                can_access_chat=bool(row['can_access_chat']),
                must_change_password=bool(row['must_change_password'])
            )
        return None
    
    def update_last_login(self, username):
        """
        Update last login timestamp for user.
        
        @param username: Username to update.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET last_login = ? WHERE username = ?',
            (datetime.now().isoformat(), username)
        )
        
        conn.commit()
        conn.close()
    
    def update_password(self, username, new_password):
        """
        Update user password.
        
        @param username: Username to update.
        @param new_password: New password (will be hashed).
        @return: True if successful, False otherwise.
        """
        if len(new_password) < 8:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Password must be at least 8 characters")
            return False
        
        password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET password_hash = ? WHERE username = ?',
            (password_hash, username)
        )
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if success:
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Password updated successfully for user: {username}")
        else:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to update password for user: {username}")
        
        return success
    
    def check_password_reset_needed(self):
        """
        Check if password reset is needed via .env file.
        If RESET_ADMIN_PASSWORD is set in .env, reset admin password.
        
        @return: True if password was reset, False otherwise.
        """
        load_dotenv()
        reset_password = os.getenv('RESET_ADMIN_PASSWORD', '').strip()
        
        if reset_password and len(reset_password) >= 8:
            success = self.update_password('admin', reset_password)
            if success:
                print(f"{self.class_prefix_message} {LogLevel.INFO}  Admin password reset from .env file")
                print(f"{self.class_prefix_message} {LogLevel.WARNING}  Remove RESET_ADMIN_PASSWORD from .env for security!")
                return True
        
        return False
    
    def get_all_users(self):
        """
        Retrieve all users from database.
        
        @return: List of User objects.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '\
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '\
            'FROM users ORDER BY username'
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append(User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=row['created_at'],
                last_login=row['last_login'],
                is_active=bool(row['is_active']),
                is_admin=bool(row['is_admin']),
                can_access_dashboard=bool(row['can_access_dashboard']),
                can_access_chat=bool(row['can_access_chat']),
                must_change_password=bool(row['must_change_password'])
            ))
        
        return users
    
    def create_user(self, username, password, is_admin=False, can_access_dashboard=True, 
                    can_access_chat=True, must_change_password=True):
        """
        Create a new user.
        
        @param username: Username for new user.
        @param password: Password (will be hashed).
        @param is_admin: Whether user has admin privileges.
        @param can_access_dashboard: Whether user can access dashboard.
        @param can_access_chat: Whether user can access chat.
        @param must_change_password: Whether user must change password on next login.
        @return: True if successful, False otherwise.
        """
        if len(password) < 8:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Password must be at least 8 characters")
            return False
        
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO users (username, password_hash, is_admin, can_access_dashboard, '\
                'can_access_chat, must_change_password) VALUES (?, ?, ?, ?, ?, ?)',
                (username, password_hash, is_admin, can_access_dashboard, can_access_chat, must_change_password)
            )
            conn.commit()
            print(f"{self.class_prefix_message} {LogLevel.INFO}  User created successfully: {username}")
            return True
        except sqlite3.IntegrityError:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Username already exists: {username}")
            return False
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to create user: {e}")
            return False
        finally:
            conn.close()
    
    def update_user_permissions(self, username, is_admin=None, can_access_dashboard=None, 
                                can_access_chat=None, is_active=None):
        """
        Update user permissions.
        
        @param username: Username to update.
        @param is_admin: Admin status (None to skip).
        @param can_access_dashboard: Dashboard access (None to skip).
        @param can_access_chat: Chat access (None to skip).
        @param is_active: Active status (None to skip).
        @return: True if successful, False otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if is_admin is not None:
            updates.append('is_admin = ?')
            params.append(is_admin)
        
        if can_access_dashboard is not None:
            updates.append('can_access_dashboard = ?')
            params.append(can_access_dashboard)
        
        if can_access_chat is not None:
            updates.append('can_access_chat = ?')
            params.append(can_access_chat)
        
        if is_active is not None:
            updates.append('is_active = ?')
            params.append(is_active)
        
        if not updates:
            conn.close()
            return False
        
        params.append(username)
        query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
        
        cursor.execute(query, params)
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if success:
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Permissions updated for user: {username}")
        
        return success
    
    def reset_user_password(self, username, new_password, must_change=True):
        """
        Reset user password (typically by admin).
        
        @param username: Username to reset.
        @param new_password: New password (will be hashed).
        @param must_change: Whether user must change password on next login.
        @return: True if successful, False otherwise.
        """
        if len(new_password) < 8:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Password must be at least 8 characters")
            return False
        
        password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET password_hash = ?, must_change_password = ? WHERE username = ?',
            (password_hash, must_change, username)
        )
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if success:
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Password reset for user: {username}")
        
        return success
    
    def clear_password_change_flag(self, username):
        """
        Clear the must_change_password flag after user changes password.
        
        @param username: Username to update.
        @return: True if successful, False otherwise.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE users SET must_change_password = 0 WHERE username = ?',
            (username,)
        )
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete_user(self, username):
        """
        Delete a user (cannot delete admin).
        
        @param username: Username to delete.
        @return: True if successful, False otherwise.
        """
        if username == 'admin':
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Cannot delete admin user")
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE username = ?', (username,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if success:
            print(f"{self.class_prefix_message} {LogLevel.INFO}  User deleted: {username}")
        
        return success
