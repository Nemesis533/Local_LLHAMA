# === System Imports ===
import os
import torch
import json
import re
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList,LlamaForSequenceClassification
from accelerate import Accelerator
from torch.nn.functional import softmax
import requests

# === Custom Imports ===
from .Home_Assistant_Interface import HomeAssistantClient
from .Shared_Logger import LogLevel

# Reusable system prompt template
SMART_HOME_PROMPT_TEMPLATE = """
You are a smart home assistant that extracts structured commands from user speech or can use agentic methods and internet searches to reply to them.

Device list and supported actions:
{devices_context}

Your job:
- Map user input (in any language) to the most likely **English** device name and action from the list above.
- Do not make up device names or actions.
- If the input is vague, infer the most appropriate valid command.
- Extract one command per device only.
- Always respond with a single valid JSON object matching the format below, and nothing else.

Examples:

User input:
"What is the weather at home?"

JSON response:
{{
"commands": [
    {{
    "action": "home_weather",
    "target": "home_weather"
    }}
]
}}

User input:
"Turn off the wall-e alarm."

JSON response:
{{
"commands": [
    {{
    "action": "turn off",
    "target": "wall-e alarm"
    }}
]
}}

User input:
"Play some music"

JSON response:
{{"commands": []}}

Respond in this format exactly:
{{
"commands": [
    {{"action": "turn on", "target": "living room AC"}},
    {{"action": "increase temperature", "target": "bedroom thermostat", "value": "20°C"}}
]
}}

If nothing matches, respond with:
{{"commands": []}}
"""


class StopOnTokens(StoppingCriteria):
    """
    @brief Custom stopping criteria to stop generation on specific token(s).
    """
    def __init__(self, tokenizer, stop_tokens):
        """
        @param tokenizer The tokenizer used to decode tokens.
        @param stop_tokens List of token IDs that trigger stopping when generated.
        """
        super().__init__()
        self.tokenizer = tokenizer
        self.stop_tokens = stop_tokens  # list of token ids

    def __call__(self, input_ids, scores, **kwargs):
        """
        @brief Check if the last token in input_ids is in stop_tokens.
        @param input_ids Tensor of token ids generated so far.
        @param scores Model output scores (not used here).
        @return True if last token is a stop token, else False.
        """
        for stop_token in self.stop_tokens:
            if input_ids[0][-1] == stop_token:
                return True
        return False


