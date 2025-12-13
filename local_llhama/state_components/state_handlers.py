"""
State Handlers Component

Contains all state handling logic for the state machine.
Each state has its own dedicated handler method.
"""

import time
from queue import Empty

from ..audio_output import SoundActions
from ..error_handler import ErrorHandler
from ..ollama import OllamaClient
from ..shared_logger import LogLevel


class StateHandlers:
    """
    @brief Encapsulates all state handling logic for cleaner separation of concerns.
    """

    def __init__(self, state_machine):
        """
        Initialize state handlers with reference to the main state machine.

        @param state_machine: Reference to the StateMachineInstance
        """
        self.sm = state_machine
        self.log_prefix = state_machine.class_prefix_message

    # ===============================
    # State Handler Methods
    # ===============================

    def handle_listening(self):
        """
        @brief Handle the LISTENING state.
        """
        # Ensure wake word detection is resumed
        self.sm.audio_manager.resume_wake_word()
        self.sm.state_manager.print_once("Listening for input...", end="\r")

    @ErrorHandler.handle_with_callback(
        "[StateMachine]",
        callback=lambda e: None,  # Just log, transition handled after decorator
        context="Recording",
    )
    def handle_recording(self):
        """
        @brief Handle the RECORDING state.
        """
        self.sm.state_manager.print_once("Recording state active.")
        self.sm.play_sound(SoundActions.system_awake)

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Recording...")
        self.sm.audio_manager.pause_wake_word()

        transcription = self.sm.audio_manager.record_and_transcribe()
        transcription_words = len(str.split(transcription, " "))

        if transcription_words > 4:
            success = self.sm.queue_manager.put_safe(
                self.sm.queue_manager.transcription_queue,
                transcription,
                log_prefix=self.log_prefix,
            )
            if success:
                self.sm.state_manager.transition(self.sm.State.PARSING_VOICE)
                return
        else:
            print(
                f"{self.log_prefix} [{LogLevel.INFO.name}] Transcription only had {transcription_words} words, returning to listening"
            )
        self.sm.state_manager.transition(self.sm.State.LISTENING)

    def handle_parsing_voice(self):
        """
        @brief Handle the PARSING_VOICE state.
        """
        self.sm.state_manager.print_once("Generating state active.")
        self._command_worker()

    def handle_send_commands(self):
        """
        @brief Handle the SEND_COMMANDS state.
        """
        self.sm.state_manager.print_once("Sending commands to HA client.")

        try:
            command = self.sm.queue_manager.command_queue.get_nowait()
            language = command.get("language", "en")

            command_result = self.sm.ha_client.send_commands(command)

            if command_result:
                # Check if any results are simple functions
                has_simple_function = any(
                    result.get("type") == "simple_function"
                    for result in command_result
                    if isinstance(result, dict)
                )

                if has_simple_function:
                    self._handle_simple_function_result(command_result, language)
                else:
                    # Pure HA commands: just play success sound, no verbal feedback
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] HA command(s) executed successfully: {command_result}"
                    )
                    message = f"{self.log_prefix} [HA Command Result]: {command_result}"
                    client_id = getattr(self.sm, "client_id", None)
                    self.sm.message_handler.send_to_web_server(
                        message, client_id=client_id
                    )
                    self.sm.play_sound(SoundActions.system_awake)
                    self.sm.state_manager.transition(self.sm.State.LISTENING)
            else:
                self.sm.play_sound(SoundActions.system_awake)
                self.sm.state_manager.transition(self.sm.State.LISTENING)

        except Empty:
            print(
                f"{self.log_prefix} [{LogLevel.WARNING.name}] Command queue empty when expected, returning to LISTENING"
            )
            self.sm.state_manager.transition(self.sm.State.LISTENING)
        except Exception as e:
            print(
                f"{self.log_prefix} [{LogLevel.CRITICAL.name}] Failed to send command: {type(e).__name__}: {e}"
            )
            self.sm.state_manager.transition(self.sm.State.LISTENING)

    def handle_speaking(self):
        """
        @brief Handle the SPEAKING state.
        """
        self.sm.state_manager.print_once("Speaking state active.")

        print(f"{self.log_prefix} [{LogLevel.INFO.name}] Speaking response...")
        self.sm.audio_manager.pause_wake_word()

        transcription = self.sm.queue_manager.get_safe(
            self.sm.queue_manager.speech_queue, timeout=2, log_prefix=self.log_prefix
        )

        if transcription:
            with ErrorHandler.catch_and_log(
                self.log_prefix, context="Speaking", suppress=True
            ):
                self.sm.audio_manager.speak_text(transcription[0], transcription[1])
                time.sleep(0.3)  # delay for more natural interactions
                if not isinstance(self.sm.command_llm, OllamaClient):
                    self.sm.audio_manager.sound_player.play(SoundActions.action_closing)

        self.sm.state_manager.transition(self.sm.State.LISTENING)

    def handle_error(self):
        """
        @brief Handle the ERROR state.
        """
        self.sm.state_manager.print_once("Error state active.")
        print(f"{self.log_prefix} [{LogLevel.INFO.name}] An error occurred.")
        self.sm.audio_manager.sound_player.play(SoundActions.system_error)
        time.sleep(2)
        self.sm.state_manager.transition(self.sm.State.LISTENING)

    def handle_no_commands(self):
        """
        @brief Handle the NO_COMMANDS state.
        """
        self.sm.state_manager.print_once("No commands available.")
        self.sm.audio_manager.sound_player.play(SoundActions.system_error, 0.5)
        self.sm.state_manager.transition(self.sm.State.LISTENING)

    # ===============================
    # Helper Methods
    # ===============================

    def _command_worker(self):
        """
        @brief Thread worker that processes transcriptions and parses commands using the LLM.
        """
        transcription_data = self.sm.queue_manager.get_safe(
            self.sm.queue_manager.transcription_queue,
            timeout=2,
            log_prefix=self.log_prefix,
        )

        if transcription_data is None:
            self.sm.state_manager.transition(self.sm.State.LISTENING)
            return

        # Handle both old string format and new dict format
        if isinstance(transcription_data, dict):
            transcription = transcription_data.get("text", transcription_data)
            from_webui = transcription_data.get("from_webui", False)
            client_id = transcription_data.get("client_id")
        else:
            transcription = transcription_data
            from_webui = False
            client_id = None

        # Store from_webui flag and client_id for use in other handlers
        self.sm.from_webui = from_webui
        self.sm.client_id = client_id

        message = f"{self.log_prefix} [User Prompt]: {transcription} (from_webui={from_webui})"
        self.sm.message_handler.send_to_web_server(message, client_id=client_id)

        structured_output = self.sm.command_processor.parse_transcription(
            transcription, from_webui=from_webui, client_id=client_id
        )

        if structured_output:
            if structured_output.get("commands"):
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] Structured Commands: {structured_output}"
                )
                success = self.sm.queue_manager.put_safe(
                    self.sm.queue_manager.command_queue,
                    structured_output,
                    log_prefix=self.log_prefix,
                )
                if success:
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] Successfully put command into queue"
                    )
                    self.sm.state_manager.transition(self.sm.State.SEND_COMMANDS)
                else:
                    self.sm.state_manager.transition(self.sm.State.LISTENING)

            elif structured_output.get("nl_response"):
                nl_message = structured_output.get("nl_response")
                lang = structured_output.get("language")
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] NL Response: {nl_message}"
                )

                # Always send response to WebUI
                message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
                client_id = getattr(self.sm, "client_id", None)
                self.sm.message_handler.send_to_web_server(message, client_id=client_id)

                # Only queue for speaking if NOT from WebUI
                if not from_webui:
                    success = self.sm.queue_manager.put_safe(
                        self.sm.queue_manager.speech_queue,
                        [nl_message, lang],
                        log_prefix=self.log_prefix,
                    )

                    if success:
                        print(
                            f"{self.log_prefix} [{LogLevel.INFO.name}] Successfully put NL response into speech queue"
                        )
                        self.sm.state_manager.transition(self.sm.State.SPEAKING)
                    else:
                        self.sm.state_manager.transition(self.sm.State.LISTENING)
                else:
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] Skipping speech for WebUI request"
                    )
                    self.sm.state_manager.transition(self.sm.State.LISTENING)

            else:
                self._queue_error_message(
                    "No valid commands or responses extracted, Please try again.",
                    from_webui,
                )

    def _queue_error_message(self, message, from_webui=False):
        """
        @brief Queue an error message to be spoken.
        @param message Error message text
        @param from_webui Whether the request came from web UI
        """
        print(f"{self.log_prefix} [{LogLevel.WARNING.name}] {message}")

        # Send to WebUI
        web_message = f"{self.log_prefix} [Error]: {message}"
        client_id = getattr(self.sm, "client_id", None)
        self.sm.message_handler.send_to_web_server(web_message, client_id=client_id)

        # Only queue for speaking if NOT from WebUI
        if not from_webui:
            success = self.sm.queue_manager.put_safe(
                self.sm.queue_manager.speech_queue,
                [message, "en"],
                log_prefix=self.log_prefix,
            )
            if success:
                self.sm.state_manager.transition(self.sm.State.SPEAKING)
            else:
                self.sm.state_manager.transition(self.sm.State.LISTENING)
        else:
            self.sm.state_manager.transition(self.sm.State.LISTENING)

    def _handle_simple_function_result(self, command_result, language):
        """
        @brief Handle results from simple functions by converting to natural language.
        @param command_result Result dictionary from simple function
        @param language Language code for response
        """
        from_webui = getattr(self.sm, "from_webui", False)

        if isinstance(self.sm.command_llm, OllamaClient):
            nl_output = self.sm.command_processor.process_command_result(
                command_result, language
            )

            if nl_output and nl_output.get("nl_response"):
                nl_message = nl_output.get("nl_response")
                lang = nl_output.get("language", language)
                print(
                    f"{self.log_prefix} [{LogLevel.INFO.name}] LLM converted response: {nl_message}"
                )

                message = f"{self.log_prefix} [LLM Reply]: {nl_message}"
                client_id = getattr(self.sm, "client_id", None)
                self.sm.message_handler.send_to_web_server(message, client_id=client_id)

                # Only queue for speaking if NOT from WebUI
                if not from_webui:
                    success = self.sm.queue_manager.put_safe(
                        self.sm.queue_manager.speech_queue,
                        [nl_message, lang],
                        log_prefix=self.log_prefix,
                    )
                    if success:
                        self.sm.state_manager.transition(self.sm.State.SPEAKING)
                    else:
                        self.sm.state_manager.transition(self.sm.State.LISTENING)
                else:
                    print(
                        f"{self.log_prefix} [{LogLevel.INFO.name}] Skipping speech for WebUI request"
                    )
                    self.sm.state_manager.transition(self.sm.State.LISTENING)
            else:
                # Fallback: use raw response
                simple_function_results = [
                    r
                    for r in command_result
                    if isinstance(r, dict) and r.get("type") == "simple_function"
                ]
                fallback_msg = str(simple_function_results)
                message = f"{self.log_prefix} [Command Result]: {fallback_msg}"
                client_id = getattr(self.sm, "client_id", None)
                self.sm.message_handler.send_to_web_server(message, client_id=client_id)

                # Only queue for speaking if NOT from WebUI
                if not from_webui:
                    success = self.sm.queue_manager.put_safe(
                        self.sm.queue_manager.speech_queue,
                        [fallback_msg, language],
                        log_prefix=self.log_prefix,
                    )
                    if success:
                        self.sm.state_manager.transition(self.sm.State.SPEAKING)
                    else:
                        self.sm.state_manager.transition(self.sm.State.LISTENING)
                else:
                    self.sm.state_manager.transition(self.sm.State.LISTENING)
        else:
            # Non-Ollama client: use raw response
            message = f"{self.log_prefix} [Command Result]: {command_result}"
            client_id = getattr(self.sm, "client_id", None)
            self.sm.message_handler.send_to_web_server(message, client_id=client_id)

            # Only queue for speaking if NOT from WebUI
            if not from_webui:
                success = self.sm.queue_manager.put_safe(
                    self.sm.queue_manager.speech_queue,
                    [str(command_result), language],
                    log_prefix=self.log_prefix,
                )
                if success:
                    self.sm.state_manager.transition(self.sm.State.SPEAKING)
                else:
                    self.sm.state_manager.transition(self.sm.State.LISTENING)
            else:
                self.sm.state_manager.transition(self.sm.State.LISTENING)

            if success:
                self.sm.state_manager.transition(self.sm.State.SPEAKING)
            else:
                self.sm.state_manager.transition(self.sm.State.LISTENING)
