// Chat Interface JavaScript
const socket = io();

// Global state
let currentAssistantName = 'Assistant';

// DOM elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-chat-btn');
const logoutBtn = document.getElementById('logout-btn');

// Logout handler
logoutBtn.addEventListener('click', async () => {
  try {
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
    alert('Logout failed. Please try again.');
  }
});

// Auto-scroll to bottom
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to chat
function addMessage(content, type = 'system') {
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${type}-message`;
  
  const timestamp = new Date().toLocaleTimeString();
  
  // Apply Markdown formatting
  const formattedContent = formatMarkdown(content);
  
  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${type === 'user' ? 'You' : type === 'assistant' ? currentAssistantName : 'System'}</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">${formattedContent}</div>
  `;
  
  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Format Markdown syntax (bold, italic, etc.)
function formatMarkdown(text) {
  // First escape HTML to prevent XSS
  let formatted = escapeHtml(text);
  
  // Code blocks: ```language\ncode\n``` or ```\ncode\n```
  formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, function(match, language, code) {
    const lang = language ? ` class="language-${language}"` : '';
    return `<pre><code${lang}>${code.trim()}</code></pre>`;
  });
  
  // Apply Markdown formatting
  // Bold: **text**
  formatted = formatted.replace(/\*\*([^\*]+?)\*\*/g, '<strong>$1</strong>');
  
  // Italic: *text* (single asterisk, not part of **)
  formatted = formatted.replace(/(?<!\*)\*([^\*\n]+?)\*(?!\*)/g, '<em>$1</em>');
  
  // Inline code: `text`
  formatted = formatted.replace(/`([^`]+?)`/g, '<code>$1</code>');
  
  // Line breaks
  formatted = formatted.replace(/\n/g, '<br>');
  
  return formatted;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Show loading indicator
function showLoadingIndicator() {
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'chat-message assistant-message loading-message';
  loadingDiv.id = 'loading-indicator';
  
  loadingDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${currentAssistantName}</span>
    </div>
    <div class="message-content">
      <div class="loading-dots">
        <span class="loading-text">Thinking</span><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>
    </div>
  `;
  
  chatMessages.appendChild(loadingDiv);
  scrollToBottom();
}

// Hide loading indicator
function hideLoadingIndicator() {
  const loadingDiv = document.getElementById('loading-indicator');
  if (loadingDiv) {
    loadingDiv.remove();
  }
  hideStatusMessage();
}

