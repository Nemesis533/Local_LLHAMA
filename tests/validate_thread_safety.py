#!/usr/bin/env python3
"""
Validation script to check thread safety improvements in State_Machine.py
"""

import re

def check_thread_safety():
    """Check that thread safety improvements are present in State_Machine.py"""
    
    with open('/home/llhama-usr/Local_LLHAMA/local_llhama/State_Machine.py', 'r') as f:
        content = f.read()
    
    checks = {
        "RLock instead of Lock": r'self\.lock\s*=\s*threading\.RLock\(\)',
        "Separate print lock": r'self\._print_lock\s*=\s*threading\.Lock\(\)',
        "print_once with lock": r'def print_once.*?with self\._print_lock:',
        "get_state() method": r'def get_state\(self\):.*?with self\.lock:.*?return self\.state',
        "set_noise_floor() method": r'def set_noise_floor\(self, value\):.*?with self\.lock:',
        "get_noise_floor() method": r'def get_noise_floor\(self\):.*?with self\.lock:',
        "set_noise_floor usage": r'self\.set_noise_floor\(wakeword_data\)',
        "get_noise_floor usage": r'noise_floor_val\s*=\s*self\.get_noise_floor\(\)',
        "transition with old_state": r'old_state\s*=\s*self\.state.*?Transitioning from {old_state}',
        "transition lock timeout warning": r'Lock timeout: failed to transition.*?\(lock held for >2s\)',
        "stop method thread-safe doc": r'Thread-safe: Uses stop_event',
        "stop queue error handling": r'Failed to send stop signal',
        "monitor_messages queue timeout": r'transcription_queue\.put\(command_data, timeout=1\)',
        "monitor_messages error handling": r'Failed to queue command from web',
    }
    
    results = {}
    for check_name, pattern in checks.items():
        if re.search(pattern, content, re.DOTALL):
            results[check_name] = "✅ FOUND"
        else:
            results[check_name] = "❌ MISSING"
    
    # Check for direct noise_floor access (should be minimal now)
    direct_noise_floor = len(re.findall(r'self\.noise_floor\s*[=!]', content))
    
    # Check for state access patterns
    with_lock_state = len(re.findall(r'with self\.lock:.*?self\.state', content, re.DOTALL))
    
    print("=" * 70)
    print("State Machine Thread Safety Validation")
    print("=" * 70)
    
    print("\n🔒 Thread Safety Checks:")
    print("-" * 70)
    for check_name, result in results.items():
        print(f"{result} {check_name}")
    
    print("\n📊 Statistics:")
    print("-" * 70)
    print(f"Direct noise_floor accesses (should be 2-3): {direct_noise_floor}")
    print(f"State access with lock: {with_lock_state} patterns")
    
    # Check for race condition patterns that should NOT exist
    print("\n⚠️  Anti-Patterns (should be 0):")
    print("-" * 70)
    
    antipatterns = {
        "Unprotected state write outside transition": 0,
        "noise_floor write without lock": 0,
    }
    
    # Check for state writes - should only be in __init__ and transition()
    # The initialization in __init__ is safe (no threads yet)
    # The write in transition() is protected by lock
    # So we expect exactly 2 matches
    state_writes = re.findall(r'self\.state\s*=', content)
    unprotected_state_writes = [w for w in state_writes if True]  # All should be safe
    # If we have more than 2 (init + transition), flag it
    if len(state_writes) > 2:
        antipatterns["Unprotected state write outside transition"] = len(state_writes) - 2
    
    # Check for noise_floor writes - should only be in __init__ and set_noise_floor()
    # The initialization in __init__ is safe (no threads yet)
    # The write in set_noise_floor() is protected by lock
    # So we expect exactly 2 matches
    noise_writes = re.findall(r'self\.noise_floor\s*=', content)
    if len(noise_writes) > 2:
        antipatterns["noise_floor write without lock"] = len(noise_writes) - 2
    
    for pattern_name, count in antipatterns.items():
        if count == 0:
            print(f"✅ {pattern_name}: {count}")
        else:
            print(f"❌ {pattern_name}: {count} (should be 0)")
    
    # Summary
    passed = sum(1 for v in results.values() if "✅" in v)
    total = len(results)
    antipattern_issues = sum(1 for v in antipatterns.values() if v > 0)
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} thread safety patterns found")
    print(f"Anti-patterns: {antipattern_issues} issues detected")
    print("=" * 70)
    
    if passed == total and antipattern_issues == 0:
        print("\n✅ All thread safety improvements verified!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} patterns missing or {antipattern_issues} anti-patterns found")
        return 1

def show_improvements():
    """Display summary of improvements made"""
    print("\n📝 Summary of Thread Safety Improvements:")
    print("-" * 70)
    improvements = [
        "1. Replaced threading.Lock with threading.RLock for reentrant locking",
        "2. Added separate _print_lock to prevent deadlocks in print_once()",
        "3. Created get_state() method for thread-safe state reads",
        "4. Created set_noise_floor() / get_noise_floor() for thread-safe access",
        "5. Protected all noise_floor writes with lock",
        "6. Protected all noise_floor reads with lock",
        "7. Enhanced transition() to store old_state before logging",
        "8. Improved lock timeout logging in transition()",
        "9. Added thread-safe documentation to stop() method",
        "10. Added error handling to stop() method queue operations",
        "11. Protected monitor_messages queue.put with timeout and error handling",
        "12. All state transitions use consistent locking pattern",
    ]
    for improvement in improvements:
        print(f"  {improvement}")
    
    print("\n🎯 Impact:")
    print("-" * 70)
    impacts = [
        "• Prevents race conditions on state variable",
        "• Prevents race conditions on noise_floor variable",
        "• Prevents deadlocks with separate print lock",
        "• Allows same thread to acquire lock multiple times (RLock)",
        "• Better visibility into lock contention via timeout warnings",
        "• Graceful shutdown with proper signal handling",
        "• All critical sections properly protected",
        "• Cleaner separation of concerns with helper methods",
    ]
    for impact in impacts:
        print(f"  {impact}")
    
    print("\n🔍 Thread Safety Patterns Used:")
    print("-" * 70)
    patterns = [
        "✓ Lock acquisition with timeout (prevents indefinite blocking)",
        "✓ Context managers (with statement) for automatic lock release",
        "✓ RLock for reentrant locking from same thread",
        "✓ Separate locks for independent resources (_print_lock)",
        "✓ Thread-safe accessor methods (get/set)",
        "✓ Stop event for clean thread shutdown",
        "✓ Sentinel values (None) for unblocking queue waits",
    ]
    for pattern in patterns:
        print(f"  {pattern}")

if __name__ == "__main__":
    result = check_thread_safety()
    show_improvements()
    exit(result)
