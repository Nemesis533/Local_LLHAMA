"""
Authentication Manager for Local_LLHAMA.
Handles login verification, session management, and password operations.
"""

from werkzeug.security import check_password_hash
from .db_manager import DatabaseManager


class AuthManager:
    """
    Manages authentication operations including login verification,
    session management, and password validation.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize authentication manager.
        
        @param db_path: Path to SQLite database file. If None, uses default location.
        """
        self.db = DatabaseManager(db_path)
        
        # Check if password reset is needed on initialization
        self.db.check_password_reset_needed()
    
    def verify_credentials(self, username, password):
        """
        Verify username and password credentials.
        
        @param username: Username to verify.
        @param password: Password to verify.
        @return: User object if credentials are valid, None otherwise.
        """
        if not username or not password:
            print("[Auth] [WARNING] Empty username or password provided")
            return None
        
        # Get user from database
        user = self.db.get_user_by_username(username)
        
        if not user:
            print(f"[Auth] [WARNING] Login attempt for non-existent user: {username}")
            return None
        
        # Check if user is active
        if not user.is_active:
            print(f"[Auth] [WARNING] Login attempt for inactive user: {username}")
            return None
        
        # Verify password
        if check_password_hash(user.password_hash, password):
            print(f"[Auth] [INFO] Successful login for user: {username}")
            # Update last login timestamp
            self.db.update_last_login(username)
            return user
        else:
            print(f"[Auth] [WARNING] Failed login attempt for user: {username}")
            return None
    
    def get_user_by_id(self, user_id):
        """
        Retrieve user by ID (used by Flask-Login).
        
        @param user_id: User ID to look up.
        @return: User object if found, None otherwise.
        """
        return self.db.get_user_by_id(user_id)
    
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
        success = self.db.update_password(username, new_password)
        if success:
            return True, "Password changed successfully"
        else:
            return False, "Failed to update password"
