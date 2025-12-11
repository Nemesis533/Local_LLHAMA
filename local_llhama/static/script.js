const outputEl = document.getElementById('log-box');

// Start server
const socket = io();

let lastLines = new Set();

// Check if coming from restart action
window.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('restarting') === 'true') {
    // Add restart notification to log
    addLogLine('🔄 System restart initiated... Monitoring progress below.');
    // Clean up URL
    window.history.replaceState({}, document.title, window.location.pathname);
  }
});

// Logout functionality
document.getElementById('logout-btn').addEventListener('click', async () => {
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
    alert('Logout error. Please try again.');
  }
});

socket.onAny((event, ...args) => {
  console.log('Received event:', event, args);
});

socket.on('connect', () => {
  console.log('✅ Connected to SocketIO server');
});

function addLogLine(text) {
  const line = document.createElement('div');
  line.className = 'log-line';
  line.textContent = text;
  outputEl.appendChild(line);
  outputEl.scrollTop = outputEl.scrollHeight;
}

function isImageFilename(line) {
  return /\.(jpeg|jpg|gif|png|webp|bmp|svg)$/i.test(line.trim());
}

function buildImageURL(filename) {
  // Make sure no accidental leading slashes
  const cleanName = filename.trim().replace(/^\/+/, '');
  return `/static/images/${cleanName}`;
}

function selectImageForLine(line) {
  const trimmed = line.trim();

  if (/error/i.test(trimmed)) {
    return '/static/images/error-icon.png';
  } else if (/warning/i.test(trimmed)) {
    return '/static/images/warning-icon.png';
  } else if (isImageFilename(trimmed)) {
    return buildImageURL(trimmed);
  } else if (/success/i.test(trimmed)) {
    return '/static/images/success-icon.png';
  }
  return null;
}

function isHttpMessage(line) {
  return /^HTTP/.test(line) || line.includes('HTTP/');
}

function isHttpGetToHost(line) {
  return /GET\s+(\S+)\s+HTTP\/[0-9.]+/.test(line);
}

socket.on('log_line', (data) => {
  console.log('Received log_line:', data); // <-- is this visible?
  const line = data.line;
  if (!line) {
    console.warn('log_line received but line is missing or falsy:', data); // <-- put it here
    return;
  }
  if (!line) {
    console.warn('log_line event received with no line');
    return;
  }
  const trimmed = line.trim();
  if (!trimmed || lastLines.has(trimmed) || isHttpGetToHost(trimmed)) return;

  const div = document.createElement('div');
  const imgUrl = selectImageForLine(trimmed);

  if (imgUrl) {
    const img = document.createElement('img');
    img.src = imgUrl;
    img.alt = 'Log image';
    img.style.maxWidth = '100%';
    img.onerror = () => { img.remove(); };
    div.appendChild(img);
  } else {
    div.textContent = trimmed;

    // Default log style
    div.classList.add('log-line');

  if (trimmed.includes('[LLM Reply]')) {
    div.classList.add('llm-reply-line'); // purple
  } else if (trimmed.includes('[User Prompt]')) {
    div.classList.add('user-prompt-line'); // blue
  } else if (trimmed.includes('[Main]')) {
    div.classList.add('main-line'); // cyan
  } else if (trimmed.includes('[Supervisor]')) {
    div.classList.add('supervisor-line'); // magenta
  } else if (/warning/i.test(trimmed)) {
    div.classList.add('log-warning'); // yellow
  } else if (/critical|error/i.test(trimmed)) {
    div.classList.add('log-critical'); // red
  } else if (/info/i.test(trimmed)) {
    div.classList.add('log-info'); // green
  } else if (isHttpMessage(trimmed)) {
    div.classList.add('http-message'); // optional styling
  }
  }

  outputEl.appendChild(div);
  lastLines.add(trimmed);

  if (lastLines.size > 500) {
    lastLines = new Set(Array.from(lastLines).slice(-500));
  }

  outputEl.scrollTop = outputEl.scrollHeight;
});

// Listen for system messages (startup, restart notifications, etc.)
socket.on('system_message', (data) => {
  console.log('Received system_message:', data);
  const message = data.data || data;
  if (!message) return;
  
  addLogLine(message);
});

async function fetchSettings() {
  try {
    const res = await fetch('/settings');
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    const container = document.getElementById('settings-content');
    container.innerHTML = '';  // clear loading

    for (const section in data) {
      const sectionData = data[section];

      const sectionDiv = document.createElement('div');
      sectionDiv.classList.add('settings-section');

      const title = document.createElement('h3');
      title.textContent = section;
      sectionDiv.appendChild(title);

      for (const key in sectionData) {
        const { value, type } = sectionData[key];

        const label = document.createElement('label');
        label.textContent = key;
        label.style.display = 'block';
        label.style.marginTop = '10px';

        let input;
        if (type === 'list') {
          input = document.createElement('input');
          input.type = 'text';
          input.value = value.join(', ');
          input.placeholder = 'Comma-separated values';
        } else if (type === 'bool') {
          input = document.createElement('select');
          ['True', 'False'].forEach(optVal => {
            const opt = document.createElement('option');
            opt.value = optVal;
            opt.text = optVal;
            if (String(value) === optVal) opt.selected = true;
            input.appendChild(opt);
          });
        } else {
          input = document.createElement('input');
          input.type = 'text';
          input.value = value;
        }

        input.classList.add('setting-input');
        input.dataset.section = section;
        input.dataset.key = key;
        input.dataset.type = type;

        sectionDiv.appendChild(label);
        sectionDiv.appendChild(input);
      }

      container.appendChild(sectionDiv);
    }
  } catch (err) {
    document.getElementById('settings-content').textContent =
      'Error loading settings: ' + err.message;
  }
}

