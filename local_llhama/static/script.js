const outputEl = document.getElementById('log-box');

// Start server
const socket = io();

let lastLines = new Set();

socket.onAny((event, ...args) => {
  console.log('Received event:', event, args);
});

socket.on('connect', () => {
  console.log('✅ Connected to SocketIO server');
});

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

    if (trimmed.includes('[Main]')) {
      div.classList.add('main-line'); // cyan
    } else if (/warning/i.test(trimmed)) {
      div.classList.add('log-warning');
    } else if (/error/i.test(trimmed)) {
      div.classList.add('log-error');
    } else if (/info/i.test(trimmed)) {
      div.classList.add('log-info');
    } else if (isHttpMessage(trimmed)) {
      div.classList.add('http-message');
    }
  }

  outputEl.appendChild(div);
  lastLines.add(trimmed);

  if (lastLines.size > 500) {
    lastLines = new Set(Array.from(lastLines).slice(-500));
  }

  outputEl.scrollTop = outputEl.scrollHeight;
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



// Initial clear
outputEl.innerHTML = '';

fetchSettings();
