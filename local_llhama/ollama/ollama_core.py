"""
Ollama Core Client

This module provides the main OllamaClient class for interacting with
Ollama LLM server for command parsing and response processing.
"""

# === System Imports ===
import json
import threading
import time

import requests

# === Custom Imports ===
from ..llm_prompts import (
    CONVERSATION_PROCESSOR_PROMPT,
    RESPONSE_PROCESSOR_PROMPT,
    RESUME_CONVERSATION_PROMPT,
    SAFETY_INSTRUCTION_PROMPT,
    SMART_HOME_DECISION_MAKING_EXTENSION,
    SMART_HOME_PROMPT_TEMPLATE,
    is_safety_enabled,
)
from ..shared_logger import LogLevel
from .ollama_context_builders import ContextBuilder
from .ollama_embeddings import EmbeddingClient


class OllamaClient:
    """
    Client to interact with Ollama server for language model inference.

    Handles:
    - Command parsing from natural language
    - Response processing for function results
    - Conversation management with context
    - Embedding generation for message storage
    """

    def __init__(
        self,
        ha_client,
        host: str = "http://your_ip:11434", # leaving placeholder to force user to set
        model: str = "qwen3-14b",
        pg_client=None,
        conversation_loader=None,
        embedding_model: str = "nomic-embed-text",
        decision_model: str = None,
        use_separate_decision_model: bool = False,
        keepalive_enabled: bool = True,
        keepalive_interval: int = 180,
    ):
        """
        Initialize Ollama client with connection details.

        @param ha_client HomeAssistantClient instance for device context
        @param host Ollama server URL
        @param model Model name to use on Ollama server
        @param system_prompt Optional system prompt override
        @param pg_client Optional PostgreSQLClient for storing message embeddings
        @param conversation_loader Optional ConversationLoader for accessing previous conversations
        @param embedding_model Embedding model name to use (default: nomic-embed-text)
        @param decision_model Optional separate model for decision-making phase
        @param use_separate_decision_model Whether to use separate model for decisions
        @param keepalive_enabled Whether to enable model keepalive thread
        @param keepalive_interval Seconds between keepalive pings
        """
        self.class_prefix_message = "[OllamaClient]"
        # Ensure host has http:// scheme
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        self.host = host.rstrip("/")
        self.model = model
        self.decision_model = decision_model if decision_model else model
        self.use_separate_decision_model = use_separate_decision_model
        self.keepalive_enabled = keepalive_enabled
        self.keepalive_interval = keepalive_interval
        self.keepalive_thread = None
        self.keepalive_running = False
        self.ha_client = ha_client
        self.pg_client = pg_client
        self.conversation_loader = conversation_loader

        # Debug: Log decision model configuration
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Main model: {self.model}"
        )
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Decision model: {self.decision_model}"
        )
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Use separate decision model: {self.use_separate_decision_model}"
        )

        self.context_builder = ContextBuilder(ha_client, self.class_prefix_message)
        self.devices_context = self.context_builder.get_devices_context()

        self.response_processor_prompt = RESPONSE_PROCESSOR_PROMPT
        self.conversation_processor_prompt = CONVERSATION_PROCESSOR_PROMPT
        self.decision_making_extension = SMART_HOME_DECISION_MAKING_EXTENSION
        self.resume_conversation_prompt = RESUME_CONVERSATION_PROMPT
        self.safety_prompt = SAFETY_INSTRUCTION_PROMPT if is_safety_enabled() else ""

        self.embedding_client = EmbeddingClient(
            host=self.host, model=embedding_model, pg_client=self.pg_client
        )

        # Initialize models list for keepalive management
        self._initialize_models_list()

        # Context management - keep only last request and response
        self.last_user_message = None
        self.last_message_from_chat = False  # Track if last command was from chat
        self.last_user_embedding = None  # Store embedding of last user question

        # Languages will be loaded from settings
        self.languages = {}

        # Build system prompt for decision-making (FIRST PARSE)
        extended_prompt = self._build_extended_prompt()
        simple_functions_context = (
            self.context_builder.generate_simple_functions_context()
        )

        self.system_prompt = extended_prompt.format(
            devices_context=self.devices_context,
            simple_functions_context=simple_functions_context,
        )

        # Start keepalive thread if enabled
        if self.keepalive_enabled:
            self._start_keepalive()

    def _initialize_models_list(self):
        """Initialize the list of models for keepalive management."""
        self.models = []
        
        # Add main text generation model
        self.models.append({
            "name": self.model,
            "type": "text",
            "description": "Main text generation model"
        })
        
        # Add decision model if it's different from main model
        if self.use_separate_decision_model and self.decision_model != self.model:
            self.models.append({
                "name": self.decision_model,
                "type": "text",
                "description": "Decision-making model"
            })
        
        # Add embedding model if embedding client exists
        if self.embedding_client:
            self.models.append({
                "name": self.embedding_client.model,
                "type": "embedding",
                "description": "Embedding generation model"
            })

    def _start_keepalive(self):
        """Start the model keepalive background thread."""
        if self.keepalive_running:
            return

        self.keepalive_running = True
        self.keepalive_thread = threading.Thread(
            target=self._keepalive_worker, daemon=True
        )
        self.keepalive_thread.start()
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Model keepalive started (interval: {self.keepalive_interval}s)"
        )

    def _stop_keepalive(self):
        """Stop the keepalive thread."""
        self.keepalive_running = False
        if self.keepalive_thread:
            self.keepalive_thread.join(timeout=5)
        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Model keepalive stopped"
        )

    def _keepalive_worker(self):
        """Background worker that sends keepalive requests to models."""
        while self.keepalive_running:
            try:
                # Wait for the interval
                for _ in range(self.keepalive_interval):
                    if not self.keepalive_running:
                        return
                    time.sleep(1)

                # Send keepalive to all registered models
                for model_info in self.models:
                    is_embedding = model_info["type"] == "embedding"
                    self._send_keepalive(
                        model_info["name"],
                        is_embedding=is_embedding,
                        description=model_info["description"]
                    )

            except Exception as e:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Keepalive error: {type(e).__name__}: {e}"
                )

    def _send_keepalive(self, model_name, is_embedding=False, description=""):
        """
        Send a minimal request to keep a model loaded.

        @param model_name Name of the model to ping
        @param is_embedding Whether this is an embedding model
        @param description Optional description of the model's purpose
        """
        try:
            url = f"{self.host}/api/{'embed' if is_embedding else 'generate'}"

            if is_embedding:
                # For embedding models, embed a single character
                payload = {"model": model_name, "input": "1"}
            else:
                # For LLM models, generate a minimal response
                payload = {
                    "model": model_name,
                    "prompt": "Reply only with the number 1, nothing else.",
                    "stream": False,
                    "options": {"num_predict": 2, "temperature": 0},
                }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                desc_suffix = f" ({description})" if description else ""
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Keepalive ping successful: {model_name}{desc_suffix}"
                )
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Keepalive ping failed for {model_name}: HTTP {response.status_code}"
                )

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Keepalive failed for {model_name}: {type(e).__name__}: {e}"
            )

    def _build_extended_prompt(self):
        """
        Build the extended smart home prompt with decision-making guidelines.
        Composes from: base template + decision-making extension (with language tags injected).

        @return Extended prompt template
        """
        # Build language tag list dynamically from configured languages
        language_tags = "\n".join(
            [
                f'                "{name}": "{code}",'
                for name, code in self.languages.items()
            ]
        )
        if language_tags:
            language_tags = language_tags.rstrip(
                ","
            )  # Remove trailing comma from last item
        else:
            # Fallback if no languages configured
            language_tags = '                "English": "en"'

        # Compose from three parts: base template + decision-making extension (with language tags)
        extended_section = self.decision_making_extension.format(
            language_tags=language_tags
        )

        return SMART_HOME_PROMPT_TEMPLATE + extended_section

    def set_model(self, model_name: str):
        """
        Change the model used for inference.

        @param model_name New model name
        """
        self.model = model_name

    def set_system_prompt(self, prompt: str):
        """
        Override the system prompt.

        @param prompt New system prompt
        """
        self.system_prompt = prompt

    def send_message(
        self,
        user_message: str,
        temperature: float = 0.1,
        top_p: float = 1,
        max_tokens: int = 4096,
        message_type: str = "command",
        from_chat: bool = False,
        conversation_id: str = None,
        original_text: str = None,
        stream: bool = False,
    ):
        """
        Send message to Ollama for processing.

        @param user_message The message to process (may include context for LLM)
        @param temperature Sampling temperature (0.1 for commands, 0.8 for responses)
        @param top_p Nucleus sampling parameter
        @param max_tokens Maximum tokens to generate
        @param message_type Either "command" for command parsing or "response" for processing function results
        @param from_chat Whether this command originates from chat (tracked for response processing)
        @param conversation_id Optional UUID of the conversation for message storage
        @param original_text The original user text without LLM context (used for storage only)
        @param stream Whether to stream the response (generator) or return complete response (dict)
        @return Parsed JSON response dict if stream=False, otherwise yields dict chunks
        """
        # Validate input
        if not user_message or not user_message.strip():
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Empty message provided"
            )
            if stream:
                yield {"response": "", "done": True}
                return
            else:
                return {"commands": []}

        # Choose system prompt based on message type and origin
        if message_type == "response":
            # SECOND PARSE: Response generation with full context
            # Add resume conversation and safety prompts
            base_prompt = (
                self.conversation_processor_prompt
                if self.last_message_from_chat
                else self.response_processor_prompt
            )

            # Compose: base prompt + resume conversation + safety
            system_prompt = base_prompt
            if self.resume_conversation_prompt:
                system_prompt += f"\n\n{self.resume_conversation_prompt}"
            if self.safety_prompt:
                system_prompt += f"\n\n{self.safety_prompt}"

            stream_suffix = " (streaming)" if stream else ""
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Response generation with context{stream_suffix} (resume + safety prompts included)"
            )
        else:
            # FIRST PARSE: Decision-making with minimal context
            system_prompt = self.system_prompt

        # Build the prompt with context if available
        prompt = self._build_prompt_with_context(user_message, message_type, from_chat)

        # Use higher temperature for response processing to make it more creative
        if message_type == "response":
            temperature = 0.8  # More creative for processing Wikipedia/news responses
            top_p = 0.90

        # Track from_chat for response processing (for both stream and non-stream)
        if message_type == "command" and from_chat:
            self.last_message_from_chat = from_chat
            self.last_user_message = original_text if original_text else user_message

        # Determine if we should use decision model (only for command parsing, not responses)
        use_decision_model = message_type == "command"

        # Send request to Ollama
        ollama_response = self._send_to_ollama(
            prompt,
            system_prompt,
            temperature,
            top_p,
            max_tokens,
            stream=stream,
            use_decision_model=use_decision_model,
        )

        if ollama_response is None:
            if stream:
                yield {"response": "", "done": True}
                return
            else:
                return {"commands": []}

        # Handle streaming response
        if stream:
            full_response = ""
            for chunk in ollama_response:
                if "response" in chunk:
                    full_response += chunk["response"]
                # Always yield the chunk (includes done flag)
                yield chunk

            # Parse complete response and queue for embedding/storage
            if conversation_id and original_text and full_response:
                try:
                    # Try to parse as JSON to extract nl_response
                    parsed = json.loads(full_response)
                    nl_response = parsed.get("nl_response", full_response)
                except json.JSONDecodeError:
                    # If not JSON, use full response
                    nl_response = full_response

                # Queue for embedding and storage
                if nl_response and self.pg_client and self.embedding_client:
                    try:
                        embedding_batch = {
                            "user_message": original_text,
                            "assistant_response": nl_response,
                            "conversation_id": conversation_id,
                        }
                        self.embedding_client.queue_messages(embedding_batch)
                        print(
                            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Queued streaming response for embedding and storage"
                        )
                    except Exception as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue streaming messages: {repr(e)}"
                        )
            return

        # Handle non-streaming response
        parsed = self._parse_ollama_response(ollama_response)

        self._handle_post_processing(
            parsed,
            message_type,
            from_chat,
            user_message,
            original_text,
            conversation_id,
        )

        return parsed

    def send_message_streaming(
        self,
        user_message: str,
        temperature: float = 0.8,
        top_p: float = 0.90,
        max_tokens: int = 4096,
        message_type: str = "command",
        from_chat: bool = False,
        conversation_id: str = None,
        original_text: str = None,
    ):
        """
        Send message to Ollama for processing with streaming response.
        
        DEPRECATED: Use send_message() with stream=True instead.

        @param user_message The message to process (may include context for LLM)
        @param temperature Sampling temperature (default 0.8 for more creative NL responses)
        @param top_p Nucleus sampling parameter
        @param max_tokens Maximum tokens to generate
        @param message_type Either "command" for command parsing or "response" for processing function results
        @param from_chat Whether this command originates from chat (tracked for response processing)
        @param conversation_id Optional UUID of the conversation for message storage
        @param original_text The original user text without LLM context (used for storage only)
        @yield Dict chunks with partial responses
        """
        # Delegate to unified send_message with stream=True
        yield from self.send_message(
            user_message=user_message,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            message_type=message_type,
            from_chat=from_chat,
            conversation_id=conversation_id,
            original_text=original_text,
            stream=True,
        )

    def _build_prompt_with_context(
        self, user_message: str, message_type: str, from_chat: bool
    ):
        """
        Build the prompt with appropriate context.

        @param user_message The user's message
        @param message_type Type of message (command/response)
        @param from_chat Whether from chat interface
        @return Formatted prompt with context
        """
        prompt = user_message

        if self.last_user_message:
            if message_type == "command":
                # Include last conversation in context for command parsing
                context_prefix = f"Previous user message: {self.last_user_message}\n\nCurrent user message: "
                prompt = context_prefix + user_message
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Including previous context in prompt"
                )
            elif message_type == "response":
                # Include last user message and response for response processing
                context_prefix = f"Original user query: {self.last_user_message}\n\n"
                prompt = context_prefix + user_message
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Including user query context in response processing"
                )

        return prompt

    def _send_to_ollama(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        stream: bool = False,
        use_decision_model: bool = False,
    ):
        """
        Send request to Ollama server.

        @param prompt User prompt
        @param system_prompt System prompt
        @param temperature Sampling temperature
        @param top_p Nucleus sampling
        @param max_tokens Max tokens to generate
        @param stream Whether to stream responses (for generators)
        @param use_decision_model Whether to use the decision model instead of main model
        @return Response data or None on error, or generator if stream=True
        """
        # Append safety prompt if enabled
        if is_safety_enabled() and SAFETY_INSTRUCTION_PROMPT:
            system_prompt = f"{system_prompt}\n\n{SAFETY_INSTRUCTION_PROMPT}"

        # Choose model based on whether this is decision-making phase
        model_to_use = (
            self.decision_model
            if (use_decision_model and self.use_separate_decision_model)
            else self.model
        )

        # Log which model is being used
        if use_decision_model and self.use_separate_decision_model:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using decision model: {model_to_use}"
            )
        elif stream:
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Using main model for response: {model_to_use}"
            )

        url = f"{self.host}/api/generate"

        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "system": system_prompt,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens,
            },
            "stream": stream,
            "reasoning_effort": "low",
        }

        try:
            if stream:
                # Return generator for streaming responses
                response = requests.post(url, json=payload, timeout=60, stream=True)
                response.raise_for_status()
                return self._stream_response(response)
            else:
                # Regular non-streaming response
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                return response.json()

        except requests.exceptions.Timeout:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request timeout connecting to Ollama at {self.host}"
            )
            return {
                "_timeout_detected": True,
                "response": json.dumps(
                    {
                        "nl_response": "I'm sorry, the request timed out. The language model is taking too long to respond. This might be due to a very long conversation context. Please try again or start a new conversation.",
                        "language": "en",
                    }
                ),
            }

        except requests.exceptions.ConnectionError as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Connection error to Ollama: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check if Ollama is running at {self.host}"
            )
            return None

        except requests.exceptions.HTTPError as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] HTTP error from Ollama: {repr(e)}"
            )
            if hasattr(e.response, "status_code"):
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Status code: {e.response.status_code}"
                )
            return None

        except requests.exceptions.RequestException as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request error: {repr(e)}"
            )
            return None

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error during request: {type(e).__name__}: {repr(e)}"
            )
            return None

    def _stream_response(self, response):
        """
        Generator that yields streaming response chunks from Ollama.

        @param response The requests Response object with stream=True
        @yield Dict chunks containing response text
        """
        try:
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        yield chunk
                    except json.JSONDecodeError as e:
                        print(
                            f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to parse streaming chunk: {repr(e)}"
                        )
                        continue
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Error during streaming: {type(e).__name__}: {repr(e)}"
            )
            yield {"error": str(e)}

    def _parse_ollama_response(self, data):
        """
        Parse response from Ollama server.

        @param data Response data from Ollama
        @return Parsed JSON response or error dict
        """
        # Extract response field
        if "response" not in data:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No 'response' field in Ollama output"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Response keys: {list(data.keys())}"
            )
            return {"commands": []}

        try:
            output = str(data["response"])
        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to extract response: {repr(e)}"
            )
            return {"commands": []}

        if not output or not output.strip():
            print(
                f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned empty response"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] This may indicate Ollama is not properly loaded or the model is having issues"
            )
            return {"commands": []}

        print(
            f"{self.class_prefix_message} [{LogLevel.INFO.name}] Ollama response: {output[:100]}..."
        )

        try:
            parsed = json.loads(output)

            if not isinstance(parsed, dict):
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Response is not a dict"
                )
                return {"commands": []}

            return parsed

        except json.JSONDecodeError as e:
            # Try to recover from double-brace errors ({{ instead of {)
            if output and output.startswith("{{") and output.endswith("}}"):
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Detected double braces, stripping and retrying"
                )
                try:
                    parsed = json.loads(output[1:-1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

            # If model returned plain text instead of JSON, treat it as an nl_response
            if output and not output.strip().startswith("{"):
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Model returned plain text instead of JSON, treating as nl_response"
                )
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Text response: {output[:200]}..."
                )
                return {"nl_response": output.strip(), "language": "en"}

            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse Ollama response as JSON: {repr(e)}"
            )
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Output length: {len(output) if output else 0}"
            )
            if output:
                print(
                    f"{self.class_prefix_message} [{LogLevel.INFO.name}] Raw output (first 300 chars): {output[:300]}"
                )
            else:
                print(
                    f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned EMPTY response - check if Ollama server is running and responding"
                )
            return {"commands": []}

        except Exception as e:
            print(
                f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error parsing output: {repr(e)}"
            )
            return {"commands": []}

    def _handle_post_processing(
        self,
        parsed,
        message_type,
        from_chat,
        user_message,
        original_text,
        conversation_id,
    ):
        """
        Handle post-processing after parsing response.

        @param parsed Parsed response
        @param message_type Type of message
        @param from_chat Whether from chat
        @param user_message User's message
        @param original_text Original text without context
        @param conversation_id Conversation UUID
        """
        # Queue embeddings when nl_response exists
        text_to_save = original_text if original_text else user_message
        if "nl_response" in parsed and (from_chat or self.last_message_from_chat):
            nl_response_text = parsed.get("nl_response", "")
            if nl_response_text and self.pg_client and self.embedding_client:
                try:
                    embedding_batch = {
                        "user_message": text_to_save,
                        "assistant_response": nl_response_text,
                        "conversation_id": conversation_id,
                    }
                    self.embedding_client.queue_messages(embedding_batch)
                    print(
                        f"{self.class_prefix_message} [{LogLevel.INFO.name}] Queued message batch for embedding and storage (user_message + nl_response)"
                    )

                except Exception as e:
                    print(
                        f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to queue messages for embedding: {repr(e)}"
                    )

        if message_type == "command":
            self.last_user_message = user_message
            self.last_message_from_chat = from_chat
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Updated context with current exchange (from_chat={from_chat})"
            )
        elif message_type == "response":
            self.last_message_from_chat = False
            print(
                f"{self.class_prefix_message} [{LogLevel.INFO.name}] Reset chat origin flag after response processing"
            )
