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


class User:
    """Simple User model for authentication."""
    
    def __init__(self, user_id, username, password_hash, created_at, last_login, is_active=True):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self.created_at = created_at
        self.last_login = last_login
        self.is_active = is_active
    
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
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
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
                print("[Auth] WARNING: DEFAULT_ADMIN_PASSWORD too short, using 'changeme123'")
                default_password = 'changeme123'
            
            password_hash = generate_password_hash(default_password, method='pbkdf2:sha256')
            
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                ('admin', password_hash)
            )
            conn.commit()
            print(f"[Auth] [INFO] Created default admin user with password: {default_password}")
            print(f"[Auth] [WARNING] Please change the default password after first login!")
        
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
            'SELECT id, username, password_hash, created_at, last_login, is_active '
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
                is_active=bool(row['is_active'])
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
            'SELECT id, username, password_hash, created_at, last_login, is_active '
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
                is_active=bool(row['is_active'])
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
            print(f"[Auth] [ERROR] Password must be at least 8 characters")
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
            print(f"[Auth] [INFO] Password updated successfully for user: {username}")
        else:
            print(f"[Auth] [ERROR] Failed to update password for user: {username}")
        
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
                print(f"[Auth] [INFO] Admin password reset from .env file")
                print(f"[Auth] [WARNING] Remove RESET_ADMIN_PASSWORD from .env for security!")
                return True
        
        return False
