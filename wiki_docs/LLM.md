# Documentation for `LLM.py`

## Function `__init__`

**Parameters:**

- `tokenizer`: The tokenizer used to decode tokens.
- `stop_tokens`: List of token IDs that trigger stopping when generated.

## Function `__call__`

**Description:**

Check if the last token in input_ids is in stop_tokens.

**Parameters:**

- `input_ids`: Tensor of token ids generated so far.
- `scores`: Model output scores (not used here).

## Function `__init__`

**Parameters:**

- `model_path`: Path where the model files are stored or cached.
- `model_name`: Name of the model to load.
- `device`: Device to run the model on (e.g., 'cuda' or 'cpu').
- `ha_client`: HomeAssistantClient instance for smart home context.
- `prompt_guard_model_name`: Name of the model used for prompt safety checks.
- `base_prompt`: Optional system prompt to prepend before user input.
- `reuse_devices`: Flag to reuse device context prompt or regenerate each time.

## Function `load_model`

**Description:**

Load the language model with optional int8 quantization or fp16 precision.

**Parameters:**

- `use_int8`: If True, load the model using 8-bit quantization.

## Function `build_prompt`

**Description:**

Build the complete prompt including system instructions and user transcription.

**Parameters:**

- `transcription`: User speech input as a string.

## Function `parse_with_llm`

**Description:**

Parse user transcription into structured JSON commands using the language model.

**Parameters:**

- `transcription`: User input string.

## Function `__init__`

**Parameters:**

- `model_path`: Path to the directory containing the guard model.
- `prompt_guard_model_name`: Name of the prompt guard model.
- `device`: Device to run the model on (e.g., 'cuda' or 'cpu').
- `threshold`: Probability threshold to classify prompt as safe.

## Function `load_model`

**Description:**

Load the LLaMA-based prompt guard model with FP16 precision.


## Function `build_prompt`

**Description:**

Build a short-form prompt formatted for the safety classifier.

**Parameters:**

- `user_input`: Raw user input string.

## Function `is_safe`

**Description:**

Check if the user input is safe or suspicious.

**Parameters:**

- `user_input`: Raw user input string to evaluate.

