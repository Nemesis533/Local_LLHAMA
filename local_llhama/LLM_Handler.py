# === System Imports ===
import os
import torch
import json
import re
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList
from accelerate import Accelerator

# === Custom Imports ===
from .Home_Assistant_Interface import HomeAssistantClient
from .Shared_Logger import LogLevel
from .Prompt_Guard import PromptGuard_Class
from .LLM_Prompts import SMART_HOME_PROMPT_TEMPLATE


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

    def build_prompt(self, transcription):
        """
        @brief Build the complete prompt including system instructions and user transcription.
        @param transcription User speech input as a string.
        @return Formatted prompt string ready for LLM input.
        """
        # Regenerate devices context if empty
        devices_context = self.devices_context or self.ha_client.generate_devices_prompt_fragment()
        
        # Generate simple functions context from command schema
        simple_functions_context = self._generate_simple_functions_context()

        # Combine system instructions with user input
        return f"{SMART_HOME_PROMPT_TEMPLATE.format(devices_context=devices_context, simple_functions_context=simple_functions_context).strip()}\n\nUser input:\n{transcription.strip()}\n\nJSON response:"

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
                    max_new_tokens=200,
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