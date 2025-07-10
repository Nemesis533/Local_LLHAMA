# Documentation for `StateMachine.py`

## Function `__init__`

**Description:**

Constructor for LocalLLMChecker.

**Parameters:**

- `host:`: IP address to bind the Flask app to. Default is '127.0.0.1'.
- `port:`: Port number for the Flask app. Default is 5001.
- `stdout_buffer:`: Optional buffer for capturing stdout.

## Function `view_stdout`

**Description:**

Simple text output of captured stdout.


## Function `run`

**Description:**

Starts the Flask web server.


## Function `__init__`

**Description:**

Initialize the state machine, threads, queues, and component instances.

**Parameters:**

- `command_llm`: The LLM instance used for command parsing.
- `device`: The computation device (e.g., "cuda" or "cpu").
- `ha_client`: The Home Assistant client interface.

## Function `command_worker`

**Description:**

Thread worker that processes transcriptions and parses commands using the LLM.


## Function `sound_player_worker`

**Description:**

Background thread that plays queued sound actions asynchronously.


## Function `play_sound`

**Description:**

Enqueue a sound action to be played asynchronously by the sound thread.

**Parameters:**

- `sound_action`: The SoundActions enum member to play.

## Function `transition`

**Description:**

Safely transition the state machine to a new state.

**Parameters:**

- `new_state`: The new State to transition to.

## Function `start_recording`

**Description:**

Start audio recording and enqueue transcription if valid.


## Function `speak`

**Description:**

Speak the next queued speech response and play closing sound.


## Function `handle_error`

**Description:**

Handle errors by transitioning to ERROR state, playing error sound, and returning to LISTENING.


