#!/usr/bin/env python3
"""
Test script for web_search functionality in SimpleFunctions
"""

import json
import sys
import os

# Add the parent directory to the path to import local_llhama
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_llhama.Simple_Functions import SimpleFunctions

def test_web_search():
    """Test the web_search function"""
    
    print("=" * 60)
    print("Testing Web Search Functionality")
    print("=" * 60)
    
    # Create SimpleFunctions instance with dummy home location
    home_location = {"latitude": 40.7128, "longitude": -74.0060}
    simple_functions = SimpleFunctions(home_location)
    
    # Test 1: Search without specific query
    print("\n[TEST 1] Web search without specific query:")
    print("-" * 60)
    result = simple_functions.web_search()
    print(result)
    
    # Test 2: Search with query
    print("\n[TEST 2] Web search with query 'technology news':")
    print("-" * 60)
    result = simple_functions.web_search(query="technology news")
    print(result)
    
    # Test 3: Search specific website
    print("\n[TEST 3] Search Wikipedia:")
    print("-" * 60)
    result = simple_functions.web_search(query="artificial intelligence", website="wikipedia")
    print(result)
    
    # Test 4: Test command schema integration
    print("\n[TEST 4] Command schema integration:")
    print("-" * 60)
    command = {
        "entity_id": "web_search",
        "action": "web_search"
    }
    action = simple_functions.find_matching_action(command)
    print(f"Found matching action: {action}")
    
    if action:
        result = simple_functions.call_function_by_name(action, query="latest news")
        print(f"Result: {result}")
    
    print("\n" + "=" * 60)
    print("Testing Complete")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_web_search()
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
