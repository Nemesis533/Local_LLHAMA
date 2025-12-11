/**
 * Model Configuration Module
 * Manages assistant name, model settings, chat interaction, and calendar events
 */

let modelConfig = null;
let modelSocket = null;

/**
 * Initialize socket connection for model tab
 */
function initModelSocket() {
    if (modelSocket) return; // Already initialized
    
    modelSocket = io();
    
    modelSocket.on('connect', () => {
        console.log('✅ Model tab connected to SocketIO server');
    });
    
    // Listen for log lines
    modelSocket.on('log_line', (data) => {
        const line = data.line;
        if (!line) return;
        
        const trimmed = line.trim();
        if (!trimmed) return;
        
        addModelLogLine(trimmed);
    });
    
    // Listen for system messages
    modelSocket.on('system_message', (data) => {
        const message = data.data || data;
        if (!message) return;
        addModelLogLine(message);
    });
}

/**
 * Add a log line to the model log box
 */
function addModelLogLine(text) {
    const logBox = document.getElementById('model-log-box');
    if (!logBox) return;
    
    const div = document.createElement('div');
    div.classList.add('log-line');
    div.textContent = text;
    
    // Add styling based on content
    if (text.includes('[LLM Reply]')) {
        div.style.color = '#9b59b6'; // purple
    } else if (text.includes('[User Prompt]')) {
        div.style.color = '#3498db'; // blue
    } else if (/warning/i.test(text)) {
        div.style.color = '#f39c12'; // yellow
    } else if (/critical|error/i.test(text)) {
        div.style.color = '#e74c3c'; // red
    } else if (/info/i.test(text)) {
        div.style.color = '#27ae60'; // green
    }
    
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
}

/**
 * Load model configuration from server
 */
export async function loadModelConfig() {
    try {
        const response = await fetch('/settings/model');
        const data = await response.json();
        
        if (data.status === 'ok') {
            modelConfig = data.config;
        } else {
            console.error('Failed to load model config:', data.message);
        }
    } catch (error) {
        console.error('Error loading model config:', error);
    }
}

/**
 * Display model configuration
 */
export function displayModelConfig() {
    if (!modelConfig) {
        console.error('No model config data loaded');
        return;
    }
    
    // Set assistant name
    document.getElementById('assistant-name').value = modelConfig.assistant_name || 'Assistant';
    
    // Display model information (read-only)
    document.getElementById('current-ollama-model').textContent = modelConfig.ollama_model || 'unknown';
    document.getElementById('current-embedding-model').textContent = modelConfig.embedding_model || 'unknown';
    document.getElementById('current-internet-searches').textContent = modelConfig.internet_searches ? 'Enabled' : 'Disabled';
    
    // Initialize socket and other features
    initModelSocket();
    initPromptSender();
    fetchModelCalendarEvents();
}

/**
 * Initialize prompt sender
 */
function initPromptSender() {
    const sendBtn = document.getElementById('model-send-prompt-btn');
    const inputEl = document.getElementById('model-prompt-input');
    
    if (!sendBtn || !inputEl) return;
    
    const sendPrompt = async () => {
        const text = inputEl.value.trim();
        if (!text) return;
        
        try {
            const res = await fetch('/from_user_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            
            if (res.ok) {
                console.log('✅ Prompt sent successfully:', text);
                inputEl.value = ''; // clear input
                addModelLogLine(`[User Prompt] ${text}`);
            } else {
                const errText = await res.text();
                console.error('❌ Failed to send prompt:', errText);
                addModelLogLine(`[Error] Failed to send prompt: ${errText}`);
            }
        } catch (err) {
            console.error('❌ Error sending prompt:', err);
            addModelLogLine(`[Error] ${err.message}`);
        }
    };
    
    sendBtn.onclick = sendPrompt;
    
    // Allow Enter key to send
    inputEl.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendPrompt();
        }
    });
}

/**
 * Fetch and display calendar events
 */
