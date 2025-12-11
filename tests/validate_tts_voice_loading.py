#!/usr/bin/env python3
"""
Validation script to check TTS voice file loading error handling improvements
"""

import re


def check_tts_voice_loading():
    """Check that TTS voice loading error handling improvements are present"""

    with open(
        "/home/llhama-usr/Local_LLHAMA/local_llhama/Sound_And_Speech.py", "r"
    ) as f:
        content = f.read()

    checks = {
        "Voice directory validation in __init__": r"Voice directory not found.*voice_dir",
        "Directory type check": r"Voice path is not a directory",
        "Voice file scanning": r"glob\(.*\.onnx.*\)",
        "Voice file count logging": r"Found.*voice file",
        "Voice caching dictionary": r"self\.voice_cache\s*=\s*\{\}",
        "Current language tracking": r"self\.current_lang",
        "Cache check in select_voice": r"if lang_tag in self\.voice_cache:",
        "Already loaded check": r"if lang_tag == self\.current_lang",
        "Unsupported language error": r"Unsupported language tag.*Supported:",
        "Glob search error handling": r"Error searching for voice files",
        "No voice found with available list": r"Available voices:",
        "Voice file exists check": r"if not voice_file\.exists\(\):",
        "Voice file type check": r"if not voice_file\.is_file\(\):",
        "Voice file size check": r"voice_file\.stat\(\)\.st_size",
        "Empty file detection": r"Voice file is empty",
        "Small file warning": r"Voice file suspiciously small",
        "PiperVoice.load error handling": r"except.*Failed to load voice file",
        "FileNotFoundError handling": r"except FileNotFoundError.*Voice file not found during load",
        "PermissionError handling": r"except PermissionError.*Permission denied reading voice file",
        "Voice load success logging": r"Successfully loaded voice",
        "Cache usage logging": r"Using cached voice",
    }

    results = {}
    for check_name, pattern in checks.items():
        if re.search(pattern, content, re.DOTALL):
            results[check_name] = "✅ FOUND"
        else:
            results[check_name] = "❌ MISSING"

    # Count LogLevel usage in TextToSpeech class
    tts_section = re.search(r"class TextToSpeech:.*?(?=class\s|\Z)", content, re.DOTALL)
    if tts_section:
        tts_content = tts_section.group(0)
        loglevel_count = len(
            re.findall(r"LogLevel\.(INFO|WARNING|CRITICAL)", tts_content)
        )
    else:
        loglevel_count = 0

    # Count error handling
    tts_try_blocks = len(re.findall(r"\btry:", tts_content)) if tts_section else 0
    tts_except_blocks = (
        len(re.findall(r"\bexcept\b", tts_content)) if tts_section else 0
    )

    print("=" * 70)
    print("TTS Voice File Loading Error Handling Validation")
    print("=" * 70)

    print("\n🎤 Voice Loading Checks:")
    print("-" * 70)
    for check_name, result in results.items():
        print(f"{result} {check_name}")

    print("\n📊 Statistics:")
    print("-" * 70)
    print(f"LogLevel usage in TextToSpeech: {loglevel_count} instances")
    print(f"Try blocks in TextToSpeech: {tts_try_blocks}")
    print(f"Except blocks in TextToSpeech: {tts_except_blocks}")

    # Summary
    passed = sum(1 for v in results.values() if "✅" in v)
    total = len(results)

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} error handling patterns found")
    print("=" * 70)

    if passed == total:
        print("\n✅ All TTS voice loading error handling improvements verified!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} error handling patterns missing")
        return 1


def show_improvements():
    """Display summary of improvements made"""
    print("\n📝 Summary of TTS Voice Loading Improvements:")
    print("-" * 70)
    improvements = [
        "1. Voice directory validation in __init__ (exists, is_dir)",
        "2. Voice file scanning with error handling",
        "3. Voice file count logging for debugging",
        "4. Voice caching by language to avoid reload",
        "5. Current language tracking to skip redundant loads",
        "6. Cache hit detection with logging",
        "7. Already-loaded voice detection",
        "8. Unsupported language validation with suggestions",
        "9. Error handling for glob search operations",
        "10. List available voices when requested voice not found",
        "11. Voice file existence validation",
        "12. Voice file type validation (is_file)",
        "13. Voice file size checking",
        "14. Empty voice file detection",
        "15. Suspiciously small file warning (< 1KB)",
        "16. PiperVoice.load() error handling",
        "17. FileNotFoundError specific handling",
        "18. PermissionError specific handling",
        "19. Generic exception catching for voice load",
        "20. Success logging for loaded voices",
        "21. Cache storage after successful load",
    ]
    for improvement in improvements:
        print(f"  {improvement}")

    print("\n🎯 Impact:")
    print("-" * 70)
    impacts = [
        "• System won't crash on missing voice files",
        "• Clear error messages for voice file issues",
        "• Voice caching improves performance",
        "• Helpful debugging info (available voices listed)",
        "• Validates file integrity before loading",
        "• Prevents loading corrupted/empty files",
        "• Better user feedback on unsupported languages",
        "• Permission errors clearly identified",
        "• Avoids redundant voice reloading",
        "• Directory validation prevents startup errors",
    ]
    for impact in impacts:
        print(f"  {impact}")

    print("\n🔍 Validation Strategies:")
    print("-" * 70)
    strategies = [
        "✓ Directory existence and type validation",
        "✓ File existence and type validation",
        "✓ File size and integrity checks",
        "✓ Language tag validation with suggestions",
        "✓ Caching to prevent redundant loads",
        "✓ Descriptive error messages with context",
        "✓ Logging at appropriate LogLevels",
        "✓ Available voice file enumeration",
        "✓ Permission error detection",
        "✓ Empty/corrupted file detection",
    ]
    for strategy in strategies:
        print(f"  {strategy}")


if __name__ == "__main__":
    result = check_tts_voice_loading()
    show_improvements()
    exit(result)