document.getElementById('save-settings-btn').addEventListener('click', async () => {
  const inputs = document.querySelectorAll('.setting-input');
  const updatedSettings = {};

  inputs.forEach(input => {
    const section = input.dataset.section;
    const key = input.dataset.key;
    const type = input.dataset.type;
    let value = input.value;

    if (!updatedSettings[section]) updatedSettings[section] = {};

    if (type === 'list') {
      value = value.split(',').map(v => v.trim());
    } else if (type === 'bool') {
      value = value === 'True';
    }

    updatedSettings[section][key] = {
      value: value,
      type: type
    };
  });

  try {
    const res = await fetch('/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updatedSettings)
    });

    if (res.ok) {
      alert('✅ Settings saved!');
    } else {
      const text = await res.text();
      alert('❌ Failed to save: ' + text);
    }
  } catch (err) {
    alert('❌ Error saving settings: ' + err.message);
  }
});

document.getElementById("restart-system-btn").addEventListener("click", () => {
  fetch("/restart-system", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "restart" })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert("System restart initiated.");
    } else {
      alert("Failed to restart system: " + data.error);
    }
  })
  .catch(err => alert("Error: " + err));
});
// Handle prompt send
document.getElementById('send-prompt-btn').addEventListener('click', async () => {
  const inputEl = document.getElementById('prompt-input');
  const text = inputEl.value.trim();

  if (!text) return; // do nothing if empty

  try {
    const res = await fetch('/from_user_text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (res.ok) {
      console.log('✅ Prompt sent successfully:', text);
      inputEl.value = ''; // clear input after sending
    } else {
      const errText = await res.text();
      console.error('❌ Failed to send prompt:', errText);
    }
  } catch (err) {
    console.error('❌ Error sending prompt:', err);
  }
});


// Initial clear
outputEl.innerHTML = '';

fetchSettings();
fetchCalendarEvents();

// Fetch and display calendar events
function fetchCalendarEvents() {
  fetch('/api/calendar/events')
    .then(response => response.json())
    .then(data => {
      const calendarEl = document.getElementById('calendar-events');
      
      if (!data.success || data.events.length === 0) {
        calendarEl.innerHTML = '<p class="no-events">No upcoming reminders or alarms</p>';
        return;
      }
      
      // Group events by type
      const reminders = data.events.filter(e => e.type === 'reminder');
      const alarms = data.events.filter(e => e.type === 'alarm');
      const appointments = data.events.filter(e => e.type === 'appointment');
      
      let html = '';
      
      if (reminders.length > 0) {
        html += '<div class="event-group"><h4>Reminders</h4>';
        reminders.forEach(event => {
          html += formatEventHTML(event);
        });
        html += '</div>';
      }
      
      if (alarms.length > 0) {
        html += '<div class="event-group"><h4>Alarms</h4>';
        alarms.forEach(event => {
          html += formatEventHTML(event);
        });
        html += '</div>';
      }
      
      if (appointments.length > 0) {
        html += '<div class="event-group"><h4>Appointments</h4>';
        appointments.forEach(event => {
          html += formatEventHTML(event);
        });
        html += '</div>';
      }
      
      calendarEl.innerHTML = html;
      
      // Add delete button listeners
      document.querySelectorAll('.delete-event-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const eventId = e.target.dataset.eventId;
          deleteCalendarEvent(eventId);
        });
      });
    })
    .catch(err => {
      console.error('Error fetching calendar events:', err);
      document.getElementById('calendar-events').innerHTML = '<p class="error">Failed to load events</p>';
    });
}

function formatEventHTML(event) {
  const repeatBadge = event.repeat !== 'none' ? `<span class="repeat-badge">${event.repeat}</span>` : '';
  const description = event.description ? `<p class="event-desc">${event.description}</p>` : '';
  
  return `
    <div class="calendar-event">
      <div class="event-header">
        <span class="event-title">${event.title}</span>
        <button class="delete-event-btn" data-event-id="${event.id}" title="Delete">✕</button>
      </div>
      <div class="event-time">${event.due_display} ${repeatBadge}</div>
      ${description}
    </div>
  `;
}

function deleteCalendarEvent(eventId) {
  if (!confirm('Are you sure you want to delete this event?')) {
    return;
  }
  
  fetch(`/api/calendar/delete/${eventId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        fetchCalendarEvents(); // Refresh the list
      } else {
        alert('Failed to delete event: ' + data.message);
      }
    })
    .catch(err => {
      console.error('Error deleting event:', err);
      alert('Error deleting event');
    });
}

// Refresh calendar events every 30 seconds
setInterval(fetchCalendarEvents, 30000);

