"""
Admin Routes

Handles admin panel functionality including user management,
password resets, and permission management.
"""

import secrets
import string
from functools import wraps

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from ..error_handler import FlaskErrorHandler

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """
    @brief Decorator to require admin privileges.
    @param f Function to decorate
    @return Decorated function
    """

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
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return password


@admin_bp.route("/admin")
@login_required
@admin_required
def admin_panel():
    """
    @brief Render the admin panel page.
    @return Rendered admin template
    """
    return render_template("admin.html")


@admin_bp.route("/admin/users", methods=["GET"])
@login_required
@admin_required
@FlaskErrorHandler.handle_route()
def get_users():
    """
    @brief Get list of all users.
    @return JSON response with user list or error
    """
    auth_manager = current_app.config.get("AUTH_MANAGER")
    if not auth_manager:
        return jsonify({"error": "Auth manager not initialized"}), 500

    users = auth_manager.db_manager.get_all_users()

    users_data = []
    for user in users:
        users_data.append(
            {
                "id": user.id,
                "username": user.username,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "can_access_chat": user.can_access_chat,
                "must_change_password": user.must_change_password,
            }
        )

    return {"users": users_data}


@admin_bp.route("/admin/users", methods=["POST"])
@login_required
@admin_required
@FlaskErrorHandler.handle_route()
def create_user():
    """
    @brief Create a new user.
    @return JSON response with creation result
    """
    data = request.get_json()

    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username required"}), 400

    # Generate secure random password
    password = generate_secure_password(12)

    is_admin = data.get("is_admin", False)
    can_access_chat = data.get("can_access_chat", True)

    auth_manager = current_app.config.get("AUTH_MANAGER")
    if not auth_manager:
        return jsonify({"error": "Auth manager not initialized"}), 500

    success = auth_manager.db_manager.create_user(
        username=username,
        password=password,
        is_admin=is_admin,
        can_access_chat=can_access_chat,
        must_change_password=True,  # Always require password change on first login
    )

    if success:
        return jsonify(
            {
                "success": True,
                "message": "User created successfully",
                "username": username,
                "password": password,
                "warning": "Save this password - it will only be shown once",
            }
        )
    else:
        return (
            jsonify({"error": "Failed to create user (username may already exist)"}),
            400,
        )


@admin_bp.route("/admin/users/<username>/password", methods=["POST"])
@login_required
@admin_required
@FlaskErrorHandler.handle_route()
def reset_password(username):
    """
    @brief Reset user password.
    @param username Username of user to reset password for
    @return JSON response with new password or error
    """
    # Generate new secure password
    new_password = generate_secure_password(12)

    auth_manager = current_app.config.get("AUTH_MANAGER")
    if not auth_manager:
        return jsonify({"error": "Auth manager not initialized"}), 500

    success = auth_manager.db_manager.reset_user_password(
        username=username,
        new_password=new_password,
        must_change=True,  # Require password change on next login
    )

    if success:
        return jsonify(
            {
                "success": True,
                "message": "Password reset successfully",
                "username": username,
                "password": new_password,
                "warning": "Save this password - it will only be shown once",
            }
        )
    else:
        return (
            jsonify({"error": "Failed to reset password (user may not exist)"}),
            400,
        )


@admin_bp.route("/admin/users/<username>/permissions", methods=["PUT"])
@login_required
@admin_required
@FlaskErrorHandler.handle_route()
def update_permissions(username):
    """
    @brief Update user permissions.
    @param username Username of user to update permissions for
    @return JSON response with update result
    """
    data = request.get_json()

    auth_manager = current_app.config.get("AUTH_MANAGER")
    if not auth_manager:
        return jsonify({"error": "Auth manager not initialized"}), 500

    success = auth_manager.db_manager.update_user_permissions(
        username=username,
        is_admin=data.get("is_admin"),
        can_access_chat=data.get("can_access_chat"),
        is_active=data.get("is_active"),
    )

    if success:
        return {"message": "Permissions updated successfully"}
    else:
        return jsonify({"error": "Failed to update permissions"}), 400


@admin_bp.route("/admin/users/<username>", methods=["DELETE"])
@login_required
@admin_required
@FlaskErrorHandler.handle_route()
def delete_user(username):
    """
    @brief Delete a user.
    @param username Username of user to delete
    @return JSON response with deletion result
    """
    if username == "admin":
        return jsonify({"error": "Cannot delete admin user"}), 400

    if username == current_user.username:
        return jsonify({"error": "Cannot delete your own account"}), 400

    auth_manager = current_app.config.get("AUTH_MANAGER")
    if not auth_manager:
        return jsonify({"error": "Auth manager not initialized"}), 500

    success = auth_manager.db_manager.delete_user(username)

    if success:
        return {"message": "User deleted successfully"}
    else:
        return jsonify({"error": "Failed to delete user"}), 400
