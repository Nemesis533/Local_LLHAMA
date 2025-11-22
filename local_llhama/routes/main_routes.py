# main_routes.py
from flask import Blueprint, send_file, current_app

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def index():
    """
    Serves the main dashboard HTML page.
    """
    static_path = current_app.config.get("STATIC_PATH")
    return send_file(static_path / 'dashboard.html')
