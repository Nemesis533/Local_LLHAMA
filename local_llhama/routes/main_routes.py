# main_routes.py
from flask import Blueprint, send_file, current_app, redirect
from flask_login import login_required, current_user

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def index():
    """
    Redirect to login or dashboard based on authentication.
    """
    if current_user.is_authenticated:
        return redirect('/dashboard')
    return redirect('/login')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Serves the main dashboard HTML page.
    """
    static_path = current_app.config.get("STATIC_PATH")
    return send_file(static_path / 'dashboard.html')
