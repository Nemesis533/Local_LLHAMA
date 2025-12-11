#!/usr/bin/env python3
"""
Validation script for Issues #13, #14, #15
Checks comprehensive error handling improvements across LLM_Handler, System_Controller, and Settings_Loader
"""

import re
from pathlib import Path

def check_llm_handler():
    """Validate Issue #13: LLM Handler error handling"""
    print("="*80)
    print("ISSUE #13: LLM Handler Tokenizer/Model Error Recovery")
    print("="*80)
    
    file_path = Path("local_llhama/LLM_Handler.py")
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False
    
    content = file_path.read_text()
    
    patterns = {
        # parse_with_llm improvements
        "Empty transcription check": r"if not transcription or not transcription\.strip\(\):",
        "Model/tokenizer loaded check": r"if self\.model is None or self\.tokenizer is None:",
        "Prompt guard error handling": r"except Exception as e:.*Prompt guard check failed",
        "Build prompt error handling": r"except Exception as e:.*Failed to build prompt",
        "Tokenization error handling": r"except Exception as e:.*Tokenization failed",
        "Tokenization with truncation": r"truncation=True",
        "Tokenization with max_length": r"max_length=\d+",
        "Stopping criteria error handling": r"except Exception as e:.*Failed to setup stopping criteria",
        "CUDA OOM handling during inference": r"except torch\.cuda\.OutOfMemoryError.*CUDA OOM",
        "Runtime error during inference": r"except RuntimeError.*Runtime error during inference",
        "Generic inference error": r"except Exception as e:.*Model inference failed",
        "Decode error handling": r"except Exception as e:.*Failed to decode output",
        "Response extraction error": r"except Exception as e:.*Failed to extract response",
        "JSON structure validation": r"if not isinstance\(parsed_output, dict\)",
        "Commands key validation": r'if "commands" not in parsed_output',
        "Nested JSON decode error": r"except json\.JSONDecodeError.*JSON decode error",
        "JSON extraction error": r"except Exception as e:.*Failed to extract/parse JSON",
        
        # PromptGuard is_safe improvements
        "PromptGuard model check": r"if self\.model is None or self\.tokenizer is None:.*defaulting to safe",
        "PromptGuard empty input check": r"if not user_input or not user_input\.strip\(\):.*treating as safe",
        "PromptGuard build prompt error": r"except Exception as e:.*Failed to build prompt.*return True",
        "PromptGuard tokenization error": r"except Exception as e:.*Tokenization failed.*return True",
        "PromptGuard CUDA OOM": r"except torch\.cuda\.OutOfMemoryError.*CUDA OOM.*return True",
        "PromptGuard runtime error": r"except RuntimeError.*Runtime error in safety check.*return True",
        "PromptGuard probability extraction": r"except \(IndexError, ValueError\).*Failed to extract probabilities",
        
        # OllamaClient improvements
        "Ollama empty message check": r"if not user_message or not user_message\.strip\(\):",
        "Ollama RequestException": r"except requests\.exceptions\.RequestException",
        "Ollama status code logging": r"if hasattr\(e\.response, 'status_code'\)",
        "Ollama response parse error": r"except Exception as e:.*Failed to parse response",
        "Ollama response keys logging": r'list\(data\.keys\(\)\)',
        "Ollama response extraction error": r"except Exception as e:.*Failed to extract response",
        "Ollama structure validation": r"if not isinstance\(parsed, dict\)",
        "Ollama parse error handling": r"except Exception as e:.*Unexpected error parsing output",
    }
    
    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        results[name] = len(matches) > 0
        status = "✅" if results[name] else "❌"
        print(f"{status} {name}")
    
    # Count statistics
    loglevel_count = len(re.findall(r'LogLevel\.(INFO|WARNING|CRITICAL)', content))
    try_blocks = len(re.findall(r'\btry:', content))
    except_blocks = len(re.findall(r'\bexcept\b', content))
    
    print(f"\n📊 Statistics:")
    print(f"LogLevel usage: {loglevel_count}")
    print(f"Try blocks: {try_blocks}")
    print(f"Except blocks: {except_blocks}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\n✅ Passed: {passed}/{total} checks")
    return passed == total


