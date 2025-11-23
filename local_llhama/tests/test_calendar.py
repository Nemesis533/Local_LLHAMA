#!/usr/bin/env python3
"""
Test script for Calendar/Reminder functionality.
"""

from datetime import datetime, timedelta
from local_llhama.auth.calendar_manager import CalendarManager


def test_calendar_operations():
    """Test all calendar operations."""
    print("=== Testing Calendar Manager ===\n")
    
    # Initialize
    calendar = CalendarManager()
    print("✓ Calendar manager initialized\n")
    
    # Test 1: Add reminders
    print("Test 1: Adding reminders")
    future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    success, msg, id1 = calendar.add_reminder(
        "Take medication", 
        future, 
        "Daily vitamin D",
        repeat_pattern="daily"
    )
    print(f"  {msg}")
    
    success, msg, id2 = calendar.add_reminder(
        "Team meeting",
        "tomorrow at 14:00",
        "Discuss Q4 results"
    )
    print(f"  {msg}\n")
    
    # Test 2: Add appointments
    print("Test 2: Adding appointments")
    future_apt = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d 10:30")
    success, msg, id3 = calendar.add_appointment(
        "Doctor appointment",
        future_apt,
        "Annual checkup with Dr. Smith"
    )
    print(f"  {msg}\n")
    
    # Test 3: Add alarms
    print("Test 3: Adding alarms")
    tomorrow_7am = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 07:00")
    success, msg, id4 = calendar.add_alarm(
        "Morning wakeup",
        tomorrow_7am,
        repeat_pattern="daily"
    )
    print(f"  {msg}\n")
    
    # Test 4: Get upcoming events
    print("Test 4: Getting upcoming events")
    events = calendar.get_upcoming_events(days=7)
    print(f"  Found {len(events)} upcoming events:")
    for event in events:
        dt = datetime.fromisoformat(event['due_datetime'])
        print(f"  - [{event['event_type']}] {event['title']} at {dt.strftime('%Y-%m-%d %H:%M')}")
    print()
    
    # Test 5: Search events
    print("Test 5: Searching for 'meeting'")
    results = calendar.search_events("meeting")
    print(f"  Found {len(results)} matching events:")
    for event in results:
        print(f"  - {event['title']}")
    print()
    
    # Test 6: Complete a reminder
    print("Test 6: Completing a reminder")
    if id1:
        success, msg = calendar.complete_event(id1)
        print(f"  {msg}\n")
    
    # Test 7: Update an event
    print("Test 7: Updating an event")
    if id2:
        success, msg = calendar.update_event(
            id2,
            description="Updated: Discuss Q4 results and 2025 planning"
        )
        print(f"  {msg}\n")
    
    # Test 8: Get specific event types
    print("Test 8: Getting alarms only")
    alarms = calendar.get_upcoming_events(event_type='alarm', days=30)
    print(f"  Found {len(alarms)} alarms:")
    for alarm in alarms:
        dt = datetime.fromisoformat(alarm['due_datetime'])
        print(f"  - {alarm['title']} at {dt.strftime('%Y-%m-%d %H:%M')}")
    print()
    
    # Test 9: Delete an event
    print("Test 9: Deleting an event")
    if id4:
        success, msg = calendar.delete_event(id4)
        print(f"  {msg}\n")
    
    print("=== All tests completed ===")


def test_simple_functions_integration():
    """Test SimpleFunctions integration with calendar."""
    print("\n\n=== Testing SimpleFunctions Integration ===\n")
    
    from local_llhama.Simple_Functions import SimpleFunctions
    
    # Initialize
    sf = SimpleFunctions(home_location="40.7128,-74.0060")
    print("✓ SimpleFunctions initialized with calendar\n")
    
    # Test add reminder
    print("Test: add_reminder()")
    result = sf.add_reminder("Buy groceries", "tomorrow at 18:00", "Milk, eggs, bread")
    print(f"  {result}\n")
    
    # Test add appointment
    print("Test: add_appointment()")
    future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d 15:00")
    result = sf.add_appointment("Client meeting", future, "Presentation with ABC Corp")
    print(f"  {result}\n")
    
    # Test add alarm
    print("Test: add_alarm()")
    result = sf.add_alarm("Morning workout", "tomorrow at 06:30", repeat="daily")
    print(f"  {result}\n")
    
    # Test get upcoming
    print("Test: get_all_upcoming_events()")
    result = sf.get_all_upcoming_events(days=7)
    print(f"  {result}\n")
    
    # Test get reminders
    print("Test: get_upcoming_reminders()")
    result = sf.get_upcoming_reminders(days=7)
    print(f"  {result}\n")
    
    # Test complete reminder
    print("Test: complete_reminder()")
    result = sf.complete_reminder("groceries")
    print(f"  {result}\n")
    
    # Test delete
    print("Test: delete_reminder()")
    result = sf.delete_reminder("workout")
    print(f"  {result}\n")
    
    print("=== Integration tests completed ===")


if __name__ == "__main__":
    test_calendar_operations()
    test_simple_functions_integration()
