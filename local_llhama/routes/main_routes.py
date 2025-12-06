# main_routes.py
from flask import Blueprint, send_file, current_app, redirect
from flask_login import login_required, current_user

main_bp = Blueprint("main", __name__)

def is_system_ready():
    """Check if the system controller is ready."""
    system_controller = current_app.config.get('SYSTEM_CONTROLLER')
    return system_controller and getattr(system_controller, 'started', False)

@main_bp.route('/')
def index():
    """
    Redirect to login or dashboard based on authentication.
    """
    # Only show loading if not authenticated AND system not ready
    if not current_user.is_authenticated and not is_system_ready():
        static_path = current_app.config.get("STATIC_PATH")
        return send_file(static_path / 'loading.html')
    
    if current_user.is_authenticated:
        return redirect('/dashboard')
    return redirect('/login')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Serves the main dashboard HTML page.
    """
    # Check if user must change password
    if current_user.must_change_password:
        return redirect('/change-password-required')
    
    # Check if user has dashboard access
    if not current_user.can_access_dashboard:
        return "Access Denied: You do not have permission to access the dashboard", 403
    
    # Authenticated users can always access, show loading within page if needed
    static_path = current_app.config.get("STATIC_PATH")
    return send_file(static_path / 'dashboard.html')

@main_bp.route('/chat')
@login_required
def chat():
    """
    Serves the chat interface HTML page.
    """
    # Check if user must change password
    if current_user.must_change_password:
        return redirect('/change-password-required')
    
    # Check if user has chat access
    if not current_user.can_access_chat:
        return "Access Denied: You do not have permission to access the chat", 403
    
    # Authenticated users can always access
    static_path = current_app.config.get("STATIC_PATH")
    return send_file(static_path / 'chat.html')