def check_system_controller():
    """Validate Issue #14: System Controller error handling"""
    print("\n" + "="*80)
    print("ISSUE #14: System Controller Subprocess & Resource Management")
    print("="*80)
    
    file_path = Path("local_llhama/System_Controller.py")
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False
    
    content = file_path.read_text()
    
    patterns = {
        # check_mic_volume improvements
        "pactl timeout parameter": r"subprocess\.run\(.*timeout=\d+",
        "pactl returncode check": r"if result\.returncode != 0:",
        "pactl stderr logging": r"if result\.stderr:",
        "pactl volume not found warning": r"if not volume_found:",
        "pactl TimeoutExpired": r"except subprocess\.TimeoutExpired:",
        "pactl FileNotFoundError": r"except FileNotFoundError:.*pactl command not found",
        
        # setup_audio improvements
        "setup_audio timeout": r"timeout=\d+",
        "setup_audio returncode check": r"if result\.returncode != 0:.*Failed to set audio volume",
        "setup_audio success logging": r"Audio volume set successfully",
        "setup_audio timeout error": r"except subprocess\.TimeoutExpired:.*Audio setup command timed out",
        "setup_audio file not found": r"except FileNotFoundError:.*pactl not found",
        "setup_audio continue message": r"Continuing without audio",
        
        # unload_model improvements
        "unload_model None check": r"if model is None:",
        "unload_model hasattr check": r"if hasattr\(model, \"model\"\) and model\.model is not None:",
        "unload_model del error": r"except Exception as e:.*Failed to delete model",
        "unload_model CUDA available check": r"if torch\.cuda\.is_available\(\):",
        "unload_model CUDA synchronize": r"torch\.cuda\.synchronize\(\)",
        "unload_model CUDA RuntimeError": r"except RuntimeError.*CUDA cache clear failed",
        "unload_model gc error": r"except Exception as e:.*Garbage collection failed",
        
        # start_system improvements
        "start_system settings try-except": r"try:.*loader = self\.setup_settings\(\).*except Exception as e:.*Failed to load settings",
        "start_system HA try-except": r"try:.*ha_client = self\.setup_home_assistant.*except Exception as e:.*Failed to initialize Home Assistant",
        "start_system HA continue": r"Continuing without Home Assistant",
        "start_system prompt guard cleanup": r"try:.*self\.unload_model\(self\.command_llm\.prompt_guard\).*except",
        "start_system LLM cleanup error": r"Error during LLM cleanup",
        "start_system LLM None check": r"if self\.command_llm is None:",
        "start_system LLM traceback": r"import traceback.*traceback\.print_exc\(\)",
        "start_system state machine stop": r"try:.*self\.state_machine\.stop\(\).*except",
        "start_system state machine None check": r"if self\.state_machine is None:",
        "start_system audio error": r"except Exception as e:.*Audio setup failed",
        "start_system settings error": r"except Exception as e:.*Failed to apply additional settings",
        "start_system return False": r"return False",
        "start_system return True": r"return True",
    }
    
    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        results[name] = len(matches) > 0
        status = "✅" if results[name] else "❌"
        print(f"{status} {name}")
    
    # Count statistics
    loglevel_count = len(re.findall(r'LogLevel\.(INFO|WARNING|CRITICAL)', content))
    try_blocks = len(re.findall(r'\btry:', content))
    except_blocks = len(re.findall(r'\bexcept\b', content))
    
    print(f"\n📊 Statistics:")
    print(f"LogLevel usage: {loglevel_count}")
    print(f"Try blocks: {try_blocks}")
    print(f"Except blocks: {except_blocks}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\n✅ Passed: {passed}/{total} checks")
    return passed == total


