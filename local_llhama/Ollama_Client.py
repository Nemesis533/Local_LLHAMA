"""
@file Ollama_Client.py
@brief Client for interacting with Ollama server for LLM inference.

This module provides a lightweight client to communicate with an Ollama
server for language model inference, supporting both command parsing
and response processing. Includes EmbeddingClient for non-blocking vector embeddings.
"""

# === System Imports ===
import json
import requests
import threading
from queue import Queue
from typing import List, Optional

# === Custom Imports ===
from .Shared_Logger import LogLevel
from .LLM_Prompts import SMART_HOME_PROMPT_TEMPLATE, RESPONSE_PROCESSOR_PROMPT,CONVERSATION_PROCESSOR_PROMPT


class OllamaClient:
    """
    Client to interact with Ollama server for language model inference.
    """
 
    def __init__(self, ha_client, host: str = 'http://your_ip:11434', model: str = 'qwen3-14b-gpu128', system_prompt: str = '', pg_client=None, conversation_loader=None):
        """
        @brief Initialize Ollama client with connection details.
        @param ha_client HomeAssistantClient instance for device context.
        @param host Ollama server URL.
        @param model Model name to use on Ollama server.
        @param system_prompt Optional system prompt override.
        @param pg_client Optional PostgreSQLClient for storing message embeddings.
        @param conversation_loader Optional ConversationLoader for accessing previous conversations.
        """
        self.class_prefix_message = "[OllamaClient]"
        self.host = host.rstrip('/')
        self.model = model
        self.ha_client = ha_client
        self.pg_client = pg_client
        self.conversation_loader = conversation_loader
        self.devices_context = self.ha_client.generate_devices_prompt_fragment()
        self.response_processor_prompt = RESPONSE_PROCESSOR_PROMPT
        self.conversation_processor_prompt = CONVERSATION_PROCESSOR_PROMPT
        
        # Initialize embedding client (non-blocking)
        self.embedding_client = EmbeddingClient(host=self.host, model='embeddinggemma', pg_client=self.pg_client)
        
        # Context management - keep only last request and response
        self.last_user_message = None
        self.last_message_from_chat = False  # Track if last command was from chat


        self.languages = {
            "English": "en",
            "French": "fr",
            "German": "de",
            "Italian": "it",
            "Spanish": "es",
            "Russian": "ru"
        }

        # Extend smart home prompt with additional decision-making guidelines
        extended_prompt = SMART_HOME_PROMPT_TEMPLATE + """
        IMPORTANT DECISION MAKING:
        
        1. If the user asks about factual information, current events, or topics requiring external knowledge:
           - Use get_wikipedia_summary for general knowledge and facts
           - Use get_news_summary for recent events and news
           - DO NOT make up information in an nl_response
        
        2. Only use nl_response for:
           - Simple conversational replies (greetings, thanks, clarifications)
           - Acknowledgments or confirmations
           - Questions you can answer with absolute certainty
           - General chitchat that doesn't require facts
        
        3. When in doubt about a topic, ALWAYS prefer calling a function over generating an nl_response.
        
        If you cannot respond with a command and the query doesn't need external information, provide a natural language response in this JSON format:

        {{
            "nl_response": "<string>",
            "language":"<string>"
        }}

        choosing between the following language tags:
                "English": "en",
                "French": "fr",
                "German": "de",
                "Italian": "it",
                "Spanish": "es",
                "Russian": "ru"             

        """
        
        # Generate simple functions context from command schema
        simple_functions_context = self._generate_simple_functions_context()
        
        self.system_prompt = extended_prompt.format(
            devices_context=self.devices_context,
            simple_functions_context=simple_functions_context,
        )
        
    def _generate_simple_functions_context(self):
        """
        @brief Generate description of available simple functions from command schema.
        @return Formatted string describing available simple functions.
        """
        if not hasattr(self.ha_client, 'simple_functions') or not self.ha_client.simple_functions:
            return "No additional simple functions available."
        
        command_schema = self.ha_client.simple_functions.command_schema
        if not command_schema:
            return "No additional simple functions available."
        
        functions_desc = ["Available Simple Functions:"]
        
        for entity_id, entity_info in command_schema.items():
            actions = entity_info.get('actions', [])
            if not actions:
                continue
            
            # Get description from schema
            description = entity_info.get('description', f'Available actions: {", ".join(actions)}')
            functions_desc.append(f"- {entity_id}: {description}")
            
            # Get example from schema
            example = entity_info.get('example')
            if example:
                functions_desc.append(f'  Example: {json.dumps(example)}')
            else:
                # Fallback example if not provided
                functions_desc.append(f'  Example: {{"action": "{actions[0]}", "target": "{entity_id}"}}')
            
            # Add parameter information if available
            parameters = entity_info.get('parameters', {})
            if parameters:
                optional_params = [name for name, info in parameters.items() if not info.get('required', False)]
                if optional_params:
                    param_desc = ', '.join([f'"{p}"' for p in optional_params])
                    functions_desc.append(f'  Optional parameters: {param_desc}')
        
        return "\n".join(functions_desc) if len(functions_desc) > 1 else "No additional simple functions available."
    
    def set_model(self, model_name: str):
        """
        @brief Change the model used for inference.
        @param model_name New model name.
        """
        self.model = model_name
 
    def set_system_prompt(self, prompt: str):
        """
        @brief Override the system prompt.
        @param prompt New system prompt.
        """
        self.system_prompt = prompt
    
    def send_message(self, user_message: str, 
                     temperature: float = 0.1, 
                     top_p: float = 1,
                       max_tokens: int = 4096, 
                       message_type: str = "command", 
                       from_chat: bool = False,
                       conversation_id: str = None,
                       original_text: str = None,
                       client_id: str = None):
        """
        @brief Send message to Ollama for processing.
        @param user_message The message to process (may include context for LLM).
        @param temperature Sampling temperature.
        @param top_p Nucleus sampling parameter.
        @param max_tokens Maximum tokens to generate.
        @param message_type Either "command" for command parsing or "response" for processing function results.
        @param from_chat Whether this command originates from chat (tracked for response processing).
        @param conversation_id Optional UUID of the conversation for message storage.
        @param original_text The original user text without LLM context (used for storage only).
        @param client_id Optional client identifier for context window tracking.
        @return Parsed JSON response.
        """
        # Validate input
        if not user_message or not user_message.strip():
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Empty message provided")
            return {"commands": []}
        
        # Choose system prompt based on message type and origin
        if message_type == "response":
            # Use conversation prompt if the original command was from chat
            if self.last_message_from_chat:
                system_prompt = self.conversation_processor_prompt
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing chat response with conversation prompt")
            else:
                system_prompt = self.response_processor_prompt
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing simple function response")
        else:
            system_prompt = self.system_prompt
        
        # Build the prompt with context if available
        prompt = user_message
        if self.last_user_message:
            if message_type == "command":
                # Include last conversation in context for command parsing
                context_prefix = f"Previous user message: {self.last_user_message}\n\nCurrent user message: "
                prompt = context_prefix + user_message
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Including previous context in prompt")
            elif message_type == "response":
                # Include last user message and response for response processing
                context_prefix = f"Original user query: {self.last_user_message}\n\n"
                prompt = context_prefix + user_message
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Including user query context in response processing")
        
        url = f"http://{self.host}/api/generate"

        # Use higher temperature for response processing to make it more creative
        if message_type == "response":
            temperature = 0.8  # More creative for processing Wikipedia/news responses
            top_p = 0.90

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_predict": max_tokens
            },
            "stream": False,
            "reasoning_effort": "low"
        }

        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request timeout connecting to Ollama at {self.host}")
            # Return timeout marker that ChatHandler can detect
            return {
                "_timeout_detected": True,
                "nl_response": "I'm sorry, the request timed out. The language model is taking too long to respond. This might be due to a very long conversation context. Please try again or start a new conversation.",
                "language": "en"
            }
        except requests.exceptions.ConnectionError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Connection error to Ollama: {repr(e)}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check if Ollama is running at {self.host}")
            return {"commands": []}
        except requests.exceptions.HTTPError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] HTTP error from Ollama: {repr(e)}")
            if hasattr(e.response, 'status_code'):
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Status code: {e.response.status_code}")
            return {"commands": []}
        except requests.exceptions.RequestException as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request error: {repr(e)}")
            return {"commands": []}
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error during request: {type(e).__name__}: {repr(e)}")
            return {"commands": []}
        
        # Parse response
        try:
            data = response.json()
        except ValueError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Invalid JSON from Ollama: {repr(e)}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Response text: {response.text[:200]}...")
            return {"commands": []}
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse response: {repr(e)}")
            return {"commands": []}

        # Extract response field
        if "response" not in data:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No 'response' field in Ollama output")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Response keys: {list(data.keys())}")
            return {"commands": []}
        
        try:
            output = str(data["response"])
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to extract response: {repr(e)}")
            return {"commands": []}
        
        # Check for empty response
        if not output or not output.strip():
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned empty response")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] This may indicate Ollama is not properly loaded or the model is having issues")
            return {"commands": []}

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Ollama response: {output[:100]}...")

        # Parse JSON from output
        try:
            parsed = json.loads(output)
            # Validate structure
            if not isinstance(parsed, dict):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Response is not a dict")
                return {"commands": []}
            
            # Queue embeddings when nl_response exists AND (message is from chat OR last message was from chat)
            # Only save user message + LLM response, skip intermediate system responses
            # Use original_text (without context) if provided, otherwise use user_message
            text_to_save = original_text if original_text else user_message
            if "nl_response" in parsed and (from_chat or self.last_message_from_chat):
                nl_response_text = parsed.get("nl_response", "")
                if nl_response_text and self.pg_client and self.embedding_client:
                    try:
                        # Queue both messages as a batch for embedding and storage
                        embedding_batch = {
                            "user_message": text_to_save,
                            "assistant_response": nl_response_text,
                            "conversation_id": conversation_id
                        }
                        self.embedding_client.queue_messages(embedding_batch)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Queued message batch for embedding and storage (user_message + nl_response)")
                    
                    except Exception as e:
                        print(f"{self.class_prefix_message} [{LogLevel.CRITICAL}] Failed to queue messages for embedding: {repr(e)}")
            
            # Update context for command type messages and nl_response messages (not for response processing)
            if message_type == "command":
                # Store current exchange as the "last" exchange, replacing any previous one
                self.last_user_message = user_message
                self.last_message_from_chat = from_chat  # Track if this command is from chat
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Updated context with current exchange (from_chat={from_chat})")
            elif message_type == "response":
                # Reset the chat flag after processing response
                self.last_message_from_chat = False
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Reset chat origin flag after response processing")
                    
            
            return parsed
        except json.JSONDecodeError as e:
            # Try to recover from double-brace errors ({{ instead of {)
            if output and output.startswith('{{') and output.endswith('}}'):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Detected double braces, stripping and retrying")
                try:
                    parsed = json.loads(output[1:-1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            
            # If model returned plain text instead of JSON, treat it as an nl_response
            if output and not output.strip().startswith('{'):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Model returned plain text instead of JSON, treating as nl_response")
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Text response: {output[:200]}...")
                return {
                    "nl_response": output.strip(),
                    "language": "en"
                }
            
            # Log the actual response for debugging
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse Ollama response as JSON: {repr(e)}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Output length: {len(output) if output else 0}")
            if output:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Raw output (first 300 chars): {output[:300]}")
            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned EMPTY response - check if Ollama server is running and responding")
            return {"commands": []}
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error parsing output: {repr(e)}")
            return {"commands": []}


class EmbeddingClient:
    """
    @brief Non-blocking embedding client using embedding-gemma model via Ollama.
    
    Processes embedding requests asynchronously via queue to avoid blocking main thread.
    Automatically saves embeddings to PostgreSQL via callback.
    """
    
    def __init__(self, host: str = 'http://localhost:11434', model: str = 'embedding-gemma', pg_client=None):
        """
        @brief Initialize embedding client with Ollama connection.
        
        @param host Ollama server URL.
        @param model Embedding model name (default: embedding-gemma).
        @param pg_client PostgreSQLClient instance for storing embeddings.
        """
        self.class_prefix_message = "[EmbeddingClient]"
        # Ensure host has http:// scheme for requests library
        if not host.startswith('http://') and not host.startswith('https://'):
            host = f'http://{host}'
        self.host = host.rstrip('/')
        self.model = model
        self.pg_client = pg_client
        
        # Queue for embedding requests (message_id, text, user_data)
        self.embedding_queue = Queue()
        
        # Results cache (message_id -> embedding)
        self.results_cache = {}
        
        # Lock for thread-safe cache access
        self._cache_lock = threading.Lock()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._embedding_worker, daemon=True)
        self.worker_thread.start()
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Initialized with host={self.host}, model={self.model}")
    
    def _embedding_worker(self) -> None:
        """
        @brief Worker thread that processes embedding requests from queue.
        
        Runs continuously, pulls message batches from queue, inserts messages to DB,
        generates embeddings, saves to PostgreSQL, and stores in results cache.
        """
        while True:
            try:
                item = self.embedding_queue.get()
                
                if item is None:  # Shutdown signal
                    break
                
                batch = item
                
                try:
                    # Write user message to DB and get its ID
                    user_msg_id = self.pg_client.insert_message(
                        conversation_id=batch.get("conversation_id", 0),
                        role='user',
                        content=batch.get("user_message", "")
                    )
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Inserted user message {user_msg_id}")
                    
                    # Write assistant response to DB and get its ID
                    assistant_msg_id = self.pg_client.insert_message(
                        conversation_id=batch.get("conversation_id", 0),
                        role='assistant',
                        content=batch.get("assistant_response", "")
                    )
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Inserted assistant response {assistant_msg_id}")
                    
                    # Get embeddings for both messages
                    user_embedding = self._get_embedding_from_ollama(batch.get("user_message", ""))
                    assistant_embedding = self._get_embedding_from_ollama(batch.get("assistant_response", ""))
                    
                    # Save embeddings to DB
                    if user_embedding:
                        self.pg_client.insert_message_embedding(user_msg_id, user_embedding)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Saved embedding for user message {user_msg_id}")
                    
                    if assistant_embedding:
                        self.pg_client.insert_message_embedding(assistant_msg_id, assistant_embedding)
                        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Saved embedding for assistant response {assistant_msg_id}")
                    
                    # Store in cache for retrieval if needed
                    with self._cache_lock:
                        self.results_cache[user_msg_id] = user_embedding
                        self.results_cache[assistant_msg_id] = assistant_embedding
                
                except Exception as e:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL}] Error processing message batch: {str(e)}")
                
                finally:
                    self.embedding_queue.task_done()
            
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL}] Worker thread error: {str(e)}")
    
    def _get_embedding_from_ollama(self, text: str) -> Optional[List[float]]:
        """
        @brief Get embedding vector from Ollama server.
        
        @param text Text to embed.
        @return List of floats representing embedding, or None if failed.
        """
        try:
            response = requests.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if embedding:
                    return embedding
            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Ollama returned status {response.status_code}")
        
        except requests.exceptions.RequestException as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL}] Request failed: {str(e)}")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL}] Embedding error: {str(e)}")
        
        return None
    
    def queue_embedding(self, message_id: int, text: str) -> None:
        """
        @brief Queue a message for embedding (non-blocking).
        
        Processing happens asynchronously in worker thread.
        
        @param message_id ID of the message being embedded.
        @param text Text content to embed.
        
        @deprecated Use queue_messages() instead for batch processing.
        """
        # Legacy method - convert to batch format
        batch = {
            "user_message": text,
            "assistant_response": "",
            "conversation_id": 0
        }
        self.queue_messages(batch)
    
    def queue_messages(self, batch: dict) -> None:
        """
        @brief Queue a batch of messages for DB insertion and embedding.
        
        Processes both user message and assistant response in single transaction.
        
        @param batch Dictionary with keys:
            - user_message: User's message text (str)
            - assistant_response: LLM's response text (str)
            - conversation_id: UUID of conversation (str, required)
        """
        self.embedding_queue.put(batch)
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Queued message batch for processing")
    
    def get_embedding(self, message_id: int, timeout: float = 30.0) -> Optional[List[float]]:
        """
        @brief Get embedding result (blocking with timeout).
        
        Waits for embedding to complete or timeout.
        
        @param message_id ID of the message to retrieve embedding for.
        @param timeout Maximum seconds to wait for result.
        @return Embedding vector or None if not found/timeout.
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._cache_lock:
                if message_id in self.results_cache:
                    embedding = self.results_cache[message_id]
                    # Clean up cache
                    del self.results_cache[message_id]
                    return embedding
            
            time.sleep(0.1)
        
        print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Timeout waiting for embedding {message_id}")
        return None
    
    def shutdown(self) -> None:
        """
        @brief Gracefully shutdown embedding worker thread.
        
        Waits for queue to empty before shutting down.
        """
        self.embedding_queue.join()  # Wait for all pending items
        self.embedding_queue.put(None)  # Shutdown signal
        self.worker_thread.join(timeout=5)
        
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Shutdown complete")

