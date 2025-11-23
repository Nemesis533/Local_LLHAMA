from .main_routes import main_bp
from .settings_routes import settings_bp
from .llm_routes import llm_bp
from .system_routes import system_bp
from .user_routes import user_bp
from .auth_routes import auth_bp

__all__ = ["main_bp", "settings_bp", "llm_bp", "system_bp", "user_bp", "auth_bp"]