def check_settings_loader():
    """Validate Issue #15: Settings Loader error handling"""
    print("\n" + "="*80)
    print("ISSUE #15: Settings Loader File I/O Error Handling")
    print("="*80)
    
    file_path = Path("local_llhama/Settings_Loader.py")
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return False
    
    content = file_path.read_text()
    
    patterns = {
        # load() improvements
        "File exists check": r"if not os\.path\.exists\(self\.settings_file\):",
        "Is file check": r"if not os\.path\.isfile\(self\.settings_file\):",
        "Read permission check": r"if not os\.access\(self\.settings_file, os\.R_OK\):",
        "File size check": r"file_size = os\.path\.getsize\(self\.settings_file\)",
        "Empty file check": r"if file_size == 0:",
        "Large file warning": r"elif file_size > .* # \d+MB",
        "UTF-8 encoding": r"open\(.*encoding='utf-8'\)",
        "JSONDecodeError handling": r"except json\.JSONDecodeError as e:",
        "JSON error line/column": r"Line {e\.lineno}, column {e\.colno}",
        "Data type validation": r"if not isinstance\(self\.data, dict\):",
        "Empty data warning": r"if len\(self\.data\) == 0:",
        "FileNotFoundError catch": r"except FileNotFoundError as e:",
        "PermissionError catch": r"except PermissionError as e:",
        "File permissions advice": r"ls -l",
        "Generic load exception": r"except Exception as e:.*Unexpected error loading settings",
        
        # load_llm_models() improvements
        "Ollama IP validation": r"if not ollama_ip:.*OLLAMA_IP not configured",
        "Ollama port validation": r"if ':' not in ollama_ip:",
        "Ollama default port": r'ollama_ip = f.*:11434',
        "Ollama model validation": r"if not self\.ollama_model or not self\.ollama_model\.strip\(\):",
        "Ollama client exception": r"except Exception as e:.*Failed to create Ollama client",
        "Local LLM name validation": r"if not self\.command_llm_name or not self\.command_llm_name\.strip\(\):",
        "Base model path check": r"if not self\.base_model_path or not os\.path\.exists\(self\.base_model_path\):",
        "LLM loading exception": r"except Exception as e:.*Failed to load command LLM",
        "Model load return check": r"if not command_llm\.load_model",
        
        # apply() improvements
        "Apply objects type check": r"if not isinstance\(objects, list\):",
        "Apply None object check": r"if obj is None:",
        "Apply config dict check": r"if not isinstance\(class_config, dict\):",
        "Apply info dict check": r"if not isinstance\(info, dict\):",
        "Apply type None check": r"if expected_type is None:",
        "Apply ValueError catch": r"except ValueError as e:",
        "Apply TypeError catch": r"except TypeError as e:",
        "Apply statistics logging": r"Applied .* setting.*error",
        
        # cast_value() improvements
        "cast_value type validation": r"if type_str is None or not isinstance\(type_str, str\):",
        "cast_value type strip": r"type_str = type_str\.strip\(\)\.lower\(\)",
        "cast_value None to int": r"if value is None:.*Cannot convert None to int",
        "cast_value None to bool": r"if value is None:.*return False",
        "cast_value None to str": r"if value is None:.*return \"\"",
        "cast_value None to list": r"if value is None:.*return \[\]",
        "cast_value bool 'on'": r'"on"',
        "cast_value empty string list": r"if not value\.strip\(\):.*return \[\]",
        "cast_value type name in error": r"type\(value\).__name__",
        "cast_value exception chain": r"from e",
    }
    
    results = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        results[name] = len(matches) > 0
        status = "✅" if results[name] else "❌"
        print(f"{status} {name}")
    
    # Count statistics
    try_blocks = len(re.findall(r'\btry:', content))
    except_blocks = len(re.findall(r'\bexcept\b', content))
    valueerror_count = len(re.findall(r'raise ValueError', content))
    
    print(f"\n📊 Statistics:")
    print(f"Try blocks: {try_blocks}")
    print(f"Except blocks: {except_blocks}")
    print(f"ValueError raises: {valueerror_count}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\n✅ Passed: {passed}/{total} checks")
    return passed == total


if __name__ == "__main__":
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "Issues #13, #14, #15 Validation" + " "*27 + "║")
    print("╚" + "="*78 + "╝")
    print()
    
    results = []
    results.append(("Issue #13", check_llm_handler()))
    results.append(("Issue #14", check_system_controller()))
    results.append(("Issue #15", check_settings_loader()))
    
    print("\n" + "="*80)
    print("OVERALL SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL ISSUES VALIDATED SUCCESSFULLY!")
    else:
        print("⚠️  SOME ISSUES HAVE MISSING PATTERNS")
    print("="*80)
