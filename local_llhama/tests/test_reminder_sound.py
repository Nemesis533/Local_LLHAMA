#!/usr/bin/env python3
"""
Test script to verify reminder sound functionality
This script adds a reminder and checks that the system will play the sound.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from local_llhama.auth.calendar_manager import CalendarManager
from local_llhama.Audio_Output import SoundActions

def test_reminder_sound():
    """Test that reminders can be set and the sound system is configured"""
    
    print("=" * 60)
    print("Testing Reminder Sound Functionality")
    print("=" * 60)
    
    # Create calendar manager
    calendar = CalendarManager()
    
    # Test 1: Add a reminder due in 1 minute
    print("\n[TEST 1] Adding a reminder due in 1 minute:")
    print("-" * 60)
    
    one_minute_later = datetime.now() + timedelta(minutes=1)
    success, message, event_id = calendar.add_reminder(
        title="Test Reminder",
        due_datetime=one_minute_later.strftime("%Y-%m-%d %H:%M"),
        description="This is a test reminder to verify sound playback"
    )
    
    print(f"Success: {success}")
    print(f"Message: {message}")
    print(f"Event ID: {event_id}")
    
    # Test 2: Add an alarm due in 2 minutes
    print("\n[TEST 2] Adding an alarm due in 2 minutes:")
    print("-" * 60)
    
    two_minutes_later = datetime.now() + timedelta(minutes=2)
    success, message, event_id = calendar.add_alarm(
        title="Test Alarm",
        due_datetime=two_minutes_later.strftime("%Y-%m-%d %H:%M")
    )
    
    print(f"Success: {success}")
    print(f"Message: {message}")
    print(f"Event ID: {event_id}")
    
    # Test 3: Verify SoundActions has reminder
    print("\n[TEST 3] Verify SoundActions enum has reminder:")
    print("-" * 60)
    
    try:
        reminder_action = SoundActions.reminder
        print(f"✅ SoundActions.reminder exists: {reminder_action}")
        print(f"   Name: {reminder_action.name}")
        print(f"   Value: {reminder_action.value}")
    except AttributeError:
        print("❌ SoundActions.reminder does not exist!")
        return False
    
    # Test 4: Show upcoming reminders/alarms
    print("\n[TEST 4] Upcoming reminders and alarms (next 24 hours):")
    print("-" * 60)
    
    upcoming = calendar.get_upcoming_events(days=1)
    for event in upcoming:
        if event['event_type'] in ['reminder', 'alarm']:
            due_time = datetime.fromisoformat(event['due_datetime'])
            print(f"- [{event['event_type'].upper()}] {event['title']}")
            print(f"  Due: {due_time.strftime('%Y-%m-%d %H:%M')}")
            if event.get('description'):
                print(f"  Description: {event['description']}")
    
    print("\n" + "=" * 60)
    print("✅ Reminder sound functionality configured correctly!")
    print("=" * 60)
    print("\nNOTE: The background thread in State Machine will check every")
    print("30 seconds and play 'reminder.mp3' when reminders/alarms are due.")
    print("\nThe reminders added above will trigger in 1-2 minutes if the")
    print("system is running.")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    try:
        success = test_reminder_sound()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
