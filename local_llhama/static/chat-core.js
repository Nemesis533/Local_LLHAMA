// Chat Core - Main Chat Interface Logic
const socket = io();

// Global state
window.currentAssistantName = 'Assistant';
let pageHidden = false;
let pendingUpdates = 0;

// Track current streaming message element
let currentStreamingMessage = null;

// DOM elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-chat-btn');
const logoutBtn = document.getElementById('logout-btn');

// Track page visibility to ensure updates work even when tab is not focused
document.addEventListener('visibilitychange', () => {
  pageHidden = document.hidden;
  if (!pageHidden && pendingUpdates > 0) {
    // Page became visible and we had pending updates - update title
    document.title = `Chat (${pendingUpdates} new)`;
    // Clear after a moment
    setTimeout(() => {
      document.title = 'Chat';
      pendingUpdates = 0;
    }, 2000);
  }
});

// Logout handler
logoutBtn.addEventListener('click', async () => {
  try {
    // Clean up empty conversations before logout
    await cleanupEmptyConversations();
    
    const response = await fetch('/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    if (response.ok) {
      window.location.href = '/login';
    } else {
      alert('Logout failed. Please try again.');
    }
  } catch (error) {
    console.error('Logout error:', error);
    window.location.href = '/login';
  }
});

// Send message
async function sendMessage() {
  const message = chatInput.value.trim();
  
  if (!message) {
    return;
  }
  
  // Add user message to chat
  addMessage(message, 'user');
  
  // Clear input
  chatInput.value = '';
  chatInput.style.height = 'auto';
  
  // Show loading indicator
  showLoadingIndicator();
  
  // Disable send button
  sendBtn.disabled = true;
  sendBtn.innerHTML = '<span>Sending...</span>';
  
  try {
    // Send to backend using existing route
    const conversationId = chatInput.dataset.conversationId || null;
    const response = await fetch('/from_user_text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: message,
        from_webui: true,
        conversation_id: conversationId
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!data.success) {
      hideLoadingIndicator();
      addMessage('Failed to send message. Please try again.', 'system');
    } else {
      // Store the conversation_id returned by backend for subsequent messages
      if (data.conversation_id) {
        chatInput.dataset.conversationId = data.conversation_id;
        console.log(`Conversation ID set to: ${data.conversation_id}`);
      }
    }
    
  } catch (error) {
    console.error('Error sending message:', error);
    hideLoadingIndicator();
    addMessage(`Error: ${error.message}`, 'system');
  } finally {
    // Re-enable send button
    sendBtn.disabled = false;
    sendBtn.innerHTML = '<span>Send</span>';
    chatInput.focus();
    
    // Refresh conversations to show updates (with a small delay to ensure DB is updated)
    setTimeout(() => {
      loadChatConversations();
    }, 500);
  }
}

// Listen for streaming response chunks
socket.on('streaming_chunk', (data) => {
  const chunk = data.chunk;
  const isComplete = data.complete;
  
  if (!currentStreamingMessage) {
    // Create new streaming message element
    hideLoadingIndicator();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'chat-message assistant-message streaming-message';
    messageDiv.id = 'streaming-message';
    
    const timestamp = new Date().toLocaleTimeString();
    messageDiv.innerHTML = `
      <div class="message-header">
        <span class="message-type">${window.currentAssistantName}</span>
        <span class="message-time">${timestamp}</span>
      </div>
      <div class="message-content"></div>
    `;
    
    chatMessages.appendChild(messageDiv);
    currentStreamingMessage = messageDiv.querySelector('.message-content');
    currentStreamingMessage.setAttribute('data-raw-text', '');
  }
  
  // Append chunk to current message
  if (chunk) {
    const currentText = currentStreamingMessage.getAttribute('data-raw-text') || '';
    const newText = currentText + chunk;
    currentStreamingMessage.setAttribute('data-raw-text', newText);
    
    // Display the text directly with Markdown formatting
    currentStreamingMessage.innerHTML = formatMarkdown(newText);
    scrollToBottom();
  }
  
  // Finalize streaming message when complete
  if (isComplete) {
    if (currentStreamingMessage) {
      // Remove streaming indicator
      const messageDiv = currentStreamingMessage.parentElement;
      if (messageDiv) {
        messageDiv.classList.remove('streaming-message');
        
        // Update pending counter if page is hidden
        if (pageHidden) {
          pendingUpdates++;
          document.title = `Chat (${pendingUpdates} new)`;
        }
        
        // Check if we need to refresh calendar
        const finalText = currentStreamingMessage.textContent;
        if (finalText.match(/\b(reminder|appointment|alarm)\b.*\b(set|created|added|scheduled)\b/i) ||
            finalText.match(/\b(set|created|added|scheduled)\b.*\b(reminder|appointment|alarm)\b/i)) {
          loadCalendarEvents();
        }
      }
    }
    currentStreamingMessage = null;
    
    // Refresh conversations to show updates
    setTimeout(() => {
      loadChatConversations();
    }, 500);
  }
});

