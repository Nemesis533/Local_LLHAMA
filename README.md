# Local_LLAMA: Offline, Multilingual Smart Home Voice and Chat Assistant

**Local_LLAMA** is a local-first, multilingual, LLaMA-powered voice assistant that integrates seamlessly with [Home Assistant](https://www.home-assistant.io/) and custom function calling. Designed for privacy, flexibility, and natural interaction, it allows users to control smart home devices using natural language — all without relying on the cloud or requiring exact device names. As an independent system that runs on base Linux and interfaces with HA (or potentially other domotics systems) via API, it bypasses many compatibility restrictions that running similar systems in HA have (e.g., smart-speaker compatibility).

## NEW!
## Because of the recent direction of online LLM services, which will pivotr towards adding ads to either the pages or the responses, I decided to add some unplanned features, namely the ability to chat directly with the LLM while intgreating the same capabilities (HA control, function calling, etc) that the system already had. These features will be expanded upon and while this does not aim to reach the levels of other solutions for local LLM interaction such as the amazin work of the people behidn OpenWebUI, the hope is to provide a solution that can provide chat interactions beyond speaking to the system. Development of these features temporarly takes precedence over previously planned ones.

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
- Ollama integration.
- FROZEN- LLaMA 3.1 (8B) LLM for command parsing and entity resolution (currently still supported, but not being developed)
- Optional PromptGuard safety layer (LLaMA 3.2 3B fine-tuned model)
- Multilingual support: English, French, Spanish, Italian, German, Russian (and more)
  This allows you to call the command in any of the supported languages and not have to worry about it - you can say "la lumière du salon" for "living room light"
- Fuzzy device/entity matching using dynamic Home Assistant entity list; for optmization purposes, a manual list of devices can also be assigned instead of filtering the full list from HA.
  This solves the problem of having to call devices by the exact name that they are saved under - you can now say "light above the desk" to call the "desk light".
- Execute multiple commands in a single sentence
- Per-client chat window that inegrates in the standard workflow.
- Thanks to Integration with Ollama, natual language responses will be returned when no device is present.
- Calendar and reminder system with automatic notifications - set reminders, alarms, and appointments with natural language
- Web interface for output monitoring, connection status, and calendar management
- Ability to integrate non-Home Assistant devices and commands with the same pipeline as the one used for Home Assistant.

## Latest Additions
- NEW! Multi-user chat interface with real-time WebSocket communication - separate from voice pipeline
- NEW! Per-user conversation history tracking (last 3 exchanges) for contextual responses
- NEW! Admin panel with user management - create users, assign permissions, reset passwords
- NEW! Per-user calendar system with automatic notifications - set reminders, alarms, and appointments with natural language
- NEW! Comprehensive web interface with real-time chat, calendar sidebar, system monitoring, and settings management
- NEW! Role-based access control with granular permissions (admin, dashboard access, chat access)


## System Requirements

- **CPU**: 4–8 cores (tested with Xeon E5-2640 v4)
- **RAM**: 8 GB minimum
- **GPU**: NVIDIA RTX 4060 Ti or better (16GB+ VRAM recommended)
- **OS**: Linux (tested on Ubuntu 24.04, should work on 22.04)

**Performance Notes:**
- GPU-accelerated processing; most computational load on GPU
- Local setup uses ~17 GB VRAM with all models loaded; a 20GB can handle the entire system on its own.
- About 5-6 GB of RAM necessary on the main system.
- Ollama server setup: core system uses ~5.0GB VRAM
- 15GB VRAM possible with guard model disabled and small Whisper model
- Typical latency: 1–4 seconds (single machine, above hardware)
- Multi-machine setup tested with RTX 2080 Ti (system) + RTX 4060 Ti 16GB (Ollama): ~1 second latency
- System tested in Ubuntu VM (Proxmox) with GPU passthrough, Vms on 2 servers communicating via ethernet.

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
   - **Voice Pipeline**: Optional PromptGuard safety check, processes through state machine sequentially
   - **Chat Pipeline**: Parallel processing via ChatHandler, bypasses state machine for multi-user support
   - Transcribed text + HA entities sent to LLM (local or Ollama)
   - Entities manually supplied or auto-fetched from HA
   - LLM identifies devices/actions, generates HA JSON or NL response
   - Different prompts for voice (RESPONSE_PROCESSOR_PROMPT) vs chat (CONVERSATION_PROCESSOR_PROMPT)
   - Per-user conversation history maintained in chat for contextual responses
   - Calendar operations parsed and executed via natural language (per-user in chat)
   - Web queries fetch real-time data (weather, news, Wikipedia)

5. **Command Execution**  
   - Valid JSON sent to HA API
   - Calendar events stored in local SQLite database
   - Background thread monitors for due reminders/alarms and triggers notification sound
   - Non-HA actions matched via `command_schema.txt` using reflection
   - Failed queries reported to user

6. **Feedback and Output**  
   - The piper-tts engine provides spoken confirmation or failure (voice pipeline only)
   - Real-time WebSocket communication for chat interface with instant LLM responses
   - Output and logs available through comprehensive web UI with multiple views
   - Per-user calendar events displayed in chat sidebar with real-time updates
   - Calendar event notifications sent directly to user's chat when reminders/alarms trigger
   - Loading indicators show when LLM is processing ("Thinking..." animation)
   - The language is returned along with the response by the LLM
  
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
Set a reminder to drink water in 30 minutes.
Add an appointment for tomorrow at 2 PM.
What reminders do I have today?
List my calendar for the next week.
```

Features demonstrated:
- Natural, free-form language
- Multilingual input (6 languages)
- No exact device names required
- Multiple commands per sentence
- Mixed HA actions + information queries
- Calendar and reminder management with natural time parsing
- Web information retrieval
- One turn Command Conversational context maintained (e.g., "turn them back on" after turning lights off)

## Dependencies

Key libraries used in this project include:

Lowest supported python version is 3.10, but 3.12 is recommended.

- `torch`, `transformers` (LLaMA model support)
- `whisper` (OpenAI's STT)
- `openwakeword` (wake word detection)
- `TTS` (Piper TTS engine)
- `pygame` (audio playback)
- `librosa`, `wave` (audio processing)
- `flask` (web UI)

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
│   ├── chat_handler.py              # Multi-user chat processing with conversation history
│   ├── HA_Utils.py                  # Home Assistant utility functions
│   ├── Home_Assistant_Interface.py  # HA API communication
│   ├── LLM_Handler.py               # LLaMA inference logic
│   ├── LLM_Prompts.py               # Prompt templates (voice, chat, calendar)
│   ├── Ollama_Client.py             # Ollama server client with context tracking
│   ├── Prompt_Guard.py              # Safety filtering (LLaMA Guard 3)
│   ├── Run_System.py                # Entry point
│   ├── Runtime_Supervisor.py        # System orchestration
│   ├── Settings_Loader.py           # Configuration loader (reflection-based)
│   ├── Shared_Logger.py             # Centralized logging
│   ├── Simple_Functions.py          # Non-HA utilities (weather, news, calendar, etc.)
│   ├── State_Machine.py             # FSM implementation with calendar monitoring and notifications
│   ├── System_Controller.py         # Component orchestration
│   ├── Web_Server.py                # Flask backend with WebSocket support
│   ├── command_schema.txt           # Custom command definitions
│   ├── auth/                        # Authentication and calendar management
│   │   ├── auth_manager.py          # User authentication
│   │   ├── calendar_manager.py      # SQLite-based calendar/reminder system
│   │   └── db_manager.py            # Database utilities
│   ├── routes/                      # Web UI route handlers
│   │   ├── auth_routes.py           # Login/logout
│   │   ├── calendar_routes.py       # Calendar API endpoints
│   │   ├── llm_routes.py            # LLM interaction
│   │   ├── main_routes.py           # Dashboard
│   │   ├── settings_routes.py       # Configuration management
│   │   ├── system_routes.py         # System control
│   │   └── user_routes.py           # User management
│   ├── settings/
│   │   ├── object_settings.json     # Non-sensitive config
│   │   └── web_search_config.json   # Web search settings
│   ├── sounds/                      # System audio files (confirmation, reminder, etc.)
│   ├── static/                      # Web UI (HTML, CSS, JS, images)
│   ├── state_components/            # State machine components
│   │   ├── audio_manager.py         # Audio handling
│   │   ├── command_processor.py     # Command processing
│   │   ├── message_handler.py       # Message routing
│   │   ├── queue_manager.py         # Queue management
│   │   └── state_handlers.py        # State transition logic
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

**Chat Interface:**
- Real-time multi-user chat with LLM using WebSockets
- Per-user conversation history (last 3 exchanges) for contextual responses
- Loading indicators during LLM processing ("Thinking..." animation)
- Per-user calendar sidebar showing upcoming events
- Add calendar events directly from chat interface
- Real-time calendar event notifications when reminders/alarms trigger
- Separate processing from voice pipeline for concurrent users

**Admin Panel:**
- User management (create, edit, delete users)
- Role-based permission assignment (admin, dashboard access, chat access)
- Password management with force-change option
- User activity monitoring

**Dashboard:**
- Real-time system output monitoring
- Settings editor with live reload
- Text-based command interaction (voice-free)
- Calendar management - view upcoming reminders, alarms, and appointments
- Delete calendar events with confirmation
- Auto-refresh calendar display every 30 seconds
- Connection status indicators
- Configuration management
- Voice-created calendar events display

**General:**
- User authentication with Flask-Login session management
- IP restrictions configured via `ALLOWED_IP_PREFIXES` in `.env`
- Permission-based UI element visibility

Access via browser after system start. Default admin account created on first run.


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
- Remote LLM support (Ollama server)
- Multi-user chat interface with WebSocket communication
- Per-user conversation history tracking
- Admin panel with comprehensive user management
- Role-based access control system
- Per-user calendar system with notifications
- Dual processing paths (voice pipeline vs chat pipeline)
- Web UI with system control and real-time monitoring
- Prompt Guard toggle
- Multiple LLM support
- Web search integration
- Modular audio architecture
- Calendar and reminder system with natural language parsing
- Automatic reminder/alarm notifications (sound + chat messages)
- Web-based calendar management interface

**Planned:**
- Auto-rescheduling for repeating reminders and alarms
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

*Natural language control for smart homes — privately, locally*