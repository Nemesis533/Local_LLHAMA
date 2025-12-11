#!/usr/bin/env python3
"""
Validation script for Issue #10: Web Server Message Queue Error Handling
Checks that all queue operations have proper error handling and logging.
"""

import re
from pathlib import Path


def check_web_server_error_handling():
    """Validate Web_Server.py has comprehensive queue error handling."""

    web_server_file = Path("local_llhama/Web_Server.py")

    if not web_server_file.exists():
        print(f"❌ File not found: {web_server_file}")
        return False

    content = web_server_file.read_text()

    patterns = {
        # Queue initialization validation
        "queue_validation_action": r"if\s+not\s+self\.action_message_queue:",
        "queue_validation_web": r"if\s+not\s+self\.web_server_message_queue:",
        # Queue put with timeout
        "put_with_timeout": r"\.put\([^)]+,\s*timeout=\d+\.?\d*\)",
        # Queue get with timeout (already exists)
        "get_with_timeout": r"\.get\(timeout=\d+\.?\d*\)",
        # Error handling around queue operations
        "try_except_queue_put": r"try:.*?self\.action_message_queue\.put.*?except.*?as\s+e:",
        "try_except_emit": r"try:.*?self\.emit_messages.*?except.*?as\s+e:",
        "try_except_socketio_emit": r"try:.*?self\.socketio\.emit.*?except.*?as\s+e:",
        # Socket.IO emission error handling
        "emit_client_error_handling": r"for\s+sid\s+in\s+self\.connected_clients:.*?try:.*?self\.socketio\.emit.*?except",
        # Empty exception handling
        "empty_exception": r"except\s+Empty:",
        # AttributeError for queue issues
        "attribute_error": r"except\s+AttributeError\s+as\s+e:",
        # Message validation
        "message_validation": r"if\s+not\s+message:",
        "message_data_validation": r"if\s+message_data:",
        # Failed client cleanup
        "client_removal": r"clients_to_remove",
        "discard_failed_client": r"self\.connected_clients\.discard\(sid\)",
        # LogLevel usage for errors
        "loglevel_critical": r"LogLevel\.CRITICAL\.name",
        "loglevel_warning": r"LogLevel\.WARNING\.name",
        "loglevel_info": r"LogLevel\.INFO\.name",
        # Specific error messages
        "queue_not_initialized": r"queue not initialized",
        "failed_to_queue": r"Failed to queue",
        "failed_to_emit": r"Failed to emit",
        "message_queue_error": r"[Mm]essage queue error",
        # Monitor startup logging
        "monitor_startup": r"Starting message monitor",
        # Sleep on errors (backoff)
        "socketio_sleep": r"self\.socketio\.sleep\(",
    }

    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        results[name] = len(matches)
        if matches:
            print(f"✅ {name}: {len(matches)} instance(s)")
        else:
            print(f"❌ {name}: NOT FOUND")

    # Anti-patterns to check for
    anti_patterns = {
        "bare_put_no_timeout": r"\.put\([^)]+\)(?!\s*,\s*timeout)",  # put without timeout
        "bare_except": r"except:\s*$",  # bare except without Exception
    }

    print("\n=== Anti-pattern Check ===")
    anti_pattern_found = False
    for name, pattern in anti_patterns.items():
        # For bare_put, exclude the one with timeout
        if name == "bare_put_no_timeout":
            # Check for .put() calls without timeout parameter
            all_puts = re.findall(r"\.put\([^)]+\)", content)
            puts_without_timeout = [p for p in all_puts if "timeout" not in p]
            if puts_without_timeout:
                print(
                    f"⚠️  {name}: {len(puts_without_timeout)} instance(s) - {puts_without_timeout}"
                )
                anti_pattern_found = True
        else:
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                print(f"⚠️  {name}: {len(matches)} instance(s)")
                anti_pattern_found = True

    if not anti_pattern_found:
        print("✅ No anti-patterns detected")

    # Count LogLevel usage
    print("\n=== LogLevel Usage ===")
    loglevel_count = len(re.findall(r"LogLevel\.\w+\.name", content))
    print(f"Total LogLevel uses: {loglevel_count}")

    # Count try-except blocks
    print("\n=== Exception Handling ===")
    try_count = len(re.findall(r"\btry:", content))
    except_count = len(re.findall(r"\bexcept\s+\w+", content))
    print(f"Try blocks: {try_count}")
    print(f"Except blocks: {except_count}")

    # Summary
    print("\n=== Summary ===")
    total_patterns = len(patterns)
    found_patterns = sum(1 for count in results.values() if count > 0)
    print(f"Patterns found: {found_patterns}/{total_patterns}")

    # Minimum requirements
    requirements = {
        "Queue validation": results["queue_validation_action"] >= 1
        and results["queue_validation_web"] >= 1,
        "Put with timeout": results["put_with_timeout"] >= 1,
        "Get with timeout": results["get_with_timeout"] >= 1,
        "Try-except for put": results["try_except_queue_put"] >= 1,
        "Try-except for emit": results["try_except_emit"] >= 1,
        "Socket emission error handling": results["try_except_socketio_emit"] >= 1,
        "Empty exception handling": results["empty_exception"] >= 1,
        "Client removal on failure": results["client_removal"] >= 1,
        "LogLevel CRITICAL usage": results["loglevel_critical"] >= 5,
        "LogLevel WARNING usage": results["loglevel_warning"] >= 3,
        "Socket.IO sleep backoff": results["socketio_sleep"] >= 2,
    }

    print("\n=== Requirements Check ===")
    all_passed = True
    for req, passed in requirements.items():
        status = "✅" if passed else "❌"
        print(f"{status} {req}")
        if not passed:
            all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 60)
    print("Issue #10: Web Server Message Queue Error Handling")
    print("=" * 60)
    print()

    success = check_web_server_error_handling()

    print("\n" + "=" * 60)
    if success:
        print("✅ All validation checks PASSED")
    else:
        print("❌ Some validation checks FAILED")
    print("=" * 60)
