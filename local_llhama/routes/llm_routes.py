# llm_routes.py
import time

import psutil
import requests
from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import login_required

from ..error_handler import FlaskErrorHandler

llm_bp = Blueprint("llm", __name__)


@llm_bp.route("/check-local-llm")
@login_required
def check_local_llm():
    """
    Checks if a process named 'local_llm' is currently running.
    """
    service = current_app.config["SERVICE_INSTANCE"]

    if not service._is_ip_allowed(request.remote_addr):
        abort(403, description="Access denied")

    process_found = any(
        "local_llm" in (proc.info["name"] or "")
        or "local_llm" in " ".join(proc.info.get("cmdline", []))
        for proc in psutil.process_iter(["pid", "name", "cmdline"])
        if service._safe_process(proc)
    )

    status = "up" if process_found else "down"
    return jsonify({"status": status, "timestamp": time.time()})


@llm_bp.route("/llm_status/<host>", methods=["GET"])
@FlaskErrorHandler.handle_route()
def llm_status(host):
    """
    Returns the online/offline status of the Local LLHAMA system on a given host.
    Checks if the Flask web server is responding on port 5001.
    No authentication required for monitoring purposes.
    """
    # If checking localhost or same host, return online immediately
    if host in ["localhost", "127.0.0.1"] or host == request.host.split(":")[0]:
        return {"host": host, "status": "online"}

    # Get port from host if included, otherwise use default port 5001
    if ":" in host:
        system_url = f"http://{host}"
    else:
        system_url = f"http://{host}:5001"

    # Try to reach the system's health check endpoint
    try:
        # Simple GET request to verify server is responding
        response = requests.get(f"{system_url}/system_status", timeout=3)
        if response.status_code == 200:
            return {"host": host, "status": "online"}
        else:
            return {"host": host, "status": "offline", "code": response.status_code}
    except requests.RequestException as e:
        return {"host": host, "status": "offline", "error": str(e)}


@llm_bp.route("/ollama_status", methods=["GET"])
@FlaskErrorHandler.handle_route()
def ollama_status():
    """
    Returns the online/offline status of the configured Ollama server.
    Reads host from system settings and checks API availability.
    No authentication required for monitoring purposes.
    """
    # Get Ollama host from system settings
    try:
        import json
        from pathlib import Path

        settings_file = (
            Path(__file__).parent.parent / "settings" / "system_settings.json"
        )
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)

            ollama_host = (
                settings.get("ollama", {})
                .get("host", {})
                .get("value", "localhost:11434")
            )
        else:
            ollama_host = "localhost:11434"
    except Exception as e:
        return {"status": "error", "error": f"Failed to read settings: {str(e)}"}

    # Ensure proper URL format
    if not ollama_host.startswith("http://") and not ollama_host.startswith("https://"):
        ollama_url = f"http://{ollama_host}"
    else:
        ollama_url = ollama_host

    # Try to reach the Ollama API endpoint
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        if response.status_code == 200:
            # Parse available models
            try:
                models_data = response.json()
                models = [
                    model.get("name", "unknown")
                    for model in models_data.get("models", [])
                ]
                return {
                    "host": ollama_host,
                    "status": "online",
                    "models": models,
                    "model_count": len(models),
                }
            except Exception:
                return {"host": ollama_host, "status": "online"}
        else:
            return {
                "host": ollama_host,
                "status": "offline",
                "code": response.status_code,
            }
    except requests.RequestException as e:
        return {"host": ollama_host, "status": "offline", "error": str(e)}


@llm_bp.route("/system_status", methods=["GET"])
@FlaskErrorHandler.handle_route()
def system_status():
    """
    Returns comprehensive status of the Local LLHAMA system.
    Checks both the web server and Ollama availability.
    No authentication required for monitoring purposes.
    """
    status_info = {
        "system": "Local LLHAMA",
        "web_server": "online",  # If this endpoint responds, web server is online
        "timestamp": time.time(),
    }

    # Check Ollama status
    try:
        import json
        from pathlib import Path

        settings_file = (
            Path(__file__).parent.parent / "settings" / "system_settings.json"
        )
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)

            ollama_host = (
                settings.get("ollama", {})
                .get("host", {})
                .get("value", "localhost:11434")
            )
        else:
            ollama_host = "localhost:11434"

        if not ollama_host.startswith("http://") and not ollama_host.startswith(
            "https://"
        ):
            ollama_url = f"http://{ollama_host}"
        else:
            ollama_url = ollama_host

        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=3)
            if response.status_code == 200:
                status_info["ollama"] = "online"
                status_info["ollama_host"] = ollama_host
            else:
                status_info["ollama"] = "offline"
                status_info["ollama_host"] = ollama_host
        except requests.RequestException:
            status_info["ollama"] = "offline"
            status_info["ollama_host"] = ollama_host
    except Exception as e:
        status_info["ollama"] = "error"
        status_info["ollama_error"] = str(e)

    return status_info
