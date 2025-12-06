// Chat Interface JavaScript
const socket = io();

// DOM elements
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-chat-btn');
const logoutBtn = document.getElementById('logout-btn');

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
socket.on('connect', async () => {
  console.log('Connected to server');
  
  // Register user with WebSocket for per-user message routing
  try {
    const response = await fetch('/api/current_user');
    const userData = await response.json();
    socket.emit('register_user', { user_id: userData.id });
    console.log('Registered user:', userData.id);
    
    // Show dashboard button if user has access
    if (userData.can_access_dashboard) {
      const dashboardBtn = document.getElementById('dashboard-btn');
      if (dashboardBtn) {
        dashboardBtn.style.display = 'block';
      }
    }
  } catch (error) {
    console.error('Failed to register user:', error);
  }
});

socket.on('disconnect', () => {
  console.log('Disconnected from server');
  addMessage('Connection lost. Reconnecting...', 'system');
});

// Event listeners
sendBtn.addEventListener('click', sendMessage);

// Dashboard button
const dashboardBtn = document.getElementById('dashboard-btn');
if (dashboardBtn) {
  dashboardBtn.addEventListener('click', () => {
    window.location.href = '/dashboard';
  });
}

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

// === Calendar Functions ===

// Load calendar events
async function loadCalendarEvents() {
  try {
    const response = await fetch('/calendar/events');
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
    const response = await fetch(`/calendar/delete/${eventId}`, { method: 'POST' });
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
    const response = await fetch('/calendar/create', {
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
// Refresh events every 60 seconds
setInterval(loadCalendarEvents, 60000);
