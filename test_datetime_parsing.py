#!/usr/bin/env python3
"""Quick test for improved datetime parsing."""

from local_llhama.auth.calendar_manager import CalendarManager
from datetime import datetime

calendar = CalendarManager()

test_cases = [
    "today at 19:00",
    "today at 7:00 PM",
    "today at 7pm",
    "tomorrow at 9:30",
    "tomorrow at 9:30 AM",
    "in 2 hours",
    "in 30 minutes",
    "in 3 days",
    "next week at 14:00",
    "2025-12-25 14:30",
]

print("Testing datetime parsing:\n")
for test in test_cases:
    success, msg, _ = calendar.add_reminder(f"Test: {test}", test)
    if success:
        print(f"✓ '{test}' -> {msg}")
    else:
        print(f"✗ '{test}' -> {msg}")
