# calendar_routes.py
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
from ..auth.calendar_manager import CalendarManager

calendar_bp = Blueprint("calendar", __name__)

# Create a shared calendar manager instance
_calendar_manager = None

def get_calendar_manager():
    """Get or create the calendar manager instance."""
    global _calendar_manager
    if _calendar_manager is None:
        _calendar_manager = CalendarManager()
    return _calendar_manager

@calendar_bp.route('/calendar/events', methods=['GET'])
@login_required
def get_calendar_events():
    """
    Get upcoming calendar events for the current user.
    """
    try:
        calendar_manager = get_calendar_manager()
        user_id = current_user.id
        
        # Get upcoming events (next 30 days) for this user only
        upcoming_events = calendar_manager.get_upcoming_events(days=30, include_completed=False, user_id=user_id)
        
        # Format events for display
        formatted_events = []
        for event in upcoming_events:
            try:
                due_time = datetime.fromisoformat(event['due_datetime'])
                formatted_events.append({
                    'id': event['id'],
                    'title': event['title'],
                    'description': event.get('description', ''),
                    'type': event['event_type'],
                    'due_datetime': due_time.strftime('%Y-%m-%d %H:%M'),
                    'due_display': due_time.strftime('%b %d, %I:%M %p'),
                    'repeat': event.get('repeat_pattern', 'none'),
                    'is_completed': event.get('is_completed', 0)
                })
            except Exception as e:
                print(f"[CalendarRoutes] Error formatting event: {e}")
                continue
        
        return jsonify({
            "success": True,
            "events": formatted_events,
            "count": len(formatted_events)
        })
        
    except Exception as e:
        print(f"[CalendarRoutes] Error getting calendar events: {e}")
        return jsonify({"error": str(e)}), 500


@calendar_bp.route('/calendar/create', methods=['POST'])
@login_required
def create_calendar_event():
    """
    Create a new calendar event for the current user.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        title = data.get('title')
        event_type = data.get('type', 'reminder')
        due_datetime = data.get('due_datetime')
        description = data.get('description', '')
        repeat_pattern = data.get('repeat', 'none')
        
        if not title or not due_datetime:
            return jsonify({"error": "Title and due_datetime are required"}), 400
        
        calendar_manager = get_calendar_manager()
        user_id = current_user.id
        
        # Create event based on type
        if event_type == 'appointment':
            success, message, event_id = calendar_manager.add_appointment(
                title, due_datetime, description, user_id=user_id
            )
        elif event_type == 'alarm':
            success, message, event_id = calendar_manager.add_alarm(
                title, due_datetime, repeat_pattern, user_id=user_id
            )
        else:  # reminder
            success, message, event_id = calendar_manager.add_reminder(
                title, due_datetime, description, repeat_pattern, user_id=user_id
            )
        
        return jsonify({
            "success": success,
            "message": message,
            "event_id": event_id
        })
        
    except Exception as e:
        print(f"[CalendarRoutes] Error creating event: {e}")
        return jsonify({"error": str(e)}), 500


@calendar_bp.route('/calendar/delete/<int:event_id>', methods=['POST'])
@login_required
def delete_calendar_event(event_id):
    """
    Delete a calendar event.
    """
    try:
        calendar_manager = get_calendar_manager()
        
        # Delete the event
        success, message = calendar_manager.delete_event(event_id)
        
        return jsonify({
            "success": success,
            "message": message
        })
        
    except Exception as e:
        print(f"[CalendarRoutes] Error deleting event: {e}")
        return jsonify({"error": str(e)}), 500
