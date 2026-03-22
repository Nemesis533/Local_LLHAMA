"""
Wikipedia Image Orchestration Service

Handles Wikipedia image selection, verification, and fallback to image generation.
Extracted from chat_handler.py to separate Wikipedia-specific logic.

This service:
- Selects appropriate Wikipedia images from candidates
- Verifies image appropriateness using VLM (when enabled)
- Handles image deduplication in conversations
- Falls back to image generation when needed
"""

import re
import requests
from pathlib import Path

from ..shared_logger import LogLevel
from ..model_registry import ModelState, ModelType


class WikipediaImageOrchestrator:
    """
    Orchestrates Wikipedia image selection and verification workflow.
    Separated from ChatHandler for better testability and maintainability.
    """

    def __init__(self, media_service, model_registry, message_handler, command_llm, log_prefix="[WikiImg]"):
        """
        Initialize Wikipedia image orchestrator.

        @param media_service     MediaHandlingService for image operations
        @param model_registry   ModelRegistry for GPU coordination
        @param message_handler  MessageHandler for client communication
        @param command_llm      OllamaClient for LLM operations
        @param log_prefix       Prefix for log messages
        """
        self.media_service = media_service
        self.registry = model_registry
        self.message_handler = message_handler
        self.command_llm = command_llm
        self.log_prefix = log_prefix

    def get_thumbnail_url(self, url: str, max_width: int = 500) -> str:
        """
        Convert a Wikipedia/Wikimedia image URL to a thumbnail with max width.
        This scales images proportionally and improves load times.

        @param url The original Wikipedia image URL
        @param max_width Maximum width in pixels (default 500)
        @return Thumbnail URL or original if conversion not possible
        """
        if not url or "upload.wikimedia.org" not in url:
            return url

        # Skip if already a thumbnail with correct size
        if "/thumb/" in url and f"/{max_width}px-" in url:
            return url

        # Extract filename from original URL
        # Pattern: .../commons/4/4d/Filename.jpg or .../commons/thumb/4/4d/Filename.jpg/NNNpx-Filename.jpg
        try:
            if "/thumb/" in url:
                # Already a thumb, just need to adjust size - remove the sized part at the end
                url = url.rsplit("/", 1)[0]

            # Now convert to thumb format
            # .../commons/4/4d/File.jpg → .../commons/thumb/4/4d/File.jpg/500px-File.jpg
            parts = url.split("/wikipedia/commons/")
            if len(parts) == 2:
                base = parts[0]
                path_and_file = parts[1]
                filename = path_and_file.split("/")[-1]
                return f"{base}/wikipedia/commons/thumb/{path_and_file}/{max_width}px-{filename}"
        except Exception:
            pass

        return url

    def select_image(self, wiki_data: dict, user_query: str, conversation_id: str = None, 
                    client_id: str = None) -> str:
        """
        Return the first Wikipedia image from the candidates list.
        If user wants a better image, they can ask again and the system will use VLM
        to understand what was wrong, then generate a more appropriate image.

        @param wiki_data        The wikipedia_image_request sentinel dict
        @param user_query       The original user message (used for context)
        @param conversation_id  Conversation UUID (unused now - no deduplication)
        @param client_id        Client ID for sending status messages
        @return URL of the first image, or None if no images available
        """
        candidates = wiki_data.get("candidates", [])
        fallback_url = wiki_data.get("fallback_url")

        # Return first candidate, or fallback, or None
        if candidates:
            return candidates[0]["url"]
        return fallback_url

    def verify_image_appropriateness(self, image_url: str, user_query: str, 
                                    image_title: str = "") -> tuple:
        """
        Use vision model to verify if a Wikipedia image is appropriate for the user's query.

        NOTE: This is disabled by default (wikipedia_image_verification_enabled: false).
        Strategy: Show Wikipedia images immediately on first request for speed.
        Only enable verification when user explicitly asks to improve/refine the image selection.
        Falls back to image generation if no appropriate images found after verification.
        
        The VLM response is passed through the main LLM for rephrasing to maintain consistent
        conversation tone and style.

        @param image_url    URL of the Wikipedia image to verify
        @param user_query   The original user question/query
        @param image_title  Title/caption of the image
        @return Tuple of (is_appropriate: bool, explanation: str)
        """
        settings = self.media_service._get_image_analysis_settings()
        if not settings.get("wikipedia_image_verification_enabled", True):
            # Verification disabled, assume appropriate
            return True, "Verification disabled"

        llava_model = settings.get("llava_model", "llava:13b-v1.6-vicuna-q8_0")
        ollama_host = getattr(self.command_llm, "host", None)
        ollama_model = getattr(self.command_llm, "model", None)

        if not ollama_host:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Cannot verify Wikipedia image: no Ollama host configured"
            )
            return True, "No vision model available"

        try:
            from ..image_generation import ImageGenerationManager as _IM

            host_url = _IM._normalize_ollama_host(ollama_host)

            # Prepare the image
            try:
                image_b64 = self.media_service._prepare_image_for_llava(image_url)
            except Exception as img_err:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not prepare Wikipedia image for verification: {img_err}"
                )
                return False, f"Image load failed: {img_err}"

            # Offload main LLM to free VRAM for vision model
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Offloading main model for Wikipedia image verification"
            )
            try:
                # Mark LLM as unloading in registry
                self.registry.set_model_state(ollama_model, ModelState.UNLOADING)
                
                requests.post(
                    f"{host_url}/api/generate",
                    json={"model": ollama_model, "keep_alive": 0},
                    timeout=10,
                )
                
                # Mark as unloaded
                self.registry.set_model_state(ollama_model, ModelState.UNLOADED)
            except Exception as e:
                print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to offload LLM: {e}")
                self.registry.set_model_state(ollama_model, ModelState.ERROR, str(e))

            # Build verification prompt
            caption_part = f' with caption: "{image_title}"' if image_title else ""
            verification_prompt = (
                f'The user asked: "{user_query}"\n\n'
                f"This image is from Wikipedia{caption_part}.\n\n"
                f"Question: Is this image a good match for what the user is asking about? "
                f"Answer with YES or NO, followed by a brief 1-2 sentence explanation of why it matches or doesn't match their query."
            )

            # Register VLM with registry and mark as loading
            self.registry.register_model(
                name=llava_model,
                model_type=ModelType.VLM,
                host=host_url,
                description="Vision-language model for image analysis",
                initial_state=ModelState.UNLOADED
            )
            self.registry.set_model_state(llava_model, ModelState.LOADING)
            
            # Call LLaVA (increased timeout to allow for model loading - can take 60-90s)
            resp = requests.post(
                f"{host_url}/api/generate",
                json={
                    "model": llava_model,
                    "prompt": verification_prompt,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 100},
                },
                timeout=120,
            )
            
            # Mark VLM as loaded
            self.registry.set_model_state(llava_model, ModelState.LOADED)

            if resp.status_code != 200:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Vision model verification failed with status {resp.status_code}"
                )
                return False, "Vision model request failed"

            vlm_raw_response = resp.json().get("response", "").strip()

            # Unload LLaVA and reload main model
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Unloading vision model, loading main model"
            )
            try:
                # Mark VLM as unloading
                self.registry.set_model_state(llava_model, ModelState.UNLOADING)
                
                # Unload LLaVA
                requests.post(
                    f"{host_url}/api/generate",
                    json={"model": llava_model, "keep_alive": 0},
                    timeout=10,
                )
                
                # Mark VLM as unloaded
                self.registry.set_model_state(llava_model, ModelState.UNLOADED)
                
                # Wait a moment for VLM to fully unload
                import time
                time.sleep(1)
                
                # Reload main LLM
                self.registry.set_model_state(ollama_model, ModelState.LOADING)
                requests.post(
                    f"{host_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": "1",
                        "stream": False,
                        "options": {"num_predict": 1},
                    },
                    timeout=30,
                )
                self.registry.set_model_state(ollama_model, ModelState.LOADED)
                
            except Exception as e:
                print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Model transition failed: {e}")
            
            # Rephrase VLM response through main LLM for better tone
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Rephrasing VLM response through main LLM"
            )
            try:
                rephrase_prompt = (
                    f"Rephrase this image analysis in a conversational way (1-2 sentences): {vlm_raw_response}"
                )
                rephrase_resp = requests.post(
                    f"{host_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": rephrase_prompt,
                        "stream": False,
                        "options": {"temperature": 0.7, "num_predict": 80},
                    },
                    timeout=30,
                )
                if rephrase_resp.status_code == 200:
                    response_text = rephrase_resp.json().get("response", vlm_raw_response).strip()
                else:
                    response_text = vlm_raw_response
            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to rephrase VLM response: {e}"
                )
                response_text = vlm_raw_response

            # Parse the response
            is_appropriate = response_text.upper().startswith("YES")

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Wikipedia image verification: "
                f"{'✓ APPROPRIATE' if is_appropriate else '✗ NOT APPROPRIATE'} - {response_text[:100]}"
            )

            return is_appropriate, response_text

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Wikipedia image verification failed: {e}"
            )
            # Try to reload main model even on error
            try:
                from ..image_generation import ImageGenerationManager as _IM

                host_url = _IM._normalize_ollama_host(ollama_host)
                requests.post(
                    f"{host_url}/api/generate",
                    json={"model": ollama_model, "prompt": "", "keep_alive": "5m"},
                    timeout=10,
                )
            except Exception:
                pass
            return False, f"Verification error: {str(e)}"

    @staticmethod
    def normalize_filename(url: str) -> str:
        """
        Normalize Wikipedia image filename for deduplication.
        Removes size prefixes like "500px-" to match different thumbnail sizes.

        @param url Wikipedia image URL
        @return Normalized filename
        """
        fname = url.rstrip("/").split("/")[-1].lower()
        # Remove NNNpx- prefix if present (e.g., 500px-File.jpg → File.jpg)
        fname = re.sub(r"^\d+px-", "", fname)
        return fname