// Show status message (what assistant is doing)
function showStatusMessage(status) {
  // Remove existing status if any
  hideStatusMessage();
  
  const statusDiv = document.createElement('div');
  statusDiv.className = 'chat-message assistant-message status-message';
  statusDiv.id = 'status-indicator';
  
  statusDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${currentAssistantName}</span>
    </div>
    <div class="message-content">
      <div class="status-text">
        <span class="status-icon">⚙️</span> ${escapeHtml(status)}
      </div>
    </div>
  `;
  
  chatMessages.appendChild(statusDiv);
  scrollToBottom();
}

// Hide status message
function hideStatusMessage() {
  const statusDiv = document.getElementById('status-indicator');
  if (statusDiv) {
    statusDiv.remove();
  }
}

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

// Track current streaming message element
let currentStreamingMessage = null;

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
        <span class="message-type">${currentAssistantName}</span>
        <span class="message-time">${timestamp}</span>
      </div>
      <div class="message-content"></div>
    `;
    
    chatMessages.appendChild(messageDiv);
    currentStreamingMessage = messageDiv.querySelector('.message-content');
  }
  
  // Append chunk to current message
  if (chunk) {
    const currentText = currentStreamingMessage.getAttribute('data-raw-text') || '';
    const newText = currentText + chunk;
    currentStreamingMessage.setAttribute('data-raw-text', newText);
    
    // Parse and render the accumulated text as JSON if possible
    try {
      const parsed = JSON.parse(newText);
      if (parsed.nl_response) {
        currentStreamingMessage.innerHTML = formatMarkdown(parsed.nl_response);
      } else {
        currentStreamingMessage.innerHTML = formatMarkdown(newText);
      }
    } catch {
      // Not valid JSON yet, display as-is
      currentStreamingMessage.innerHTML = formatMarkdown(newText);
    }
    
    scrollToBottom();
  }
  
  // Finalize streaming message when complete
  if (isComplete) {
    if (currentStreamingMessage) {
      // Remove streaming indicator
      const messageDiv = currentStreamingMessage.parentElement;
      if (messageDiv) {
        messageDiv.classList.remove('streaming-message');
        
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
      currentAssistantName = modelData.config.assistant_name || 'Assistant';
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

// Navigation
logoutBtn.addEventListener('click', async () => {
  try {
    // Clean up empty conversations before logout
    await cleanupEmptyConversations();
    
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
  } catch (error) {
    console.error('Logout error:', error);
    window.location.href = '/login';
  }
});

// Clean up empty conversations (0 messages) before logout
async function cleanupEmptyConversations() {
  try {
    const response = await fetch('/api/chat/conversations?limit=100');
    const data = await response.json();
    
    if (data.success && data.conversations) {
      // Find and delete conversations with 0 messages
      const emptyConvs = data.conversations.filter(conv => conv.message_count === 0);
      
      for (const conv of emptyConvs) {
        try {
          await fetch(`/api/chat/conversations/${conv.id}/delete`, { method: 'POST' });
          console.log(`Deleted empty conversation ${conv.id}`);
        } catch (err) {
          console.error(`Failed to delete conversation ${conv.id}:`, err);
        }
      }
    }
  } catch (error) {
    console.error('Error cleaning up empty conversations:', error);
  }
}


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

// === Calendar Functions ===

// Load calendar events
async function loadCalendarEvents() {
  try {
    const response = await fetch('/api/calendar/events');
    const data = await response.json();
    
    if (data.success) {
      displayCalendarEvents(data.events);
    } else {
      document.getElementById('calendar-events').innerHTML = '<p class="error-text">Failed to load events</p>';
    }
  } catch (error) {
    console.error('Error loading calendar events:', error);
    document.getElementById('calendar-events').innerHTML = '<p class="error-text">Error loading events</p>';
  }
}

// Display calendar events
function displayCalendarEvents(events) {
  const container = document.getElementById('calendar-events');
  
  if (!events || events.length === 0) {
    container.innerHTML = '<p class="placeholder-text">No upcoming events</p>';
    return;
  }
  
  container.innerHTML = events.map(event => `
    <div class="calendar-event" data-event-id="${event.id}">
      <div class="event-type-badge ${event.type}">${event.type}</div>
      <div class="event-title">${event.title}</div>
      <div class="event-time">${event.due_display}</div>
      ${event.description ? `<div class="event-description">${event.description}</div>` : ''}
      <button class="event-delete-btn" onclick="deleteCalendarEvent(${event.id})">Delete</button>
    </div>
  `).join('');
}

// Delete calendar event
async function deleteCalendarEvent(eventId) {
  if (!confirm('Are you sure you want to delete this event?')) {
    return;
  }
  
  try {
    const response = await fetch(`/api/calendar/delete/${eventId}`, { method: 'POST' });
    const data = await response.json();
    
    if (data.success) {
      loadCalendarEvents(); // Refresh list
    } else {
      alert('Failed to delete event: ' + (data.message || 'Unknown error'));
    }
  } catch (error) {
    console.error('Error deleting event:', error);
    alert('Error deleting event');
  }
}

// Modal handling
const modal = document.getElementById('add-event-modal');
const addEventBtn = document.getElementById('add-event-btn');
const closeModal = document.querySelector('.close');
const cancelBtn = document.getElementById('cancel-event-btn');
const addEventForm = document.getElementById('add-event-form');

addEventBtn.addEventListener('click', () => {
  modal.style.display = 'block';
  // Set default datetime to now
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById('event-datetime').value = now.toISOString().slice(0, 16);
});

closeModal.addEventListener('click', () => {
  modal.style.display = 'none';
});

cancelBtn.addEventListener('click', () => {
  modal.style.display = 'none';
});

window.addEventListener('click', (e) => {
  if (e.target === modal) {
    modal.style.display = 'none';
  }
});

// Create event form submission
addEventForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const eventData = {
    title: document.getElementById('event-title').value,
    type: document.getElementById('event-type').value,
    due_datetime: document.getElementById('event-datetime').value,
    description: document.getElementById('event-description').value,
    repeat: document.getElementById('event-repeat').value
  };
  
  try {
    const response = await fetch('/api/calendar/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(eventData)
    });
    
    const data = await response.json();
    
    if (data.success) {
      modal.style.display = 'none';
      addEventForm.reset();
      loadCalendarEvents(); // Refresh list
      addMessage(`Calendar event created: ${eventData.title}`, 'system');
    } else {
      alert('Failed to create event: ' + (data.message || data.error || 'Unknown error'));
    }
  } catch (error) {
    console.error('Error creating event:', error);
    alert('Error creating event');
  }
});

