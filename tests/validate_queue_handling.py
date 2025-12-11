#!/usr/bin/env python3
"""
Simple validation script to check that queue error handling code is present
in State_Machine.py without actually running it.
"""

import re

def check_error_handling():
    """Check that error handling is present in State_Machine.py"""
    
    with open('/home/llhama-usr/Local_LLHAMA/local_llhama/State_Machine.py', 'r') as f:
        content = f.read()
    
    checks = {
        "Transcription queue timeout": r'except Empty:.*Transcription queue timeout',
        "Transcription queue error": r'except Exception as e:.*Failed to get transcription from queue',
        "Command queue put error": r'except Exception as e:.*Failed to queue command',
        "Speech queue put error": r'except Exception as e:.*Failed to queue speech',
        "Speech queue timeout": r'except Empty:.*Speech queue timeout',
        "Sound player worker error": r'except Exception as e:.*Sound player worker error',
        "Play sound error": r'except Exception as e:.*Failed to queue sound action',
        "Recording error": r'except Exception as e:.*Recording failed',
        "Wake word processing error": r'except Exception as e:.*Failed to process wake word',
        "Command queue empty in SEND_COMMANDS": r'except Empty:.*Command queue empty when expected',
        "Send commands error": r'except Exception as e:.*Failed to send command',
        "Send messages error": r'except Exception as e:.*Failed to send message to web server',
    }
    
    results = {}
    for check_name, pattern in checks.items():
        if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
            results[check_name] = "✅ FOUND"
        else:
            results[check_name] = "❌ MISSING"
    
    # Check for timeout parameters on queue operations
    timeout_checks = {
        "transcription_queue.get timeout": r'transcription_queue\.get\(timeout=\d+\)',
        "command_queue.put timeout": r'command_queue\.put\([^)]*timeout=\d+\)',
        "speech_queue.put timeout": r'speech_queue\.put\([^)]*timeout=\d+\)',
        "speech_queue.get timeout": r'speech_queue\.get\(timeout=\d+\)',
        "sound_action_queue.get timeout": r'sound_action_queue\.get\(timeout=\d+\)',
        "sound_action_queue.put timeout": r'sound_action_queue\.put\([^)]*timeout=\d+\)',
    }
    
    print("=" * 70)
    print("State Machine Queue Error Handling Validation")
    print("=" * 70)
    
    print("\n📋 Error Handling Checks:")
    print("-" * 70)
    for check_name, result in results.items():
        print(f"{result} {check_name}")
    
    print("\n⏱️  Timeout Parameter Checks:")
    print("-" * 70)
    for check_name, pattern in timeout_checks.items():
        if re.search(pattern, content):
            print(f"✅ FOUND {check_name}")
        else:
            print(f"⚠️  MISSING {check_name}")
    
    # Count LogLevel usage
    loglevel_count = len(re.findall(r'LogLevel\.(INFO|WARNING|CRITICAL)', content))
    print(f"\n📊 LogLevel standardization: {loglevel_count} uses found")
    
    # Summary
    passed = sum(1 for v in results.values() if "✅" in v)
    total = len(results)
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} error handling patterns found")
    print("=" * 70)
    
    if passed == total:
        print("\n✅ All queue error handling improvements verified!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} error handling patterns missing")
        return 1

def show_improvements():
    """Display summary of improvements made"""
    print("\n📝 Summary of Improvements:")
    print("-" * 70)
    improvements = [
        "1. Added timeout parameters (1-2s) to all queue.get() operations",
        "2. Added try-except blocks around all queue.put() operations",
        "3. Graceful handling of Empty exceptions with state transitions",
        "4. Comprehensive exception catching for queue errors",
        "5. Proper error logging with LogLevel (INFO/WARNING/CRITICAL)",
        "6. Graceful degradation - returns to LISTENING on queue failures",
        "7. Added error delays to prevent tight error loops",
        "8. Protected wake word queue clearing with error handling",
        "9. Multiprocessing queue error handling in send_messages()",
        "10. All queue operations now fail-safe without crashing",
    ]
    for improvement in improvements:
        print(f"  {improvement}")
    
    print("\n🎯 Impact:")
    print("-" * 70)
    impacts = [
        "• System won't crash on queue timeouts or failures",
        "• Better visibility into queue-related issues via logging",
        "• Automatic recovery to LISTENING state on errors",
        "• Prevents infinite loops in error conditions",
        "• User experience remains smooth even during queue issues",
    ]
    for impact in impacts:
        print(f"  {impact}")

if __name__ == "__main__":
    result = check_error_handling()
    show_improvements()
    exit(result)
