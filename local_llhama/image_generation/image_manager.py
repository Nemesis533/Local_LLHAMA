"""
@file image_manager.py
@brief Manages AI image generation using Stable Diffusion 3.5 with NF4 quantisation.

Handles the full lifecycle of image generation:
  - LLM offloading before loading the heavy diffusion pipeline
  - Lazy pipeline loading and explicit unloading after each generation
  - Per-user image storage and database persistence
"""

# === System Imports ===
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# === Custom Imports ===
from ..shared_logger import LogLevel

CLASS_PREFIX = "[ImageManager]"


class ImageGenerationManager:
    """
    @class ImageGenerationManager
    @brief Manages the Stable Diffusion 3.5 image generation pipeline.

    Follows a load-on-demand, unload-after-use strategy to coexist with
    the Ollama LLM on systems with limited VRAM.

    Pipeline is never kept in memory between requests. Before loading,
    the Ollama model is offloaded to free GPU memory.
    """

    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-3.5-large-turbo",
        cache_dir: str = "/mnt/fast_storage/diffusers",
        hf_token: str = None,
        storage_base_path: str = None,
        cuda_device: str = "auto",
        num_steps: int = 4,
        guidance_scale: float = 0.0,
        max_sequence_length: int = 512,
    ):
        """
        @brief Initialise manager with config. Does NOT load the pipeline.

        @param model_id   HuggingFace model repo ID for the diffusion model.
        @param cache_dir  Local path where model weights are cached.
        @param hf_token   HuggingFace API token (reads HF_TOKEN env var if None).
        @param storage_base_path Root folder for saving generated images.
        @param cuda_device Device string: 'auto', 'cpu', 'cuda:0', etc.
        @param num_steps  Inference steps (default 4 for SD3.5-turbo).
        @param guidance_scale CFG scale (0.0 for turbo variant).
        @param max_sequence_length Maximum token length for T5 text encoder.
        """
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.storage_base_path = storage_base_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "generated_images",
        )
        self.cuda_device = cuda_device
        self.num_steps = num_steps
        self.guidance_scale = guidance_scale
        self.max_sequence_length = max_sequence_length

        # Pipeline is loaded lazily
        self._pipeline = None

        print(
            f"{CLASS_PREFIX} [{LogLevel.INFO.name}] ImageGenerationManager initialised. "
            f"model={model_id}, storage={self.storage_base_path}"
        )

    # === Storage ===

    def ensure_storage_dir(self, user_id: int) -> Path:
        """
        @brief Create user-specific storage directory if it does not exist.

        @param user_id Numeric user ID.
        @return Path to the user's image directory.
        """
        user_dir = Path(self.storage_base_path) / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    # === Ollama offloading ===

    def offload_ollama_model(self, ollama_host: str, model_name: str) -> bool:
        """
        @brief Unload the Ollama model from GPU memory.

        Sends a keep_alive=0 request to Ollama so it releases VRAM
        before the heavy diffusion pipeline is loaded.

        @param ollama_host Ollama server URL (e.g. "http://192.168.1.10:11434").
        @param model_name  Model name to unload (e.g. "qwen3-14b").
        @return True if unload succeeded or was not needed, False on error.
        """
        if not ollama_host or not model_name:
            print(
                f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] Cannot offload — ollama_host or model_name not set"
            )
            return False
        try:
            host = ollama_host.rstrip("/")
            if not host.startswith("http"):
                host = f"http://{host}"
            url = f"{host}/api/generate"
            payload = {"model": model_name, "keep_alive": 0}
            resp = requests.post(url, json=payload, timeout=10)
            print(
                f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Ollama unload request → status {resp.status_code}"
            )
            return resp.status_code < 400
        except Exception as e:
            print(
                f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] Ollama offload failed (non-critical): {e}"
            )
            return False

    # === Pipeline lifecycle ===

    def load_pipeline(self):
        """
        @brief Load the NF4-quantised Stable Diffusion 3.5 pipeline onto GPU.

        @raises RuntimeError If diffusers/torch are unavailable or HF token is missing.
        """
        if self._pipeline is not None:
            print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Pipeline already loaded, reusing.")
            return

        if not self.hf_token:
            raise RuntimeError(
                "No HuggingFace token found. Set HF_TOKEN in .env or run `huggingface-cli login`."
            )

        try:
            import torch
            from diffusers import (
                BitsAndBytesConfig,
                SD3Transformer2DModel,
                StableDiffusion3Pipeline,
            )
            from transformers import T5EncoderModel

        except ImportError as e:
            raise RuntimeError(
                f"Image generation dependencies not installed. "
                f"Run: pip install diffusers transformers accelerate bitsandbytes. "
                f"Original error: {e}"
            )

        print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Loading SD3.5 NF4 pipeline…")

        nf4_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        transformer = SD3Transformer2DModel.from_pretrained(
            self.model_id,
            subfolder="transformer",
            quantization_config=nf4_config,
            torch_dtype=torch.bfloat16,
            cache_dir=self.cache_dir,
            token=self.hf_token,
        )

        t5_nf4 = T5EncoderModel.from_pretrained(
            "diffusers/t5-nf4",
            torch_dtype=torch.bfloat16,
            cache_dir=self.cache_dir,
            token=self.hf_token,
        )

        pipeline = StableDiffusion3Pipeline.from_pretrained(
            self.model_id,
            transformer=transformer,
            text_encoder_3=t5_nf4,
            torch_dtype=torch.bfloat16,
            cache_dir=self.cache_dir,
            token=self.hf_token,
        )

        # Ensure all non-quantised components are bfloat16 before offloading
        pipeline.vae = pipeline.vae.to(torch.bfloat16)
        pipeline.text_encoder = pipeline.text_encoder.to(torch.bfloat16)
        pipeline.text_encoder_2 = pipeline.text_encoder_2.to(torch.bfloat16)
        pipeline.enable_model_cpu_offload()

        self._pipeline = pipeline
        print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Pipeline loaded successfully.")

    def unload_pipeline(self):
        """
        @brief Unload the pipeline and release GPU/CPU memory.
        """
        if self._pipeline is None:
            return
        try:
            import torch

            del self._pipeline
            self._pipeline = None
            torch.cuda.empty_cache()
            print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Pipeline unloaded, GPU cache cleared.")
        except Exception as e:
            print(f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] Error during pipeline unload: {e}")
            self._pipeline = None

    # === Generation ===

    def generate(self, prompt: str):
        """
        @brief Generate an image from a text prompt.

        Pipeline must be loaded before calling this method.

        @param prompt Detailed description of the image to generate.
        @return PIL.Image object.
        @raises RuntimeError If pipeline is not loaded.
        """
        if self._pipeline is None:
            raise RuntimeError("Pipeline is not loaded. Call load_pipeline() first.")

        print(
            f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Generating image "
            f"(steps={self.num_steps}, guidance={self.guidance_scale})…"
        )

        result = self._pipeline(
            prompt=prompt,
            num_inference_steps=self.num_steps,
            guidance_scale=self.guidance_scale,
            max_sequence_length=self.max_sequence_length,
        )
        return result.images[0]

    # === Persistence ===

    def save_image(
        self,
        image,
        user_id: int,
        title: str,
        prompt: str,
        conversation_id: str = None,
        pg_client=None,
    ) -> dict:
        """
        @brief Save a generated image to disk and record it in the database.

        @param image           PIL.Image object to save.
        @param user_id         ID of the owning user.
        @param title           Human-readable title for the image.
        @param prompt          Prompt string used for generation.
        @param conversation_id UUID of the related conversation (may be None).
        @param pg_client       PostgreSQLClient instance for DB write.
        @return Dict with id, filename, title, url_path, etc.
        """
        image_uuid = str(uuid.uuid4())
        filename = f"{image_uuid}.png"
        user_dir = self.ensure_storage_dir(user_id)
        file_path = user_dir / filename

        # Save image to disk
        image.save(str(file_path))
        print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Image saved to {file_path}")

        image_id = image_uuid  # re-use the same uuid for both filename and DB id

        # Persist to database
        if pg_client:
            try:
                with pg_client.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO generated_images
                                (id, user_id, conversation_id, filename, title, prompt, model_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                image_uuid,
                                user_id,
                                conversation_id,
                                filename,
                                title,
                                prompt,
                                self.model_id,
                            ),
                        )
                    conn.commit()
                print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Image record saved to DB, id={image_uuid}")
            except Exception as e:
                print(f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] DB insert failed: {e}")

        return {
            "image_id": image_uuid,
            "filename": filename,
            "title": title,
            "prompt": prompt,
            "user_id": user_id,
            "url": f"/api/images/{image_uuid}",
            "download_url": f"/api/images/{image_uuid}/download",
        }

    # === High-level orchestration ===

    def generate_and_save(
        self,
        prompt: str,
        title: str,
        user_id: int,
        conversation_id: str = None,
        pg_client=None,
        ollama_host: str = None,
        ollama_model: str = None,
    ) -> dict:
        """
        @brief Full pipeline: offload LLM → load → generate → save → unload.

        This is the main entry point for the background generation thread.

        @param prompt          Image generation prompt.
        @param title           Image title (already determined by LLM).
        @param user_id         Owning user ID.
        @param conversation_id Related conversation UUID.
        @param pg_client       PostgreSQLClient instance.
        @param ollama_host     Ollama server URL (for model offloading).
        @param ollama_model    Ollama model name (for model offloading).
        @return Dict returned by save_image(), or dict with 'error' key on failure.
        """
        try:
            # Step 1: free VRAM by unloading Ollama model
            print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Offloading Ollama model before generation…")
            self.offload_ollama_model(ollama_host, ollama_model)

            # Step 2: load diffusion pipeline
            self.load_pipeline()

            # Step 3: generate
            image = self.generate(prompt)

            # Step 4: save to disk + DB
            result = self.save_image(
                image,
                user_id=user_id,
                title=title,
                prompt=prompt,
                conversation_id=conversation_id,
                pg_client=pg_client,
            )
            return result

        except Exception as e:
            print(f"{CLASS_PREFIX} [{LogLevel.CRITICAL.name}] Generation failed: {type(e).__name__}: {e}")
            return {"error": str(e)}

        finally:
            # Always unload to free memory, even on failure
            self.unload_pipeline()