// Load events on page load
loadCalendarEvents();
loadChatConversations();
// Refresh events every 60 seconds
setInterval(loadCalendarEvents, 60000);
// Refresh conversations every 30 seconds
setInterval(loadChatConversations, 30000);

// === Chat Conversation Functions ===

// Load chat conversations (first 40 with messages, rest metadata only)
async function loadChatConversations() {
  try {
    const response = await fetch('/api/chat/conversations?limit=100');
    if (!response.ok) {
      console.warn('Failed to load conversations:', response.status);
      return;
    }
    const data = await response.json();
    
    if (data.success && data.conversations) {
      displayChatConversations(data.conversations);
    }
  } catch (error) {
    console.error('Error loading chat conversations:', error);
  }
}

// Display chat conversations in sidebar
function displayChatConversations(conversations) {
  const conversationsContainer = document.getElementById('chat-history');
  if (!conversationsContainer) return;
  
  if (conversations.length === 0) {
    conversationsContainer.innerHTML = '<p class="text-muted">No conversations yet</p>';
    return;
  }
  
  // Get currently selected conversation ID
  const chatInput = document.getElementById('chat-input');
  const currentConvId = chatInput?.dataset.conversationId || null;
  
  let html = '<div class="conversations-list">';
  conversations.forEach(conv => {
    const date = new Date(conv.created_at);
    const dateStr = date.toLocaleDateString();
    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    // Highlight current conversation
    const isCurrentConv = conv.id === currentConvId;
    const bgColor = isCurrentConv ? '#e3f2fd' : '#f5f5f5';
    const borderColor = isCurrentConv ? '#1976d2' : '#007bff';
    const fontWeight = isCurrentConv ? '700' : '600';
    
    html += `
      <div class="conversation-item" id="conv-${conv.id}" style="position: relative; cursor: pointer; padding: 10px; margin: 6px 0; background: ${bgColor}; border-radius: 4px; transition: background 0.2s; border-left: 3px solid ${borderColor}; display: flex; justify-content: space-between; align-items: flex-start;" onmouseover="this.style.background='${isCurrentConv ? '#bbdefb' : '#efefef'}'" onmouseout="this.style.background='${bgColor}'">
        <div onclick="loadConversation('${conv.id}')" style="flex: 1;">
          <div style="font-weight: ${fontWeight}; color: #333;">${conv.title}</div>
          <div class="text-muted" style="font-size: 0.85em; color: #666; margin-top: 4px;">${conv.message_count} messages</div>
          <div class="text-muted" style="font-size: 0.8em; color: #999; margin-top: 2px;">${dateStr} at ${timeStr}</div>
        </div>
        <div style="position: relative;">
          <button onclick="event.stopPropagation(); toggleConversationMenu('${conv.id}')" style="background: none; border: none; font-size: 1.2em; cursor: pointer; color: #999; padding: 0; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;">⋮</button>
          <div id="menu-${conv.id}" style="display: none; position: absolute; top: 24px; right: 0; background: white; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); z-index: 100; min-width: 120px;">
            <button onclick="event.stopPropagation(); deleteConversation('${conv.id}', '${conv.title.replace(/'/g, "\\'")}')"; style="display: block; width: 100%; text-align: left; padding: 8px 12px; border: none; background: none; cursor: pointer; color: #d32f2f; font-size: 0.9em;" onmouseover="this.style.background='#ffebee'" onmouseout="this.style.background='white'">Delete</button>
          </div>
        </div>
      </div>
    `;
  });
  html += '</div>';
  conversationsContainer.innerHTML = html;
}

