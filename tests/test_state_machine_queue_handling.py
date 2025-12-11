#!/usr/bin/env python3
"""
Test script to validate queue error handling in State_Machine.py
Tests timeout handling, Empty exceptions, and graceful degradation.
"""

import multiprocessing as mp
import sys
from unittest.mock import MagicMock, Mock, patch

# Mock all the heavy imports before importing State_Machine
sys.modules["torch"] = MagicMock()
sys.modules["transformers"] = MagicMock()
sys.modules["pyaudio"] = MagicMock()
sys.modules["pygame"] = MagicMock()
sys.modules["pygame.mixer"] = MagicMock()
sys.modules["pvporcupine"] = MagicMock()
sys.modules["struct"] = MagicMock()
sys.modules["wave"] = MagicMock()
sys.modules["faster_whisper"] = MagicMock()

# Mock the custom imports


class MockSoundPlayer:
    def play(self, action, volume=1.0):
        pass


class MockTTS:
    def __init__(self, voice_dir):
        pass

    def speak(self, text, lang):
        pass


class MockWakeWordListener:
    def __init__(self, noise_monitor):
        pass

    def listen_for_wake_word(self, queue):
        pass


class MockAudioRecorder:
    def __init__(self, noise_floor_monitor):
        pass

    def record_audio(self, transcriptor, noise_floor):
        return "test transcription with enough words"


class MockTranscriptor:
    def init_model(self, device):
        pass


class MockNoiseFloorMonitor:
    pass


# Patch the imports
sys.modules["local_llhama.Sound_And_Speech"] = Mock(
    SoundPlayer=MockSoundPlayer,
    TextToSpeech=MockTTS,
    WakeWordListener=MockWakeWordListener,
    AudioRecorderClass=MockAudioRecorder,
    AudioTranscriptionClass=MockTranscriptor,
    NoiseFloorMonitor=MockNoiseFloorMonitor,
    SoundActions=Mock(system_awake=1, system_error=2, action_closing=3),
)

from local_llhama.state_machine import State, StateMachineInstance


def test_transcription_queue_timeout():
    """Test that transcription queue timeout is handled gracefully"""
    print("\n[TEST 1] Testing transcription queue timeout handling...")

    # Create minimal mock objects
    mock_llm = Mock()
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    # Set state to PARSING_VOICE but don't put anything in transcription queue
    sm.state = State.PARSING_VOICE

    # Call command_worker - should timeout and return to LISTENING
    sm.command_worker()

    if sm.state == State.LISTENING:
        print("✅ PASSED: Transcription queue timeout handled correctly")
        return True
    else:
        print(f"❌ FAILED: Expected LISTENING state, got {sm.state}")
        return False


def test_command_queue_put_failure():
    """Test that command queue put failure is handled"""
    print("\n[TEST 2] Testing command queue put failure handling...")

    mock_llm = Mock()
    mock_llm.parse_with_llm = Mock(return_value={"commands": [{"test": "command"}]})
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    sm.state = State.PARSING_VOICE
    sm.transcription_queue.put("test transcription")

    # Mock the command queue to raise an exception
    original_put = sm.command_queue.put
    sm.command_queue.put = Mock(side_effect=Exception("Queue full"))

    # Call command_worker
    sm.command_worker()

    # Restore original
    sm.command_queue.put = original_put

    if sm.state == State.LISTENING:
        print("✅ PASSED: Command queue put failure handled correctly")
        return True
    else:
        print(f"❌ FAILED: Expected LISTENING state, got {sm.state}")
        return False


def test_speech_queue_timeout():
    """Test that speech queue timeout is handled"""
    print("\n[TEST 3] Testing speech queue timeout handling...")

    mock_llm = Mock()
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    # Set state to SPEAKING but don't put anything in speech queue
    sm.state = State.SPEAKING

    # Call speak - should timeout and return to LISTENING
    sm.speak()

    if sm.state == State.LISTENING:
        print("✅ PASSED: Speech queue timeout handled correctly")
        return True
    else:
        print(f"❌ FAILED: Expected LISTENING state, got {sm.state}")
        return False


def test_wake_word_queue_error():
    """Test that wake word queue errors are handled"""
    print("\n[TEST 4] Testing wake word queue error handling...")

    mock_llm = Mock()
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    sm.state = State.LISTENING

    # Mock result_queue to raise exception
    sm.result_queue.get = Mock(side_effect=Exception("Queue corrupted"))
    sm.result_queue.empty = Mock(return_value=False)

    # Call run - should handle error gracefully
    try:
        sm.run()
        print("✅ PASSED: Wake word queue error handled gracefully")
        return True
    except Exception as e:
        print(f"❌ FAILED: Unhandled exception: {e}")
        return False


def test_sound_queue_put_failure():
    """Test that sound queue put failure is handled"""
    print("\n[TEST 5] Testing sound queue put failure handling...")

    mock_llm = Mock()
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    # Mock sound_action_queue to raise exception
    sm.sound_action_queue.put = Mock(side_effect=Exception("Queue error"))

    # Call play_sound - should handle error gracefully without crashing
    try:
        sm.play_sound(1)  # Mock sound action
        print("✅ PASSED: Sound queue put failure handled gracefully")
        return True
    except Exception as e:
        print(f"❌ FAILED: Unhandled exception: {e}")
        return False


def test_command_queue_empty_in_send_commands():
    """Test that empty command queue in SEND_COMMANDS state is handled"""
    print("\n[TEST 6] Testing command queue empty in SEND_COMMANDS state...")

    mock_llm = Mock()
    mock_ha = Mock()
    action_queue = mp.Queue()
    web_queue = mp.Queue()

    with patch("local_llhama.State_Machine.threading.Thread"):
        sm = StateMachineInstance(
            command_llm=mock_llm,
            device="cpu",
            ha_client=mock_ha,
            base_path="/tmp",
            action_message_queue=action_queue,
            web_server_message_queue=web_queue,
        )

    # Set state to SEND_COMMANDS but command queue is empty
    sm.state = State.SEND_COMMANDS

    # Run the state machine
    sm.run()

    if sm.state == State.LISTENING:
        print("✅ PASSED: Empty command queue handled correctly")
        return True
    else:
        print(f"❌ FAILED: Expected LISTENING state, got {sm.state}")
        return False


def main():
    print("=" * 60)
    print("State Machine Queue Error Handling Tests")
    print("=" * 60)

    tests = [
        test_transcription_queue_timeout,
        test_command_queue_put_failure,
        test_speech_queue_timeout,
        test_wake_word_queue_error,
        test_sound_queue_put_failure,
        test_command_queue_empty_in_send_commands,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n✅ All queue error handling tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
