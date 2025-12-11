"""
Command Processor Component

Processes voice commands using LLM and handles command parsing.
"""

from ..Ollama_Client import OllamaClient
from ..Shared_Logger import LogLevel


class CommandProcessor:
    """
    @brief Processes voice commands using LLM and handles command parsing.
    """
    def __init__(self, command_llm, log_prefix=""):
        self.command_llm = command_llm
        self.log_prefix = log_prefix

    def parse_transcription(self, transcription, from_webui=False, client_id=None):
        """Parse transcription using LLM and return structured output.
        
        @param transcription The text to parse
        @param from_webui Boolean indicating if request came from WebUI (True) or STT (False)
        @param client_id Optional client identifier for WebUI requests
        """
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Got transcription: {transcription} (from_webui={from_webui}, client_id={client_id})")
        
        # Store client_id for use in response routing
        self.current_client_id = client_id
        
        if not isinstance(self.command_llm, OllamaClient):
            structured_output = self.command_llm.parse_with_llm(transcription)
        else:
            structured_output = self.command_llm.send_message(transcription)
        
        return structured_output

    def process_command_result(self, command_result, language="en"):
        """Process command execution results and prepare response."""
        if not command_result:
            return None
        
        # Check if any results are simple functions
        has_simple_function = any(
            result.get("type") == "simple_function" 
            for result in command_result 
            if isinstance(result, dict)
        )
        
        if has_simple_function and isinstance(self.command_llm, OllamaClient):
            # Extract only simple function results
            simple_function_results = [
                r for r in command_result 
                if isinstance(r, dict) and r.get("type") == "simple_function"
            ]
            
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Simple function result(s) received: {simple_function_results}")
            
            # Send for natural language conversion
            llm_input = f"Convert these function results into a natural language response in {language} language: {simple_function_results}"
            print(f"{self.log_prefix} [{LogLevel.INFO.name}] Sending to LLM for NL conversion")
            
            return self.command_llm.send_message(llm_input, message_type="response")
        
        return None
