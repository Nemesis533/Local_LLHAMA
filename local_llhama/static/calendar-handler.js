// Calendar Event Handler

// Load calendar events
async function loadCalendarEvents() {
  try {
    const response = await fetch('/api/calendar/events');
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
    const response = await fetch(`/api/calendar/delete/${eventId}`, { method: 'POST' });
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

// Initialize calendar UI
function initCalendar() {
  const modal = document.getElementById('add-event-modal');
  const addEventBtn = document.getElementById('add-event-btn');
  const closeModal = document.querySelector('.close');
  const cancelBtn = document.getElementById('cancel-event-btn');
  const addEventForm = document.getElementById('add-event-form');
  
  if (!addEventBtn || !modal) {
    console.warn('Calendar UI elements not found');
    return;
  }
  
  // Modal handling
  addEventBtn.addEventListener('click', () => {
    modal.style.display = 'block';
    // Set default datetime to now
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('event-datetime').value = now.toISOString().slice(0, 16);
  });
  
  if (closeModal) {
    closeModal.addEventListener('click', () => {
      modal.style.display = 'none';
    });
  }
  
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      modal.style.display = 'none';
    });
  }
  
  window.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none';
    }
  });
  
  // Create event form submission
  if (addEventForm) {
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
        const response = await fetch('/api/calendar/create', {
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
  }
  
  // Load events on page load
  loadCalendarEvents();
  
  // Refresh events every 60 seconds
  setInterval(loadCalendarEvents, 60000);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCalendar);
} else {
  initCalendar();
}
