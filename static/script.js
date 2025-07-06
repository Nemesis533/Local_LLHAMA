const outputEl = document.getElementById('log-box');

let lastLines = new Set();

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

async function fetchLogs() {
  try {
    const res = await fetch('/stdout');
    if (!res.ok) {
      outputEl.innerHTML += `<div class="error">Error fetching logs: ${res.status} ${res.statusText}</div>`;
      return;
    }
    const text = await res.text();
    const lines = text.split('\n');

    // Filter out lines:
    //  - Already displayed
    //  - Empty lines
    //  - GET requests to host that you want to hide
    const newLines = lines.filter(line => 
    !lastLines.has(line) && 
    line.trim() !== '' &&
    !isHttpGetToHost(line)
    );
    if (newLines.length > 0) {
        for (const line of newLines) {
        const trimmed = line.trim();
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
            if (isHttpMessage(trimmed)) {
            div.classList.add('http-message');
            }
        }

        outputEl.appendChild(div);
        lastLines.add(line);
        }

      if (lastLines.size > 500) {
        lastLines = new Set(Array.from(lastLines).slice(-500));
      }

      outputEl.scrollTop = outputEl.scrollHeight;
    }
  } catch (err) {
    outputEl.innerHTML += `<div class="error">Error fetching logs: ${err}</div>`;
  }
}

// Initial clear
outputEl.innerHTML = '';

// Fetch logs every 3 seconds
fetchLogs();
setInterval(fetchLogs, 3000);
