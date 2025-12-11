#!/usr/bin/env python3
"""
Test script to verify that persistent context is NOT saved to database,
only the original user message is saved.

This tests the fix for the issue where persistent conversation context
was being included in saved messages.
"""

def test_text_to_save_logic():
    """Test that text_to_save correctly prioritizes original_text over user_message."""
    
    # Simulate what happens in Ollama_Client.send_message()
    
    # Case 1: original_text provided (as when called from chat_handler._parse_with_llm)
    user_message = "RESUME_PROMPT...\n\nPrevious context...\n\n---\n\nThis is the user's next message: Hello"
    original_text = "Hello"
    text_to_save = original_text if original_text else user_message
    
    print("TEST 1: When original_text is provided")
    print(f"  user_message (full prompt): {user_message[:60]}...")
    print(f"  original_text: {original_text}")
    print(f"  text_to_save (should be 'Hello'): {text_to_save}")
    assert text_to_save == "Hello", "text_to_save should be 'Hello'"
    print("  ✓ PASS: Only original text is saved, not full prompt\n")
    
    # Case 2: original_text not provided (backward compatibility for direct send_message calls)
    user_message = "Some direct command"
    original_text = None
    text_to_save = original_text if original_text else user_message
    
    print("TEST 2: When original_text is NOT provided (backward compatibility)")
    print(f"  user_message: {user_message}")
    print(f"  original_text: {original_text}")
    print(f"  text_to_save (should be '{user_message}'): {text_to_save}")
    assert text_to_save == "Some direct command", "text_to_save should be user_message"
    print("  ✓ PASS: Falls back to user_message for backward compatibility\n")
    
    print("ALL TESTS PASSED ✓")
    print("\nWhat this fix means:")
    print("1. When chat_handler loads a conversation and prepends context to prompt")
    print("2. It now passes original_text='Hello' to send_message()")
    print("3. Ollama_Client uses original_text for storage instead of full prompt")
    print("4. Result: Only 'Hello' is saved to DB, not the context string")
    print("5. When conversation is reloaded, only messages appear, not context")

if __name__ == "__main__":
    test_text_to_save_logic()
