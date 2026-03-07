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
        cuda_device: str = "cuda:0",
        num_steps: int = 4,
        guidance_scale: float = 0.0,
        max_sequence_length: int = 512,
        output_format: str = "png",
        keep_pipeline_loaded: bool = False,
        keep_pipeline_loaded_min_vram_gb: float = 10.0,
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
        self.hf_token = hf_token or os.environ.get("HF_TOKEN") or self._load_hf_token()
        self.storage_base_path = storage_base_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "generated_images",
        )
        self.cuda_device = cuda_device
        self.num_steps = num_steps
        self.guidance_scale = guidance_scale
        self.max_sequence_length = max_sequence_length
        self.output_format = output_format.lower()
        self.keep_pipeline_loaded = keep_pipeline_loaded
        self.keep_pipeline_loaded_min_vram_gb = keep_pipeline_loaded_min_vram_gb

        # Pipeline is loaded lazily; _pipeline_kept_alive tracks whether it is
        # intentionally staying resident across requests.
        self._pipeline = None
        self._pipeline_kept_alive = False

        print(
            f"{CLASS_PREFIX} [{LogLevel.INFO.name}] ImageGenerationManager initialised. "
            f"model={model_id}, storage={self.storage_base_path}"
        )

    # === Token helpers ===

    @staticmethod
    def _load_hf_token() -> str:
        """
        @brief Try to read the HuggingFace token from the CLI login cache.

        Checks the location written by `huggingface-cli login`, falling back
        to the legacy path.  Returns an empty string if nothing is found.

        @return Token string or empty string.
        """
        try:
            from huggingface_hub import get_token
            token = get_token()
            if token:
                return token
        except Exception:
            pass

        # Manual fallback: read the file directly
        for candidate in [
            Path.home() / ".cache" / "huggingface" / "token",
            Path.home() / ".huggingface" / "token",
        ]:
            if candidate.exists():
                token = candidate.read_text(encoding="utf-8").strip()
                if token:
                    return token

        return ""

    @staticmethod
    def _normalize_ollama_host(host: str) -> str:
        """
        @brief Strip trailing slash and ensure an http:// scheme is present.

        @param host Raw host string (e.g. "192.168.1.10:11434" or "http://...").
        @return Normalised URL string.
        """
        host = host.rstrip("/")
        if not host.startswith("http"):
            host = f"http://{host}"
        return host

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
            host = self._normalize_ollama_host(ollama_host)
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

    def _find_device_with_enough_vram(self, min_vram_gb: float):
        """
        @brief Scan all CUDA devices and return the index of the first one with
               at least min_vram_gb of free memory.

        @param min_vram_gb Minimum free VRAM required, in gigabytes.
        @return Device index (int), or None if no qualifying device is found.
        """
        try:
            import torch

            if not torch.cuda.is_available():
                return None
            for i in range(torch.cuda.device_count()):
                free_bytes, _ = torch.cuda.mem_get_info(i)
                free_gb = free_bytes / (1024 ** 3)
                if free_gb >= min_vram_gb:
                    print(
                        f"{CLASS_PREFIX} [{LogLevel.INFO.name}] "
                        f"cuda:{i} has {free_gb:.1f} GB free — selected for persistent pipeline."
                    )
                    return i
            print(
                f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] "
                f"No device found with \u2265{min_vram_gb:.1f} GB free VRAM; "
                f"pipeline will unload normally after each generation."
            )
        except Exception as e:
            print(f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] VRAM scan failed: {e}")
        return None

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
                "No HuggingFace token found. Set HF_TOKEN env var, add it to .env, "
                "or run `huggingface-cli login` and restart the service."
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

        # Resolve target CUDA device — default cuda:0, fall back to cpu gracefully
        cuda_device = self.cuda_device or "cuda:0"
        if cuda_device.startswith("cuda"):
            if not torch.cuda.is_available():
                print(
                    f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] "
                    f"CUDA not available, falling back to CPU."
                )
                cuda_device = "cpu"
            else:
                # Validate the requested device index is actually available
                device_index = int(cuda_device.split(":")[1]) if ":" in cuda_device else 0
                if device_index >= torch.cuda.device_count():
                    print(
                        f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] "
                        f"Device {cuda_device} not found (only {torch.cuda.device_count()} device(s)), "
                        f"falling back to cuda:0."
                    )
                    device_index = 0
                    cuda_device = "cuda:0"
        else:
            device_index = None  # CPU path

        # Persistent-pipeline mode: prefer the device with the most headroom so the
        # model stays resident between requests instead of reloading every time.
        _will_keep_alive = False
        if self.keep_pipeline_loaded and device_index is not None:
            best = self._find_device_with_enough_vram(self.keep_pipeline_loaded_min_vram_gb)
            if best is not None:
                device_index = best
                cuda_device = f"cuda:{best}"
                _will_keep_alive = True

        print(
            f"{CLASS_PREFIX} [{LogLevel.INFO.name}] "
            f"Loading SD3.5 NF4 pipeline on {cuda_device}…"
        )

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

        # Pin to the explicit GPU and allow spilling excess tensors to CPU RAM
        if device_index is not None:
            pipeline.enable_model_cpu_offload(gpu_id=device_index)
        else:
            # Pure CPU — no GPU offloading
            pipeline.to("cpu")

        self._pipeline = pipeline
        self._pipeline_kept_alive = _will_keep_alive
        if _will_keep_alive:
            print(
                f"{CLASS_PREFIX} [{LogLevel.INFO.name}] "
                f"Pipeline loaded on {cuda_device} and will remain resident between requests."
            )
        else:
            print(
                f"{CLASS_PREFIX} [{LogLevel.INFO.name}] "
                f"Pipeline loaded successfully on {cuda_device} (CPU spillover enabled)."
            )

    def unload_pipeline(self, force: bool = False):
        """
        @brief Unload the pipeline and release GPU/CPU memory.

        When keep_pipeline_loaded is active, this is a no-op unless force=True.

        @param force Bypass the keep-alive flag and unload unconditionally
                     (intended for clean shutdown).
        """
        if self._pipeline_kept_alive and not force:
            print(
                f"{CLASS_PREFIX} [{LogLevel.INFO.name}] "
                f"Pipeline kept alive — skipping unload (pass force=True to override)."
            )
            return
        if self._pipeline is None:
            return
        try:
            import torch

            del self._pipeline
            self._pipeline = None
            self._pipeline_kept_alive = False
            # TODO: worth adding gc.collect() here before empty_cache() if we ever
            # see VRAM not draining cleanly between generations — haven't hit it yet
            # but keeping it in mind for smaller cards. — (llhama)
            torch.cuda.empty_cache()
            print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Pipeline unloaded, GPU cache cleared.", flush=True)
        except Exception as e:
            print(f"{CLASS_PREFIX} [{LogLevel.WARNING.name}] Error during pipeline unload: {e}")
            self._pipeline = None
            self._pipeline_kept_alive = False

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
        ext = "jpg" if self.output_format == "jpeg" else self.output_format
        filename = f"{image_uuid}.{ext}"
        user_dir = self.ensure_storage_dir(user_id)
        file_path = user_dir / filename

        # Save image to disk (format negotiation: PIL wants 'JPEG' not 'JPG')
        pil_format = {"jpg": "JPEG"}.get(self.output_format, self.output_format.upper())
        save_kwargs = {"quality": 92} if pil_format in ("JPEG", "WEBP") else {}
        image.save(str(file_path), format=pil_format, **save_kwargs)
        print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Image saved to {file_path}", flush=True)

        image_id = image_uuid  # re-use the same uuid for both filename and DB id

        # Persist to database
        if pg_client:
            try:
                pg_client.execute_write(
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
                print(f"{CLASS_PREFIX} [{LogLevel.INFO.name}] Image record saved to DB, id={image_uuid}", flush=True)
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


