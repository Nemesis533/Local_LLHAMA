"""
@file Prompt_Guard.py
@brief Prompt safety checker using LLaMA-based classification model.

This module provides a safety layer to detect potentially harmful prompts
before they are processed by the main language model.
"""

# === System Imports ===
import os
import torch
from transformers import AutoTokenizer, LlamaForSequenceClassification
from torch.nn.functional import softmax

# === Custom Imports ===
from .Shared_Logger import LogLevel


class PromptGuard_Class:
    """
    @brief Class to guard prompts for safety using a classification model.
    """
    def __init__(self, model_path, prompt_guard_model_name, device=None, threshold=0.95):
        """
        @param model_path Path to the directory containing the guard model.
        @param prompt_guard_model_name Name of the prompt guard model.
        @param device Device to run the model on (e.g., 'cuda' or 'cpu').
        @param threshold Probability threshold to classify prompt as safe.
        """
        self.class_prefix_message = "[PromptGuard]"
        self.model_path = model_path
        self.model_name = prompt_guard_model_name
        self.device = device
        self.threshold = threshold
        self.model = None  # Placeholder for the safety classification model
        self.tokenizer = None  # Placeholder for tokenizer

    def load_model(self):
        """
        @brief Load the LLaMA-based prompt guard model with FP16 precision.
        @return True if model and tokenizer loaded successfully, False otherwise.
        """
        try:
            # Determine the full path for the model (local or fallback)
            full_path = os.path.join(self.model_path, self.model_name)
            model_path_to_use = full_path if os.path.exists(full_path) else self.model_path

            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading PromptGuard model from {model_path_to_use}...")

            # Load the sequence classification model for safety detection
            self.model = LlamaForSequenceClassification.from_pretrained(
                model_path_to_use,
                torch_dtype=torch.float16,
                device_map=self.device,
                trust_remote_code=True,
            )

            # Load the tokenizer compatible with the model
            self.tokenizer = AutoTokenizer.from_pretrained(
                "meta-llama/Llama-3.1-8B",
                trust_remote_code=True,
                legacy=False,
                use_fast=False,
            )

            # Fix missing pad token by setting it to eos token if necessary
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            self.model.eval()  # Set model to evaluation mode
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] PromptGuard model loaded successfully")
            return True

        except OSError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Model files not found: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check path: {model_path_to_use}")
            return False
            
        except torch.cuda.OutOfMemoryError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] CUDA Out of Memory: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] PromptGuard model requires additional GPU memory")
            return False
            
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error loading PromptGuard model: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def build_prompt(self, user_input):
        """
        @brief Build a short-form prompt formatted for the safety classifier.
        @param user_input Raw user input string.
        @return Formatted prompt string for classification.
        """
        return f"[INST] <<SYS>>\nYou are a helpful and harmless assistant. \n<</SYS>>\n{user_input.strip()} [/INST]"

    def is_safe(self, user_input):
        """
        @brief Check if the user input is safe or suspicious.
        @param user_input Raw user input string to evaluate.
        @return True if input is considered safe, False if suspicious.
        """
        # Validate model is loaded
        if self.model is None or self.tokenizer is None:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Model not loaded, defaulting to safe")
            return True  # Fail-open for availability
        
        # Validate input
        if not user_input or not user_input.strip():
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Empty input, treating as safe")
            return True
        
        # Prepare the prompt for classification
        try:
            prompt = self.build_prompt(user_input)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to build prompt: {repr(e)}")
            return True  # Fail-open

        # Tokenize the prompt with padding, truncation and move to correct device
        try:
            inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Tokenization failed: {repr(e)}")
            return True  # Fail-open

        # Perform model inference without gradient calculation
        try:
            with torch.no_grad():
                logits = self.model(**inputs).logits
                probs = softmax(logits, dim=-1)[0]  # Get probabilities for each class
        except torch.cuda.OutOfMemoryError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] CUDA OOM in safety check: {repr(e)}")
            torch.cuda.empty_cache()
            return True  # Fail-open
        except RuntimeError as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Runtime error in safety check: {repr(e)}")
            return True  # Fail-open
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Safety inference failed: {repr(e)}")
            return True  # Fail-open

        try:
            unsafe_score = probs[0].item()  # Probability that input is unsafe
            safe_score = probs[1].item()    # Probability that input is safe
            is_safe = unsafe_score < self.threshold  # Compare with threshold

            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Evaluating: {user_input[:50]}...")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Safety check: unsafe={unsafe_score:.4f}, threshold={self.threshold}, safe={is_safe}")

            return is_safe
        except (IndexError, ValueError) as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to extract probabilities: {repr(e)}")
            return True  # Fail-open
