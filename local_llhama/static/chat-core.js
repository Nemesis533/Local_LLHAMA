// Chat Core - Main Chat Interface Logic
const socket = io();

// Global state
window.currentAssistantName = 'Assistant';
let pageHidden = false;
let pendingUpdates = 0;

// Track current streaming message element
let currentStreamingMessage = null;

// Global state for uploaded image
let uploadedImageId = null;
let uploadedImageUrl = null;
let uploadedImageFilename = null;

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

// ── Image Upload ──────────────────────────────────────────────────────────────
// Image upload input and preview elements
const imageUploadInput = document.getElementById('image-upload-input');
const imagePreviewContainer = document.getElementById('image-preview-container');
const imagePreview = document.getElementById('image-preview');
const removeImageBtn = document.getElementById('remove-image-btn');

// Handle file selection
imageUploadInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    await handleImageUpload(file);
  }
});

// Handle remove image
removeImageBtn.addEventListener('click', () => {
  clearUploadedImage();
});

// Drag and drop handlers
const chatInputContainer = document.querySelector('.chat-input-container');

chatInputContainer.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInputContainer.classList.add('drag-over');
});

chatInputContainer.addEventListener('dragleave', (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInputContainer.classList.remove('drag-over');
});

chatInputContainer.addEventListener('drop', async (e) => {
  e.preventDefault();
  e.stopPropagation();
  chatInputContainer.classList.remove('drag-over');
  
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    const file = files[0];
    if (file.type.startsWith('image/')) {
      await handleImageUpload(file);
    } else {
      alert('Please drop an image file (PNG, JPG, GIF, or WebP)');
    }
  }
});

// Handle image upload
async function handleImageUpload(file) {
  // Validate file size (10 MB max)
  const maxSize = 10 * 1024 * 1024;
  if (file.size > maxSize) {
    alert(`File too large. Maximum size is ${maxSize / 1024 / 1024} MB`);
    return;
  }
  
  // Show preview
  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.src = e.target.result;
    imagePreviewContainer.style.display = 'flex';
  };
  reader.readAsDataURL(file);
  
  // Upload to server
  const formData = new FormData();
  formData.append('image', file);
  
  // Add conversation_id if available
  const conversationId = chatInput.dataset.conversationId || null;
  if (conversationId) {
    formData.append('conversation_id', conversationId);
  }
  
  try {
    const response = await fetch('/api/images/upload', {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (data.success) {
      uploadedImageId = data.image_id;
      uploadedImageUrl = data.url;
      uploadedImageFilename = data.original_filename || data.filename;
      console.log('Image uploaded:', uploadedImageId);
    } else {
      throw new Error(data.error || 'Upload failed');
    }
  } catch (error) {
    console.error('Image upload error:', error);
    alert('Failed to upload image: ' + error.message);
    clearUploadedImage();
  }
}

// Clear uploaded image
function clearUploadedImage() {
  uploadedImageId = null;
  uploadedImageUrl = null;
  uploadedImageFilename = null;
  imagePreview.src = '';
  imagePreviewContainer.style.display = 'none';
  imageUploadInput.value = '';
}

// Send message
async function sendMessage() {
  const message = chatInput.value.trim();
  
  // Allow empty message if image is present
  if (!message && !uploadedImageId) {
    return;
  }
  
  // Prepare message text and request body
  let messageText = message;
  let requestBody = {
    from_webui: true,
    conversation_id: chatInput.dataset.conversationId || null
  };
  
  // If image is uploaded, include it in the request
  if (uploadedImageId) {
    requestBody.uploaded_image_url = uploadedImageUrl;
    requestBody.uploaded_image_id = uploadedImageId;
    
    // Format message to trigger image analysis
    if (messageText) {
      messageText = `analyze this image: ${messageText}`;
    } else {
      messageText = 'Please analyze this image';
    }
  }
  
  requestBody.text = messageText;
  
  // Add user message to chat
  if (uploadedImageId) {
    // Show uploaded image with query
    addUploadedImageMessage(uploadedImageUrl, uploadedImageFilename, message);
  } else if (message) {
    // Regular text message
    addMessage(message, 'user');
  }
  
  // Store for later if we need to show image during analysis
  const hadUploadedImage = Boolean(uploadedImageId);
  const analysingImageUrl = hadUploadedImage ? uploadedImageUrl : null;
  
  // Clear uploaded image state after sending
  if (hadUploadedImage) {
    clearUploadedImage();
  }
  
  // Clear input
  chatInput.value = '';
  chatInput.style.height = 'auto';
  
  // Show loading indicator (with image if analyzing)
  if (analysingImageUrl) {
    showLoadingIndicatorWithImage(analysingImageUrl);
  } else {
    showLoadingIndicator();
  }
  
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
      body: JSON.stringify(requestBody)
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

// ── Image generation result ──────────────────────────────────────────────────
socket.on('image_ready', (data) => {
  hideLoadingIndicator();

  // If the shimmer placeholder exists, replace its content in-place so the
  // image appears exactly where the preview was (no jump to bottom).
  const placeholder = document.getElementById('image-preview-placeholder');
  if (placeholder) {
    const timeStr = new Date().toLocaleTimeString();
    const safeComment  = escapeHtml(data.comment || '');
    const safeTitle    = escapeHtml(data.title || 'Generated Image');
    const safeUrl      = escapeHtml(data.url);
    const safeDlUrl    = escapeHtml(data.download_url);

    placeholder.removeAttribute('id'); // no longer the placeholder
    placeholder.dataset.imageId = data.image_id;
    placeholder.innerHTML = `
      <div class="message-header">
        <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
        <span class="message-time">${timeStr}</span>
      </div>
      <div class="message-content">
        <p class="image-comment">${safeComment}</p>
        <div class="generated-image-wrapper">
          <p class="image-title"><strong>${safeTitle}</strong></p>
          <img
            class="generated-image"
            src="${safeUrl}"
            alt="${safeTitle}"
            loading="lazy"
            onerror="this.closest('.generated-image-wrapper').innerHTML='<p class=\\'image-error\\'>Image could not be loaded.</p>'"
          />
          <div class="image-actions">
            <a class="image-download-btn" href="${safeDlUrl}" download title="Download image">⬇ Download</a>
          </div>
        </div>
      </div>
    `;
    scrollToBottom();
  } else {
    addImageMessage(data.image_id, data.title, data.comment, data.url, data.download_url);
  }
});

// ── Wikipedia cover image ────────────────────────────────────────────────────
socket.on('wikipedia_image_ready', (data) => {
  hideLoadingIndicator();
  addWikipediaImageMessage(data.url, data.title);
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
