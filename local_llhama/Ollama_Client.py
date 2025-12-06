"""
@file Ollama_Client.py
@brief Client for interacting with Ollama server for LLM inference.

This module provides a lightweight client to communicate with an Ollama
server for language model inference, supporting both command parsing
and response processing.
"""

# === System Imports ===
import json
import requests

# === Custom Imports ===
from .Shared_Logger import LogLevel
from .LLM_Prompts import SMART_HOME_PROMPT_TEMPLATE, RESPONSE_PROCESSOR_PROMPT


class OllamaClient:
    """
    Client to interact with Ollama server for language model inference.
    """
 
    def __init__(self, ha_client, host: str = 'http://your_ip:11434', model: str = 'qwen3-14b-gpu128', system_prompt: str = ''):
        """
        @brief Initialize Ollama client with connection details.
        @param ha_client HomeAssistantClient instance for device context.
        @param host Ollama server URL.
        @param model Model name to use on Ollama server.
        @param system_prompt Optional system prompt override.
        """
        self.class_prefix_message = "[OllamaClient]"
        self.host = host.rstrip('/')
        self.model = model
        self.ha_client = ha_client
        self.devices_context = self.ha_client.generate_devices_prompt_fragment()
        self.response_processor_prompt = RESPONSE_PROCESSOR_PROMPT
        
        # Context management - keep only last request and response
        self.last_user_message = None
        self.last_assistant_response = None

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
    
    def send_message(self, user_message: str, temperature: float = 0.1, top_p: float = 1, max_tokens: int = 4096, message_type: str = "command"):
        """
        @brief Send message to Ollama for processing.
        @param user_message The message to process.
        @param temperature Sampling temperature.
        @param top_p Nucleus sampling parameter.
        @param max_tokens Maximum tokens to generate.
        @param message_type Either "command" for command parsing or "response" for processing function results.
        @return Parsed JSON response.
        """
        # Validate input
        if not user_message or not user_message.strip():
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Empty message provided")
            return {"commands": []}
        
        # Choose system prompt based on message type
        if message_type == "response":
            system_prompt = self.response_processor_prompt
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Processing simple function response")
        else:
            system_prompt = self.system_prompt
        
        # Build the prompt with context if available
        prompt = user_message
        if message_type == "command" and self.last_user_message and self.last_assistant_response:
            # Include last conversation in context
            context_prefix = f"Previous user message: {self.last_user_message}\nPrevious assistant response: {self.last_assistant_response}\n\nCurrent user message: "
            prompt = context_prefix + user_message
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Including previous context in prompt")
        
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
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request timeout connecting to Ollama at {self.host}")
            return {"commands": []}
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

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Ollama response: {output[:100]}...")

        # Parse JSON from output
        try:
            parsed = json.loads(output)
            # Validate structure
            if not isinstance(parsed, dict):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Response is not a dict")
                return {"commands": []}
            
            # Update context for command type messages only (not for response processing)
            if message_type == "command":
                # Store current exchange as the "last" exchange, replacing any previous one
                self.last_user_message = user_message
                self.last_assistant_response = output
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Updated context with current exchange")
            
            return parsed
        except json.JSONDecodeError as e:
            # Try to recover from double-brace errors ({{ instead of {)
            if output.startswith('{{') and output.endswith('}}'):
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Detected double braces, stripping and retrying")
                try:
                    parsed = json.loads(output[1:-1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse Ollama response as JSON: {repr(e)}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Raw output: {output[:200]}...")
            return {"commands": []}
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error parsing output: {repr(e)}")
            return {"commands": []}
