# Documentation for `Sound_And_Speech.py`

## Function `__init__`

**Description:**

Initialize the pygame mixer, volume, sound cache, and sound file mappings.


## Function `load_sound`

**Description:**

Load a sound by name if not already loaded.

**Parameters:**

- `sound_name`: The name key of the sound (matching sounds_dictionary keys).

## Function `play`

**Description:**

Play a sound with optional volume and blocking until done.

**Parameters:**

- `sound_to_play`: SoundActions enum member specifying which sound to play.
- `volume`: Playback volume between 0.0 and 1.0.
- `wait_for_finish`: Whether to block execution until sound playback completes.

## Function `stop`

**Description:**

Immediately stop all currently playing sounds.


## Function `set_volume`

**Description:**

Set the global playback volume and update currently playing sounds.

**Parameters:**

- `volume`: Volume level between 0.0 and 1.0.

## Function `__init__`

**Description:**

Constructor that loads the specified TTS model.

**Parameters:**

- `model_name:`: The Coqui TTS model name to load.

## Function `preprocess_text`

**Description:**

Preprocesses the input text to remove unsupported characters.

**Parameters:**

- `text:`: The raw input text.

## Function `set_playback_volume`

**Description:**

Adjusts the volume of audio data.

**Parameters:**

- `data:`: The audio data as a NumPy array.
- `volume:`: Volume scaling factor between 0.0 and 1.0.

## Function `reduce_noise`

**Description:**

Reduces background noise using spectral gating.

**Parameters:**

- `audio:`: The input audio waveform.
- `sr:`: The sample rate.
- `n_fft:`: Number of FFT components.
- `hop_length:`: Number of samples between frames.
- `n_std_thresh:`: Noise threshold in standard deviations.

## Function `speak`

**Description:**

Converts input text to speech, processes audio, and plays it.

**Parameters:**

- `text`: The input text string to be synthesized and spoken.
- `blocksize`: The audio block size for playback buffering (default: 4096).
- `latency`: Latency setting for audio playback, e.g., 'low' or 'high' (default: 'low').

## Function `init_model`

**Description:**

Loads the Whisper model onto the specified device.

**Parameters:**

- `device:`: The device to load the model on ('cpu', 'cuda', etc.).

## Function `transcribe_audio`

**Description:**

Transcribes the audio from the given file using Whisper.

**Parameters:**

- `filename:`: Path to the audio file to transcribe.

## Function `__init__`

**Description:**

Constructor for AudioRecorderClass.

**Parameters:**

- `noise_floor_monitor:`: Instance of NoiseFloorMonitor for background noise analysis.
- `duration:`: Maximum recording duration in seconds.
- `sample_rate:`: Sampling rate in Hz.
- `channels:`: Number of input audio channels.
- `chunk_size:`: Number of frames per buffer (block size).

## Function `get_silence`

**Description:**

Calculates the average RMS over the recent silence window.


## Function `record_audio`

**Description:**

Records audio from the microphone until silence is detected or duration expires.

**Parameters:**

- `transcriptor:`: Instance of AudioTranscriptionClass used to transcribe audio.
- `noise_floor:`: Baseline noise floor value to set silence threshold.

## Function `__init__`

**Description:**

Constructor for NoiseFloorMonitor.

**Parameters:**

- `rate:`: The sampling rate of the audio in Hz.
- `chunk_size:`: Number of samples per audio chunk.
- `window_seconds:`: Number of seconds to average RMS over.

## Function `_calculate_rms`

**Description:**

Calculates the Root Mean Square (RMS) value from raw audio bytes.

**Parameters:**

- `data:`: Byte string of audio data.

## Function `update_and_get_average_rms`

**Description:**

Updates the RMS buffer with new audio data and returns the running average in dBFS.

**Parameters:**

- `data:`: Byte string of audio data.

## Function `get_noise_floor`

**Description:**

Returns the current estimated noise floor in dBFS.


## Function `rms_to_dbfs`

**Description:**

Converts an RMS value to dBFS (decibels relative to full scale).

**Parameters:**

- `rms:`: The RMS value to convert.
- `ref:`: The reference value for 0 dBFS. Default is 32768.0 (max 16-bit PCM).

## Function `__init__`

**Description:**

Constructor for WakeWordListener.

**Parameters:**

- `noise_floor_monitor:`: Instance of NoiseFloorMonitor to track RMS levels for ambient noise.

## Function `listen_for_wake_word`

**Description:**

Continuously listens to audio input and triggers when a wake word is detected.

**Parameters:**

- `result_queue:`: Queue to communicate detection result (e.g., noise floor) back to main thread.

