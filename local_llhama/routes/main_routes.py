# main_routes.py
from flask import Blueprint, current_app, redirect, send_file
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


def is_system_ready():
    """
    @brief Check if the system controller is ready.
    @return True if system is ready, False otherwise
    """
    system_controller = current_app.config.get("SYSTEM_CONTROLLER")
    return system_controller and getattr(system_controller, "started", False)


@main_bp.route("/")
def index():
    """
    Redirect to login or chat based on authentication.
    """
    # Only show loading if not authenticated AND system not ready
    if not current_user.is_authenticated and not is_system_ready():
        static_path = current_app.config.get("STATIC_PATH")
        return send_file(static_path / "loading.html")

    if current_user.is_authenticated:
        return redirect("/chat")
    return redirect("/login")


@main_bp.route("/chat")
@login_required
def chat():
    """
    Serves the chat interface HTML page.
    """
    if current_user.must_change_password:
        return redirect("/change-password-required")

    if not current_user.can_access_chat:
        return "Access Denied: You do not have permission to access the chat", 403

    # All Authenticated users can access chat
    static_path = current_app.config.get("STATIC_PATH")
    return send_file(static_path / "chat.html")