// Listen for responses from the system via WebSocket
socket.on('log_line', (data) => {
  const message = data.line || data;
  
  // Parse different message types
  if (typeof message === 'string') {
    // Check if it's a user prompt or LLM reply
    if (message.includes('[User Prompt]:')) {
      // Skip - we already showed the user message
      return;
    } else if (message.includes('[Status]:')) {
      // Show status message (what the assistant is doing)
      const status = message.split('[Status]:')[1]?.trim();
      if (status) {
        hideLoadingIndicator();
        showStatusMessage(status);
      }
    } else if (message.includes('[LLM Reply]:')) {
      // Skip if we're currently streaming - streaming takes precedence
      if (currentStreamingMessage) {
        return;
      }
      // Extract the actual reply and hide loading indicator
      const reply = message.split('[LLM Reply]:')[1]?.trim();
      if (reply) {
        hideLoadingIndicator();
        addMessage(reply, 'assistant');
        
        // Refresh calendar if the reply mentions creating/setting a reminder, appointment, or alarm
        if (reply.match(/\b(reminder|appointment|alarm)\b.*\b(set|created|added|scheduled)\b/i) ||
            reply.match(/\b(set|created|added|scheduled)\b.*\b(reminder|appointment|alarm)\b/i)) {
          loadCalendarEvents();
        }
      }
    } else if (message.includes('[Command Result]:')) {
      // Show command execution results and hide loading indicator
      const result = message.split('[Command Result]:')[1]?.trim();
      if (result) {
        hideLoadingIndicator();
        addMessage(result, 'assistant');
      }
      addMessage(message, 'system');
    } else if (message.includes('[Error]:')) {
      // Hide loading indicator on error
      hideLoadingIndicator();
    }
  }
});

// Fetch and display current model info
async function loadModelInfo() {
  try {
    // Fetch both preset and model settings
    const [presetResponse, modelResponse] = await Promise.all([
      fetch('/presets/current'),
      fetch('/settings/model')
    ]);
    
    const presetData = await presetResponse.json();
    const modelData = await modelResponse.json();
    
    // Set assistant name from model settings (e.g., "Larry")
    if (modelData.status === 'ok' && modelData.config) {
      window.currentAssistantName = modelData.config.assistant_name || 'Assistant';
    }
    
    // Update model name display in UI
    if (presetData.status === 'ok' && presetData.current_config) {
      const modelName = presetData.current_config.llm_model || 'Unknown';
      const modelNameEl = document.getElementById('model-name');
      if (modelNameEl) {
        modelNameEl.textContent = modelName;
      }
    }
  } catch (error) {
    console.error('Failed to load model info:', error);
    const modelNameEl = document.getElementById('model-name');
    if (modelNameEl) {
      modelNameEl.textContent = 'N/A';
    }
  }
}

// Handle connection events
socket.on('connect', async () => {
  console.log('Connected to server');
  
  // Register user with WebSocket for per-user message routing
  try {
    const response = await fetch('/api/current_user');
    const userData = await response.json();
    socket.emit('register_user', { user_id: userData.id });
    console.log('Registered user:', userData.id);
  } catch (error) {
    console.error('Failed to register user:', error);
  }
  
  // Load model info on connect
  loadModelInfo();
});

socket.on('disconnect', () => {
  console.log('Disconnected from server');
  addMessage('Connection lost. Reconnecting...', 'system');
});

// Event listeners
sendBtn.addEventListener('click', sendMessage);

chatInput.addEventListener('keydown', (e) => {
  // Send on Enter (without Shift)
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
});

// New Chat button - clear current conversation and start fresh
const newChatBtn = document.getElementById('new-chat-btn');
if (newChatBtn) {
  newChatBtn.addEventListener('click', async () => {
    try {
      // Create new conversation immediately
      const response = await fetch('/new_conversation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        }
      });
      
      const data = await response.json();
      
      if (data.success && data.conversation_id) {
        // Clear chat input and messages
        const chatInput = document.getElementById('chat-input');
        chatInput.value = '';
        chatInput.placeholder = 'Type your message here...';
        // Set the new conversation ID immediately
        chatInput.dataset.conversationId = data.conversation_id;
        
        // Clear chat display
        const chatMessages = document.getElementById('chat-messages');
        chatMessages.innerHTML = `
          <div class="welcome-message">
            <h3>Welcome to the LLM Chat Interface</h3>
            <p>Start a conversation by typing a message below. Your requests will be processed through the full system pipeline including simple functions.</p>
          </div>
        `;
        
        chatInput.focus();
        console.log(`Started new chat conversation with ID: ${data.conversation_id}`);
      } else {
        console.error('Failed to create new conversation:', data.error);
        alert('Failed to create new conversation');
      }
    } catch (error) {
      console.error('Error creating new conversation:', error);
      alert('Error creating new conversation');
    }
  });
}
