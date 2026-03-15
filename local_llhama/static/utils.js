// Shared Utility Functions

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

// Auto-scroll to bottom
function scrollToBottom() {
  const chatMessages = document.getElementById('chat-messages');
  if (chatMessages) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

// Show loading indicator
function showLoadingIndicator() {
  const chatMessages = document.getElementById('chat-messages');
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'chat-message assistant-message loading-message';
  loadingDiv.id = 'loading-indicator';
  
  loadingDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
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
  // Route image-generation statuses to the dedicated shimmer placeholder
  // Exclude:
  //   - Wikipedia image fetches (they use their own event, not the shimmer)
  //   - Image analysis messages (containing "vision" or "Preparing image")
  const isImageAnalysis = /vision|Preparing image|Analyzing/i.test(status);
  const isImageGeneration = /Freeing GPU.*image generation|Loading image model|Generating image:|Saving image/i.test(status);
  
  if (isImageGeneration && !isImageAnalysis) {
    showImagePreviewStatus(status);
    return;
  }
  
  // Skip showing status messages for image analysis - we use the loading indicator with image instead
  if (isImageAnalysis) {
    return;
  }

  // Remove existing status if any
  hideStatusMessage();
  
  const chatMessages = document.getElementById('chat-messages');
  const statusDiv = document.createElement('div');
  statusDiv.className = 'chat-message assistant-message status-message';
  statusDiv.id = 'status-indicator';
  
  statusDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
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

// Show (or update) the fuzzy shimmer placeholder for image generation
function showImagePreviewStatus(status) {
  hideStatusMessage(); // remove any plain status bubble

  let placeholder = document.getElementById('image-preview-placeholder');
  if (!placeholder) {
    const chatMessages = document.getElementById('chat-messages');
    placeholder = document.createElement('div');
    placeholder.className = 'chat-message assistant-message image-message image-preview-placeholder';
    placeholder.id = 'image-preview-placeholder';
    placeholder.innerHTML = `
      <div class="message-header">
        <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
      </div>
      <div class="message-content">
        <div class="shimmer-wrapper">
          <div class="shimmer-title-bar"></div>
          <div class="shimmer-image-area"></div>
          <div class="shimmer-status">⚙️ <span id="image-preview-status-text"></span></div>
        </div>
      </div>
    `;
    chatMessages.appendChild(placeholder);
    scrollToBottom();
  }

  // Just update the status text — leave the shimmer in place
  const statusText = document.getElementById('image-preview-status-text');
  if (statusText) statusText.textContent = status;
}

// Hide status message
function hideStatusMessage() {
  const statusDiv = document.getElementById('status-indicator');
  if (statusDiv) {
    statusDiv.remove();
  }
}

// Add message to chat
function addMessage(content, type = 'system') {
  const chatMessages = document.getElementById('chat-messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = `chat-message ${type}-message`;
  
  const timestamp = new Date().toLocaleTimeString();
  
  // Apply Markdown formatting
  const formattedContent = formatMarkdown(content);
  
  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${type === 'user' ? 'You' : type === 'assistant' ? (window.currentAssistantName || 'Assistant') : 'System'}</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">${formattedContent}</div>
  `;
  
  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Add an AI-generated image message to the chat
function addImageMessage(imageId, title, comment, imageUrl, downloadUrl, timeStr) {
  const chatMessages = document.getElementById('chat-messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message assistant-message image-message';
  messageDiv.dataset.imageId = imageId;

  const timestamp = timeStr || new Date().toLocaleTimeString();
  const safeComment = escapeHtml(comment || '');
  const safeTitle = escapeHtml(title || 'Generated Image');

  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">
      <p class="image-comment">${safeComment}</p>
      <div class="generated-image-wrapper">
        <p class="image-title"><strong>${safeTitle}</strong></p>
        <img
          class="generated-image"
          src="${escapeHtml(imageUrl)}"
          alt="${safeTitle}"
          loading="lazy"
          onerror="this.closest('.generated-image-wrapper').innerHTML='<p class=\\'image-error\\'>Image could not be loaded.</p>'"
        />
        <div class="image-actions">
          <a
            class="image-download-btn"
            href="${escapeHtml(downloadUrl)}"
            download
            title="Download image"
          >⬇ Download</a>
        </div>
      </div>
    </div>
  `;

  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Display a Wikipedia cover image inline in the chat (not saved locally, just a URL)
function addWikipediaImageMessage(imageUrl, title, timeStr) {
  const chatMessages = document.getElementById('chat-messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message assistant-message wikipedia-image-message';

  const timestamp = timeStr || new Date().toLocaleTimeString();
  const safeUrl   = escapeHtml(imageUrl);
  const safeTitle = escapeHtml(title || 'Wikipedia Image');

  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">
      <div class="wikipedia-image-wrapper">
        <p class="image-title"><strong>${safeTitle}</strong></p>
        <img
          class="wikipedia-image"
          src="${safeUrl}"
          alt="${safeTitle}"
          loading="lazy"
          onerror="this.closest('.wikipedia-image-wrapper').innerHTML='<p class=\\'image-error\\'>Image could not be loaded.</p>'"
        />
        <p class="wikipedia-image-caption" style="font-size:12px;color:#666;margin-top:4px;">Source: Wikipedia</p>
      </div>
    </div>
  `;

  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Display an uploaded image from the user
function addUploadedImageMessage(imageUrl, filename, query, timeStr) {
  const chatMessages = document.getElementById('chat-messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message user-message uploaded-image-message';

  const timestamp = timeStr || new Date().toLocaleTimeString();
  const safeUrl = escapeHtml(imageUrl);
  const safeFilename = escapeHtml(filename || 'Uploaded Image');
  const safeQuery = escapeHtml(query || '');

  messageDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">You</span>
      <span class="message-time">${timestamp}</span>
    </div>
    <div class="message-content">
      ${safeQuery ? `<p>${safeQuery}</p>` : ''}
      <div class="uploaded-image-wrapper" style="margin-top: 8px;">
        <p class="image-filename" style="font-size: 12px; color: #666; margin-bottom: 4px;">📎 ${safeFilename}</p>
        <img
          class="uploaded-image"
          src="${safeUrl}"
          alt="${safeFilename}"
          style="max-width: 300px; max-height: 300px; border-radius: 8px; border: 1px solid #e0e0e0;"
          loading="lazy"
          onerror="this.closest('.uploaded-image-wrapper').innerHTML='<p class=\\'image-error\\'>Image could not be loaded.</p>'"
        />
      </div>
    </div>
  `;

  chatMessages.appendChild(messageDiv);
  scrollToBottom();
}

// Show loading indicator with an image (for image analysis)
function showLoadingIndicatorWithImage(imageUrl) {
  const chatMessages = document.getElementById('chat-messages');
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'chat-message assistant-message loading-message';
  loadingDiv.id = 'loading-indicator';
  
  const safeUrl = escapeHtml(imageUrl);
  
  loadingDiv.innerHTML = `
    <div class="message-header">
      <span class="message-type">${window.currentAssistantName || 'Assistant'}</span>
    </div>
    <div class="message-content">
      <div class="analyzing-image-wrapper" style="margin-bottom: 12px;">
        <img
          src="${safeUrl}"
          alt="Analyzing image"
          style="max-width: 200px; max-height: 200px; border-radius: 8px; border: 1px solid #e0e0e0; opacity: 0.7;"
        />
      </div>
      <div class="loading-dots">
        <span class="loading-text">Analyzing image</span><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>
    </div>
  `;
  
  chatMessages.appendChild(loadingDiv);
  scrollToBottom();
}