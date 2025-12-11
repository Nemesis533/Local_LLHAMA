"""
Authentication routes for Local_LLHAMA web interface.
Provides login, logout, and password change endpoints.
"""

from flask import Blueprint, request, jsonify, redirect, url_for, render_template_string, current_app
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps

auth_bp = Blueprint("auth", __name__)


def get_auth_manager():
    """Get AuthManager instance from Flask app context."""
    return current_app.config.get("AUTH_MANAGER")


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle login requests.
    GET: Serve login page
    POST: Process login credentials
    """
    # If already logged in, redirect to chat
    if current_user.is_authenticated:
        return redirect('/chat')
    
    if request.method == 'GET':
        # Serve login page
        return current_app.send_static_file('login.html')
    
    # POST request - process login
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    remember = data.get('remember', False)
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    # Verify credentials
    auth_manager = get_auth_manager()
    user = auth_manager.verify_credentials(username, password)
    
    if user:
        # Log user in with Flask-Login
        login_user(user, remember=remember)
        print(f"[Auth] [INFO] User {username} logged in successfully")
        
        # Check if password change is required
        if user.must_change_password:
            return jsonify({"success": True, "redirect": "/change-password-required"}), 200
        
        return jsonify({"success": True, "redirect": "/chat"}), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Handle logout requests."""
    username = current_user.username
    logout_user()
    print(f"[Auth] [INFO] User {username} logged out")
    return jsonify({"success": True, "redirect": "/login"}), 200


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Handle password change requests.
    Requires old password verification.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not old_password or not new_password or not confirm_password:
        return jsonify({"error": "All password fields are required"}), 400
    
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match"}), 400
    
    # Change password
    auth_manager = get_auth_manager()
    success, message = auth_manager.change_password(
        current_user.username,
        old_password,
        new_password
    )
    
    if success:
        # Clear must_change_password flag
        auth_manager.db_manager.clear_password_change_flag(current_user.username)
        print(f"[Auth] [INFO] Password changed for user: {current_user.username}")
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"error": message}), 400


@auth_bp.route('/check-auth', methods=['GET'])
def check_auth():
    """
    Check if user is authenticated.
    Used by frontend to determine if login is required.
    """
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "username": current_user.username,
            "must_change_password": current_user.must_change_password,
            "is_admin": current_user.is_admin,
            "can_access_dashboard": current_user.can_access_dashboard,
            "can_access_chat": current_user.can_access_chat
        }), 200
    else:
        return jsonify({"authenticated": False}), 200


@auth_bp.route('/change-password-required', methods=['GET'])
@login_required
def change_password_required_page():
    """Serve the forced password change page."""
    return current_app.send_static_file('change-password.html')
