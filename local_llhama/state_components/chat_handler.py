"""
Chat Handler Component

Handles chat messages from WebUI in dedicated thread, bypassing the state machine.
Allows concurrent chat interactions without interfering with voice workflow.
"""

import threading
import time
from queue import Empty

from ..Ollama_Client import OllamaClient
from ..Shared_Logger import LogLevel


class ChatHandler:
    """
    @brief Handles WebUI chat messages independently from the state machine.
    
    Processes chat messages in a dedicated thread, allowing multiple concurrent
    chat users without interfering with voice input processing.
    """
    
    def __init__(self, chat_queue, command_llm, ha_client, message_handler, log_prefix="[Chat Handler]"):
        """
        Initialize the chat handler.
        
        @param chat_queue Queue for incoming chat messages
        @param command_llm LLM instance for command parsing
        @param ha_client Home Assistant client for command execution
        @param message_handler MessageHandler instance for sending responses
        @param log_prefix Prefix for log messages
        """
        self.chat_queue = chat_queue
        self.command_llm = command_llm
        self.ha_client = ha_client
        self.message_handler = message_handler
        self.log_prefix = log_prefix
        
        # Track last 3 interactions per client (client_id -> list of {user, assistant} dicts)
        self.conversation_history = {}
        # Track current user query for command execution flow (client_id -> query)
        self.pending_user_queries = {}
        # Track conversation UUIDs per client (client_id -> conversation_uuid)
        self.client_conversations = {}
        
        # Track if first message after loading conversation (client_id -> bool)
        # True = load full context from DB on next message, False = use only in-memory history
        self.first_message_after_load = {}
        
        # Adaptive context window management (client_id -> current_max_words)
        # Starts at DEFAULT_CONTEXT_WORDS, reduces on timeout to prevent future hangs
        self.context_word_limits = {}  # Will be populated dynamically
        # These limits are restrictive, but required to keep it feasible on a modest card liek the 4060Ti 16GB
        self.DEFAULT_CONTEXT_WORDS = 200 
        self.MIN_CONTEXT_WORDS = 100  
        self.CONTEXT_REDUCTION_FACTOR = 0.7  # Reduce by 30% on timeout
        
        # Get PostgreSQL client from command_llm if available
        self.pg_client = getattr(command_llm, 'pg_client', None)
        
        # Get ConversationLoader from command_llm if available
        self.conversation_loader = getattr(command_llm, 'conversation_loader', None)
        
        self.running = False
        self.worker_thread = None
        
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler initialized")
    
    def start(self):
        """Start the chat handler worker thread."""
        if self.running:
            print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Chat handler already running")
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._process_chat_messages, daemon=True)
        self.worker_thread.start()
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler worker thread started")
    
    def stop(self):
        """Stop the chat handler worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat handler stopped")
    
    def _process_chat_messages(self):
        """Worker thread that processes incoming chat messages."""
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Chat message processor started")
        
        while self.running:
            try:
                # Non-blocking get with timeout
                message = self.chat_queue.get(timeout=0.1)
                
                if isinstance(message, dict):
                    text = message.get('text')
                    client_id = message.get('client_id')
                    conversation_id = message.get('conversation_id')  # Get conversation_id from queue
                    
                    if text:
                        self._handle_chat_message(text, client_id, conversation_id)
                        
            except Empty:
                continue
            except Exception as e:
                print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error processing chat message: {type(e).__name__}: {e}")
                time.sleep(0.1)
    
    def _handle_chat_message(self, text, client_id, passed_conversation_id=None):
        """
        Process a single chat message.
        
        @param text The user's message text
        @param client_id The client identifier for routing responses
        @param passed_conversation_id Optional conversation_id from frontend (when continuing existing chat)
        """
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Processing chat message from client {client_id}: {text}")
        
        try:
            # Ensure conversation exists for this client
            # If passed_conversation_id is provided, use it (continuing existing chat)
            # Otherwise, use cached or create new
            if passed_conversation_id:
                # User is continuing an existing conversation loaded from history
                # Only set the flag if this is a DIFFERENT conversation than before
                old_conversation_id = self.client_conversations.get(client_id)
                
                if old_conversation_id != passed_conversation_id:
                    # Conversation changed - set flag to load full context from DB
                    if client_id in self.conversation_history:
                        del self.conversation_history[client_id]
                    if client_id in self.pending_user_queries:
                        del self.pending_user_queries[client_id]
                    self.first_message_after_load[client_id] = True
                    
                    print(f"{self.log_prefix} [{LogLevel.INFO.name}] Switched to different conversation {passed_conversation_id}, cleared previous context, will load full context on next message")
                else:
                    # Same conversation, continue with existing in-memory history
                    print(f"{self.log_prefix} [{LogLevel.INFO.name}] Continuing in same conversation {passed_conversation_id}")
                
                self.client_conversations[client_id] = passed_conversation_id
                conversation_id = passed_conversation_id
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] Using existing conversation {conversation_id} for client {client_id}")
            elif client_id not in self.client_conversations:
                # This should rarely happen now since Web_Server creates conversations
                # But keep as fallback for internal routing
                if self.pg_client:
                    try:
                        # Create new conversation with authenticated user_id (client_id is user.id)
                        user_id = int(client_id)
                        from datetime import datetime
                        now = datetime.now()
                        conv_datetime = now.strftime("%b %d, %Y at %H:%M")
                        conversation_id = self.pg_client.create_conversation(user_id=user_id, title=f"Chat - {conv_datetime}")
                        self.client_conversations[client_id] = conversation_id
                        print(f"{self.log_prefix} [{LogLevel.INFO.name}] [Fallback] Created new conversation {conversation_id} for user {user_id}")
                        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Cleared in-memory history for fresh start")
                    except Exception as e:
                        print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to create conversation: {e}")
                        self.client_conversations[client_id] = None
                else:
                    self.client_conversations[client_id] = None
            
            conversation_id = self.client_conversations.get(client_id)
            
            # Send user message to WebUI
            user_message = f"{self.log_prefix} [User Prompt]: {text}"
            self.message_handler.send_to_web_server(user_message, client_id=client_id)
            
            # Parse with LLM
            structured_output = self._parse_with_llm(text, client_id, conversation_id)
            
            if not structured_output:
                self._send_error_response("Failed to parse message", client_id)
                return
            
            # Handle different response types and track responses
            assistant_response = None
            if structured_output.get("commands"):
                # Store user query for later (will be saved after command completes)
                self.pending_user_queries[client_id] = text
                self._handle_commands(structured_output, client_id, conversation_id)
                return  # Don't store yet, will be stored in _handle_simple_function_result or _handle_commands
            elif structured_output.get("nl_response"):
                assistant_response = structured_output.get("nl_response")
                self._handle_nl_response(structured_output, client_id)
            else:
                self._send_error_response("No valid commands or responses extracted", client_id)
                return
            
            # Store interaction in history (only for nl_response, commands stored separately)
            if assistant_response:
                self._add_to_history(client_id, text, assistant_response)
                
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error handling chat message: {type(e).__name__}: {e}")
            self._send_error_response("An error occurred processing your message", client_id)
    
    def _parse_with_llm(self, text, client_id, conversation_id=None):
        """Parse text with LLM and return structured output."""
        try:
            # Build prompt with conversation history
            prompt = text
            
            # Check if this is the first message after loading a conversation
            # If so, load full context from DB. Otherwise, use only in-memory history (last 3 interactions)
            persistent_context = None
            is_first_message_after_load = self.first_message_after_load.get(client_id, False)
            
            if is_first_message_after_load and hasattr(self, 'conversation_loader') and self.conversation_loader and conversation_id:
                try:
                    # Get current context word limit for this client (adaptive window)
                    if client_id not in self.context_word_limits:
                        self.context_word_limits[client_id] = self.DEFAULT_CONTEXT_WORDS
                    
                    max_words = self.context_word_limits[client_id]
                    
                    # Load full context from DB on first message after conversation load
                    persistent_context = self.conversation_loader.get_conversation_context_for_llm(
                        conversation_id,
                        max_words=max_words
                    )
                    if persistent_context:
                        context_chars = len(persistent_context)
                        context_words = len(persistent_context.split())
                        print(f"{self.log_prefix} [{LogLevel.INFO.name}] [FIRST MESSAGE] Loaded full conversation context ({context_chars} chars, ~{context_words} words, limit: {max_words})")
                        # Reset flag after loading - subsequent messages use in-memory history
                        self.first_message_after_load[client_id] = False
                    else:
                        print(f"{self.log_prefix} [{LogLevel.INFO.name}] No persistent context found for conversation {conversation_id}")
                        self.first_message_after_load[client_id] = False
                except Exception as e:
                    print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Failed to load conversation context: {repr(e)}")
                    self.first_message_after_load[client_id] = False
            elif is_first_message_after_load:
                # Flag was set but we couldn't load (missing loader/conversation_id)
                self.first_message_after_load[client_id] = False
            
            # Include conversation context if available (only for first message after load)
            if persistent_context:
                from ..LLM_Prompts import RESUME_CONVERSATION_PROMPT
                context_prompt = f"{RESUME_CONVERSATION_PROMPT}\n\n{persistent_context}\n\n---\n\nThis is the user's next message: {text}"
                prompt = context_prompt
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] Using full persistent context from database (first message after load)")
            elif client_id in self.conversation_history and self.conversation_history[client_id]:
                # Use in-memory conversation history (last 3 interactions) for all subsequent messages
                history = self.conversation_history[client_id]
                history_text = "Previous interactions with the user:\n"
                for interaction in history:
                    history_text += f"User: {interaction['user']}\n"
                    history_text += f"Assistant: {interaction['assistant']}\n"
                prompt = f"{history_text}\nThis is the last thing the user asked: {text}"
                print(f"{self.log_prefix} [{LogLevel.INFO.name}] Using in-memory history with {len(history)} previous interactions")
            
            if not isinstance(self.command_llm, OllamaClient):
                return self.command_llm.parse_with_llm(prompt)
            else:
                # Pass original_text separately so it's saved to DB instead of the full prompt with context
                result = self.command_llm.send_message(prompt, from_chat=True, conversation_id=conversation_id, original_text=text, client_id=client_id)
                
                # Check if request timed out (indicating context too large)
                if result and result.get('_timeout_detected'):
                    self._reduce_context_window(client_id)
                    # Don't return yet - just log and continue (timeout handled by returning nl_response fallback)
                    print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Timeout detected, reduced context window to {self.context_word_limits.get(client_id, self.DEFAULT_CONTEXT_WORDS)} words")
                    # Remove the marker before returning
                    result.pop('_timeout_detected', None)
                
                return result
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] LLM parsing failed: {type(e).__name__}: {e}")
            # If timeout, attempt to reduce context window for next attempt
            if 'timeout' in str(e).lower():
                self._reduce_context_window(client_id)
            return None
    
    def _reduce_context_window(self, client_id):
        """
        Reduce the context window for a client after timeout.
        Uses CONTEXT_REDUCTION_FACTOR to gradually reduce until MIN_CONTEXT_WORDS.
        """
        if client_id not in self.context_word_limits:
            self.context_word_limits[client_id] = self.DEFAULT_CONTEXT_WORDS
        
        old_limit = self.context_word_limits[client_id]
        new_limit = max(
            int(old_limit * self.CONTEXT_REDUCTION_FACTOR),
            self.MIN_CONTEXT_WORDS
        )
        self.context_word_limits[client_id] = new_limit
        
        print(f"{self.log_prefix} [{LogLevel.WARNING.name}] Context window reduced for client {client_id}: {old_limit} -> {new_limit} words")
    
    def _handle_commands(self, structured_output, client_id, conversation_id=None):
        """
        Execute commands and send results back to client.
        
        @param structured_output Parsed command structure from LLM
        @param client_id Client identifier for routing
        @param conversation_id UUID of the conversation
        """
        commands = structured_output.get("commands", [])
        language = structured_output.get("language", "en")
        
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Executing {len(commands)} command(s)")
        
        try:
            # Execute commands using HA client (same as state machine)
            results = self.ha_client.send_commands(structured_output)
            
            if results:
                # Check if any simple function results need LLM conversion
                has_simple_function = any(
                    result.get("type") == "simple_function" 
                    for result in results 
                    if isinstance(result, dict)
                )
                
                if has_simple_function and isinstance(self.command_llm, OllamaClient):
                    self._handle_simple_function_result(results, language, client_id, conversation_id)
                else:
                    # Pure HA commands: just send confirmation
                    confirmation = "Commands executed successfully"
                    message = f"{self.log_prefix} [Command Result]: {confirmation}"
                    self.message_handler.send_to_web_server(message, client_id=client_id)
                    
                    # Store interaction in history
                    if client_id in self.pending_user_queries:
                        self._add_to_history(client_id, self.pending_user_queries[client_id], confirmation)
                        del self.pending_user_queries[client_id]
            else:
                self._send_error_response("Command execution returned no results", client_id)
                
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Command execution failed: {type(e).__name__}: {e}")
            self._send_error_response(f"Failed to execute commands: {str(e)}", client_id)
    
    def _handle_simple_function_result(self, command_result, language, client_id, conversation_id=None):
        """
        Convert simple function results to natural language.
        
        @param command_result Results from command execution
        @param language Target language for response
        @param client_id Client identifier for routing
        @param conversation_id UUID of the conversation
        """
        try:
            simple_function_results = [
                r for r in command_result 
                if isinstance(r, dict) and r.get("type") == "simple_function"
            ]
            
            # Send to LLM for natural language conversion
            # This is an internal processing step, so we pass the original user query as original_text
            # This ensures the DB saves the user's actual question, not the conversion instruction
            llm_input = f"Convert these function results into a natural language response in {language} language: {simple_function_results}"
            original_user_query = self.pending_user_queries.get(client_id, "")
            nl_output = self.command_llm.send_message(llm_input, message_type="response", conversation_id=conversation_id, original_text=original_user_query)
            
            if nl_output and nl_output.get("nl_response"):
                nl_message = nl_output.get("nl_response")
                message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
                self.message_handler.send_to_web_server(message, client_id=client_id)
                
                # Store interaction in history
                if client_id in self.pending_user_queries:
                    self._add_to_history(client_id, self.pending_user_queries[client_id], nl_message)
                    del self.pending_user_queries[client_id]
            else:
                # Fallback
                fallback_msg = str(simple_function_results)
                message = f"{self.log_prefix} [Command Result]: {fallback_msg}"
                self.message_handler.send_to_web_server(message, client_id=client_id)
                
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Simple function conversion failed: {type(e).__name__}: {e}")
            self._send_error_response("Failed to format response", client_id)
    
    def _handle_nl_response(self, structured_output, client_id):
        """
        Send natural language response to client.
        
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
    
    def _add_to_history(self, client_id, user_text, assistant_text):
        """
        Add interaction to conversation history, keeping last 3.
        
        @param client_id Client identifier
        @param user_text User's message
        @param assistant_text Assistant's response
        """
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        
        self.conversation_history[client_id].append({
            'user': user_text,
            'assistant': assistant_text
        })
        
        # Keep only last 3 interactions
        if len(self.conversation_history[client_id]) > 3:
            self.conversation_history[client_id] = self.conversation_history[client_id][-3:]
        
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Stored interaction for client {client_id} (history size: {len(self.conversation_history[client_id])})")
