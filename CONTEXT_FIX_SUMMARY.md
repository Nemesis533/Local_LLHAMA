# Persistent Context Fix - Summary

## Problem
When users loaded a conversation and sent a new message, the persistent conversation context (loaded from previous messages for LLM reasoning) was being saved to the database along with the message. This caused the context string to appear as a message when the conversation was reloaded.

### What was happening:
1. User loads conversation with previous messages
2. `ConversationLoader.get_conversation_context_for_llm()` builds context string from previous messages
3. `chat_handler._parse_with_llm()` creates: `prompt = f"{RESUME_PROMPT}\n\n{context}\n\n---\n\nThis is the user's next message: {original_text}"`
4. This full `prompt` (with context) is passed to `send_message(prompt, ...)`
5. `send_message` processes the prompt through Ollama
6. When saving to DB: `embedding_batch = {"user_message": user_message}` where `user_message` is the FULL prompt
7. Result: Context string gets saved to database as a message

## Solution
Separate the LLM input (which includes context for reasoning) from the storage data (which should only be the original user message).

### Changes Made:

#### 1. Modified `Ollama_Client.send_message()` signature (line 161-169)
Added new parameter: `original_text: str = None`

**Before:**
```python
def send_message(self, user_message: str, 
                 temperature: float = 0.1, 
                 top_p: float = 1,
                 max_tokens: int = 4096, 
                 message_type: str = "command", 
                 from_chat: bool = False,
                 conversation_id: str = None):
```

**After:**
```python
def send_message(self, user_message: str, 
                 temperature: float = 0.1, 
                 top_p: float = 1,
                 max_tokens: int = 4096, 
                 message_type: str = "command", 
                 from_chat: bool = False,
                 conversation_id: str = None,
                 original_text: str = None):
```

#### 2. Updated message storage logic in `Ollama_Client.send_message()` (line 292)
Added logic to prioritize `original_text` for storage:

```python
# Use original_text (without context) if provided, otherwise use user_message
text_to_save = original_text if original_text else user_message
```

Then use `text_to_save` in the embedding batch:
```python
embedding_batch = {
    "user_message": text_to_save,  # Only the original message, not the context
    "assistant_response": nl_response_text,
    "conversation_id": conversation_id
}
```

#### 3. Updated `chat_handler._parse_with_llm()` call (line 206-207)
Modified to pass original text separately:

**Before:**
```python
return self.command_llm.send_message(prompt, from_chat=True, conversation_id=conversation_id)
```

**After:**
```python
# Pass original_text separately so it's saved to DB instead of the full prompt with context
return self.command_llm.send_message(prompt, from_chat=True, conversation_id=conversation_id, original_text=text)
```

## How It Works Now

### Message Flow with Fix:
1. User sends message: "Hello"
2. `chat_handler._parse_with_llm()` loads conversation context
3. Creates full prompt: `f"{RESUME_PROMPT}\n\n{persistent_context}\n\n---\n\nThis is the user's next message: Hello"`
4. Calls: `send_message(full_prompt, original_text="Hello", conversation_id=...)`
5. `send_message()` sends full prompt to Ollama for reasoning (LLM gets context)
6. When saving to DB: `text_to_save = "Hello"` (original_text takes priority)
7. Saves to DB: `{"user_message": "Hello", "assistant_response": "...", ...}`
8. Result: Only "Hello" is stored, context is temporary-only for LLM

### Result:
- ✅ LLM still has conversation context for reasoning
- ✅ Only original user messages are saved to database
- ✅ When conversation is reloaded, only messages appear, not context
- ✅ Persistent context is used for LLM only, not persisted to storage

## Backward Compatibility
The `original_text` parameter is optional (defaults to `None`). If `original_text` is not provided, the code falls back to using `user_message` for storage:
```python
text_to_save = original_text if original_text else user_message
```

This ensures that direct calls to `send_message()` without the new parameter continue to work as before.

## Testing
Run: `python3 test_context_fix.py`
- Tests that original_text takes priority when provided
- Tests backward compatibility when original_text is not provided
