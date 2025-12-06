"""
Admin Routes

Handles admin panel functionality including user management, 
password resets, and permission management.
"""

from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from functools import wraps
import secrets
import string


admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        if not current_user.is_admin:
            return jsonify({"error": "Admin privileges required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def generate_secure_password(length=12):
    """
    Generate a secure random password.
    
    @param length: Length of password (default 12).
    @return: Random alphanumeric password.
    """
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password


@admin_bp.route('/admin')
@login_required
@admin_required
def admin_panel():
    """Render the admin panel page."""
    return render_template('admin.html')


@admin_bp.route('/admin/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    """Get list of all users."""
    try:
        auth_manager = current_app.config.get('AUTH_MANAGER')
        if not auth_manager:
            return jsonify({"error": "Auth manager not initialized"}), 500
        
        users = auth_manager.db_manager.get_all_users()
        
        users_data = []
        for user in users:
            users_data.append({
                'id': user.id,
                'username': user.username,
                'created_at': user.created_at,
                'last_login': user.last_login,
                'is_active': user.is_active,
                'is_admin': user.is_admin,
                'can_access_dashboard': user.can_access_dashboard,
                'can_access_chat': user.can_access_chat,
                'must_change_password': user.must_change_password
            })
        
        return jsonify({"users": users_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/admin/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Create a new user."""
    try:
        data = request.get_json()
        
        username = data.get('username', '').strip()
        if not username:
            return jsonify({"error": "Username required"}), 400
        
        # Generate secure random password
        password = generate_secure_password(12)
        
        is_admin = data.get('is_admin', False)
        can_access_dashboard = data.get('can_access_dashboard', True)
        can_access_chat = data.get('can_access_chat', True)
        
        auth_manager = current_app.config.get('AUTH_MANAGER')
        if not auth_manager:
            return jsonify({"error": "Auth manager not initialized"}), 500
        
        success = auth_manager.db_manager.create_user(
            username=username,
            password=password,
            is_admin=is_admin,
            can_access_dashboard=can_access_dashboard,
            can_access_chat=can_access_chat,
            must_change_password=True  # Always require password change on first login
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": "User created successfully",
                "username": username,
                "password": password,
                "warning": "Save this password - it will only be shown once"
            })
        else:
            return jsonify({"error": "Failed to create user (username may already exist)"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/admin/users/<username>/password', methods=['POST'])
@login_required
@admin_required
def reset_password(username):
    """Reset user password."""
    try:
        # Generate new secure password
        new_password = generate_secure_password(12)
        
        auth_manager = current_app.config.get('AUTH_MANAGER')
        if not auth_manager:
            return jsonify({"error": "Auth manager not initialized"}), 500
        
        success = auth_manager.db_manager.reset_user_password(
            username=username,
            new_password=new_password,
            must_change=True  # Require password change on next login
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": "Password reset successfully",
                "username": username,
                "password": new_password,
                "warning": "Save this password - it will only be shown once"
            })
        else:
            return jsonify({"error": "Failed to reset password (user may not exist)"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/admin/users/<username>/permissions', methods=['PUT'])
@login_required
@admin_required
def update_permissions(username):
    """Update user permissions."""
    try:
        data = request.get_json()
        
        auth_manager = current_app.config.get('AUTH_MANAGER')
        if not auth_manager:
            return jsonify({"error": "Auth manager not initialized"}), 500
        
        success = auth_manager.db_manager.update_user_permissions(
            username=username,
            is_admin=data.get('is_admin'),
            can_access_dashboard=data.get('can_access_dashboard'),
            can_access_chat=data.get('can_access_chat'),
            is_active=data.get('is_active')
        )
        
        if success:
            return jsonify({"success": True, "message": "Permissions updated successfully"})
        else:
            return jsonify({"error": "Failed to update permissions"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/admin/users/<username>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(username):
    """Delete a user."""
    try:
        if username == 'admin':
            return jsonify({"error": "Cannot delete admin user"}), 400
        
        if username == current_user.username:
            return jsonify({"error": "Cannot delete your own account"}), 400
        
        auth_manager = current_app.config.get('AUTH_MANAGER')
        if not auth_manager:
            return jsonify({"error": "Auth manager not initialized"}), 500
        
        success = auth_manager.db_manager.delete_user(username)
        
        if success:
            return jsonify({"success": True, "message": "User deleted successfully"})
        else:
            return jsonify({"error": "Failed to delete user"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
