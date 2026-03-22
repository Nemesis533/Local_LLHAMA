"""
Media handling service for image generation and analysis.
Extracted from chat_handler.py to separate media concerns from chat orchestration.

This service handles:
- Image generation via Stable Diffusion
- Image analysis via LLaVA vision model
- Model coordination with ModelRegistry
- GPU memory management (offloading/loading models)
"""

import os
import io
import json
import base64
import threading
import traceback
import time
from pathlib import Path
import requests

# Import from PIL only when needed
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

from ..shared_logger import LogLevel
from ..model_registry import ModelState, ModelType


class MediaHandlingService:
    """
    Handles all media-related operations (image generation and analysis).
    Separated from ChatHandler for better organization and testability.
    """

    def __init__(self, model_registry, message_handler, command_llm, log_prefix="[Media]"):
        """
        Initialize the media handling service.

        @param model_registry    ModelRegistry instance for GPU memory coordination
        @param message_handler   MessageHandler for sending status/results  to clients
        @param command_llm       OllamaClient for LLM operations
        @param log_prefix        Prefix for log messages
        """
        self.registry = model_registry
        self.message_handler = message_handler
        self.command_llm = command_llm
        self.log_prefix = log_prefix
        self._image_manager = None

    # =========================================================
    # Image Generation Settings & Manager
    # =========================================================

    def _get_image_settings(self) -> dict:
        """
        Load image generation settings from object_settings.json.

        @return Dict with all ImageGenerationManager config keys.
        """
        defaults = {
            "enabled": True,
            "model_id": "stabilityai/stable-diffusion-3.5-large-turbo",
            "cache_dir": "/mnt/fast_storage/diffusers",
            "num_steps": 4,
            "guidance_scale": 0.0,
            "max_sequence_length": 512,
            "cuda_device": "cuda:0",
            "output_format": "png",
            "keep_pipeline_loaded": False,
            "keep_pipeline_loaded_min_vram_gb": 10.0,
        }
        try:
            settings_path = (
                Path(__file__).parent.parent / "settings" / "object_settings.json"
            )
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                section = data.get("ImageGenerationManager", {})
                for key in defaults:
                    entry = section.get(key, {})
                    if isinstance(entry, dict) and "value" in entry:
                        defaults[key] = entry["value"]
        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not load image settings: {e}"
            )
        return defaults

    def _get_image_manager(self):
        """
        Return a (lazily-created) ImageGenerationManager instance.

        @return ImageGenerationManager configured from object_settings.json.
        """
        if self._image_manager is not None:
            return self._image_manager

        from ..image_generation import ImageGenerationManager

        settings = self._get_image_settings()
        storage_base = Path(__file__).parent.parent / "data" / "generated_images"
        self._image_manager = ImageGenerationManager(
            model_id=settings["model_id"],
            cache_dir=settings["cache_dir"],
            hf_token=os.environ.get("HF_TOKEN"),
            storage_base_path=str(storage_base),
            cuda_device=settings["cuda_device"],
            num_steps=settings["num_steps"],
            guidance_scale=settings["guidance_scale"],
            max_sequence_length=settings["max_sequence_length"],
            output_format=settings["output_format"],
            keep_pipeline_loaded=settings["keep_pipeline_loaded"],
            keep_pipeline_loaded_min_vram_gb=settings[
                "keep_pipeline_loaded_min_vram_gb"
            ],
        )
        return self._image_manager

    def _get_image_analysis_settings(self) -> dict:
        """
        Load image analysis settings from object_settings.json.

        @return Dict with ImageAnalysisManager config keys.
        """
        defaults = {
            "enabled": True,
            "llava_model": "llava:13b-v1.6-vicuna-q8_0",
            "wikipedia_image_verification_enabled": True,
        }
        try:
            settings_path = (
                Path(__file__).parent.parent / "settings" / "object_settings.json"
            )
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                section = data.get("ImageAnalysisManager", {})
                for key in defaults:
                    entry = section.get(key, {})
                    if isinstance(entry, dict) and "value" in entry:
                        defaults[key] = entry["value"]
        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not load image analysis settings: {e}"
            )
        return defaults

    # =========================================================
    # Image Generation Support
    # =========================================================

    def _generate_image_intro(
        self, prompt: str, title_hint: str, ollama_host: str, model: str
    ) -> tuple:
        """
        Ask Ollama for a title and brief intro comment for the image.

        Makes a raw HTTP call to Ollama (not stored in conversation history).

        @param prompt       The image generation prompt.
        @param title_hint   Suggested title from user (may be empty).
        @param ollama_host  Ollama server URL.
        @param model        Ollama model name.
        @return Tuple of (title: str, comment: str).
        """
        default_title = title_hint or "Generated Image"
        default_comment = "Here's the image I generated for you!"

        if not ollama_host or not model:
            return default_title, default_comment

        # Check if model is loaded and ready
        if not self.registry.can_use_model(model):
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                f"Model {model} is not loaded, skipping intro generation"
            )
            return default_title, default_comment

        try:
            from ..image_generation import ImageGenerationManager as _IM
            from ..llm_prompts import IMAGE_INTRO_USER_PROMPT

            host = _IM._normalize_ollama_host(ollama_host)

            title_instruction = (
                f'The user has given this title: "{title_hint}". Keep it exactly.'
                if title_hint
                else "Invent a short, creative title (3-6 words)."
            )

            system = (
                "You are a helpful assistant. Respond ONLY with valid JSON — "
                "no markdown, no code fences, no extra text."
            )
            user_msg = IMAGE_INTRO_USER_PROMPT.format(
                description=prompt,
                title_instruction=title_instruction,
            )

            resp = requests.post(
                f"{host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 120},
                },
                timeout=60,
            )

            if resp.status_code == 200:
                content = resp.json().get("message", {}).get("content", "")
                # Strip possible markdown fences
                content = content.strip().strip("```json").strip("```").strip()

                if not content:
                    print(
                        f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                        f"LLM returned empty content for image intro"
                    )
                    return default_title, default_comment

                parsed = json.loads(content)
                title = parsed.get("title") or default_title
                comment = parsed.get("comment") or default_comment
                return title, comment
            else:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                    f"Image intro request failed with status {resp.status_code}"
                )

        except json.JSONDecodeError as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                f"Could not parse image intro JSON: {e}. Content was: {content[:100]}"
            )
        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not get image intro from LLM: {e}"
            )

        return default_title, default_comment

    # =========================================================
    # Image Preparation for LLaVA
    # =========================================================

    def _prepare_image_for_llava(self, image_source: str) -> str:
        """
        Fetch/decode an image, resize to the best-matching LLaVA 1.6 resolution,
        and return it as a base64-encoded PNG string.

        LLaVA 1.6 natively supports three tile resolutions (up to 4× the base
        336×336 pixel budget):
            672×672  — square  (ratio ≈ 1.0)
            336×1344 — portrait (ratio ≈ 0.25)
            1344×336 — landscape (ratio ≈ 4.0)

        The resolution whose aspect ratio is closest to the source image is
        chosen. Resizing uses LANCZOS for maximum quality.

        @param image_source  URL, data-URI, or raw base64 string of the image.
        @return Base64-encoded PNG string ready to embed in the Ollama API payload.
        """
        import requests as _req

        if PILImage is None:
            raise ImportError("PIL (Pillow) is required for image processing")

        # LLaVA 1.6 supported resolutions: (width, height)
        LLAVA_RESOLUTIONS = [
            (672, 672),  # square     — aspect 1.0
            (336, 1344),  # portrait   — aspect 0.25
            (1344, 336),  # landscape  — aspect 4.0
        ]

        # --- Load image bytes ---
        if image_source.startswith("/api/images/"):
            # Handle relative URLs from uploaded images route
            image_id = image_source.split("/")[-1]

            # Get database client to look up image location
            pg_client = getattr(self.command_llm, "pg_client", None)

            if not pg_client:
                raise ValueError(
                    f"Cannot load uploaded image without database connection: {image_source}"
                )

            try:
                # Look up image in database
                row = pg_client.execute_one(
                    "SELECT user_id, filename, model_id FROM generated_images WHERE id = %s",
                    (image_id,),
                )

                if not row:
                    raise ValueError(f"Image not found in database: {image_id}")

                user_id, filename, model_id = row
                is_uploaded = model_id == "uploaded"

                # Build file path based on image type
                if is_uploaded:
                    base_path = (
                        Path(__file__).parent.parent / "data" / "uploaded_images"
                    )
                else:
                    base_path = (
                        Path(__file__).parent.parent / "data" / "generated_images"
                    )

                image_path = base_path / str(user_id) / filename

                if not image_path.exists():
                    raise ValueError(f"Image file not found on disk: {image_path}")

                with open(image_path, "rb") as fh:
                    image_bytes = fh.read()

            except Exception as e:
                raise ValueError(f"Failed to load uploaded image {image_id}: {e}")

        elif image_source.startswith("data:"):
            # data:image/png;base64,<data>
            _, encoded = image_source.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        elif image_source.startswith("http://") or image_source.startswith("https://"):
            # Add headers to avoid 403 errors from Wikipedia and other sites
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            resp = _req.get(image_source, timeout=15, headers=headers)
            resp.raise_for_status()
            image_bytes = resp.content
        else:
            # Assume raw base64 or file path
            try:
                image_bytes = base64.b64decode(image_source)
            except Exception:
                # Try as file path
                with open(image_source, "rb") as fh:
                    image_bytes = fh.read()

        # Validate image_bytes before attempting to open
        if not image_bytes:
            raise ValueError(f"Image source yielded empty data: {image_source[:100]}")

        if len(image_bytes) < 10:
            raise ValueError(
                f"Image data too small ({len(image_bytes)} bytes), likely corrupted. "
                f"Source: {image_source[:100]}"
            )

        # Create BytesIO and ensure pointer is at the beginning
        image_buffer = io.BytesIO(image_bytes)
        image_buffer.seek(0)

        try:
            image = PILImage.open(image_buffer)
        except Exception as e:
            raise ValueError(
                f"Cannot identify image file. Received {len(image_bytes)} bytes from source. "
                f"Source type: {type(image_source).__name__}, "
                f"Source preview: {image_source[:100] if isinstance(image_source, str) else 'N/A'}. "
                f"Original error: {e}"
            )
        if image.mode != "RGB":
            image = image.convert("RGB")

        # --- Pick best resolution by closest aspect ratio ---
        orig_w, orig_h = image.size
        orig_ratio = orig_w / orig_h
        target_w, target_h = min(
            LLAVA_RESOLUTIONS,
            key=lambda r: abs((r[0] / r[1]) - orig_ratio),
        )

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Scaling image {orig_w}×{orig_h} "
            f"(ratio {orig_ratio:.2f}) → {target_w}×{target_h} for LLaVA"
        )

        image = image.resize((target_w, target_h), PILImage.LANCZOS)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # =========================================================
    # Main Entry Points
    # =========================================================

    def handle_image_generation(
        self, image_request: dict, client_id: str, conversation_id: str
    ):
        """
        Orchestrate image generation in a background thread.

        Flow:
          1. Get title + comment from LLM (while LLM is still loaded)
          2. Show "Generating image…" status to user
          3. Spawn background thread:
               a. Offload Ollama model (free VRAM)
               b. Load SD3.5 pipeline, generate image
               c. Save to disk + DB
               d. Unload pipeline
               e. Push image_ready message to web_server_message_queue

        @param image_request  Dict with keys: prompt, title, user_id.
        @param client_id      Socket client identifier.
        @param conversation_id UUID of the conversation.
        """
        settings = self._get_image_settings()
        if not settings.get("enabled", True):
            self.message_handler.send_to_web_server(
                f"{self.log_prefix} [Error]: Image generation is disabled in system settings.",
                client_id=client_id
            )
            return

        prompt = image_request.get("prompt", "")
        title_hint = image_request.get("title", "")
        user_id_val = image_request.get("user_id")
        user_id = int(user_id_val) if user_id_val is not None else None

        if not prompt:
            self.message_handler.send_to_web_server(
                f"{self.log_prefix} [Error]: No image prompt was provided.",
                client_id=client_id
            )
            return

        # Step 1: Get title + intro comment from LLM while it is still loaded
        ollama_host = getattr(self.command_llm, "host", None)
        ollama_model = getattr(self.command_llm, "model", None)

        # Check if LLM is available before trying to get intro
        if self.registry.can_use_model(ollama_model):
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] "
                f"Requesting image intro from LLM (host={ollama_host}, model={ollama_model})"
            )
            title, comment = self._generate_image_intro(
                prompt, title_hint, ollama_host, ollama_model
            )
        else:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] "
                f"LLM not loaded, using default title/comment for image"
            )
            title = title_hint or "Generated Image"
            comment = "Here's the image I generated for you!"

        # Step 2: Send status to client — shows the spinner
        status_msg = f"{self.log_prefix} [Status]: Generating image: {title}"
        self.message_handler.send_to_web_server(status_msg, client_id=client_id)

        # Step 3: Capture everything in thread closure and spawn
        pg_client = getattr(self.command_llm, "pg_client", None)
        message_handler = self.message_handler
        log_prefix = self.log_prefix

        def _send_status(text: str):
            message_handler.send_to_web_server(
                f"{log_prefix} [Status]: {text}", client_id=client_id
            )

        def _generation_thread():
            image_manager = self._get_image_manager()
            try:
                # Offload Ollama model to free VRAM
                _send_status("Freeing GPU memory...")
                try:
                    if ollama_host and ollama_model:
                        from ..image_generation import ImageGenerationManager as _IM
                        host_url = _IM._normalize_ollama_host(ollama_host)
                        requests.post(
                            f"{host_url}/api/generate",
                            json={"model": ollama_model, "keep_alive": 0},
                            timeout=10,
                        )
                except Exception:
                    pass  # Non-critical

                # Generate the image
                _send_status(f"Generating: {title}...")
                result = image_manager.generate_image(
                    prompt=prompt,
                    user_id=user_id,
                    title=title,
                    conversation_id=conversation_id,
                )

                if result and result.get("success"):
                    image_id = result.get("image_id")
                    image_url = result.get("image_url", f"/api/images/{image_id}")

                    # Send image_ready message
                    message_handler.send_image_ready(
                        image_url=image_url,
                        image_id=image_id,
                        title=title,
                        comment=comment,
                        client_id=client_id,
                    )

                    print(
                        f"{log_prefix} [{LogLevel.INFO.name}] Image generation complete: {image_id}"
                    )
                else:
                    error_msg = result.get("error", "Unknown error") if result else "No result"
                    _send_status(f"Image generation failed: {error_msg}")

            except Exception as e:
                print(
                    f"{log_prefix} [{LogLevel.CRITICAL.name}] "
                    f"Image generation thread error: {type(e).__name__}: {e}\n"
                    + traceback.format_exc()
                )
                _send_status(f"Image generation failed: {e}")
            finally:
                # Reload main LLM
                try:
                    if ollama_host and ollama_model:
                        from ..image_generation import ImageGenerationManager as _IM
                        host_url = _IM._normalize_ollama_host(ollama_host)
                        requests.post(
                            f"{host_url}/api/generate",
                            json={"model": ollama_model, "prompt": "", "keep_alive": "5m"},
                            timeout=10,
                        )
                except Exception:
                    pass

        thread = threading.Thread(target=_generation_thread, daemon=True)
        thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Image generation thread started for client {client_id}"
        )

    def handle_image_analysis(
        self, analysis_request: dict, client_id: str, conversation_id: str, 
        context_manager=None, pending_user_queries=None
    ):
        """
        Analyse an image with LLaVA in a background thread, bypassing the main LLM.

        Flow:
          1. Show "Analysing image…" status to the user.
          2. Spawn a background thread that:
               a. Offloads the main Ollama model to free VRAM.
               b. Scales the image to the best LLaVA 1.6 resolution.
               c. Calls LLaVA via /api/generate with the image + query.
               d. Streams the answer directly to the client.
               e. Unloads LLaVA and warms the main model back up.

        @param analysis_request Dict with keys: image, query, user_id.
        @param client_id        Socket client identifier.
        @param conversation_id  UUID of the conversation.
        @param context_manager  ChatContextManager for history storage
        @param pending_user_queries  Dict mapping client_id to original user query
        """
        settings = self._get_image_analysis_settings()
        if not settings.get("enabled", True):
            self.message_handler.send_to_web_server(
                f"{self.log_prefix} [Error]: Image analysis is disabled in system settings.",
                client_id=client_id
            )
            return

        image_source = analysis_request.get("image", "")
        query = analysis_request.get("query", "Describe what you see in this image.")
        user_id_val = analysis_request.get("user_id")
        user_id = int(user_id_val) if user_id_val is not None else None  # noqa: F841
        uploaded_image_id = analysis_request.get("uploaded_image_id")  # UUID if uploaded

        if not image_source:
            self.message_handler.send_to_web_server(
                f"{self.log_prefix} [Error]: No image source was provided.",
                client_id=client_id
            )
            return

        llava_model = settings.get("llava_model", "llava:13b-v1.6-vicuna-q8_0")
        ollama_host = getattr(self.command_llm, "host", None)
        ollama_model = getattr(self.command_llm, "model", None)

        original_query = pending_user_queries.pop(client_id, query) if pending_user_queries else query

        status_msg = f"{self.log_prefix} [Status]: Analysing image…"
        self.message_handler.send_to_web_server(status_msg, client_id=client_id)

        pg_client = getattr(self.command_llm, "pg_client", None)
        message_handler = self.message_handler
        log_prefix = self.log_prefix

        def _send_status(text: str):
            message_handler.send_to_web_server(
                f"{log_prefix} [Status]: {text}", client_id=client_id
            )

        def _analysis_thread():
            try:
                from ..image_generation import ImageGenerationManager as _IM

                host_url = _IM._normalize_ollama_host(ollama_host)

                # Step 1: scale image to best LLaVA resolution
                _send_status("Preparing image…")
                try:
                    image_b64 = self._prepare_image_for_llava(image_source)
                except Exception as img_err:
                    print(
                        f"{log_prefix} [{LogLevel.CRITICAL.name}] Image prep failed: {img_err}"
                    )
                    _send_status(f"Could not load image: {img_err}")
                    return

                # Step 2: offload main LLM to free VRAM
                _send_status("Freeing GPU memory for vision model…")
                try:
                    requests.post(
                        f"{host_url}/api/generate",
                        json={"model": ollama_model, "keep_alive": 0},
                        timeout=10,
                    )
                except Exception:
                    pass  # non-critical

                # Step 3: build system prompt (with optional safety prepend)
                from ..llm_prompts import (
                    IMAGE_ANALYSIS_PROMPT,
                    IMAGE_ANALYSIS_SAFETY_PROMPT,
                    is_safety_enabled,
                )

                system_prompt = (
                    IMAGE_ANALYSIS_SAFETY_PROMPT + "\n\n" + IMAGE_ANALYSIS_PROMPT
                    if is_safety_enabled()
                    else IMAGE_ANALYSIS_PROMPT
                )

                # Step 4: call LLaVA
                _send_status("Running vision model…")
                resp = requests.post(
                    f"{host_url}/api/generate",
                    json={
                        "model": llava_model,
                        "prompt": query,
                        "images": [image_b64],
                        "system": system_prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 1024},
                    },
                    timeout=120,
                )

                if resp.status_code != 200:
                    _send_status(f"Vision model returned HTTP {resp.status_code}")
                    return

                response_text = resp.json().get("response", "").strip()

                # Step 5: stream the answer directly to the client
                chunk_size = 5
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i : i + chunk_size]
                    is_complete = i + chunk_size >= len(response_text)
                    message_handler.send_streaming_chunk(
                        chunk, client_id=client_id, is_complete=is_complete
                    )

                # Step 6: persist to conversation history and DB
                if context_manager:
                    context_manager.add_to_history(client_id, original_query, response_text)
                    
                if pg_client and conversation_id:
                    try:
                        from datetime import datetime

                        pg_client.execute(
                            """
                            INSERT INTO conversation_history 
                            (conversation_id, role, content, timestamp, image_id)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (conversation_id, "user", original_query, datetime.now(), uploaded_image_id),
                        )
                        pg_client.execute(
                            """
                            INSERT INTO conversation_history 
                            (conversation_id, role, content, timestamp)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (conversation_id, "assistant", response_text, datetime.now()),
                        )
                    except Exception as db_err:
                        print(
                            f"{log_prefix} [{LogLevel.WARNING.name}] Failed to save analysis to DB: {db_err}"
                        )

                print(
                    f"{log_prefix} [{LogLevel.INFO.name}] Image analysis complete for client {client_id}"
                )

            except Exception as e:
                print(
                    f"{log_prefix} [{LogLevel.CRITICAL.name}] "
                    f"Image analysis thread error: {type(e).__name__}: {e}\n"
                    + traceback.format_exc()
                )
                _send_status(f"Image analysis failed: {e}")
            finally:
                # Step 7: unload LLaVA then warm up the main model
                try:
                    from ..image_generation import ImageGenerationManager as _IM

                    host_url = _IM._normalize_ollama_host(ollama_host)
                    
                    # Unload LLaVA
                    requests.post(
                        f"{host_url}/api/generate",
                        json={"model": llava_model, "keep_alive": 0},
                        timeout=10,
                    )
                    
                    # Warm up main model
                    requests.post(
                        f"{host_url}/api/generate",
                        json={"model": ollama_model, "prompt": "", "keep_alive": "5m"},
                        timeout=10,
                    )
                except Exception:
                    pass

        thread = threading.Thread(target=_analysis_thread, daemon=True)
        thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Image analysis thread started for client {client_id}"
        )
