
"""
CONVERSATION HISTORY SYSTEM DOCUMENTATION
==========================================

This document explains how the conversation history system works in Local_LLHAMA.

## Architecture Overview

The conversation history system consists of three main components:

1. **ConversationLoader** (state_components/conversation_loader.py)
   - Loads conversations and messages from PostgreSQL
   - Manages Conversation and ConversationMessage objects
   - Handles word-count limiting for LLM context (last 80k words)

2. **Web Routes** (routes/chat_history_routes.py)
   - Provides HTTP endpoints for the web UI to:
     * List all conversations for a user
     * Load full conversation details with all messages

3. **ChatHandler** (state_components/chat_handler.py)
   - Processes chat messages
   - Injects conversation context when resuming conversations
   - Uses RESUME_CONVERSATION_PROMPT for LLM summarization

## Data Flow

### Loading a Conversation List

1. User navigates to "Chat History" in the web UI
2. Web UI calls: `GET /api/chat/conversations?limit=50`
3. Web_Server handler:
   - Gets user ID from session
   - Calls ConversationLoader.get_user_conversations(user_id)
   - Returns list of conversations (title, id, created_at, last_updated, message_count)
4. Web UI displays conversations as a list, sorted by most recent first

### Loading a Full Conversation

1. User clicks on a conversation in the list
2. Web UI calls: `GET /api/chat/conversations/<conversation_id>`
3. Web_Server handler:
   - Verifies user ownership of conversation
   - Calls ConversationLoader.load_conversation(conversation_id)
   - Returns full conversation with all messages in chronological order
4. Web UI displays messages in chat format (user bubbles, assistant bubbles)

### Resuming a Conversation

1. User selects a previous conversation to resume
2. Web UI needs to:
   a. Display all previous messages
   b. Enable user to type a new message
3. When user sends a new message:
   a. Message is sent via: `POST /api/chat/from_user_text`
   b. ChatHandler receives message with client_id = user_id
   c. ChatHandler detects existing conversation in client_conversations
   d. ChatHandler calls ConversationLoader.get_conversation_context_for_llm(
      conversation_id, max_words=80000
   )
   e. LLM receives context + RESUME_CONVERSATION_PROMPT + user's new message
   f. LLM generates summary of previous conversation
   g. LLM appends this to next user prompt
   h. New assistant response is generated

### Key Implementation Details

**Creating a Conversation**
- When a new chat starts, ChatHandler creates a conversation in PostgreSQL
- conversation_id is a UUID
- user_id is from authenticated user
- Title is generated as "Chat {conversation_id[:8]}"

**Storing Messages**
- Each user and assistant message is stored in PostgreSQL messages table
- conversation_id, user_id, role (user/assistant), content, created_at
- Optional: embedding_id for message embeddings

**Word Counting for Context**
- Conversation.get_last_n_words(n_words=80000)
- Counts words in reverse chronological order (newest first)
- Stops when word limit is reached
- Returns concatenated messages in chronological order (oldest first)
- Format: "User: message\nAssistant: response\n..."

**LLM Context Injection**
- ChatHandler._parse_with_llm() checks for persistent_context
- If available, creates prompt with RESUME_CONVERSATION_PROMPT
- Format: "{RESUME_CONVERSATION_PROMPT}\n\n{context}\n\n---\n\nThis is the user's next message: {text}"
- IMPORTANT: Context is NOT stored in memory after this call
- Context is only provided to LLM for this single request
- Only the new user message and assistant response are stored

## Database Tables Used

1. **conversations**
   - id (UUID): Primary key
   - user_id (int): Foreign key to users
   - title (text): Conversation title
   - created_at (timestamp): When conversation started
   - updated_at (timestamp): Last message time

2. **messages**
   - id (int): Primary key
   - conversation_id (UUID): Foreign key to conversations
   - user_id (int): Foreign key to users
   - role (enum/text): 'user' or 'assistant'
   - content (text): Message content
   - created_at (timestamp): When message was created
   - embedding_id (int): Optional foreign key to message_embeddings

## Web UI Integration

### Display Conversations (Sidebar/History)

```javascript
// Fetch user's conversations
fetch('/api/chat/conversations?limit=50')
  .then(r => r.json())
  .then(data => {
    // Display list of conversations
    // Each item shows: title, created_at, message_count
    // Click to load full conversation
  })
```

### Load Full Conversation

```javascript
// When user clicks a conversation
fetch(`/api/chat/conversations/${conversationId}`)
  .then(r => r.json())
  .then(data => {
    // Display all messages in chronological order
    // Show user and assistant messages separately
    // Enable user to type new message
  })
```

### Continue Conversation

```javascript
// When user sends message in existing conversation
fetch('/api/chat/from_user_text', {
  method: 'POST',
  body: JSON.stringify({
    text: userMessage
  })
})
// ChatHandler will:
// 1. See existing conversation in client_conversations
// 2. Load last 80k words of conversation
// 3. Send to LLM with RESUME_CONVERSATION_PROMPT
// 4. Inject summary into next prompt
// 5. Generate response based on context
```

## Important Notes

1. **No Memory Overhead**: Context is only loaded from DB and passed to LLM
   - Not cached in memory
   - Not stored after LLM call
   - Fresh load each time user continues conversation

2. **Word Limit**: 80,000 words keeps recent context while staying within LLM token limits
   - Can be adjusted per conversation_id in chat_handler.py line with max_words parameter

3. **Ownership Verification**: Web routes verify user can only access their own conversations
   - Checked by comparing current_user.id with conversation.user_id

4. **Chronological Order**: Messages always displayed oldest → newest
   - Ensures conversation flow makes sense

5. **Title Generation**: Conversation title is set at creation
   - Can be updated by user later (not yet implemented)

## Testing Checklist

- [ ] Can list conversations for logged-in user
- [ ] Conversation list shows most recent first
- [ ] Can load full conversation with all messages
- [ ] Messages display in correct chronological order
- [ ] Cannot access other users' conversations (403 Forbidden)
- [ ] Can continue conversation and LLM has context
- [ ] Context is not stored in memory after response
- [ ] Word limit works (stops at ~80k words)

## Future Enhancements

1. Allow users to rename conversations
2. Delete conversations
3. Export conversations as JSON/PDF
4. Search within conversations
5. Share conversations with other users
6. Adjust word limit per conversation type
7. Archive old conversations
"""
