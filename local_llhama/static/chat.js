// Chat Interface JavaScript
const socket = io();

// DOM elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-chat-btn');
const logoutBtn = document.getElementById('logout-btn');
const dashboardBtn = document.getElementById('dashboard-btn');

// Auto-scroll to bottom
function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Add message to chat
function addMessage(content, type = 'system') {
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${type}-message`;
  
  const timestamp = new Date().toLocaleTimeString();
  
  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${type === 'user' ? 'You' : type === 'assistant' ? 'Assistant' : 'System'}</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">${escapeHtml(content)}</div>
  `;
  
  chatMessages.appendChild(messageDiv);
  scrollToBottom();
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
      <span class="message-type">Assistant</span>
    </div>
    <div class="message-content">
      <div class="loading-dots">
        <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
        <span class="loading-text">Thinking</span>
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
    const response = await fetch('/from_user_text', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text: message,
        from_webui: true
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!data.success) {
      hideLoadingIndicator();
      addMessage('Failed to send message. Please try again.', 'system');
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
  }
}

// Listen for responses from the system via WebSocket
socket.on('log_line', (data) => {
  const message = data.line || data;
  
  // Parse different message types
  if (typeof message === 'string') {
    // Check if it's a user prompt or LLM reply
    if (message.includes('[User Prompt]:')) {
      // Skip - we already showed the user message
      return;
    } else if (message.includes('[LLM Reply]:')) {
      // Extract the actual reply and hide loading indicator
      const reply = message.split('[LLM Reply]:')[1]?.trim();
      if (reply) {
        hideLoadingIndicator();
        addMessage(reply, 'assistant');
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

// Handle connection events
socket.on('connect', () => {
  console.log('Connected to server');
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
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
  } catch (error) {
    console.error('Logout error:', error);
    window.location.href = '/login';
  }
});

dashboardBtn.addEventListener('click', () => {
  window.location.href = '/dashboard';
});

// Focus input on load
chatInput.focus();
