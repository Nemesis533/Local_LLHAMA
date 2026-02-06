// System Metrics Handler (Admin Only)

let isAdmin = false;
let metricsInterval = null;

// Check if user is admin and initialize metrics panel
async function initMetricsPanel() {
  try {
    const response = await fetch('/check-auth');
    if (response.ok) {
      const data = await response.json();
      isAdmin = data.is_admin || false;
      
      if (isAdmin) {
        // Show the metrics panel
        const metricsPanel = document.getElementById('metrics-panel');
        if (metricsPanel) {
          metricsPanel.style.display = 'flex';
          
          // Setup toggle functionality
          const metricsToggle = document.getElementById('metrics-toggle');
          if (metricsToggle) {
            metricsToggle.addEventListener('click', () => {
              metricsPanel.classList.toggle('collapsed');
              
              // If expanding, immediately fetch metrics
              if (!metricsPanel.classList.contains('collapsed')) {
                fetchSystemMetrics();
              }
            });
          }
          
          // Start fetching metrics every 3 seconds when panel is open
          metricsInterval = setInterval(() => {
            if (!metricsPanel.classList.contains('collapsed')) {
              fetchSystemMetrics();
            }
          }, 1000);
          
          // Initial fetch (but don't show until expanded)
          // fetchSystemMetrics();
        }
      }
    }
  } catch (error) {
    console.error('Error checking admin status:', error);
  }
}

// Fetch system metrics from the API
async function fetchSystemMetrics() {
  try {
    const response = await fetch('/api/system-metrics');
    if (!response.ok) {
      if (response.status === 403) {
        console.warn('Access denied to system metrics');
        return;
      }
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    updateMetricsDisplay(data);
  } catch (error) {
    console.error('Error fetching system metrics:', error);
  }
}

// Update the metrics display with new data
function updateMetricsDisplay(metrics) {
  // Update CPU metrics
  if (metrics.cpu) {
    const cpuUsage = document.getElementById('cpu-usage');
    if (cpuUsage) {
      cpuUsage.textContent = metrics.cpu.usage_percent 
        ? `${metrics.cpu.usage_percent.toFixed(1)}%` 
        : '--';
    }
    
    const cpuTemp = document.getElementById('cpu-temp');
    if (cpuTemp) {
      cpuTemp.textContent = metrics.cpu.temperature 
        ? `${metrics.cpu.temperature.toFixed(1)}°C` 
        : 'N/A';
    }
  }
  
  // Update RAM metrics
  if (metrics.ram) {
    const ramUsed = document.getElementById('ram-used');
    if (ramUsed) {
      ramUsed.textContent = `${metrics.ram.used_gb.toFixed(1)} GB (${metrics.ram.percent.toFixed(1)}%)`;
    }
    
    const ramTotal = document.getElementById('ram-total');
    if (ramTotal) {
      ramTotal.textContent = `${metrics.ram.total_gb.toFixed(1)} GB`;
    }
  }
  
  // Update GPU metrics
  if (metrics.gpus && metrics.gpus.length > 0) {
    const gpuContainer = document.getElementById('gpu-metrics');
    if (gpuContainer) {
      gpuContainer.innerHTML = '<h4>GPU</h4>';
      
      metrics.gpus.forEach((gpu, index) => {
        const gpuCard = document.createElement('div');
        gpuCard.className = 'gpu-card';
        
        let gpuHtml = `<div class="gpu-name">${gpu.name || `GPU ${gpu.index}`}</div>`;
        
        if (gpu.utilization_percent !== null) {
          gpuHtml += `
            <div class="metric-item">
              <span class="metric-label">Usage:</span>
              <span class="metric-value">${gpu.utilization_percent.toFixed(1)}%</span>
            </div>`;
        }
        
        if (gpu.memory_used_mb !== null && gpu.memory_total_mb !== null) {
          const usedGB = (gpu.memory_used_mb / 1024).toFixed(1);
          const totalGB = (gpu.memory_total_mb / 1024).toFixed(1);
          const memPercent = ((gpu.memory_used_mb / gpu.memory_total_mb) * 100).toFixed(1);
          gpuHtml += `
            <div class="metric-item">
              <span class="metric-label">VRAM:</span>
              <span class="metric-value">${usedGB}/${totalGB} GB (${memPercent}%)</span>
            </div>`;
        }
        
        if (gpu.temperature !== null) {
          gpuHtml += `
            <div class="metric-item">
              <span class="metric-label">Temperature:</span>
              <span class="metric-value">${gpu.temperature.toFixed(1)}°C</span>
            </div>`;
        }
        
        if (gpu.power_draw_w !== null) {
          const powerDraw = gpu.power_draw_w.toFixed(1);
          const powerLimit = gpu.power_limit_w ? `/${gpu.power_limit_w.toFixed(0)}` : '';
          gpuHtml += `
            <div class="metric-item">
              <span class="metric-label">Power:</span>
              <span class="metric-value">${powerDraw}${powerLimit} W</span>
            </div>`;
        }
        
        gpuCard.innerHTML = gpuHtml;
        gpuContainer.appendChild(gpuCard);
      });
    }
  }
  
  // Update timestamp
  const timestamp = document.getElementById('metrics-timestamp');
  if (timestamp) {
    const now = new Date();
    timestamp.textContent = now.toLocaleTimeString();
  }
}

// Initialize metrics panel on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMetricsPanel);
} else {
  initMetricsPanel();
}
