from flask import current_app


def get_service():
    """Return the SERVICE_INSTANCE from the current Flask app config."""
    return current_app.config["SERVICE_INSTANCE"]
