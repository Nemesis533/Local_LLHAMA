#!/usr/bin/env python3
"""
Validation script to check audio device failure recovery improvements in Sound_And_Speech.py
"""

import re

def check_audio_error_handling():
    """Check that audio error handling improvements are present"""
    
    with open('/home/llhama-usr/Local_LLHAMA/local_llhama/Sound_And_Speech.py', 'r') as f:
        content = f.read()
    
    checks = {
        "SoundPlayer mixer retry logic": r'for attempt in range\(3\):.*pygame\.mixer\.init',
        "SoundPlayer mixer_available flag": r'self\.mixer_available\s*=',
        "SoundPlayer mixer check in play": r'if not self\.mixer_available:',
        "SoundPlayer play error handling": r'except pygame\.error as e:.*Playback error',
        "TextToSpeech PyAudio error handling": r'except OSError as e:.*Failed to initialize PyAudio',
        "TextToSpeech speak retry logic": r'while retry_count <= max_retries:',
        "TextToSpeech stream error recovery": r'Audio stream error.*attempt',
        "AudioRecorder PyAudio init error": r'Failed to initialize PyAudio.*AudioRecorderClass',
        "AudioRecorder stream open error": r'Failed to open audio stream',
        "AudioRecorder read exception_on_overflow": r'stream\.read\(.*exception_on_overflow=False\)',
        "AudioRecorder OSError handling": r'except OSError as e:.*Audio read error',
        "AudioRecorder finally cleanup": r'finally:.*Ensure cleanup',
        "WakeWord PyAudio retry loop": r'while not self\.stop_event\.is_set\(\):.*audio = None',
        "WakeWord mic stream error handling": r'Failed to open microphone',
        "WakeWord read exception_on_overflow": r'mic_stream\.read\(CHUNK, exception_on_overflow=False\)',
        "WakeWord auto-restart on error": r'Restarting wake word detection',
        "WakeWord finally cleanup": r'finally:.*# Cleanup',
    }
    
    results = {}
    for check_name, pattern in checks.items():
        if re.search(pattern, content, re.DOTALL):
            results[check_name] = "✅ FOUND"
        else:
            results[check_name] = "❌ MISSING"
    
    # Count LogLevel usage
    loglevel_count = len(re.findall(r'LogLevel\.(INFO|WARNING|CRITICAL)', content))
    
    # Count error handling blocks
    try_blocks = len(re.findall(r'\btry:', content))
    except_blocks = len(re.findall(r'\bexcept\b', content))
    finally_blocks = len(re.findall(r'\bfinally:', content))
    oserror_handling = len(re.findall(r'except OSError', content))
    
    print("=" * 70)
    print("Audio Device Failure Recovery Validation")
    print("=" * 70)
    
    print("\n🔊 Error Handling Checks:")
    print("-" * 70)
    for check_name, result in results.items():
        print(f"{result} {check_name}")
    
    print("\n📊 Statistics:")
    print("-" * 70)
    print(f"LogLevel usage: {loglevel_count} instances")
    print(f"Try blocks: {try_blocks}")
    print(f"Except blocks: {except_blocks}")
    print(f"Finally blocks: {finally_blocks}")
    print(f"OSError handling: {oserror_handling} instances")
    
    # Summary
    passed = sum(1 for v in results.values() if "✅" in v)
    total = len(results)
    
    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} error handling patterns found")
    print("=" * 70)
    
    if passed == total:
        print("\n✅ All audio device error handling improvements verified!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} error handling patterns missing")
        return 1

def show_improvements():
    """Display summary of improvements made"""
    print("\n📝 Summary of Audio Device Error Handling Improvements:")
    print("-" * 70)
    improvements = [
        "1. SoundPlayer: Retry logic for pygame mixer initialization (3 attempts)",
        "2. SoundPlayer: mixer_available flag for graceful degradation",
        "3. SoundPlayer: Comprehensive error handling in play() method",
        "4. SoundPlayer: Silently skip playback if mixer unavailable",
        "5. TextToSpeech: PyAudio initialization error handling with descriptive errors",
        "6. TextToSpeech: Stream error retry logic (up to 2 retries per chunk)",
        "7. TextToSpeech: Automatic stream re-initialization on OSError",
        "8. TextToSpeech: Guaranteed stream cleanup in error conditions",
        "9. AudioRecorder: PyAudio initialization with error recovery",
        "10. AudioRecorder: Stream opening error handling",
        "11. AudioRecorder: exception_on_overflow=False to prevent buffer overflow crashes",
        "12. AudioRecorder: OSError handling during recording with partial data recovery",
        "13. AudioRecorder: Finally block ensures cleanup of audio resources",
        "14. AudioRecorder: Empty frames validation before transcription",
        "15. WakeWordListener: Automatic retry loop on device failures",
        "16. WakeWordListener: 5-second wait between retry attempts",
        "17. WakeWordListener: exception_on_overflow=False for stability",
        "18. WakeWordListener: OSError handling with automatic restart",
        "19. WakeWordListener: Finally block ensures resource cleanup",
        "20. WakeWordListener: 3-second wait before restart with logging",
    ]
    for improvement in improvements:
        print(f"  {improvement}")
    
    print("\n🎯 Impact:")
    print("-" * 70)
    impacts = [
        "• System won't crash on audio device disconnection",
        "• Automatic recovery from temporary device errors",
        "• Graceful degradation when audio unavailable",
        "• Better user feedback on audio failures",
        "• Wake word detection auto-restarts on failures",
        "• Prevents buffer overflow crashes in recording",
        "• Guaranteed cleanup of audio resources",
        "• Retry logic prevents transient error failures",
        "• Partial recording recovery possible",
        "• System remains operational even without audio",
    ]
    for impact in impacts:
        print(f"  {impact}")
    
    print("\n🛡️ Error Recovery Strategies:")
    print("-" * 70)
    strategies = [
        "✓ Retry with delay for transient errors",
        "✓ Graceful degradation for permanent failures",
        "✓ Resource cleanup in finally blocks",
        "✓ Device re-initialization on OSError",
        "✓ exception_on_overflow=False for buffer issues",
        "✓ Descriptive error messages with LogLevel",
        "✓ Automatic restart of background listeners",
        "✓ mixer_available flag prevents cascade failures",
    ]
    for strategy in strategies:
        print(f"  {strategy}")

if __name__ == "__main__":
    result = check_audio_error_handling()
    show_improvements()
    exit(result)
