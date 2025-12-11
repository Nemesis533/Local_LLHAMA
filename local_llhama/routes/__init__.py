from .admin_routes import admin_bp
from .auth_routes import auth_bp
from .calendar_routes import calendar_bp
from .chat_history_routes import chat_history_bp
from .llm_routes import llm_bp
from .main_routes import main_bp
from .preset_routes import preset_bp
from .settings_routes import settings_bp
from .system_routes import system_bp
from .user_routes import user_bp

__all__ = [
    "main_bp",
    "settings_bp",
    "preset_bp",
    "llm_bp",
    "system_bp",
    "user_bp",
    "auth_bp",
    "calendar_bp",
    "admin_bp",
    "chat_history_bp",
]
