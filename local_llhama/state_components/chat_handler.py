"""
Chat Handler Component

Handles chat messages from WebUI in dedicated thread, bypassing the state machine.
Allows concurrent chat interactions without interfering with voice workflow.
"""

import json
import os
import threading
import time
from pathlib import Path
from queue import Empty

import requests

from ..ollama import OllamaClient
from ..shared_logger import LogLevel
from .chat_context_manager import ChatContextManager


class ChatHandler:
    """
    @brief Handles WebUI chat messages independently from the state machine.

    Processes chat messages in a dedicated thread, allowing multiple concurrent
    chat users without interfering with voice input processing.
    """

    def __init__(
        self,
        chat_queue,
        command_llm,
        ha_client,
        message_handler,
        log_prefix="[Chat Handler]",
        max_tokens=4096,
        default_context_words=400,
        min_context_words=100,
        context_reduction_factor=0.7,
        history_exchanges=3,
        context_management_mode="truncate",
        context_summarization_model="decision",
        context_summary_target_words=150,
    ):
        """
        Initialize the chat handler.

        @param chat_queue Queue for incoming chat messages
        @param command_llm LLM instance for command parsing
        @param ha_client Home Assistant client for command execution
        @param message_handler MessageHandler instance for sending responses
        @param log_prefix Prefix for log messages
        @param max_tokens Maximum tokens to generate in LLM responses (default: 4096)
        @param default_context_words Default context window size in words (default: 400)
        @param min_context_words Minimum context window size in words (default: 100)
        @param context_reduction_factor Factor to reduce context on timeout (default: 0.7)
        @param history_exchanges Number of recent exchanges to keep in memory (default: 3)
        @param context_management_mode Mode for handling context overflow: "truncate" or "summarize"
        @param context_summarization_model Model to use for summarization: "main", "decision", or "auto"
        @param context_summary_target_words Target word count for context summaries
        """
        self.chat_queue = chat_queue
        self.command_llm = command_llm
        self.ha_client = ha_client
        self.message_handler = message_handler
        self.log_prefix = log_prefix

        # Track current user query for command execution flow (client_id -> query)
        self.pending_user_queries = {}

        # Configuration
        self.max_tokens = max_tokens

        # Get PostgreSQL client and ConversationLoader from command_llm
        pg_client = getattr(command_llm, "pg_client", None)
        conversation_loader = getattr(command_llm, "conversation_loader", None)

        # Get decision model if separate decision model is enabled
        decision_llm = None
        if (
            hasattr(command_llm, "use_separate_decision_model")
            and command_llm.use_separate_decision_model
        ):
            decision_llm = getattr(command_llm, "decision_llm", None)

        # Initialize context manager
        self.context_manager = ChatContextManager(
            pg_client=pg_client,
            conversation_loader=conversation_loader,
            log_prefix=f"{log_prefix} [Context]",
            default_context_words=default_context_words,
            min_context_words=min_context_words,
            context_reduction_factor=context_reduction_factor,
            history_exchanges=history_exchanges,
            context_management_mode=context_management_mode,
            context_summarization_model=context_summarization_model,
            context_summary_target_words=context_summary_target_words,
            main_llm_client=command_llm,
            decision_llm_client=decision_llm,
            message_handler=message_handler,
        )

        self.running = False
        self.worker_thread = None

        # Image generation manager (created lazily on first request)
        self._image_manager = None

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler initialized")

    def start(self):
        """
        @brief Start the chat handler worker thread.
        """
        if self.running:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Chat handler already running"
            )
            return

        self.running = True
        self.worker_thread = threading.Thread(
            target=self._process_chat_messages, daemon=True
        )
        self.worker_thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler worker thread started"
        )

    def stop(self):
        """
        @brief Stop the chat handler worker thread.
        """
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler stopped")

    def _process_chat_messages(self):
        """
        @brief Worker thread that processes incoming chat messages.
        """
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Chat message processor started"
        )

        while self.running:
            try:
                # Non-blocking get with timeout
                message = self.chat_queue.get(timeout=0.1)

                if isinstance(message, dict):
                    text = message.get("text")
                    client_id = message.get("client_id")
                    conversation_id = message.get(
                        "conversation_id"
                    )  # Get conversation_id from queue

                    if text:
                        self._handle_chat_message(text, client_id, conversation_id)

            except Empty:
                continue
            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error processing chat message: {type(e).__name__}: {e}"
                )
                time.sleep(0.1)

    def _handle_chat_message(self, text, client_id, passed_conversation_id=None):
        """
        Process a single chat message.

        @param text The user's message text
        @param client_id The client identifier for routing responses
        @param passed_conversation_id Optional conversation_id from frontend (when continuing existing chat)
        """
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Processing chat message from client {client_id}: {text}"
        )

        try:
            # Ensure conversation exists for this client
            conversation_id = self.context_manager.ensure_conversation_exists(
                client_id, passed_conversation_id
            )

            # Send user message to WebUI
            user_message = f"{self.log_prefix} [User Prompt]: {text}"
            self.message_handler.send_to_web_server(user_message, client_id=client_id)

            # Parse with LLM (will store to DB if it returns NL response)
            structured_output = self._parse_with_llm(text, client_id, conversation_id)

            if not structured_output:
                self._send_error_response("Failed to parse message", client_id)
                return

            # Handle different response types
            if structured_output.get("commands"):
                # Store user query for later (will be saved after command completes)
                self.pending_user_queries[client_id] = text
                self._handle_commands(structured_output, client_id, conversation_id)
                return  # Don't store yet, will be stored in _handle_simple_function_result or _handle_commands
            elif structured_output.get("nl_response"):
                # Has explicit NL response - already stored in DB by _parse_with_llm
                # Now stream it to the user
                nl_response = structured_output.get("nl_response")
                self._stream_nl_response_to_client(nl_response, text, client_id)
            else:
                self._send_error_response(
                    "No valid commands or responses extracted", client_id
                )
                return

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error handling chat message: {type(e).__name__}: {e}"
            )
            self._send_error_response(
                "An error occurred processing your message", client_id
            )

    def _parse_with_llm(self, text, client_id, conversation_id=None):
        """
        @brief Parse text with LLM and return structured output.

        Uses MINIMAL context (only last command from OllamaClient) to prevent
        context pollution during structured JSON output.

        @param text User message to parse
        @param client_id Client identifier
        @param conversation_id Optional conversation identifier
        @return Structured output from LLM
        """
        try:
            # FIRST PARSE: Use minimal context for decision-making
            # Only use the raw user message - OllamaClient will add last command context
            # This prevents context overload that causes wrong JSON schema
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Parsing with minimal context (decision-making phase)"
            )

            if not isinstance(self.command_llm, OllamaClient):
                return self.command_llm.parse_with_llm(text)
            else:
                # Send raw text - OllamaClient adds last command context automatically
                result = self.command_llm.send_message(
                    text,
                    max_tokens=self.max_tokens,
                    from_chat=True,
                    conversation_id=conversation_id,
                    original_text=text,
                )

                # Check if request timed out (indicating context too large)
                if result and result.get("_timeout_detected"):
                    self.context_manager.reduce_context_window(client_id)
                    print(
                        f"{self.log_prefix} [{LogLevel.WARNING.name}] Timeout detected, context window reduced"
                    )
                    # Remove the marker before returning
                    result.pop("_timeout_detected", None)

                return result
        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] LLM parsing failed: {type(e).__name__}: {e}"
            )
            # If timeout, attempt to reduce context window for next attempt
            if "timeout" in str(e).lower():
                self.context_manager.reduce_context_window(client_id)
            return None

    def _handle_commands(self, structured_output, client_id, conversation_id=None):
        """
        Execute commands and send results back to client.

        @param structured_output Parsed command structure from LLM
        @param client_id Client identifier for routing
        @param conversation_id UUID of the conversation
        """
        commands = structured_output.get("commands", [])
        language = structured_output.get("language", "en")

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Executing {len(commands)} command(s)"
        )

        try:
            # Execute commands using HA client (same as state machine)
            # Pass client_id as user_id for web chat users
            user_id = int(client_id) if client_id and client_id.isdigit() else None
            results = self.ha_client.send_commands(structured_output, user_id=user_id)

            if results:
                # Always use LLM for natural response (handles both simple functions and HA commands)
                if isinstance(self.command_llm, OllamaClient):
                    self._handle_simple_function_result(
                        results, language, client_id, conversation_id
                    )
                else:
                    # Fallback: just send confirmation
                    confirmation = "Commands executed successfully"
                    message = f"{self.log_prefix} [Command Result]: {confirmation}"
                    self.message_handler.send_to_web_server(
                        message, client_id=client_id
                    )

                    # Store interaction in history
                    if client_id in self.pending_user_queries:
                        self.context_manager.add_to_history(
                            client_id,
                            self.pending_user_queries[client_id],
                            confirmation,
                        )
                        del self.pending_user_queries[client_id]
            else:
                self._send_error_response(
                    "Command execution returned no results", client_id
                )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Command execution failed: {type(e).__name__}: {e}"
            )
            self._send_error_response(
                f"Failed to execute commands: {str(e)}", client_id
            )

    def _handle_simple_function_result(
        self, command_result, language, client_id, conversation_id=None
    ):
        """
        Convert simple function results to natural language with streaming support.

        @param command_result Results from command execution
        @param language Target language for response
        @param client_id Client identifier for routing
        @param conversation_id UUID of the conversation
        """
        try:
            simple_function_results = [
                r
                for r in command_result
                if isinstance(r, dict) and r.get("type") == "simple_function"
            ]

            # --- Separate image generation requests from regular results ---
            image_gen_requests = [
                r for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "image_generation_request"
            ]
            regular_results = [
                r for r in simple_function_results
                if r not in image_gen_requests
            ]

            # Handle image generation (runs in background thread)
            for img_req in image_gen_requests:
                self._handle_image_generation(
                    img_req["response"], client_id, conversation_id
                )

            # If there are no regular results left, return now
            if not regular_results and not image_gen_requests:
                return
            if not regular_results:
                # Image gen was the only request; return — thread will finish later
                # Clean up pending query since we're handing off to the thread
                self.pending_user_queries.pop(client_id, None)
                return

            # --- Process remaining regular results normally ---
            # Extract display names for showing what the assistant is doing
            display_names = [
                r.get("display_name")
                for r in regular_results
                if r.get("display_name")
            ]

            # Send display message to show what's being processed
            if display_names:
                status_message = ", ".join(display_names)
                message = f"{self.log_prefix} [Status]: {status_message}"
                self.message_handler.send_to_web_server(message, client_id=client_id)

            # Send to LLM for natural language conversion
            llm_input = f"Convert these function results into a natural language response in {language} language: {regular_results}"
            original_user_query = self.pending_user_queries.get(client_id, "")

            # Use streaming if from chat, otherwise regular response
            if conversation_id and isinstance(self.command_llm, OllamaClient):
                # Streaming response for chat
                self._handle_simple_function_streaming(
                    llm_input, original_user_query, client_id, conversation_id
                )
            else:
                # Non-streaming fallback
                nl_output = self.command_llm.send_message(
                    llm_input,
                    max_tokens=self.max_tokens,
                    message_type="response",
                    conversation_id=conversation_id,
                    original_text=original_user_query,
                )

                if nl_output and nl_output.get("nl_response"):
                    nl_message = nl_output.get("nl_response")
                    message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
                    self.message_handler.send_to_web_server(
                        message, client_id=client_id
                    )

                    # Store interaction in history
                    if client_id in self.pending_user_queries:
                        self.context_manager.add_to_history(
                            client_id, self.pending_user_queries[client_id], nl_message
                        )
                        del self.pending_user_queries[client_id]
                else:
                    # Fallback
                    fallback_msg = str(regular_results)
                    message = f"{self.log_prefix} [Command Result]: {fallback_msg}"
                    self.message_handler.send_to_web_server(
                        message, client_id=client_id
                    )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Simple function conversion failed: {type(e).__name__}: {e}"
            )
            self._send_error_response("Failed to format response", client_id)

    def _handle_simple_function_streaming(
        self, llm_input, original_user_query, client_id, conversation_id
    ):
        """
        Handle simple function result conversion with streaming.

        SECOND PARSE: Now we add full conversation context for natural response generation.

        @param llm_input The conversion prompt for the LLM
        @param original_user_query The original user query
        @param client_id Client identifier for routing
        @param conversation_id Conversation identifier
        """
        try:
            # Add full conversation context for response generation
            context_prompt, _ = self.context_manager.get_context_for_prompt(
                client_id, original_user_query
            )

            # Combine context with function result conversion instruction
            prompt_with_context = f"{context_prompt}\n\n{llm_input}"

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Generating response with full context (response generation phase)"
            )

            # Stream the response conversion - accumulate full response first
            full_response = ""
            for chunk in self.command_llm.send_message(
                prompt_with_context,
                max_tokens=self.max_tokens,
                message_type="response",
                from_chat=True,
                conversation_id=conversation_id,
                original_text=original_user_query,
                stream=True,
            ):
                chunk_text = chunk.get("response", "")
                if chunk_text:
                    full_response += chunk_text

            # Parse complete response to extract nl_response from JSON
            nl_response = self._extract_nl_response_from_json(full_response)

            # Now stream the extracted nl_response character by character for smooth display
            chunk_size = 5  # Send a few characters at a time for smooth streaming
            for i in range(0, len(nl_response), chunk_size):
                chunk_text = nl_response[i : i + chunk_size]
                is_complete = i + chunk_size >= len(nl_response)
                self.message_handler.send_streaming_chunk(
                    chunk_text, client_id=client_id, is_complete=is_complete
                )

            # Store interaction in history
            if client_id in self.pending_user_queries:
                self.context_manager.add_to_history(
                    client_id, self.pending_user_queries[client_id], nl_response
                )
                del self.pending_user_queries[client_id]

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Completed streaming simple function result for client {client_id}"
            )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error during streaming simple function conversion: {type(e).__name__}: {e}"
            )
            self._send_error_response("Error generating response", client_id)

    def _stream_nl_response_to_client(self, nl_response, original_text, client_id):
        """
        Stream an already-received NL response to the client.

        @param nl_response The natural language response text to stream
        @param original_text The original user message
        @param client_id Client identifier for routing
        """
        try:
            # DON'T send log_line message - we're streaming directly
            # Stream the nl_response character by character for smooth display
            chunk_size = 5  # Send a few characters at a time for smooth streaming
            for i in range(0, len(nl_response), chunk_size):
                chunk_text = nl_response[i : i + chunk_size]
                is_complete = i + chunk_size >= len(nl_response)
                self.message_handler.send_streaming_chunk(
                    chunk_text, client_id=client_id, is_complete=is_complete
                )

            # Store interaction in history
            self.context_manager.add_to_history(client_id, original_text, nl_response)

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Completed streaming NL response for client {client_id}"
            )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error streaming NL response: {type(e).__name__}: {e}"
            )

    def _handle_nl_response_streaming(self, text, client_id, conversation_id):
        """
        Handle natural language response with streaming.

        @param text Original user message
        @param client_id Client identifier for routing
        @param conversation_id Conversation identifier
        """
        chunk_size = 5  # how many characters to send, used for smooth streaming
        try:
            # Get context-enhanced prompt from context manager
            prompt, _ = self.context_manager.get_context_for_prompt(
                client_id, text
            )

            if not isinstance(self.command_llm, OllamaClient):
                # Fallback to non-streaming for non-Ollama clients
                structured_output = self.command_llm.parse_with_llm(prompt)
                self._handle_nl_response(structured_output, client_id)
                if structured_output.get("nl_response"):
                    self.context_manager.add_to_history(
                        client_id, text, structured_output["nl_response"]
                    )
                return

            # Stream the response - accumulate full response first, then extract and stream nl_response
            full_response = ""
            for chunk in self.command_llm.send_message(
                prompt,
                max_tokens=self.max_tokens,
                from_chat=True,
                conversation_id=conversation_id,
                original_text=text,
                stream=True,
            ):
                chunk_text = chunk.get("response", "")
                if chunk_text:
                    full_response += chunk_text

            # Parse complete response to extract nl_response from JSON
            try:
                parsed_response = json.loads(full_response)
                nl_response = parsed_response.get("nl_response", full_response)
            except json.JSONDecodeError:
                # If not JSON, use full response as-is
                nl_response = full_response

            # Now stream the extracted nl_response character by character for smooth display
            for i in range(0, len(nl_response), chunk_size):
                chunk_text = nl_response[i : i + chunk_size]
                is_complete = i + chunk_size >= len(nl_response)
                self.message_handler.send_streaming_chunk(
                    chunk_text, client_id=client_id, is_complete=is_complete
                )

            # Store interaction in history
            self.context_manager.add_to_history(client_id, text, nl_response)

            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Completed streaming response for client {client_id}"
            )

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error during streaming response: {type(e).__name__}: {e}"
            )
            self._send_error_response("Error generating response", client_id)

    def _extract_nl_response_from_json(self, text):
        """
        Extract nl_response from JSON text, handling various edge cases.

        @param text The JSON text from LLM response
        @return Extracted nl_response content or original text if extraction fails
        """
        # First, try standard JSON parsing
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "nl_response" in parsed:
                return parsed["nl_response"]
        except json.JSONDecodeError:
            pass

        # If JSON parsing fails, try to extract nl_response manually
        # Look for "nl_response": "..." pattern
        import re

        # Pattern to match nl_response field with quoted content
        # This handles multi-line strings and escaped quotes
        pattern = r'"nl_response"\s*:\s*"((?:[^"\\]|\\.)*)"'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            # Unescape the captured content
            content = match.group(1)
            # Unescape common escape sequences
            content = content.replace('\\"', '"')
            content = content.replace("\\n", "\n")
            content = content.replace("\\t", "\t")
            content = content.replace("\\\\", "\\")
            return content

        # If pattern matching fails, check if text looks like it starts with JSON structure
        # and strip the JSON wrapper manually
        if text.strip().startswith("{") and '"nl_response"' in text:
            # Try to find the content between "nl_response": " and the closing "
            start_marker = '"nl_response":'
            start_idx = text.find(start_marker)
            if start_idx != -1:
                # Find the opening quote after the colon
                quote_start = text.find('"', start_idx + len(start_marker))
                if quote_start != -1:
                    # Find the closing quote (accounting for escaped quotes)
                    i = quote_start + 1
                    while i < len(text):
                        if text[i] == '"' and (i == 0 or text[i - 1] != "\\"):
                            # Found unescaped closing quote
                            return (
                                text[quote_start + 1 : i]
                                .replace('\\"', '"')
                                .replace("\\n", "\n")
                            )
                        i += 1

        # Last resort: if we see JSON structure markers but couldn't parse,
        # try to clean it up
        if "{" in text and '"nl_response"' in text and '"language"' in text:
            # Strip common JSON artifacts that might appear in streaming
            cleaned = (
                text.replace('{"nl_response":"', "")
                .replace('", "language":', "")
                .replace('"language":"en"', "")
                .replace('"language":"fr"', "")
                .replace('"language":"de"', "")
                .replace('"language":"it"', "")
                .replace('"language":"es"', "")
                .replace('"language":"ru"', "")
            )
            if cleaned != text:
                # Remove trailing braces
                cleaned = cleaned.rstrip("}").rstrip()
                return cleaned

        # If all else fails, return original text
        return text

    # =========================================================
    # Image generation
    # =========================================================

    def _get_image_settings(self) -> dict:
        """
        @brief Load image generation settings from system_settings.json.

        Uses the package-relative path, same pattern as llm_prompts.py.

        @return Dict with keys: enabled, model_id, cache_dir, num_steps,
                guidance_scale, max_sequence_length.
        """
        defaults = {
            "enabled": True,
            "model_id": "stabilityai/stable-diffusion-3.5-large-turbo",
            "cache_dir": "/mnt/fast_storage/diffusers",
            "num_steps": 4,
            "guidance_scale": 0.0,
            "max_sequence_length": 512,
            "cuda_device": "cuda:0",
        }
        try:
            settings_path = (
                Path(__file__).parent.parent / "settings" / "system_settings.json"
            )
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                section = data.get("image_generation", {})
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
        @brief Return a (lazily-created) ImageGenerationManager instance.

        @return ImageGenerationManager configured from system_settings.json.
        """
        if self._image_manager is not None:
            return self._image_manager

        from ..image_generation import ImageGenerationManager

        settings = self._get_image_settings()
        storage_base = (
            Path(__file__).parent.parent / "data" / "generated_images"
        )
        self._image_manager = ImageGenerationManager(
            model_id=settings["model_id"],
            cache_dir=settings["cache_dir"],
            hf_token=os.environ.get("HF_TOKEN"),
            storage_base_path=str(storage_base),
            cuda_device=settings["cuda_device"],
            num_steps=settings["num_steps"],
            guidance_scale=settings["guidance_scale"],
            max_sequence_length=settings["max_sequence_length"],
        )
        return self._image_manager

    def _generate_image_intro(
        self, prompt: str, title_hint: str, ollama_host: str, model: str
    ) -> tuple:
        """
        @brief Ask Ollama for a title and brief intro comment for the image.

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

        try:
            host = ollama_host.rstrip("/")
            if not host.startswith("http"):
                host = f"http://{host}"

            title_instruction = (
                f'The user has given this title: "{title_hint}". Keep it exactly.'
                if title_hint
                else "Invent a short, creative title (3-6 words)."
            )

            system = (
                "You are a helpful assistant. Respond ONLY with valid JSON — "
                "no markdown, no code fences, no extra text."
            )
            user_msg = (
                f"An image is being generated with this description:\n\"{prompt}\"\n\n"
                f"{title_instruction}\n"
                "Also write a single friendly sentence introducing the image to the user.\n"
                'Respond with exactly this JSON format:\n'
                '{"title": "...", "comment": "..."}'
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
                parsed = json.loads(content)
                title = parsed.get("title") or default_title
                comment = parsed.get("comment") or default_comment
                return title, comment

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not get image intro from LLM: {e}"
            )

        return default_title, default_comment

    def _handle_image_generation(
        self, image_request: dict, client_id: str, conversation_id: str
    ):
        """
        @brief Orchestrate image generation in a background thread.

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
            self._send_error_response(
                "Image generation is disabled in system settings.", client_id
            )
            return

        prompt = image_request.get("prompt", "")
        title_hint = image_request.get("title", "")
        user_id_val = image_request.get("user_id")
        user_id = int(user_id_val) if user_id_val is not None else None

        if not prompt:
            self._send_error_response("No image prompt was provided.", client_id)
            return

        # Step 1: Get title + intro comment from LLM while it is still loaded
        ollama_host = getattr(self.command_llm, "host", None)
        ollama_model = getattr(self.command_llm, "model", None)

        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Requesting image intro from LLM (host={ollama_host}, model={ollama_model})"
        )

        title, comment = self._generate_image_intro(
            prompt, title_hint, ollama_host, ollama_model
        )

        # Step 2: Send status to client — shows the spinner
        status_msg = f"{self.log_prefix} [Status]: Generating image: {title}"
        self.message_handler.send_to_web_server(status_msg, client_id=client_id)

        # Step 3: Add entry to conversation history for the user request
        original_query = self.pending_user_queries.pop(client_id, prompt)
        self.context_manager.add_to_history(
            client_id,
            original_query,
            f"[Image generated: {title}]",
        )

        # Step 4: Capture everything in thread closure and spawn
        pg_client = getattr(self.command_llm, "pg_client", None)
        message_handler = self.message_handler
        log_prefix = self.log_prefix

        def _generation_thread():
            try:
                image_manager = self._get_image_manager()
                result = image_manager.generate_and_save(
                    prompt=prompt,
                    title=title,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    pg_client=pg_client,
                    ollama_host=ollama_host,
                    ollama_model=ollama_model,
                )

                if "error" in result:
                    error_msg = f"{log_prefix} [Error]: Image generation failed: {result['error']}"
                    message_handler.send_to_web_server(error_msg, client_id=client_id)
                else:
                    message_handler.send_image_ready(
                        {
                            "image_id": result["image_id"],
                            "title": title,
                            "comment": comment,
                            "url": result["url"],
                            "download_url": result["download_url"],
                        },
                        client_id=client_id,
                    )
                    print(
                        f"{log_prefix} [{LogLevel.INFO.name}] "
                        f"Image generation complete: {result['image_id']}"
                    )

            except BaseException as e:
                import traceback
                print(
                    f"{log_prefix} [{LogLevel.CRITICAL.name}] "
                    f"Image generation thread error: {type(e).__name__}: {e}\n"
                    + traceback.format_exc()
                )
                error_msg = f"{log_prefix} [Error]: Image generation failed: {e}"
                message_handler.send_to_web_server(error_msg, client_id=client_id)

        thread = threading.Thread(target=_generation_thread, daemon=True)
        thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Image generation thread started for client {client_id}"
        )

    # =========================================================
    # Error / utility helpers
    # =========================================================

    def _handle_nl_response(self, structured_output, client_id):
        """
        Send natural language response to client (non-streaming fallback).

        @param structured_output Parsed output containing nl_response
        @param client_id Client identifier for routing
        """
        nl_message = structured_output.get("nl_response")
        message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
        self.message_handler.send_to_web_server(message, client_id=client_id)

    def _send_error_response(self, error_text, client_id):
        """
        Send error message to client.

        @param error_text Error message text
        @param client_id Client identifier for routing
        """
        message = f"{self.log_prefix} [Error]: {error_text}"
        self.message_handler.send_to_web_server(message, client_id=client_id)
