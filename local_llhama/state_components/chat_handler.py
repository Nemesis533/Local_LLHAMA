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

from ..model_registry import ModelState, ModelType, get_model_registry
from ..ollama import OllamaClient
from ..shared_logger import LogLevel
from ..services.media_handler import MediaHandlingService
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

        # Get model registry
        self.registry = get_model_registry()

        # Initialize media handling service
        self.media_service = MediaHandlingService(
            model_registry=self.registry,
            message_handler=message_handler,
            command_llm=command_llm,
            log_prefix=log_prefix,
        )

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
                    uploaded_image_url = message.get("uploaded_image_url")
                    uploaded_image_id = message.get("uploaded_image_id")

                    if text:
                        self._handle_chat_message(
                            text,
                            client_id,
                            conversation_id,
                            uploaded_image_url,
                            uploaded_image_id,
                        )

            except Empty:
                continue
            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error processing chat message: {type(e).__name__}: {e}"
                )
                time.sleep(0.1)

    def _handle_chat_message(
        self,
        text,
        client_id,
        passed_conversation_id=None,
        uploaded_image_url=None,
        uploaded_image_id=None,
    ):
        """
        Process a single chat message.

        @param text The user's message text
        @param client_id The client identifier for routing responses
        @param passed_conversation_id Optional conversation_id from frontend (when continuing existing chat)
        @param uploaded_image_url Optional URL of uploaded image for analysis
        @param uploaded_image_id Optional UUID of uploaded image in database
        """
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] Processing chat message from client {client_id}: {text}"
        )

        try:
            # Ensure conversation exists for this client
            conversation_id = self.context_manager.ensure_conversation_exists(
                client_id, passed_conversation_id
            )

            # If uploaded image is present, directly handle image analysis
            if uploaded_image_url:
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Uploaded image detected, routing to image analysis"
                )
                # Send user message to WebUI
                user_message = f"{self.log_prefix} [User Prompt]: {text}"
                self.message_handler.send_to_web_server(
                    user_message, client_id=client_id
                )

                # Extract query from text (remove "analyze this image:" prefix if present)
                query = text
                if text.lower().startswith("analyze this image:"):
                    query = text[len("analyze this image:") :].strip()
                elif text == "Please analyze this image":
                    query = None

                # Build analysis request dict
                analysis_request = {
                    "type": "image_analysis_request",
                    "image": uploaded_image_url,
                    "query": query or "Describe what you see in this image.",
                    "user_id": client_id,
                    "uploaded_image_id": uploaded_image_id,  # UUID for conversation storage
                }

                # Start image analysis in background thread
                self.media_service.handle_image_analysis(
                    analysis_request, client_id, conversation_id,
                    context_manager=self.context_manager,
                    pending_user_queries=self.pending_user_queries
                )
                return

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
                r
                for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "image_generation_request"
            ]

            # --- Separate image analysis requests from regular results ---
            image_analysis_requests = [
                r
                for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "image_analysis_request"
            ]

            # --- Separate Wikipedia image requests from regular results ---
            wiki_image_requests = [
                r
                for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "wikipedia_image_request"
            ]

            regular_results = [
                r
                for r in simple_function_results
                if r not in image_gen_requests
                and r not in image_analysis_requests
                and r not in wiki_image_requests
            ]

            # Handle image generation (runs in background thread)
            for img_req in image_gen_requests:
                self.media_service.handle_image_generation(
                    img_req["response"], client_id, conversation_id
                )

            # Handle image analysis (runs in background thread, bypasses main LLM)
            for analysis_req in image_analysis_requests:
                self.media_service.handle_image_analysis(
                    analysis_req["response"], client_id, conversation_id,
                    context_manager=self.context_manager,
                    pending_user_queries=self.pending_user_queries
                )

            # Handle Wikipedia image requests
            # Strategy: Show Wikipedia images immediately (verification disabled by default for speed).
            # If user wants a different/better image, they can ask again and verification can be enabled.
            if wiki_image_requests:
                pg_client = getattr(self.command_llm, "pg_client", None)
                original_user_query = self.pending_user_queries.get(client_id, "")
                for wiki_req in wiki_image_requests:
                    wiki_data = wiki_req["response"]

                    # Send status to user
                    topic = wiki_data.get("topic", "")
                    status_msg = (
                        f"{self.log_prefix} [Status]: Searching for images of {topic}…"
                    )
                    self.message_handler.send_to_web_server(
                        status_msg, client_id=client_id
                    )

                    chosen_url = self._select_wikipedia_image(
                        wiki_data, original_user_query, conversation_id, client_id
                    )

                    # If no URL returned (all images shown, verification failed, or no candidates),
                    # fall back to image generation
                    if not chosen_url:
                        print(
                            f"{self.log_prefix} [{LogLevel.INFO.name}] No appropriate Wikipedia images available for '{topic}', "
                            "falling back to image generation"
                        )
                        # Send status to user about fallback
                        fallback_status = (
                            f"{self.log_prefix} [Status]: Generating image: {topic}"
                        )
                        self.message_handler.send_to_web_server(
                            fallback_status, client_id=client_id
                        )

                        # Create and immediately process image generation fallback
                        image_gen_fallback = {
                            "type": "image_generation_request",
                            "prompt": f"Create an image depicting: {topic}",
                            "title": topic,
                            "user_id": client_id,
                        }
                        # Process immediately - don't add to already-processed list
                        self.media_service.handle_image_generation(
                            image_gen_fallback, client_id, conversation_id
                        )
                        continue

                    chosen_title = wiki_data.get(
                        "page_title", wiki_data.get("topic", "")
                    )

                    # Convert to 500px thumbnail for faster loading
                    display_url = self._get_wikipedia_thumbnail_url(
                        chosen_url, max_width=500
                    )

                    # Check if this image was already shown in this conversation
                    # Normalize filenames by removing size prefixes (e.g., "500px-")
                    def normalize_filename(url):
                        fname = url.rstrip("/").split("/")[-1].lower()
                        # Remove NNNpx- prefix if present (e.g., 500px-File.jpg → File.jpg)
                        import re

                        fname = re.sub(r"^\d+px-", "", fname)
                        return fname

                    if conversation_id:
                        shown_images = self.context_manager.get_shown_wikipedia_images(
                            conversation_id
                        )
                        display_filename = normalize_filename(display_url)
                        shown_filenames = {
                            normalize_filename(url) for url, _, _ in shown_images
                        }

                        if display_filename in shown_filenames:
                            print(
                                f"{self.log_prefix} [{LogLevel.INFO.name}] Wikipedia image already shown, "
                                "using VLM to analyze and generate better image"
                            )

                            # Use VLM to understand what's wrong with the existing Wikipedia image
                            # and create a better prompt for generation
                            vlm_analysis_prompt = (
                                f'The user previously saw this Wikipedia image but is asking again: "{original_user_query}"\n'
                                f"Looking at this image, what aspect of '{topic}' is the user actually interested in "
                                f"that this photo doesn't show? Reply with a brief description of what image should be generated instead."
                            )

                            # Send status
                            status_msg = f"{self.log_prefix} [Status]: Analyzing previous image ..."
                            self.message_handler.send_to_web_server(
                                status_msg, client_id=client_id
                            )

                            # Analyze with VLM - send status to user
                            try:
                                # Send analyzing status to user
                                analyzing_msg = f"{self.log_prefix} [VLM Analysis]: Analyzing existing image ..."
                                self.message_handler.send_to_web_server(
                                    analyzing_msg, client_id=client_id
                                )
                                
                                is_appropriate, analysis = (
                                    self._verify_wikipedia_image_appropriateness(
                                        display_url, vlm_analysis_prompt, chosen_title
                                    )
                                )

                                # Use the VLM's analysis to build a better generation prompt
                                generation_prompt = (
                                    f"Create an image of {topic} showing: {analysis}. "
                                    f"User's request: {original_user_query}"
                                )

                                print(
                                    f"{self.log_prefix} [{LogLevel.INFO.name}] VLM analysis complete, "
                                    f"generating image with prompt: {generation_prompt[:100]}"
                                )
                            except Exception as vlm_err:
                                print(
                                    f"{self.log_prefix} [{LogLevel.WARNING.name}] VLM analysis failed: {vlm_err}, "
                                    "using basic prompt"
                                )
                                generation_prompt = f"Create an image depicting: {topic}. {original_user_query}"

                            # Generate image with improved prompt
                            fallback_status = f"{self.log_prefix} [Status]: Generating custom image: {topic}"
                            self.message_handler.send_to_web_server(
                                fallback_status, client_id=client_id
                            )

                            image_gen_request = {
                                "type": "image_generation_request",
                                "prompt": generation_prompt,
                                "title": topic,
                                "user_id": client_id,
                            }
                            self.media_service.handle_image_generation(
                                image_gen_request, client_id, conversation_id
                            )
                            continue

                    # Track this image as shown (use display_url so it matches what we store in DB)
                    if conversation_id:
                        self.context_manager.track_wikipedia_image(
                            conversation_id, display_url, chosen_title
                        )

                    self.message_handler.send_wikipedia_image_ready(
                        {
                            "url": display_url,
                            "title": chosen_title,
                            "topic": wiki_data.get("topic", ""),
                        },
                        client_id=client_id,
                    )
                    # Persist inline tag to DB so conversation recovery can re-render
                    if pg_client and conversation_id:
                        try:
                            pg_client.insert_message(
                                conversation_id,
                                "assistant",
                                f"[wikipedia_image:{display_url}]",
                            )
                        except Exception as db_err:
                            print(
                                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not persist "
                                f"wikipedia image tag to DB: {db_err}"
                            )

            # If there are no regular results left, return now
            if (
                not regular_results
                and not image_gen_requests
                and not image_analysis_requests
                and not wiki_image_requests
            ):
                return
            if not regular_results:
                if (
                    wiki_image_requests
                    and conversation_id
                    and isinstance(self.command_llm, OllamaClient)
                ):
                    # Generate a brief LLM comment about the displayed image(s)
                    original_user_query = self.pending_user_queries.get(client_id, "")
                    wiki_topics = ", ".join(
                        w["response"].get("page_title")
                        or w["response"].get("topic", "")
                        for w in wiki_image_requests
                    )
                    llm_input = (
                        f'The user asked: "{original_user_query}"\n'
                        f"You just displayed a Wikipedia image for: {wiki_topics}.\n"
                        f"Write a short, informative comment relevant to what the user asked."
                    )
                    self._handle_simple_function_streaming(
                        llm_input, original_user_query, client_id, conversation_id
                    )
                else:
                    self.pending_user_queries.pop(client_id, None)
                return

            # --- Process remaining regular results normally ---
            # Extract display names for showing what the assistant is doing
            display_names = [
                r.get("display_name") for r in regular_results if r.get("display_name")
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
            prompt, _ = self.context_manager.get_context_for_prompt(client_id, text)

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
    # Wikipedia Image Handling
    # =========================================================

    def _get_wikipedia_thumbnail_url(self, url: str, max_width: int = 500) -> str:
        """
        Convert a Wikipedia/Wikimedia image URL to a thumbnail with max width.
        This scales images proportionally and improves load times.

        @param url The original Wikipedia image URL
        @param max_width Maximum width in pixels (default 500)
        @return Thumbnail URL or original if conversion not possible
        """
        if not url or "upload.wikimedia.org" not in url:
            return url

        # Skip if already a thumbnail
        if "/thumb/" in url and f"/{max_width}px-" in url:
            return url

        # Extract filename from original URL
        # Pattern: .../commons/4/4d/Filename.jpg or .../commons/thumb/4/4d/Filename.jpg/NNNpx-Filename.jpg
        try:
            if "/thumb/" in url:
                # Already a thumb, just need to adjust size
                # Remove the sized part at the end
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

    def _select_wikipedia_image(
        self,
        wiki_data: dict,
        user_query: str,
        conversation_id: str = None,
        client_id: str = None,
    ) -> str:
        """
        Return the first Wikipedia image from the candidates list.
        If user wants a better image, they can ask again and the system will use VLM
        to understand what was wrong, then generate a more appropriate image.

        @param wiki_data        The wikipedia_image_request sentinel dict.
        @param user_query       The original user message (used for context).
        @param conversation_id  Conversation UUID (unused now - no deduplication).
        @param client_id        Client ID for sending status messages.
        @return URL of the first image, or None if no images available.
        """
        candidates = wiki_data.get("candidates", [])
        fallback_url = wiki_data.get("fallback_url")

        # Return first candidate, or fallback, or None
        if candidates:
            return candidates[0]["url"]
        return fallback_url

    def _verify_wikipedia_image_appropriateness(
        self, image_url: str, user_query: str, image_title: str = ""
    ) -> tuple:
        """
        @brief Use vision model to verify if a Wikipedia image is appropriate for the user's query.

        NOTE: This is disabled by default (wikipedia_image_verification_enabled: false).
        Strategy: Show Wikipedia images immediately on first request for speed.
        Only enable verification when user explicitly asks to improve/refine the image selection.
        Falls back to image generation if no appropriate images found after verification.
        
        The VLM response is passed through the main LLM for rephrasing to maintain consistent
        conversation tone and style.

        @param image_url    URL of the Wikipedia image to verify.
        @param user_query   The original user question/query.
        @param image_title  Title/caption of the image.
        @return Tuple of (is_appropriate: bool, explanation: str)
        """
        settings = self._get_image_analysis_settings()
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
            import requests

            from ..image_generation import ImageGenerationManager as _IM

            host_url = _IM._normalize_ollama_host(ollama_host)

            # Prepare the image
            try:
                image_b64 = self._prepare_image_for_llava(image_url)
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
                model_type= ModelType.VLM,
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
                import requests

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
