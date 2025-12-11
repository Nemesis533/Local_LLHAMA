"""
Core State Definitions

This module defines the core state enumeration used throughout the state machine.
Separating the state enum makes it easier to import and reference states without
circular dependencies.
"""

from enum import Enum


class State(Enum):
    """
    Enumeration for various states of the voice assistant state machine.

    States:
    - LOADING: Initial state during system startup
    - LISTENING: Waiting for wake word detection
    - RECORDING: Recording user voice input
    - PARSING_VOICE: Processing voice transcription
    - GENERATING: LLM is generating a response
    - SPEAKING: System is playing audio response
    - SEND_COMMANDS: Sending commands to Home Assistant
    - NO_COMMANDS: No commands were found in the user input
    - ERROR: Error state requiring recovery
    """

    LOADING = "LOADING"
    LISTENING = "LISTENING"
    RECORDING = "RECORDING"
    GENERATING = "GENERATING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    PARSING_VOICE = "PARSING_VOICE"
    SEND_COMMANDS = "SEND_COMMANDS"
    NO_COMMANDS = "NO_COMMANDS"
