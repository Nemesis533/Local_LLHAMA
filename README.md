# Local_LLAMA: Offline, Multilingual Smart Home Voice Assistant

**Local_LLAMA** is a local-first, multilingual, LLaMA-powered voice assistant that integrates seamlessly with [Home Assistant](https://www.home-assistant.io/). Designed for privacy, flexibility, and natural interaction, it allows users to control smart home devices using natural language — all without relying on the cloud or requiring exact device names. As an independent system that runs on base Linux and interfaces with HA (or potentially other domotics systems) via API, it bypasses many compatibility restrictions that running similar systems in HA have (e.g., smart-speaker compatibility).

## Recent Updates

The system has been refactored for improved performance, maintainability, and modularity. Key improvements include:
- Modular architecture with separated audio input/output handling
- Enhanced web interface with real-time system monitoring
- Improved state machine implementation with better error handling
- Security enhancements with environment variable configuration
- Comprehensive test suite for core functionality

## Features

- Wake word detection using `OpenWakeWord`
- Voice recording with adaptive noise floor detection
- Whisper-based speech-to-text conversion
- LLaMA 3.1 (8B) LLM for command parsing and entity resolution
- Optional PromptGuard safety layer (LLaMA 3.2 3B fine-tuned model)
- Multilingual support: English, French, Spanish, Italian, German, Russian (and more)
  This allows you to call the command in any of the supported languages and not have to worry about it - you can say "la lumière du salon" for "living room light"
- Fuzzy device/entity matching using dynamic Home Assistant entity list; for optmization purposes, a manual list of devices can also be assigned instead of filtering the full list from HA.
  This solves the problem of having to call devices by the exact name that they are saved under - you can now say "light above the desk" to call the "desk light".
- Execute multiple commands in a single sentence
- NEW! Thanks to Integration with Ollama, natual language responses will be returned when no device is present.
- Basic web interface for output monitoring and connection status (expansion and system control planned)
- Ability to integrate non-Home Assistant devices and commands with the same pipeline as the one used for Home Assistant.

## System Requirements

- **CPU**: 4–8 cores (tested with Xeon E5-2640 v4)
- **RAM**: 8 GB minimum
- **GPU**: NVIDIA RTX 4060 Ti or better (16GB+ VRAM recommended)
- **OS**: Linux (tested on Ubuntu 24.04, should work on 22.04)

**Performance Notes:**
- GPU-accelerated processing; most computational load on GPU
- Local setup uses ~14.5GB VRAM with all models loaded
- Ollama server setup: core system uses ~6.5GB VRAM
- 12GB VRAM possible with guard model disabled and small Whisper model
- Typical latency: 1–4 seconds (single machine, above hardware)
- Multi-machine setup tested with RTX 2080 Ti + RTX 4060 Ti: ~1 second latency
- System tested in Ubuntu VM (Proxmox) with GPU passthrough

## Installation

1. **Clone the repository**

2. **Run the install script:**

```bash
chmod +x local_LLM_installer.sh
./local_LLM_installer.sh
```

Installs dependencies and creates a Python 3.12 virtual environment.

3. **Configure environment variables:**

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
- `HA_BASE_URL`: Home Assistant URL (e.g., `http://homeassistant.local:8123`)
- `HA_TOKEN`: Long-Lived Access Token from HA Profile settings
- `OLLAMA_IP`: Ollama server IP:port (if using Ollama)
- `ALLOWED_IP_PREFIXES`: Comma-separated IP prefixes for web UI access

**Important:** Never commit `.env` to version control.

## Configuration

### Environment Variables (.env)

Security-sensitive configuration stored in `.env` (never commit):
- `HA_BASE_URL`: Home Assistant base URL
- `HA_TOKEN`: Long-Lived Access Token
- `OLLAMA_IP`: Ollama server IP:port (if using Ollama)
- `ALLOWED_IP_PREFIXES`: IP prefixes for web UI access

See `.env.example` for template.

### object_settings.json

Non-sensitive configuration stored in JSON with class/variable structure:

```json
"HomeAssistantClient": {
  "allowed_entities": {
    "value": ["light.kitchen_light", "light.desk_light", ...],
    "type": "list"
  },
  "ALLOWED_DOMAINS": {
    "value": ["light", "climate", "switch", "fan", ...],
    "type": "list"
  }
}
```

Contains LLM paths, model settings, and other non-sensitive configuration. Modified via Settings_Loader using reflection.

### web_search_config.json

Configures web information sources (news, Wikipedia, etc.) with allowed websites, max results, and timeout settings.
 
 
## How It Works

1. **Wake Word Detection**  
   Continuous listening via `OpenWakeWord` until "Hey Jarvis" detected. Sensitivity adjustable via `wakeword_thr` in settings.

2. **Speech Recording**  
   Records 3-10 seconds after wake word; stops early on silence detection using dynamic noise floor.

3. **Speech-to-Text**  
   Whisper transcribes audio (medium model for multilingual, small model for English-only).

4. **Command Parsing**  
   - Optional PromptGuard safety check (LLaMA Guard 3)
   - Transcribed text + HA entities sent to LLM (local or Ollama)
   - Entities manually supplied or auto-fetched from HA
   - LLM identifies devices/actions, generates HA JSON or NL response
   - Web queries fetch real-time data (weather, news, Wikipedia)

5. **Command Execution**  
   - Valid JSON sent to HA API
   - Non-HA actions matched via `command_schema.txt` using reflection
   - Failed queries reported to user

6. **Feedback and Output**  
   - The piper-tts engine provides spoken confirmation or failure
   - Output and logs are also available through a simple web UI for basic monitoring.
   - The langiuage is returned along with the reponse by the LLM
  
7. **FSM Diagram**

   ![FSM Diagram](https://github.com/Nemesis533/Local_LLHAMA/blob/main/FSM_diagram_0.png)

## Example Commands

```text
Turn off the kitchen lights and turn on the living room lamp.
Éteins la lumière du salon et allume la clim dans la chambre.
Apaga la luz de la cocina y enciende la lámpara del salón.
Turn on the desk light and tell me the weather.
What's in the news today?
Tell me about the Eiffel Tower.
```

Features demonstrated:
- Natural, free-form language
- Multilingual input (6 languages)
- No exact device names required
- Multiple commands per sentence
- Mixed HA actions + information queries
- Web information retrieval

## Dependencies

Key libraries used in this project include:

Lowest supported python version is 3.10, but 3.12 is recommended.

- `torch`, `transformers` (LLaMA model support)
- `whisper` (OpenAI's STT)
- `openwakeword` (wake word detection)
- `TTS` (Piper TTS engine)
- `pygame` (audio playback)
- `librosa`, `wave` (audio processing)
- `flask` (basic web UI)

All dependencies are listed in `requirements.txt`.

## Project Structure

```
.
├── dev/
│   ├── run-dev.py                   # Development mode runner
│   └── wikidoc_creator.py           # Auto-generate documentation
├── local_llhama/
│   ├── Audio_Input.py               # Whisper STT, wake word detection, recording
│   ├── Audio_Output.py              # Piper TTS, sound playback
│   ├── Home_Assistant_Interface.py  # HA API communication
│   ├── LLM_Handler.py               # LLaMA inference logic
│   ├── LLM_Prompts.py               # Prompt templates
│   ├── Ollama_Client.py             # Ollama server client
│   ├── Prompt_Guard.py              # Safety filtering (LLaMA Guard 3)
│   ├── Run_System.py                # Entry point
│   ├── Runtime_Supervisor.py        # System orchestration
│   ├── Settings_Loader.py           # Configuration loader (reflection-based)
│   ├── Shared_Logger.py             # Centralized logging
│   ├── Simple_Functions.py          # Non-HA utilities (weather, news, etc.)
│   ├── Sound_And_Speech.py          # Legacy audio handler
│   ├── State_Machine.py             # FSM implementation
│   ├── System_Controller.py         # Component orchestration
│   ├── Web_Server.py                # Flask backend
│   ├── command_schema.txt           # Custom command definitions
│   ├── routes/                      # Web UI route handlers
│   │   ├── llm_routes.py
│   │   ├── main_routes.py
│   │   ├── settings_routes.py
│   │   ├── system_routes.py
│   │   └── user_routes.py
│   ├── settings/
│   │   ├── object_settings.json     # Non-sensitive config
│   │   └── web_search_config.json   # Web search settings
│   ├── sounds/                      # System audio files
│   ├── static/                      # Web UI (HTML, CSS, JS, images)
│   └── tests/                       # Test suite
├── piper_voices/                    # TTS voice models (.onnx)
├── wiki_docs/                       # Auto-generated documentation
├── .env.example                     # Environment variable template
├── local_LLM_installer.sh           # Installation script
├── requirements.txt                 # Python dependencies
└── README.md
```

## Web Interface

Web UI provides:
- Real-time system output monitoring
- Settings editor with live reload
- Text-based command interaction (voice-free)
- Connection status indicators
- Configuration management

Access via browser after system start. IP restrictions configured via `ALLOWED_IP_PREFIXES` in `.env`.


## License

This project is licensed under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

You are free to:

- **Share** — copy and redistribute the material in any medium or format  
- **Adapt** — remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:

- **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made.

Read the full license here: [https://creativecommons.org/licenses/by/4.0/](https://creativecommons.org/licenses/by/4.0/)

## Acknowledgments

- Meta AI for the LLaMA models [https://huggingface.co/meta-llama]
- OpenAI for Whisper [https://github.com/openai/whisper]
- Coqui for the TTS engine [https://github.com/coqui-ai/TTS]
- OpenWakeWord by dscripka [https://github.com/dscripka/openWakeWord]
- Home Assistant open-source platform [https://www.home-assistant.io/]
- Developers of Pygame ([https://github.com/pygame/pygame]), Librosa ([https://github.com/librosa/librosa]), and other community-driven tools

## Contributing

Contributions and suggestions welcome! See "Future Work" for ideas. Response time may vary due to limited availability.

Open discussions before submitting major PRs.

## Future Work

**Completed:**
- ✓ Remote LLM support (Ollama server)
- ✓ Web UI with system control
- ✓ Prompt Guard toggle
- ✓ Multiple LLM support
- ✓ Web search integration
- ✓ Modular audio architecture

**Planned:**
- Performance optimizations
- Enhanced TTS performance and flexibility
- Expanded web search capabilities
- RAG agents for context-aware responses
- Simplified custom function integration
- Dynamic failure message generation
- Improved error handling and recovery
- Test coverage expansion

## Note

Developed as a versatile domotic assistant during spare time. Suggestions for improvements welcome. Main expertise isn't coding/AI, so there's room for optimization — hope you find it useful regardless.

---

*Natural language control for smart homes — privately, locally, and powerfully.*