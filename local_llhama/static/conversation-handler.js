// Chat Conversation History Handler

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

// Load a specific conversation
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

// Clean up empty conversations (0 messages)
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

// Initialize conversation history handler
function initConversationHistory() {
  // Load conversations on page load
  loadChatConversations();
  
  // Refresh conversations every 30 seconds
  setInterval(loadChatConversations, 30000);
  
  // Close menu when clicking outside
  document.addEventListener('click', function(e) {
    if (!e.target.closest('button') && !e.target.closest('[id^="menu-"]')) {
      document.querySelectorAll('[id^="menu-"]').forEach(m => {
        m.style.display = 'none';
      });
    }
  });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initConversationHistory);
} else {
  initConversationHistory();
}
