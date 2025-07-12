# system imports
import threading
from queue import Queue, Empty
import time
from enum import Enum
import time
import logging
import sys
# custom imports
from .Sound_And_Speech import SoundPlayer, SoundActions, TextToSpeech, AudioRecorderClass, NoiseFloorMonitor, AudioTranscriptionClass, WakeWordListener
from .LLM import LLM_Class
from .HA_Interfacer import HomeAssistantClient
from .logger import shared_logger

class State(Enum):
    """
    @brief Enumeration for various states of the voice assistant state machine.
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



class StateMachineInstance:
    """
    @brief Core state machine managing voice assistant states, audio input/output, command processing, and interactions.
    """

    def __init__(self, command_llm: LLM_Class, device, ha_client, logger=None):
        """
        @brief Initialize the state machine, threads, queues, and component instances.
        @param command_llm The LLM instance used for command parsing.
        @param device The computation device (e.g., "cuda" or "cpu").
        @param ha_client The Home Assistant client interface.
        """
        self.device = device
        self.noise_floor = 0
        self.logger = logger or logging.getLogger("my_app")
        self.logger.propagate = True
        # State and synchronization primitives
        self.state: State = State.LOADING
        self.lock = threading.Lock()

        sys.stdout = shared_logger
        sys.stderr = shared_logger


        # Queues for inter-thread communication
        self.result_queue: Queue = Queue()          # Wake word detection results
        self.transcription_queue: Queue = Queue()   # Transcriptions from audio input
        self.command_queue: Queue = Queue()         # Parsed commands to be executed
        self.sound_action_queue: Queue = Queue()    # Sound actions to play asynchronously
        self.speech_queue: Queue = Queue()          # Text responses to speak aloud


        # Instantiate audio and NLP components
        self.noise_floor_monitor = NoiseFloorMonitor()
        self.awaker = WakeWordListener(self.noise_floor_monitor)
        self.recorder = AudioRecorderClass(noise_floor_monitor=self.noise_floor_monitor)
        self.transcriptor = AudioTranscriptionClass()
        self.transcriptor.init_model(device)

        self.sound_player = SoundPlayer()
        self.speaker = TextToSpeech()

        # Load the command LLM (using int8 for memory efficiency)
        self.command_llm = command_llm
        self.command_llm.load_model(use_int8=True)

        # Home Assistant client interface
        self.ha_client: HomeAssistantClient = ha_client

        # Start background threads
        self.wakeword_thread = threading.Thread(target=self.awaker.listen_for_wake_word, args=(self.result_queue,))
        self.wakeword_thread.daemon = True
        self.wakeword_thread.start()

        self.sound_thread = threading.Thread(target=self.sound_player_worker)
        self.sound_thread.daemon = True
        self.sound_thread.start()

        threading.Thread(target=self.command_worker, daemon=True).start()

        self._last_printed_message = None

        print("State machine init completed")

    def print_once(self, message, end='\n'):
        if message != self._last_printed_message:
            print(message, end=end)
            self._last_printed_message = message
        # Else do nothing, avoid printing duplicate lines

    def command_worker(self):
        """
        @brief Thread worker that processes transcriptions and parses commands using the LLM.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.PARSING_VOICE:
            try:
                transcription = self.transcription_queue.get(timeout=2)
                print(f"Got transcription: {transcription}")
            except Empty:
                print("Transcription queue was empty, retrying later...")
                self.transition(State.LISTENING)
                return

            structured_output = self.command_llm.parse_with_llm(transcription)

            if structured_output and structured_output.get("commands"):
                print("Structured Commands:", structured_output)
                self.command_queue.put(structured_output, timeout=1)
                print("Successfully put command into queue")
                self.transition(State.SEND_COMMANDS)
            else:
                message_to_speak = "No valid commands extracted, Please try again."
                print("No valid commands extracted.")
                self.speech_queue.put(message_to_speak)
                self.transition(State.SPEAKING)

    def sound_player_worker(self):
        """
        @brief Background thread that plays queued sound actions asynchronously.
        """
        while True:
            sound_action = self.sound_action_queue.get()
            if sound_action is None:
                break
            print(f"Playing sound: {sound_action}")
            self.sound_player.play(sound_action)

    def play_sound(self, sound_action):
        """
        @brief Enqueue a sound action to be played asynchronously by the sound thread.
        @param sound_action The SoundActions enum member to play.
        """
        self.sound_action_queue.put(sound_action)

    def transition(self, new_state: State):
        """
        @brief Safely transition the state machine to a new state.
        @param new_state The new State to transition to.
        """
        if self.lock.acquire(timeout=2):
            try:
                print(f"Transitioning from {self.state} to {new_state}")
                self.state = new_state
            finally:
                self.lock.release()
        else:
            print(f"Could not acquire lock to transition from {self.state} to {new_state}")

    def start_recording(self):
        """
        @brief Start audio recording and enqueue transcription if valid.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.RECORDING:
            print("Recording...")
            transcription = self.recorder.record_audio(self.transcriptor, self.noise_floor)
            transcription_words = len(str.split(transcription, " "))
            if transcription_words > 4:
                self.transcription_queue.put(transcription)
                self.transition(State.PARSING_VOICE)
            else:
                print(f"Transcription only had {transcription_words} words, returning to listening")
                self.transition(State.LISTENING)

    def speak(self):
        """
        @brief Speak the next queued speech response and play closing sound.
        """
        with self.lock:
            current_state = self.state

        if current_state == State.SPEAKING:
            print("Speaking response...")
            transcription = self.speech_queue.get()
            self.speaker.speak(transcription)
            self.sound_player.play(SoundActions.action_closing)
            self.transition(State.LISTENING)

    def handle_error(self):
        """
        @brief Handle errors by transitioning to ERROR state, playing error sound, and returning to LISTENING.
        """
        with self.lock:
            current_state = self.state

        if current_state != State.ERROR:
            print("An error occurred.")
            self.transition(State.ERROR)
            self.sound_player.play(SoundActions.system_error)
            time.sleep(2)
            self.transition(State.LISTENING)

    def run(self):
        self.transition(State.LISTENING)

        while True:
            time.sleep(0.1)  # Avoid busy waiting, reduce CPU load

            # Process wake word detection results
            if not self.result_queue.empty():
                wakeword_data = self.result_queue.get()

                with self.lock:
                    current_state = self.state

                if current_state == State.LISTENING and wakeword_data:
                    self.print_once(f"Wakeword detected! Transitioning to RECORDING. Noise Floor is {wakeword_data}")
                    self.noise_floor = wakeword_data

                    # Clear any remaining wake word events to avoid stale data
                    while not self.result_queue.empty():
                        self.result_queue.get()

                    self.transition(State.RECORDING)

            with self.lock:
                current_state = self.state

            if current_state == State.LISTENING:
                self.print_once("Listening for input...", end="\r")

            elif current_state == State.RECORDING:
                self.print_once("Recording state active.")
                self.play_sound(SoundActions.system_awake)
                self.start_recording()

            elif current_state == State.PARSING_VOICE:
                self.print_once("Generating state active.")
                self.command_worker()

            elif current_state == State.SEND_COMMANDS:
                self.print_once("Sending commands to HA client.")
                try:
                    command = self.command_queue.get_nowait()
                    command_result = self.ha_client.send_commands(command)
                except Empty:
                    command_result = None

                if command_result:
                    self.print_once("Command result received.")
                    self.speech_queue.put(command_result)
                    self.transition(State.SPEAKING)
                else:
                    self.play_sound(SoundActions.system_awake)
                    self.transition(State.LISTENING)

            elif current_state == State.NO_COMMANDS:
                self.print_once("No commands available.")
                self.sound_player.play(SoundActions.system_error, 0.5)
                self.transition(State.LISTENING)

            elif current_state == State.SPEAKING:
                self.print_once("Speaking state active.")
                self.speak()
                self.transition(State.LISTENING)

            elif current_state == State.ERROR:
                self.print_once("Error state active.")
                self.handle_error()