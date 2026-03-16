"""
@file image_routes.py
@brief Flask routes for serving, downloading, and uploading user images.

All routes require authentication. Ownership is verified against the DB
so users can only access their own images.
"""

import uuid
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ._service import get_service
from ..error_handler import FlaskErrorHandler
from ..shared_logger import LogLevel

image_bp = Blueprint("images", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _get_pg_client():
    """Retrieve PostgreSQLClient from the app's SERVICE_INSTANCE."""
    return getattr(get_service(), "pg_client", None)


def _resolve_image(image_id: str) -> dict:
    """
    Look up an image record in the DB and verify ownership.

    @param image_id UUID string.
    @return Image record dict with 'is_uploaded' flag.
    @raises 404 if not found, 403 if not the owner.
    """
    pg_client = _get_pg_client()
    if pg_client is None:
        abort(503, description="Database unavailable")

    try:
        row = pg_client.execute_one(
            "SELECT id, user_id, filename, model_id FROM generated_images WHERE id = %s",
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
        "model_id": row[3],
        "is_uploaded": row[3] == "uploaded",
    }

    if record["user_id"] != current_user.id:
        abort(403, description="Access denied")

    return record


def _image_storage_base() -> Path:
    """Return the base path for generated image storage."""
    base = getattr(get_service(), "base_path", None)
    if base:
        return Path(base) / "data" / "generated_images"
    # Fallback: derive from this file's location
    return Path(__file__).parent.parent / "data" / "generated_images"


def _uploaded_image_storage_base() -> Path:
    """Return the base path for uploaded image storage."""
    base = getattr(get_service(), "base_path", None)
    if base:
        return Path(base) / "data" / "uploaded_images"
    # Fallback: derive from this file's location
    return Path(__file__).parent.parent / "data" / "uploaded_images"


def _allowed_file(filename: str) -> bool:
    """Check if filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@image_bp.route("/api/images/<image_id>", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def serve_image(image_id: str):
    """
    Serve the raw image file (generated or uploaded).

    @param image_id UUID of the image.
    """
    record = _resolve_image(image_id)
    
    # Choose storage location based on whether it's uploaded or generated
    if record["is_uploaded"]:
        image_path = _uploaded_image_storage_base() / str(record["user_id"]) / record["filename"]
    else:
        image_path = _image_storage_base() / str(record["user_id"]) / record["filename"]

    if not image_path.exists():
        abort(404, description="Image file not found on disk")

    # Determine mimetype from extension
    ext = record["filename"].rsplit(".", 1)[1].lower() if "." in record["filename"] else "png"
    mimetype_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    mimetype = mimetype_map.get(ext, "image/png")

    return send_file(str(image_path), mimetype=mimetype)


@image_bp.route("/api/images/<image_id>/download", methods=["GET"])
@login_required
@FlaskErrorHandler.handle_route()
def download_image(image_id: str):
    """
    Download the image as an attachment.

    @param image_id UUID of the image (generated or uploaded).
    """
    record = _resolve_image(image_id)
    
    # Choose storage location based on whether it's uploaded or generated
    if record["is_uploaded"]:
        image_path = _uploaded_image_storage_base() / str(record["user_id"]) / record["filename"]
    else:
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


@image_bp.route("/api/images/upload", methods=["POST"])
@login_required
@FlaskErrorHandler.handle_route()
def upload_image():
    """
    Upload an image file.

    Accepts multipart/form-data with an 'image' file field.
    Returns JSON with image_id, url, and thumbnail_url.
    """
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"error": "File type not allowed. Use PNG, JPG, GIF, or WebP"}), 400

    # Check file size
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large. Max size is {MAX_FILE_SIZE // 1024 // 1024} MB"}), 400

    # Generate UUID and save file
    image_id = str(uuid.uuid4())
    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{image_id}.{ext}"

    # Ensure user directory exists
    user_dir = _uploaded_image_storage_base() / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = user_dir / filename
    file.save(str(file_path))
    print(f"[ImageRoutes] [{LogLevel.INFO.name}] Image uploaded: {file_path}")

    # Store in database using existing generated_images table
    pg_client = _get_pg_client()
    if pg_client:
        try:
            # Get conversation_id from form data if provided
            conversation_id = request.form.get("conversation_id", None)
            original_filename = secure_filename(file.filename)

            # Use generated_images table with model_id="uploaded" to distinguish uploaded images
            pg_client.execute_write(
                """
                INSERT INTO generated_images (id, user_id, conversation_id, filename, title, prompt, model_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    image_id,
                    current_user.id,
                    conversation_id,
                    filename,
                    f"Uploaded: {original_filename}",
                    f"User uploaded file: {original_filename}",
                    "uploaded",  # Special marker to distinguish from generated images
                ),
            )
            print(f"[ImageRoutes] [{LogLevel.INFO.name}] Uploaded image record saved to DB: {image_id}")
        except Exception as e:
            print(f"[ImageRoutes] [{LogLevel.WARNING.name}] DB insert failed: {e}")
            # Continue even if DB insert fails - file is saved

    return jsonify({
        "success": True,
        "image_id": image_id,
        "filename": filename,
        "original_filename": original_filename,
        "url": f"/api/images/{image_id}",
        "thumbnail_url": f"/api/images/{image_id}",  # Use unified endpoint
    })


# Removed separate serve_uploaded_image route - now handled by unified serve_image route
