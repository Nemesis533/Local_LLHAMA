"""
Database Manager for PostgreSQL-based authentication.
Handles user database operations and schema management.
"""

import os
from pathlib import Path
from datetime import datetime
import bcrypt
from dotenv import load_dotenv

from ..Shared_Logger import LogLevel
from ..PostgreSQL_Client import PostgreSQLClient
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
    Manages PostgreSQL database for user authentication.
    Provides methods for user CRUD operations.
    """
    
    def __init__(self, pg_client=None):
        """
        Initialize database manager.
        
        @param pg_client: PostgreSQL_Client instance. If None, creates new one.
        """
        self.class_prefix_message = "[DB_Manager]"
        if pg_client is None:
            self.pg_client = PostgreSQLClient()
        else:
            self.pg_client = pg_client
    
    def get_user_by_username(self, username):
        """
        Retrieve user by username.
        
        @param username: Username to look up.
        @return: User object if found, None otherwise.
        """
        results = self.pg_client.execute_query_dict(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '
            'FROM users WHERE username = %s',
            (username,)
        )
        
        if results and len(results) > 0:
            row = results[0]
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=str(row['created_at']),
                last_login=str(row['last_login']) if row['last_login'] else None,
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
        results = self.pg_client.execute_query_dict(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '
            'FROM users WHERE id = %s',
            (user_id,)
        )
        
        if results and len(results) > 0:
            row = results[0]
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                created_at=str(row['created_at']),
                last_login=str(row['last_login']) if row['last_login'] else None,
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
        self.pg_client.execute_write(
            'UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = %s',
            (username,)
        )
    
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
        
        # Hash password using bcrypt to match PostgreSQL crypt() function
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
        
        try:
            self.pg_client.execute_write(
                'UPDATE users SET password_hash = %s WHERE username = %s',
                (password_hash, username)
            )
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Password updated successfully for user: {username}")
            return True
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to update password for user: {username} - {e}")
            return False
    
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
        results = self.pg_client.execute_query_dict(
            'SELECT id, username, password_hash, created_at, last_login, is_active, '
            'is_admin, can_access_dashboard, can_access_chat, must_change_password '
            'FROM users ORDER BY username'
        )
        
        users = []
        if results:
            for row in results:
                users.append(User(
                    user_id=row['id'],
                    username=row['username'],
                    password_hash=row['password_hash'],
                    created_at=str(row['created_at']),
                    last_login=str(row['last_login']) if row['last_login'] else None,
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
        
        # Hash password using bcrypt to match PostgreSQL crypt() function
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        try:
            self.pg_client.execute_write(
                'INSERT INTO users (username, password_hash, is_admin, can_access_dashboard, '
                'can_access_chat, must_change_password) VALUES (%s, %s, %s, %s, %s, %s)',
                (username, password_hash, is_admin, can_access_dashboard, can_access_chat, must_change_password)
            )
            print(f"{self.class_prefix_message} {LogLevel.INFO}  User created successfully: {username}")
            return True
        except Exception as e:
            error_msg = str(e)
            if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
                print(f"{self.class_prefix_message} {LogLevel.WARNING}  Username already exists: {username}")
            else:
                print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to create user: {e}")
            return False
    
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
        updates = []
        params = []
        
        if is_admin is not None:
            updates.append('is_admin = %s')
            params.append(is_admin)
        
        if can_access_dashboard is not None:
            updates.append('can_access_dashboard = %s')
            params.append(can_access_dashboard)
        
        if can_access_chat is not None:
            updates.append('can_access_chat = %s')
            params.append(can_access_chat)
        
        if is_active is not None:
            updates.append('is_active = %s')
            params.append(is_active)
        
        if not updates:
            return False
        
        params.append(username)
        query = f"UPDATE users SET {', '.join(updates)} WHERE username = %s"
        
        try:
            self.pg_client.execute_write(query, tuple(params))
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Permissions updated for user: {username}")
            return True
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to update permissions: {e}")
            return False
    
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
        
        # Hash password using bcrypt to match PostgreSQL crypt() function
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
        
        try:
            self.pg_client.execute_write(
                'UPDATE users SET password_hash = %s, must_change_password = %s WHERE username = %s',
                (password_hash, must_change, username)
            )
            print(f"{self.class_prefix_message} {LogLevel.INFO}  Password reset for user: {username}")
            return True
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to reset password: {e}")
            return False
    
    def clear_password_change_flag(self, username):
        """
        Clear the must_change_password flag after user changes password.
        
        @param username: Username to update.
        @return: True if successful, False otherwise.
        """
        try:
            self.pg_client.execute_write(
                'UPDATE users SET must_change_password = FALSE WHERE username = %s',
                (username,)
            )
            return True
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to clear password flag: {e}")
            return False
    
    def delete_user(self, username):
        """
        Delete a user (cannot delete admin).
        
        @param username: Username to delete.
        @return: True if successful, False otherwise.
        """
        if username == 'admin':
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Cannot delete admin user")
            return False
        
        try:
            self.pg_client.execute_write(
                'DELETE FROM users WHERE username = %s',
                (username,)
            )
            print(f"{self.class_prefix_message} {LogLevel.INFO}  User deleted: {username}")
            return True
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING}  Failed to delete user: {e}")
            return False