class LLM_Class():
    """
    @brief A wrapper class for loading and interacting with a language model for smart home commands.
    """
    def __init__(self, model_path, model_name, device, ha_client, prompt_guard_model_name, base_prompt=None, reuse_devices=True, load_guard = True):
        """
        @param model_path Path where the model files are stored or cached.
        @param model_name Name of the model to load.
        @param device Device to run the model on (e.g., 'cuda' or 'cpu').
        @param ha_client HomeAssistantClient instance for smart home context.
        @param prompt_guard_model_name Name of the model used for prompt safety checks.
        @param base_prompt Optional system prompt to prepend before user input.
        @param reuse_devices Flag to reuse device context prompt or regenerate each time.
        """
        self.class_prefix_message = "[LLM_Handler]"
        self.model_path = model_path
        self.model_name = model_name
        self.prompt_guard_model_name = prompt_guard_model_name
        self.device = device
        self.model = None  # Placeholder for loaded model
        self.tokenizer = None  # Placeholder for tokenizer
        self.accelerator = Accelerator()
        self.ha_client: HomeAssistantClient = ha_client
        self.use_guard_llm = load_guard

        # Optional base system prompt
        self.base_prompt = base_prompt or ""

        # Initialize prompt guard model for input safety checks
        if self.use_guard_llm:
            self.prompt_guard = PromptGuard_Class(self.model_path, self.prompt_guard_model_name, device=self.device)
            self.prompt_guard.load_model()
        else:
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Guard model disabled - skipping load")
            self.prompt_guard = None

        # Context fragment containing device info for prompt
        self.devices_context = ""
        self.load_guard = load_guard

        if reuse_devices:
            self.devices_context = self.ha_client.generate_devices_prompt_fragment()

    def load_model(self, use_int8=False):
        """
        @brief Load the language model with optional int8 quantization or fp16 precision.
        @param use_int8 If True, load the model using 8-bit quantization.
        @return True if model loaded successfully, False otherwise.
        """
        full_path = os.path.join(self.model_path, self.model_name)
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Starting model load: {self.model_name}")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Target device: {self.device}")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Quantization: {'int8' if use_int8 else 'fp16'}")
        
        # Check if CUDA is available when requested
        if self.device == "cuda" and not torch.cuda.is_available():
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] CUDA requested but not available")
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Falling back to CPU")
            self.device = "cpu"
        
        # Check CUDA memory if using GPU
        if self.device == "cuda":
            try:
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                gpu_memory_free = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)) / (1024**3)
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] GPU memory: {gpu_memory:.2f}GB total, {gpu_memory_free:.2f}GB free")
                
                # Warn if free memory is low
                if gpu_memory_free < 4.0:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Low GPU memory available, may encounter OOM errors")
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Could not check GPU memory: {e}")

        model_kwargs = {
            "low_cpu_mem_usage": True,
            "device_map": self.device,
            "trust_remote_code": True, 
        }

        # Setup quantization if requested
        if use_int8:
            try:
                from transformers import BitsAndBytesConfig
                quant_config = BitsAndBytesConfig(load_in_8bit=True)
                model_kwargs["quantization_config"] = quant_config
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Configured 8-bit quantization")
            except ImportError as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to import BitsAndBytesConfig: {e}")
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Install bitsandbytes: pip install bitsandbytes")
                return False
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to configure quantization: {e}")
                return False
        else:
            model_kwargs["torch_dtype"] = torch.float16

        # Try loading model
        try:
            # Check if model exists locally
            if os.path.exists(full_path):
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Loading model from local path: {full_path}")
                self.model = AutoModelForCausalLM.from_pretrained(full_path, **model_kwargs)
                self.tokenizer = AutoTokenizer.from_pretrained(full_path)
            else:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Model not found locally at {full_path}")
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Downloading model from HuggingFace...")
                self.model = AutoModelForCausalLM.from_pretrained(self.model_name, cache_dir=self.model_path, **model_kwargs)
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, cache_dir=self.model_path)

        except torch.cuda.OutOfMemoryError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] CUDA Out of Memory error: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] GPU does not have enough memory for this model")
            
            # Attempt CPU fallback
            if self.device == "cuda":
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Attempting to load on CPU instead...")
                self.device = "cpu"
                model_kwargs["device_map"] = "cpu"
                
                try:
                    torch.cuda.empty_cache()
                    if os.path.exists(full_path):
                        self.model = AutoModelForCausalLM.from_pretrained(full_path, **model_kwargs)
                        self.tokenizer = AutoTokenizer.from_pretrained(full_path)
                    else:
                        self.model = AutoModelForCausalLM.from_pretrained(self.model_name, cache_dir=self.model_path, **model_kwargs)
                        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, cache_dir=self.model_path)
                    print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Successfully loaded on CPU")
                except Exception as cpu_error:
                    print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] CPU fallback also failed: {cpu_error}")
                    return False
            else:
                return False
                
        except OSError as e:
            if "No such file or directory" in str(e) or "does not appear to have a file named" in str(e):
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Model files not found: {e}")
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Ensure model is downloaded to: {full_path}")
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Or check HuggingFace model name: {self.model_name}")
            else:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] File system error loading model: {e}")
            return False
            
        except RuntimeError as e:
            if "CUDA" in str(e) or "cuda" in str(e):
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] CUDA runtime error: {e}")
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check CUDA installation and GPU drivers")
            else:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Runtime error loading model: {e}")
            return False
            
        except ValueError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Invalid configuration: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check model configuration and parameters")
            return False
            
        except ImportError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Missing dependency: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Install required packages: pip install transformers accelerate")
            return False

        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error loading model: {type(e).__name__}: {e}")
            import traceback
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Traceback:")
            traceback.print_exc()
            return False

        # Verify model and tokenizer loaded
        if self.model is None or self.tokenizer is None:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Model or tokenizer is None after loading")
            return False

        # Configure tokenizer
        try:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Tokenizer configured successfully")
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Failed to configure tokenizer: {e}")

        # Compile model for optimization (skip for int8)
        if not use_int8:
            try:
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Compiling model for optimization...")
                self.model = torch.compile(self.model, mode="reduce-overhead")
                self.model.eval()
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Model compiled successfully")
            except Exception as e:
                print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] Model compilation failed (non-critical): {e}")
                self.model.eval()

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Model loaded successfully on {self.device} using {'int8' if use_int8 else 'fp16'} mode")
        return True

    def build_prompt(self, transcription):
        """
        @brief Build the complete prompt including system instructions and user transcription.
        @param transcription User speech input as a string.
        @return Formatted prompt string ready for LLM input.
        """
        # Regenerate devices context if empty
        devices_context = self.devices_context or self.ha_client.generate_devices_prompt_fragment()

        # Combine system instructions with user input
        return f"{SMART_HOME_PROMPT_TEMPLATE.format(devices_context=devices_context).strip()}\n\nUser input:\n{transcription.strip()}\n\nJSON response:"

    def parse_with_llm(self, transcription):
        """
        @brief Parse user transcription into structured JSON commands using the language model.
        @param transcription User input string.
        @return Parsed JSON object containing commands extracted from input.
        """
        # Check input safety with prompt guard model before parsing
        if self.prompt_guard.is_safe(transcription):
            prompt_text = self.build_prompt(transcription)

            # Tokenize the prompt text for model input
            inputs = self.tokenizer(
                prompt_text,
                return_tensors="pt",
                padding=True,
            ).to(self.device)

            # Setup stopping criteria to stop generation at closing JSON brace
            stop_criteria = StoppingCriteriaList([
                StopOnTokens(self.tokenizer, stop_tokens=[
                    self.tokenizer.encode("}\n\n", add_special_tokens=False)[-1],
                    self.tokenizer.encode("}", add_special_tokens=False)[-1]
                ])
            ])

            # Generate output from the model with specified stopping conditions
            with torch.inference_mode():
                outputs = self.model.generate(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    max_new_tokens=150,
                    pad_token_id=self.tokenizer.eos_token_id,
                    top_p=1.0,
                    do_sample=False,
                    stopping_criteria=stop_criteria,
                )

            # Decode generated tokens to string, skipping special tokens
            result_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

            # Remove the echoed prompt from the output to isolate assistant response
            assistant_response = result_text[len(prompt_text):].strip()

            # Try parsing JSON from the assistant response
            try:
                json_match = re.search(r'(\{.*\})', assistant_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0).strip()
                    parsed_output = json.loads(json_str)
                else:
                    print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No JSON found in model output")
                    parsed_output = {"commands": []}           

            except json.JSONDecodeError as e:
                print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse JSON from model output: {e}")
                print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Raw model output: {result_text[:200]}...")
                parsed_output = {"commands": []}

            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Parsed output: {parsed_output}")

        else:
            # If input is not safe, return empty commands list
            parsed_output = {"commands": []}

        return parsed_output

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
        # Prepare the prompt for classification
        prompt = self.build_prompt(user_input)

        # Tokenize the prompt with padding, truncation and move to correct device
        inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True, max_length=512).to(self.device)

        # Perform model inference without gradient calculation
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = softmax(logits, dim=-1)[0]  # Get probabilities for each class

        unsafe_score = probs[0].item()  # Probability that input is unsafe
        safe_score = probs[1].item()    # Probability that input is safe
        is_safe = unsafe_score < self.threshold  # Compare with threshold

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Evaluating: {user_input[:50]}...")
        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Safety check: unsafe={unsafe_score:.4f}, threshold={self.threshold}, safe={is_safe}")

        return is_safe

