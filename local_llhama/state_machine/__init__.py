"""
State Machine Module

This module provides a refactored state machine with clean separation of concerns:
- core_state: State enum and core state definitions
- orchestrator: StateMachineInstance coordinator (main facade)
- workers: Worker thread implementations

The state machine coordinates audio input/output, command processing, and
interactions with Home Assistant through specialized component managers.

Usage:
    from local_llhama.state_machine import StateMachineInstance, State

    # Initialize the state machine
    state_machine = StateMachineInstance(
        command_llm=llm_client,
        ha_client=ha_client,
        ...
    )

    # Run the main loop
    while True:
        state_machine.run()
"""

from .core_state import State
from .orchestrator import StateMachineInstance

__all__ = ["State", "StateMachineInstance"]
