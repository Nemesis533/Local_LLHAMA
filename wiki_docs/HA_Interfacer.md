# Documentation for `HA_Interfacer.py`

## Function `__init__`

**Description:**

Initialize the client, fetch domain actions and entity map.


## Function `fetch_domain_actions`

**Description:**

Fetch all available domain actions (services) from Home Assistant.


## Function `fetch_entity_map`

**Description:**

Fetch entities from Home Assistant, optionally filtered and excluded.

**Parameters:**

- `exclusion_dict`: Dictionary of friendly name substrings to exclude.
- `filter_mode`: Filter mode: 'domain' filters by allowed domains,
- `allowed_entities`: List of entity_ids to allow if filter_mode=='entity'.

## Function `send_commands`

**Description:**

Send commands to Home Assistant devices or handle simple functions.

**Parameters:**

- `payload`: Dictionary containing 'commands' list.
- `debug`: Enable debug prints.

## Function `get_service_info`

**Description:**

Retrieve service info for a domain and action from Home Assistant.

**Parameters:**

- `domain`: Domain name (e.g., 'light')
- `action`: Action name (e.g., 'turn_on')

## Function `generate_devices_prompt_fragment`

**Description:**

Generate JSON fragment describing devices and their actions.


## Function `get_home_location`

**Description:**

Retrieve the configured home latitude and longitude from HA config.


## Function `__init__`

**Description:**

Initialize with home location and optional DB config.

**Parameters:**

- `home_location`: Dictionary with 'latitude' and 'longitude'.
- `db_config`: Optional database configuration.

## Function `call_function_by_name`

**Description:**

Call a method by name if it exists and is callable.

**Parameters:**

- `function_name`: Name of the method to call.

## Function `load_command_schema_from_file`

**Description:**

Load command schema from a JSON file.


## Function `convert_command_schema_to_entities`

**Description:**

Convert command schema to virtual entities format.

**Parameters:**

- `schema`: Command schema dictionary.

## Function `home_weather`

**Description:**

Fetch weather forecast from a local weather server.

**Parameters:**

- `place`: Optional location parameter (currently unused).

## Function `get_coordinates`

**Description:**

Get latitude and longitude coordinates for a given place name.

**Parameters:**

- `place_name`: Name of the place to geocode.

## Function `get_weather`

**Description:**

Fetch current weather for a specified place.

**Parameters:**

- `place`: Place name string.

## Function `find_matching_action`

**Description:**

Find a matching simple function action for the given command.

**Parameters:**

- `command_json`: Single command dict or list of commands.

## Function `replace_target_with_entity_id`

**Description:**

Recursively replace 'target' keys with 'entity_id' in command JSON.

**Parameters:**

- `command`: Dict or list representing the command(s).

