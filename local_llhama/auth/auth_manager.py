"""
Authentication Manager for Local_LLHAMA.
Handles login verification, session management, and password operations.
"""

import bcrypt
from .db_manager import DatabaseManager

from ..Shared_Logger import LogLevel

class AuthManager:
    """
    Manages authentication operations including login verification,
    session management, and password validation.
    """
    
    def __init__(self, pg_client=None):
        """
        Initialize authentication manager.
        
        @param pg_client: PostgreSQL_Client instance. If None, DatabaseManager creates new one.
        """
        self.class_prefix_message = "[AuthManager]"
        self.db_manager = DatabaseManager(pg_client)
        
        # Check if password reset is needed on initialization
        self.db_manager.check_password_reset_needed()
    
    def verify_credentials(self, username, password):
        """
        Verify username and password credentials.
        
        @param username: Username to verify.
        @param password: Password to verify.
        @return: User object if credentials are valid, None otherwise.
        """
        if not username or not password:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Empty username or password provided")
            return None
        
        # Get user from database
        user = self.db_manager.get_user_by_username(username)
        
        if not user:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Login attempt for non-existent user: {username}")
            return None
        
        # Check if user is active
        if not user.is_active:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Login attempt for inactive user: {username}")
            return None
        
        # Verify password using bcrypt
        try:
            # PostgreSQL stores bcrypt hashes (format: $2a$12$... or $2b$12$...)
            # bcrypt.checkpw expects bytes
            if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                print(f"{self.class_prefix_message} {LogLevel.INFO} Successful login for user: {username}")
                # Update last login timestamp
                self.db_manager.update_last_login(username)
                return user
            else:
                print(f"{self.class_prefix_message} {LogLevel.WARNING} Failed login attempt for user: {username}")
                return None
        except Exception as e:
            print(f"{self.class_prefix_message} {LogLevel.WARNING} Password verification error for user {username}: {str(e)}")
            return None
    
    def get_user_by_id(self, user_id):
        """
        Retrieve user by ID (used by Flask-Login).
        
        @param user_id: User ID to look up.
        @return: User object if found, None otherwise.
        """
        return self.db_manager.get_user_by_id(user_id)
    
    def validate_password_strength(self, password):
        """
        Validate password meets minimum requirements.
        
        @param password: Password to validate.
        @return: Tuple (is_valid: bool, error_message: str)
        """
        if not password:
            return False, "Password cannot be empty"
        
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        # Optional: Add more complexity requirements here if needed
        # For now, just enforce minimum length
        
        return True, ""
    
    def change_password(self, username, old_password, new_password):
        """
        Change user password after verifying old password.
        
        @param username: Username for password change.
        @param old_password: Current password for verification.
        @param new_password: New password to set.
        @return: Tuple (success: bool, message: str)
        """
        # Verify current credentials
        user = self.verify_credentials(username, old_password)
        if not user:
            return False, "Current password is incorrect"
        
        # Validate new password
        is_valid, error_msg = self.validate_password_strength(new_password)
        if not is_valid:
            return False, error_msg
        
        # Update password
        success = self.db_manager.update_password(username, new_password)
        if success:
            return True, "Password changed successfully"
        else:
            return False, "Failed to update password"
