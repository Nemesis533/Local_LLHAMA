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
