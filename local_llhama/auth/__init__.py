"""
Authentication module for Local_LLHAMA
Provides SQLite-based authentication with single admin user.
"""

from .auth_manager import AuthManager
from .base import BaseManager
from .db_manager import DatabaseManager

__all__ = ["AuthManager", "BaseManager", "DatabaseManager"]