async function fetchModelCalendarEvents() {
    try {
        const response = await fetch('/api/calendar/events');
        const data = await response.json();
        
        const calendarEl = document.getElementById('model-calendar-events');
        if (!calendarEl) return;
        
        if (!data.success || data.events.length === 0) {
            calendarEl.innerHTML = '<p style="color: #999; font-style: italic;">No upcoming reminders or alarms</p>';
            return;
        }
        
        // Group events by type
        const reminders = data.events.filter(e => e.type === 'reminder');
        const alarms = data.events.filter(e => e.type === 'alarm');
        const appointments = data.events.filter(e => e.type === 'appointment');
        
        let html = '';
        
        if (reminders.length > 0) {
            html += '<div style="margin-bottom: 20px;"><h4 style="color: #555; margin-bottom: 10px;">Reminders</h4>';
            reminders.forEach(event => {
                html += formatModelEventHTML(event);
            });
            html += '</div>';
        }
        
        if (alarms.length > 0) {
            html += '<div style="margin-bottom: 20px;"><h4 style="color: #555; margin-bottom: 10px;">Alarms</h4>';
            alarms.forEach(event => {
                html += formatModelEventHTML(event);
            });
            html += '</div>';
        }
        
        if (appointments.length > 0) {
            html += '<div style="margin-bottom: 20px;"><h4 style="color: #555; margin-bottom: 10px;">Appointments</h4>';
            appointments.forEach(event => {
                html += formatModelEventHTML(event);
            });
            html += '</div>';
        }
        
        calendarEl.innerHTML = html;
        
        // Add delete button listeners
        document.querySelectorAll('.model-delete-event-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const eventId = e.target.dataset.eventId;
                deleteModelCalendarEvent(eventId);
            });
        });
    } catch (err) {
        console.error('Error fetching calendar events:', err);
        const calendarEl = document.getElementById('model-calendar-events');
        if (calendarEl) {
            calendarEl.innerHTML = '<p style="color: #e74c3c;">Failed to load events</p>';
        }
    }
}

/**
 * Format event HTML
 */
function formatModelEventHTML(event) {
    const repeatBadge = event.repeat !== 'none' 
        ? `<span style="background: #3498db; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 8px;">${event.repeat}</span>` 
        : '';
    
    const description = event.description 
        ? `<div style="color: #666; font-size: 12px; margin-top: 4px;">${event.description}</div>` 
        : '';
    
    const date = new Date(event.due_datetime);
    const formattedDate = date.toLocaleString();
    
    return `
        <div style="background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #3498db;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <strong style="color: #2c3e50;">${event.title}</strong>${repeatBadge}
                    <div style="color: #7f8c8d; font-size: 13px; margin-top: 4px;">${formattedDate}</div>
                    ${description}
                </div>
                <button class="model-delete-event-btn btn-small" 
                        data-event-id="${event.id}" 
                        style="background: #e74c3c; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 11px;">
                    Delete
                </button>
            </div>
        </div>
    `;
}

/**
 * Delete a calendar event
 */
async function deleteModelCalendarEvent(eventId) {
    if (!confirm('Are you sure you want to delete this event?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/calendar/events/${eventId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Event deleted successfully');
            fetchModelCalendarEvents(); // Refresh the list
        } else {
            alert('Failed to delete event: ' + (data.message || 'Unknown error'));
        }
    } catch (err) {
        console.error('Error deleting event:', err);
        alert('Error deleting event: ' + err.message);
    }
}

/**
 * Save model configuration to server
 */
export async function saveModelConfig() {
    const statusDiv = document.getElementById('model-save-status');
    
    try {
        const assistantName = document.getElementById('assistant-name').value.trim();
        
        if (!assistantName) {
            statusDiv.className = 'save-status error';
            statusDiv.textContent = '✗ Assistant name cannot be empty';
            statusDiv.style.display = 'block';
            return;
        }
        
        // Send to server
        const response = await fetch('/settings/model', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                assistant_name: assistantName
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'ok') {
            statusDiv.className = 'save-status success';
            statusDiv.textContent = '✓ Assistant name saved successfully! Restart the system to apply changes.';
            statusDiv.style.display = 'block';
            
            // Update local config
            modelConfig.assistant_name = assistantName;
            
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 8000);
        } else {
            throw new Error(data.message || 'Failed to save');
        }
        
    } catch (error) {
        statusDiv.className = 'save-status error';
        statusDiv.textContent = '✗ Error saving model configuration: ' + error.message;
        statusDiv.style.display = 'block';
    }
}
