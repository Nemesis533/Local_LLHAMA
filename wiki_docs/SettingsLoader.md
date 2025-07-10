# Documentation for `SettingsLoader.py`

## Function `__init__`

**Description:**

Constructor for SettingLoader.

**Parameters:**

- `json_path`: Path to the JSON file containing configuration data.

## Function `load`

**Description:**

Loads and parses the JSON file into internal data.


## Function `load_llm_models`

**Description:**

Loads the command LLM model with given Home Assistant client.

**Parameters:**

- `ha_client:`: An instance of HomeAssistantClient to integrate LLM with home automation.

## Function `apply`

**Description:**

Applies loaded settings to a list of objects.

**Parameters:**

- `objects`: List of instances to update.

## Function `cast_value`

**Description:**

Converts a value to a Python object of the specified type.

**Parameters:**

- `value`: The value to convert (can already be a list, etc.)
- `type_str`: The expected type as a string: "int", "float", "bool", "str", "list".

