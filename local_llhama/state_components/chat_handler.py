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
                    uploaded_image_url = message.get("uploaded_image_url")
                    uploaded_image_id = message.get("uploaded_image_id")

                    if text:
                        self._handle_chat_message(text, client_id, conversation_id, uploaded_image_url, uploaded_image_id)

            except Empty:
                continue
            except Exception as e:
                print(
                    f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error processing chat message: {type(e).__name__}: {e}"
                )
                time.sleep(0.1)

    def _handle_chat_message(self, text, client_id, passed_conversation_id=None, uploaded_image_url=None, uploaded_image_id=None):
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
                self.message_handler.send_to_web_server(user_message, client_id=client_id)
                
                # Extract query from text (remove "analyze this image:" prefix if present)
                query = text
                if text.lower().startswith("analyze this image:"):
                    query = text[len("analyze this image:"):].strip()
                elif text == "Please analyze this image":
                    query = None
                
                # Build analysis request dict
                analysis_request = {
                    "type": "image_analysis_request",
                    "image": uploaded_image_url,
                    "query": query or "Describe what you see in this image.",
                    "user_id": client_id,
                    "uploaded_image_id": uploaded_image_id  # UUID for conversation storage
                }
                
                # Start image analysis in background thread
                self._handle_image_analysis(
                    analysis_request, client_id, conversation_id
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
                r for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "image_generation_request"
            ]

            # --- Separate image analysis requests from regular results ---
            image_analysis_requests = [
                r for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "image_analysis_request"
            ]

            # --- Separate Wikipedia image requests from regular results ---
            wiki_image_requests = [
                r for r in simple_function_results
                if isinstance(r.get("response"), dict)
                and r["response"].get("type") == "wikipedia_image_request"
            ]

            regular_results = [
                r for r in simple_function_results
                if r not in image_gen_requests
                and r not in image_analysis_requests
                and r not in wiki_image_requests
            ]

            # Handle image generation (runs in background thread)
            for img_req in image_gen_requests:
                self._handle_image_generation(
                    img_req["response"], client_id, conversation_id
                )

            # Handle image analysis (runs in background thread, bypasses main LLM)
            for analysis_req in image_analysis_requests:
                self._handle_image_analysis(
                    analysis_req["response"], client_id, conversation_id
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
                    status_msg = f"{self.log_prefix} [Status]: Searching for images of {topic}…"
                    self.message_handler.send_to_web_server(status_msg, client_id=client_id)
                    
                    chosen_url = self._select_wikipedia_image(
                        wiki_data, original_user_query, conversation_id, client_id
                    )
                    
                    # If no URL returned (all images shown, verification failed, or no candidates), 
                    # fall back to image generation
                    if not chosen_url:
                        print(
                            f"{self.log_prefix} [INFO] No appropriate Wikipedia images available for '{topic}', "
                            "falling back to image generation"
                        )
                        # Send status to user about fallback
                        fallback_status = f"{self.log_prefix} [Status]: Generating image: {topic}"
                        self.message_handler.send_to_web_server(fallback_status, client_id=client_id)
                        
                        # Create and immediately process image generation fallback
                        image_gen_fallback = {
                            "type": "image_generation_request",
                            "prompt": f"Create an image depicting: {topic}",
                            "title": topic,
                            "user_id": client_id,
                        }
                        # Process immediately - don't add to already-processed list
                        self._handle_image_generation(
                            image_gen_fallback, client_id, conversation_id
                        )
                        continue
                    
                    chosen_title = wiki_data.get("page_title", wiki_data.get("topic", ""))
                    
                    # Track this image as shown
                    if conversation_id:
                        self.context_manager.track_wikipedia_image(
                            conversation_id, chosen_url, chosen_title
                        )
                    
                    self.message_handler.send_wikipedia_image_ready(
                        {
                            "url": chosen_url,
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
                                f"[wikipedia_image:{chosen_url}]",
                            )
                        except Exception as db_err:
                            print(
                                f"{self.log_prefix} [WARNING] Could not persist "
                                f"wikipedia image tag to DB: {db_err}"
                            )

            # If there are no regular results left, return now
            if not regular_results and not image_gen_requests and not image_analysis_requests and not wiki_image_requests:
                return
            if not regular_results:
                if wiki_image_requests and conversation_id and isinstance(self.command_llm, OllamaClient):
                    # Generate a brief LLM comment about the displayed image(s)
                    original_user_query = self.pending_user_queries.get(client_id, "")
                    wiki_topics = ", ".join(
                        w["response"].get("page_title") or w["response"].get("topic", "")
                        for w in wiki_image_requests
                    )
                    llm_input = (
                        f"The user asked: \"{original_user_query}\"\n"
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
        @brief Load image generation settings from object_settings.json.

        Uses the package-relative path, same pattern as llm_prompts.py.

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
        @brief Return a (lazily-created) ImageGenerationManager instance.

        @return ImageGenerationManager configured from object_settings.json.
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
            output_format=settings["output_format"],
            keep_pipeline_loaded=settings["keep_pipeline_loaded"],
            keep_pipeline_loaded_min_vram_gb=settings["keep_pipeline_loaded_min_vram_gb"],
        )
        return self._image_manager

    def _select_wikipedia_image(self, wiki_data: dict, user_query: str, conversation_id: str = None, client_id: str = None) -> str:
        """
        Ask the LLM to pick the most contextually relevant image from the
        candidate list returned by get_wikipedia_image().

        Image Selection Strategy:
        - First request: Show Wikipedia image immediately (no verification for speed)
        - Vision verification is DISABLED by default (wikipedia_image_verification_enabled: false)
        - If user asks to improve/refine: Admin can enable verification for better selection
        - Final fallback: Return None to trigger image generation

        Falls back to the article's cover image (fallback_url) on any error,
        and ultimately to the first candidate if that is also absent.

        @param wiki_data        The wikipedia_image_request sentinel dict.
        @param user_query       The original user message (used for context).
        @param conversation_id  Conversation UUID to track shown images.
        @param client_id        Client ID for sending status messages.
        @return URL of the chosen image, or None if all have been shown.
        """
        candidates = wiki_data.get("candidates", [])
        fallback_url = wiki_data.get("fallback_url") or (candidates[0]["url"] if candidates else "")

        if not candidates:
            return fallback_url

        # Filter out images that have already been shown in this conversation
        shown_images = set()
        if conversation_id:
            shown_images = self.context_manager.get_shown_wikipedia_images(conversation_id)
            shown_urls = {url for url, _, _ in shown_images}
            
            # Filter candidates
            original_count = len(candidates)
            candidates = [c for c in candidates if c["url"] not in shown_urls]
            
            # Also filter fallback if it's been shown
            if fallback_url in shown_urls:
                fallback_url = candidates[0]["url"] if candidates else ""
            
            if original_count > len(candidates):
                print(
                    f"{self.log_prefix} [INFO] Filtered out {original_count - len(candidates)} "
                    f"already-shown Wikipedia images, {len(candidates)} remaining"
                )
        
        # If all images have been shown, return None to trigger image generation
        if not candidates:
            print(
                f"{self.log_prefix} [INFO] All Wikipedia images for this topic have been shown, "
                "will need to generate image instead"
            )
            return None

        # No need to call the LLM if there's only one option
        if len(candidates) == 1:
            chosen_url = candidates[0]["url"]
            chosen_caption = candidates[0].get("caption", "")
            
            # Verify with vision model if enabled
            settings = self._get_image_analysis_settings()
            if settings.get("wikipedia_image_verification_enabled", True):
                print(f"{self.log_prefix} [INFO] Verifying image appropriateness with vision model…")
                # Send status to user
                if client_id:
                    status_msg = f"{self.log_prefix} [Status]: Loading vision model to verify image (this may take a moment)…"
                    self.message_handler.send_to_web_server(status_msg, client_id=client_id)
                try:
                    is_appropriate, explanation = self._verify_wikipedia_image_appropriateness(
                        chosen_url, user_query, chosen_caption
                    )
                    if not is_appropriate:
                        print(
                            f"{self.log_prefix} [INFO] Single Wikipedia image failed verification: {explanation[:100]}"
                        )
                        return None  # Trigger image generation
                except Exception as verify_err:
                    print(
                        f"{self.log_prefix} [WARNING] Verification error for single candidate: {verify_err}, will generate instead"
                    )
                    return None  # Trigger image generation on error
            
            return chosen_url

        try:
            # Build a numbered menu for the LLM — keep captions short
            MAX_CANDIDATES = 10
            capped = candidates[:MAX_CANDIDATES]
            lines = []
            for i, c in enumerate(capped, 1):
                section = f"[{c['section']}] " if c.get("section") else ""
                caption = c.get("caption", "").strip() or "(no caption)"
                # Truncate very long captions
                if len(caption) > 120:
                    caption = caption[:117] + "..."
                lines.append(f"{i}. {section}{caption}")

            menu = "\n".join(lines)
            page_title = wiki_data.get("page_title", wiki_data.get("topic", ""))
            prompt = (
                f"The user asked: \"{user_query}\"\n\n"
                f"The available images come from the Wikipedia article \"{page_title}\", "
                f"but choose the image that best matches what the user is actually curious about, "
                f"not necessarily the article's main subject.\n"
                f"Reply with ONLY the number of the best image, nothing else.\n\n"
                f"{menu}"
            )

            result = self.command_llm.send_message(
                prompt,
                max_tokens=4,
                message_type="response",
                from_chat=True,
            )

            # Extract the number from the LLM reply
            raw = ""
            if isinstance(result, dict):
                raw = result.get("nl_response") or result.get("response") or ""
            elif isinstance(result, str):
                raw = result

            import re
            match = re.search(r"\d+", raw.strip())
            if match:
                idx = int(match.group()) - 1
                if 0 <= idx < len(capped):
                    chosen_url = capped[idx]["url"]
                    chosen_caption = capped[idx].get("caption", "")
                    
                    print(
                        f"{self.log_prefix} [INFO] Wikipedia image selected by LLM: "
                        f"#{idx + 1} — {chosen_url}"
                    )
                    
                    # Verify with vision model if enabled
                    settings = self._get_image_analysis_settings()
                    if settings.get("wikipedia_image_verification_enabled", True):
                        print(f"{self.log_prefix} [INFO] Verifying selected image with vision model…")
                        # Send status to user
                        if client_id:
                            status_msg = f"{self.log_prefix} [Status]: Loading vision model to verify image (this may take a moment)…"
                            self.message_handler.send_to_web_server(status_msg, client_id=client_id)
                        try:
                            is_appropriate, explanation = self._verify_wikipedia_image_appropriateness(
                                chosen_url, user_query, chosen_caption
                            )
                        except Exception as verify_err:
                            print(
                                f"{self.log_prefix} [WARNING] Verification failed for selected image: {verify_err}"
                            )
                            is_appropriate = False
                            explanation = f"Verification error: {verify_err}"
                        
                        if not is_appropriate:
                            print(
                                f"{self.log_prefix} [INFO] Selected image failed verification, trying next candidate"
                            )
                            # Try next candidates in order
                            for next_idx in range(len(capped)):
                                if next_idx == idx:
                                    continue  # Skip the already-tried one
                                
                                next_url = capped[next_idx]["url"]
                                next_caption = capped[next_idx].get("caption", "")
                                
                                print(f"{self.log_prefix} [INFO] Verifying candidate #{next_idx + 1}…")
                                try:
                                    is_appropriate, explanation = self._verify_wikipedia_image_appropriateness(
                                        next_url, user_query, next_caption
                                    )
                                except Exception as verify_err:
                                    print(
                                        f"{self.log_prefix} [WARNING] Verification failed for candidate #{next_idx + 1}: {verify_err}"
                                    )
                                    is_appropriate = False
                                    continue
                                    
                                if is_appropriate:
                                    print(
                                        f"{self.log_prefix} [INFO] Found appropriate image at position #{next_idx + 1}"
                                    )
                                    return next_url
                            
                            # No candidates passed verification
                            print(
                                f"{self.log_prefix} [INFO] No Wikipedia images passed verification, will generate instead"
                            )
                            return None
                    
                    return chosen_url

        except Exception as e:
            print(
                f"{self.log_prefix} [WARNING] Wikipedia image selection failed, "
                f"using fallback: {type(e).__name__}: {e}"
            )

        # Try to verify fallback before returning it
        settings = self._get_image_analysis_settings()
        if fallback_url and settings.get("wikipedia_image_verification_enabled", True):
            try:
                is_appropriate, _ = self._verify_wikipedia_image_appropriateness(
                    fallback_url, user_query, ""
                )
                if not is_appropriate:
                    print(
                        f"{self.log_prefix} [INFO] Fallback image also failed verification, will generate instead"
                    )
                    return None
            except Exception as verify_err:
                print(
                    f"{self.log_prefix} [WARNING] Fallback verification error: {verify_err}, will generate instead"
                )
                return None

        return fallback_url

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
                parsed = json.loads(content)
                title = parsed.get("title") or default_title
                comment = parsed.get("comment") or default_comment
                return title, comment

        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Could not get image intro from LLM: {e}"
            )

        return default_title, default_comment

    def _get_image_analysis_settings(self) -> dict:
        """
        @brief Load image analysis settings from object_settings.json.

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

    def _prepare_image_for_llava(self, image_source: str) -> str:
        """
        @brief Fetch/decode an image, resize to the best-matching LLaVA 1.6 resolution,
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
        import base64
        import io

        import requests as _req
        from PIL import Image

        # LLaVA 1.6 supported resolutions: (width, height)
        LLAVA_RESOLUTIONS = [
            (672, 672),   # square     — aspect 1.0
            (336, 1344),  # portrait   — aspect 0.25
            (1344, 336),  # landscape  — aspect 4.0
        ]

        # --- Load image bytes ---
        if image_source.startswith("/api/images/"):
            # Handle relative URLs from uploaded images route
            # Extract image_id and load file directly from disk
            image_id = image_source.split("/")[-1]
            
            # Get database client to look up image location
            pg_client = getattr(self, "command_llm", None)
            if pg_client:
                pg_client = getattr(pg_client, "pg_client", None)
            
            if not pg_client:
                raise ValueError(f"Cannot load uploaded image without database connection: {image_source}")
            
            try:
                # Look up image in database
                row = pg_client.execute_one(
                    "SELECT user_id, filename, model_id FROM generated_images WHERE id = %s",
                    (image_id,),
                )
                
                if not row:
                    raise ValueError(f"Image not found in database: {image_id}")
                
                user_id, filename, model_id = row
                is_uploaded = (model_id == "uploaded")
                
                # Build file path based on image type
                from pathlib import Path
                if is_uploaded:
                    # Path for uploaded images
                    base_path = Path(__file__).parent.parent / "data" / "uploaded_images"
                else:
                    # Path for generated images
                    base_path = Path(__file__).parent.parent / "data" / "generated_images"
                
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
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
            image = Image.open(image_buffer)
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
            f"[Chat Handler] [INFO] Scaling image {orig_w}×{orig_h} "
            f"(ratio {orig_ratio:.2f}) → {target_w}×{target_h} for LLaVA"
        )

        image = image.resize((target_w, target_h), Image.LANCZOS)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _verify_wikipedia_image_appropriateness(
        self, image_url: str, user_query: str, image_title: str = ""
    ) -> tuple:
        """
        @brief Use vision model to verify if a Wikipedia image is appropriate for the user's query.
        
        NOTE: This is disabled by default (wikipedia_image_verification_enabled: false).
        Strategy: Show Wikipedia images immediately on first request for speed.
        Only enable verification when user explicitly asks to improve/refine the image selection.
        Falls back to image generation if no appropriate images found after verification.

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
                f"{self.log_prefix} [WARNING] Cannot verify Wikipedia image: no Ollama host configured"
            )
            return True, "No vision model available"

        try:
            from ..image_generation import ImageGenerationManager as _IM
            import requests

            host_url = _IM._normalize_ollama_host(ollama_host)

            # Prepare the image
            try:
                image_b64 = self._prepare_image_for_llava(image_url)
            except Exception as img_err:
                print(
                    f"{self.log_prefix} [WARNING] Could not prepare Wikipedia image for verification: {img_err}"
                )
                return False, f"Image load failed: {img_err}"

            # Offload main LLM to free VRAM for vision model
            print(
                f"{self.log_prefix} [DEBUG] Offloading main model for Wikipedia image verification"
            )
            try:
                requests.post(
                    f"{host_url}/api/generate",
                    json={"model": ollama_model, "keep_alive": 0},
                    timeout=10,
                )
            except Exception:
                pass  # non-critical

            # Build verification prompt
            caption_part = f' with caption: "{image_title}"' if image_title else ''
            verification_prompt = (
                f"The user asked: \"{user_query}\"\n\n"
                f"This image is from Wikipedia{caption_part}.\n\n"
                f"Question: Is this image a good match for what the user is asking about? "
                f"Answer with YES or NO, followed by a brief 1-2 sentence explanation of why it matches or doesn't match their query."
            )

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

            if resp.status_code != 200:
                print(
                    f"{self.log_prefix} [WARNING] Vision model verification failed with status {resp.status_code}"
                )
                return False, "Vision model request failed"

            response_text = resp.json().get("response", "").strip()

            # Unload LLaVA and warm up main model again
            print(
                f"{self.log_prefix} [DEBUG] Unloading vision model, warming up main model"
            )
            try:
                # Unload LLaVA
                requests.post(
                    f"{host_url}/api/generate",
                    json={"model": llava_model, "keep_alive": 0},
                    timeout=10,
                )
                # Warm up main model with a tiny prompt (keep it loaded for next user query)
                requests.post(
                    f"{host_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": "",
                        "keep_alive": "5m",
                    },
                    timeout=10,
                )
            except Exception:
                pass  # non-critical

            # Parse the response
            is_appropriate = response_text.upper().startswith("YES")
            
            print(
                f"{self.log_prefix} [INFO] Wikipedia image verification: "
                f"{'✓ APPROPRIATE' if is_appropriate else '✗ NOT APPROPRIATE'} - {response_text[:100]}"
            )

            return is_appropriate, response_text

        except Exception as e:
            print(
                f"{self.log_prefix} [WARNING] Wikipedia image verification failed: {e}"
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

    def _handle_image_analysis(
        self, analysis_request: dict, client_id: str, conversation_id: str
    ):
        """
        @brief Analyse an image with LLaVA in a background thread, bypassing the main LLM.

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
        """
        settings = self._get_image_analysis_settings()
        if not settings.get("enabled", True):
            self._send_error_response(
                "Image analysis is disabled in system settings.", client_id
            )
            return

        image_source = analysis_request.get("image", "")
        query = analysis_request.get("query", "Describe what you see in this image.")
        user_id_val = analysis_request.get("user_id")
        user_id = int(user_id_val) if user_id_val is not None else None  # noqa: F841
        uploaded_image_id = analysis_request.get("uploaded_image_id")  # UUID if uploaded

        if not image_source:
            self._send_error_response("No image source was provided.", client_id)
            return

        llava_model = settings.get("llava_model", "llava:13b-v1.6-vicuna-q8_0")
        ollama_host = getattr(self.command_llm, "host", None)
        ollama_model = getattr(self.command_llm, "model", None)

        original_query = self.pending_user_queries.pop(client_id, query)

        status_msg = f"{self.log_prefix} [Status]: Analysing image…"
        self.message_handler.send_to_web_server(status_msg, client_id=client_id)

        pg_client = getattr(self.command_llm, "pg_client", None)
        message_handler = self.message_handler
        context_manager = self.context_manager
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
                context_manager.add_to_history(client_id, original_query, response_text)
                if pg_client and conversation_id:
                    try:
                        # Store user query
                        pg_client.insert_message(conversation_id, "user", original_query)
                        # Store uploaded image reference if present (like generated images)
                        if uploaded_image_id:
                            pg_client.insert_message(
                                conversation_id, "assistant", f"[uploaded_image:{uploaded_image_id}]"
                            )
                        # Store analysis response
                        pg_client.insert_message(
                            conversation_id, "assistant", response_text
                        )
                    except Exception as db_err:
                        print(
                            f"{log_prefix} [WARNING] Could not persist image analysis to DB: {db_err}"
                        )

                print(
                    f"{log_prefix} [{LogLevel.INFO.name}] Image analysis complete for client {client_id}"
                )

            except Exception as e:
                import traceback

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
                    requests.post(
                        f"{host_url}/api/generate",
                        json={"model": llava_model, "keep_alive": 0},
                        timeout=10,
                    )
                    if ollama_model:
                        requests.post(
                            f"{host_url}/api/generate",
                            json={
                                "model": ollama_model,
                                "prompt": "",
                                "keep_alive": "5m",
                            },
                            timeout=60,
                        )
                except Exception:
                    pass  # non-critical — keepalive will reload on next request

        thread = threading.Thread(target=_analysis_thread, daemon=True)
        thread.start()
        print(
            f"{self.log_prefix} [{LogLevel.INFO.name}] "
            f"Image analysis thread started for client {client_id}"
        )

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

        def _send_status(text: str):
            message_handler.send_to_web_server(
                f"{log_prefix} [Status]: {text}", client_id=client_id
            )

        def _generation_thread():
            image_manager = self._get_image_manager()
            try:
                # Step 1: free VRAM
                _send_status("Freeing GPU memory for image generation…")
                image_manager.offload_ollama_model(ollama_host, ollama_model)

                # Step 2: load diffusion pipeline — this is the slow part
                _send_status("Loading image model weights (this may take ~30 s)…")
                image_manager.load_pipeline()

                # Step 3: run inference
                _send_status(f"Generating image: {title}…")
                image = image_manager.generate(prompt)

                # Step 4: save to disk + DB
                _send_status("Saving image…")
                result = image_manager.save_image(
                    image,
                    user_id=user_id,
                    title=title,
                    prompt=prompt,
                    conversation_id=conversation_id,
                    pg_client=pg_client,
                )

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

                # Persist user message + image marker to DB so conversation
                # reload can reconstruct the image display.
                if pg_client and conversation_id:
                    try:
                        pg_client.insert_message(conversation_id, "user", original_query)
                        pg_client.insert_message(
                            conversation_id,
                            "assistant",
                            f"[image:{result['image_id']}]",
                        )
                    except Exception as db_err:
                        print(
                            f"{log_prefix} [WARNING] Could not persist image messages to DB: {db_err}"
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
                _send_status(f"Image generation failed: {e}")
            finally:
                image_manager.unload_pipeline()

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
