# calendar_routes.py
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
from ..auth.calendar_manager import CalendarManager

calendar_bp = Blueprint("calendar", __name__, url_prefix='/api/calendar')

# Shared calendar manager instance (will be set via init_calendar_routes)
_calendar_manager = None

def init_calendar_routes(pg_client=None):
    """Initialize calendar routes with PostgreSQL client."""
    global _calendar_manager
    _calendar_manager = CalendarManager(pg_client)

def get_calendar_manager():
    """Get the calendar manager instance."""
    global _calendar_manager
    if _calendar_manager is None:
        _calendar_manager = CalendarManager()
    return _calendar_manager

@calendar_bp.route('/events/upcoming', methods=['GET'])
@login_required
def get_upcoming_events():
    """Get upcoming events for current user"""
    try:
        hours = request.args.get('hours', default=24, type=int)
        calendar_manager = get_calendar_manager()
        
        # Convert hours to days for calendar_manager
        days = max(1, hours // 24)
        events = calendar_manager.get_upcoming_events(
            days=days,
            user_id=current_user.id,
            include_completed=False
        )
        return jsonify({
            'success': True,
            'events': events
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@calendar_bp.route('/events/search', methods=['GET'])
@login_required
def search_events():
    """Search events by term"""
    try:
        search_term = request.args.get('q', default='', type=str)
        if not search_term:
            return jsonify({'success': False, 'error': 'No search term provided'}), 400
        
        calendar_manager = get_calendar_manager()
        events = calendar_manager.search_events(search_term)
        return jsonify({
            'success': True,
            'events': events
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@calendar_bp.route('/events/<int:event_id>', methods=['GET'])
@login_required
def get_event(event_id):
    """Get specific event by ID"""
    try:
        calendar_manager = get_calendar_manager()
        event = calendar_manager.get_event_by_id(event_id)
        if not event:
            return jsonify({'success': False, 'error': 'Event not found'}), 404
        return jsonify({
            'success': True,
            'event': event
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@calendar_bp.route('/events/<int:event_id>/complete', methods=['POST'])
@login_required
def complete_event(event_id):
    """Mark event as completed"""
    try:
        calendar_manager = get_calendar_manager()
        success, message = calendar_manager.complete_event(event_id)
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@calendar_bp.route('/events', methods=['GET'])
@login_required
def get_calendar_events():
    """
    Get upcoming calendar events for the current user (30 day default).
    Legacy endpoint - use /events/upcoming for more control.
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

@calendar_bp.route('/create', methods=['POST'])
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

@calendar_bp.route('/delete/<int:event_id>', methods=['POST'])
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