class OllamaClient:
    """
    Client to interact with Ollama server for language model inference.
    """
 
    def __init__(self,ha_client, host: str = 'http://your_ip:11434', model: str = 'qwen3-14b-gpu128', system_prompt: str = ''):
        global SMART_HOME_PROMPT_TEMPLATE
        
        self.class_prefix_message = "[OllamaClient]"
        self.host = host.rstrip('/')
        self.model = model
        self.ha_client : HomeAssistantClient = ha_client
        self.devices_context = self.ha_client.generate_devices_prompt_fragment()

        self.languages = {
                "English": "en",
                "French": "fr",
                "German": "de",
                "Italian": "it",
                "Spanish": "es",
                "Russian": "ru"
            }

        SMART_HOME_PROMPT_TEMPLATE += """
        If you cannot respond with a command, try to provide a natural language response and the language you are providing it in 
        to the user in this JSON format:

        {{
            "nl_response": "<string>",
            "language":"<string>"
        }}

        choosign between the following language tags                
                "English": "en",
                "French": "fr",
                "German": "de",
                "Italian": "it",
                "Spanish": "es",
                "Russian": "ru"             

        """
        self.system_prompt = SMART_HOME_PROMPT_TEMPLATE.format(
            devices_context=self.devices_context,
        )
        
    def set_model(self, model_name: str):
        self.model = model_name
 
    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt
    
    def send_message(self, user_message: str, temperature: float = 0.1, top_p: float = 1, max_tokens: int = 4096):
        url = f"http://{self.host}/api/generate"  

        payload = {
            "model": self.model,
            "prompt": user_message,
            "system": self.system_prompt,
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
            data = response.json()
        except requests.exceptions.Timeout:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Request timeout connecting to Ollama at {self.host}")
            return {"commands": []}
        except requests.exceptions.ConnectionError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Connection error to Ollama: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Check if Ollama is running at {self.host}")
            return {"commands": []}
        except requests.exceptions.HTTPError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] HTTP error from Ollama: {e}")
            return {"commands": []}
        except ValueError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Invalid JSON from Ollama: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Response text: {response.text[:200]}")
            return {"commands": []}
        except Exception as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Unexpected error: {type(e).__name__}: {e}")
            return {"commands": []}

        # Ollama API usually returns a list of objects in 'output'
        # Extract the text safely
        output = ""
        if "response" in data:
            output = str(data["response"])
        else:
            print(f"{self.class_prefix_message} [{LogLevel.WARNING.name}] No 'response' field in Ollama output")
            return {"commands": []}

        print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Ollama response: {output[:100]}...")

        try:
            return json.loads(output)
        except json.JSONDecodeError as e:
            print(f"{self.class_prefix_message} [{LogLevel.CRITICAL.name}] Failed to parse Ollama response as JSON: {e}")
            print(f"{self.class_prefix_message} [{LogLevel.INFO.name}] Raw output: {output[:200]}...")
            return {"commands": []}