// Toggle conversation context menu
function toggleConversationMenu(conversationId) {
  const menu = document.getElementById(`menu-${conversationId}`);
  if (menu) {
    // Hide all other menus
    document.querySelectorAll('[id^="menu-"]').forEach(m => {
      if (m.id !== `menu-${conversationId}`) {
        m.style.display = 'none';
      }
    });
    // Toggle current menu
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  }
}

// Close menu when clicking outside
document.addEventListener('click', function(e) {
  if (!e.target.closest('button') && !e.target.closest('[id^="menu-"]')) {
    document.querySelectorAll('[id^="menu-"]').forEach(m => {
      m.style.display = 'none';
    });
  }
});

// Delete a conversation with confirmation
async function deleteConversation(conversationId, conversationTitle) {
  const confirmed = confirm(`Are you sure you want to delete "${conversationTitle}"? This action cannot be undone.`);
  if (!confirmed) return;
  
  try {
    const response = await fetch(`/api/chat/conversations/${conversationId}/delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      console.log(`Deleted conversation ${conversationId}`);
      // Show success message
      alert('Conversation deleted successfully');
      // Reload conversations list
      loadChatConversations();
      // Clear chat area
      const messagesContainer = document.getElementById('chat-messages');
      if (messagesContainer) {
        messagesContainer.innerHTML = '<p class="text-muted" style="padding: 20px; text-align: center;">Select a conversation or start a new one</p>';
      }
      // Clear conversation ID from input
      const chatInput = document.getElementById('chat-input-box');
      if (chatInput) {
        delete chatInput.dataset.conversationId;
      }
    } else {
      console.error('Delete failed:', data.error);
      alert('Error deleting conversation: ' + (data.error || 'Unknown error'));
    }
  } catch (error) {
    console.error('Error deleting conversation:', error);
    alert('Error deleting conversation: ' + error.message);
  }
}

async function loadConversation(conversationId) {
  try {
    // Show loading indicator
    const messagesContainer = document.getElementById('chat-messages');
    messagesContainer.innerHTML = '<p class="text-muted" style="padding: 20px; text-align: center;"><i class="fas fa-spinner fa-spin"></i> Loading conversation...</p>';
    
    const response = await fetch(`/api/chat/conversations/${conversationId}`);
    const data = await response.json();
    
    if (data.success && data.conversation) {
      // Clear chat area and load messages
      messagesContainer.innerHTML = '';
      
      // Display all messages
      if (data.conversation.messages && data.conversation.messages.length > 0) {
        data.conversation.messages.forEach(msg => {
          const messageDiv = document.createElement('div');
          messageDiv.className = `chat-message ${msg.role}-message`;
          
          const timestamp = new Date(msg.timestamp);
          const timeStr = timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          
          messageDiv.innerHTML = `
            <div class="message-header">
              <span class="message-type">${msg.role === 'user' ? 'You' : 'Assistant'}</span>
              <span class="message-time">${timeStr}</span>
            </div>
            <div class="message-content">${formatMarkdown(msg.content)}</div>
          `;
          messagesContainer.appendChild(messageDiv);
        });
      } else {
        messagesContainer.innerHTML = '<p class="text-muted" style="padding: 20px; text-align: center;">No messages in this conversation</p>';
      }
      
      // Scroll to bottom
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      
      // Store current conversation ID for resuming
      const chatInput = document.getElementById('chat-input');
      if (chatInput) {
        chatInput.dataset.conversationId = conversationId;
        chatInput.focus();
        chatInput.placeholder = `Continue conversation: ${data.conversation.title}`;
      }
      
      // Refresh highlighting in conversation list
      loadChatConversations();
      
      console.log(`Loaded conversation ${conversationId}. You can now continue this conversation.`);
    }
  } catch (error) {
    console.error('Error loading conversation:', error);
    alert('Error loading conversation');
  }
}

