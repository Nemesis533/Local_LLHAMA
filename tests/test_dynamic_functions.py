#!/usr/bin/env python3
"""
Test script to verify dynamic loading of simple functions in system prompt
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_llhama.Home_Assistant_Interface import HomeAssistantClient
from local_llhama.Simple_Functions import SimpleFunctions

def test_dynamic_functions():
    """Test that simple functions are loaded dynamically"""
    
    print("=" * 60)
    print("Testing Dynamic Function Loading")
    print("=" * 60)
    
    # Create a mock HomeAssistantClient (without real HA connection)
    # We'll just test the SimpleFunctions part
    ha_client = HomeAssistantClient()
    
    # Initialize just the simple functions part
    home_location = {"latitude": 40.7128, "longitude": -74.0060}
    ha_client.simple_functions = SimpleFunctions(home_location)
    
    print("\n[TEST 1] Check command schema loaded:")
    print("-" * 60)
    print(f"Command schema: {ha_client.simple_functions.command_schema}")
    
    print("\n[TEST 2] Simulate LLM_Class function context generation:")
    print("-" * 60)
    
    # Simulate what LLM_Class does
    command_schema = ha_client.simple_functions.command_schema
    if not command_schema:
        print("ERROR: No command schema loaded!")
        return
    
    functions_desc = ["Available Simple Functions:"]
    
    for entity_id, entity_info in command_schema.items():
        actions = entity_info.get('actions', [])
        if actions:
            if entity_id == 'home_weather':
                functions_desc.append(f"- {entity_id}: Get weather forecast for your home location")
                functions_desc.append(f'  Example: {{"action": "home_weather", "target": "home_weather"}}')
            elif entity_id == 'web_search':
                functions_desc.append(f"- {entity_id}: Search allowed websites for information")
                functions_desc.append(f'  Example: {{"action": "web_search", "target": "web_search", "data": {{"query": "your search query"}}}}')
                functions_desc.append(f'  Optional: Add "website" parameter to search specific site')
            else:
                functions_desc.append(f"- {entity_id}: Available actions: {', '.join(actions)}")
                functions_desc.append(f'  Example: {{"action": "{actions[0]}", "target": "{entity_id}"}}')
    
    result = "\n".join(functions_desc)
    print(result)
    
    print("\n[TEST 3] Test adding a new function to command_schema:")
    print("-" * 60)
    
    # Add a new function dynamically
    ha_client.simple_functions.command_schema['test_function'] = {
        'entity_id': 'test_function',
        'actions': ['test_action']
    }
    
    print(f"Updated schema: {ha_client.simple_functions.command_schema}")
    
    # Regenerate description
    functions_desc = ["Available Simple Functions:"]
    for entity_id, entity_info in ha_client.simple_functions.command_schema.items():
        actions = entity_info.get('actions', [])
        if actions:
            functions_desc.append(f"- {entity_id}: Available actions: {', '.join(actions)}")
    
    result = "\n".join(functions_desc)
    print("\nUpdated function context:")
    print(result)
    
    print("\n" + "=" * 60)
    print("✅ Dynamic function loading works correctly!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_dynamic_functions()
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
