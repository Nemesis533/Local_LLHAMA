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
                    
                    if text:
                        self._handle_chat_message(text, client_id)
                        
            except Empty:
                continue
            except Exception as e:
                print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error processing chat message: {type(e).__name__}: {e}")
                time.sleep(0.1)
    
    def _handle_chat_message(self, text, client_id):
        """
        Process a single chat message.
        
        @param text The user's message text
        @param client_id The client identifier for routing responses
        """
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Processing chat message from client {client_id}: {text}")
        
        try:
            # Send user message to WebUI
            user_message = f"{self.log_prefix} [User Prompt]: {text}"
            self.message_handler.send_to_web_server(user_message, client_id=client_id)
            
            # Parse with LLM
            structured_output = self._parse_with_llm(text)
            
            if not structured_output:
                self._send_error_response("Failed to parse message", client_id)
                return
            
            # Handle different response types
            if structured_output.get("commands"):
                self._handle_commands(structured_output, client_id)
            elif structured_output.get("nl_response"):
                self._handle_nl_response(structured_output, client_id)
            else:
                self._send_error_response("No valid commands or responses extracted", client_id)
                
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Error handling chat message: {type(e).__name__}: {e}")
            self._send_error_response("An error occurred processing your message", client_id)
    
    def _parse_with_llm(self, text):
        """Parse text with LLM and return structured output."""
        try:
            if not isinstance(self.command_llm, OllamaClient):
                return self.command_llm.parse_with_llm(text)
            else:
                return self.command_llm.send_message(text, from_chat=True)
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] LLM parsing failed: {type(e).__name__}: {e}")
            return None
    
    def _handle_commands(self, structured_output, client_id):
        """
        Execute commands and send results back to client.
        
        @param structured_output Parsed command structure from LLM
        @param client_id Client identifier for routing
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
                    self._handle_simple_function_result(results, language, client_id)
                else:
                    # Pure HA commands: just send confirmation
                    message = f"{self.log_prefix} [Command Result]: Commands executed successfully"
                    self.message_handler.send_to_web_server(message, client_id=client_id)
            else:
                self._send_error_response("Command execution returned no results", client_id)
                
        except Exception as e:
            print(f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Command execution failed: {type(e).__name__}: {e}")
            self._send_error_response(f"Failed to execute commands: {str(e)}", client_id)
    
    def _handle_simple_function_result(self, command_result, language, client_id):
        """
        Convert simple function results to natural language.
        
        @param command_result Results from command execution
        @param language Target language for response
        @param client_id Client identifier for routing
        """
        try:
            simple_function_results = [
                r for r in command_result 
                if isinstance(r, dict) and r.get("type") == "simple_function"
            ]
            
            # Send to LLM for natural language conversion
            llm_input = f"Convert these function results into a natural language response in {language} language: {simple_function_results}"
            nl_output = self.command_llm.send_message(llm_input, message_type="response")
            
            if nl_output and nl_output.get("nl_response"):
                nl_message = nl_output.get("nl_response")
                message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
                self.message_handler.send_to_web_server(message, client_id=client_id)
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
