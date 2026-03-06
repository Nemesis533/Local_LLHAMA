"""
@file image_routes.py
@brief Flask routes for serving and downloading user-generated images.

All routes require authentication. Ownership is verified against the DB
so users can only access their own images.
"""

from pathlib import Path

from flask import Blueprint, abort, current_app, send_file
from flask_login import current_user, login_required

from ..error_handler import FlaskErrorHandler
from ..shared_logger import LogLevel

image_bp = Blueprint("images", __name__)


def _get_pg_client():
    """Retrieve PostgreSQLClient from the app's SERVICE_INSTANCE."""
    service = current_app.config.get("SERVICE_INSTANCE")
    return getattr(service, "pg_client", None) if service else None


def _resolve_image(image_id: str) -> dict:
    """
    Look up an image record in the DB and verify ownership.

    @param image_id UUID string.
    @return Image record dict.
    @raises 404 if not found, 403 if not the owner.
    """
    pg_client = _get_pg_client()
    if pg_client is None:
        abort(503, description="Database unavailable")

    try:
        row = pg_client.execute_one(
            "SELECT id, user_id, filename FROM generated_images WHERE id = %s",
            (image_id,),
        )
    except Exception as e:
        print(f"[ImageRoutes] [{LogLevel.CRITICAL.name}] DB error: {e}")
        abort(500, description="Database error")

    if row is None:
        abort(404, description="Image not found")

    record = {
        "id": row[0],
        "user_id": row[1],
        "filename": row[2],
    }

    if record["user_id"] != current_user.id:
        abort(403, description="Access denied")

    return record


def _image_storage_base() -> Path:
    """Return the base path for generated image storage."""
    service = current_app.config.get("SERVICE_INSTANCE")
    if service:
        base = getattr(service, "base_path", None)
        if base:
            return Path(base) / "data" / "generated_images"
    # Fallback: derive from this file's location
    return Path(__file__).parent.parent / "data" / "generated_images"


@image_bp.route("/api/images/<image_id>", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def serve_image(image_id: str):
    """
    Serve the raw image file.

    @param image_id UUID of the generated image.
    """
    record = _resolve_image(image_id)
    image_path = _image_storage_base() / str(record["user_id"]) / record["filename"]

    if not image_path.exists():
        abort(404, description="Image file not found on disk")

    return send_file(str(image_path), mimetype="image/png")


@image_bp.route("/api/images/<image_id>/download", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def download_image(image_id: str):
    """
    Download the image as an attachment.

    @param image_id UUID of the generated image.
    """
    record = _resolve_image(image_id)
    image_path = _image_storage_base() / str(record["user_id"]) / record["filename"]

    if not image_path.exists():
        abort(404, description="Image file not found on disk")

    # Use the title as the download filename if we can fetch it
    pg_client = _get_pg_client()
    download_name = record["filename"]
    try:
        row = pg_client.execute_one(
            "SELECT title FROM generated_images WHERE id = %s",
            (image_id,),
        )
        if row:
            title = row[0] or ""
            safe_title = "".join(
                c if c.isalnum() or c in " _-" else "_" for c in title
            ).strip()
            if safe_title:
                download_name = f"{safe_title}.png"
    except Exception:
        pass

    return send_file(
        str(image_path),
        mimetype="image/png",
        as_attachment=True,
        download_name=download_name,
    )
