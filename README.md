# Local_LLAMA: LLM Orchestration Middleware for Smart Home Control

![Status](https://img.shields.io/badge/status-alpha-yellow)
![License](https://img.shields.io/badge/license-CC%20BY%204.0-blue)

**Now on version 0.7** 

**Local_LLAMA** is anorchestration middleware that sits between Home Assistant and Ollama, enabling smaller LLM models (8-20B parameters) to handle complex multi-intent, multi-language workloads through intelligent task decomposition, adaptive context management, and multi-pass prompt engineering.

**The Core Issue:** Raw model size isn't the bottleneck—inefficient routing and context management are.

Through dynamic orchestration, an 8B parameter model can potentially achieve what traditionally requires 70B+ models. The system coordinates parallel execution across Home Assistant APIs, calendar databases, and web services while maintaining conversational context and privacy.

**What This Means:**
- RTX 4060 Ti 16GB or even an RTX 4060 8GB Mobile handle workloads that would typically require much more powerful carts
- Few-second response time for multi-intent commands, sub minute for 5+ intent utterance with web searches
- Complete offline operation with zero cloud dependency
- Multilingual support (6+ languages) on consumer hardware

## The Orchestration Approach

**The Problem:** Standard LLM implementations for smart home control struggle with multi-intent and multi-lingual commands, require exact device names, and either underutilize context (losing conversation flow) or overload it (causing timeouts and degraded performance).

**The Porposed Solution:** Middleware that handles task decomposition, backend routing, and adaptive context composition and scaling.

![Multi-command example](screenshots/chat_window_1.png)

### How Orchestration Works

When you say *"Turn off the kitchen lights, set a 7am alarm, and tell me the weather"*, the system:

1. **Parallel Intent Decomposition** — LLM identifies independent tasks from natural language
2. **Targeted Backend Routing** — Routes each intent to appropriate service (Home Assistant API, calendar database, weather API, etc)
3. **Minimal Context Injection** — Each backend receives only relevant context, not entire conversation history
4. **Adaptive Context Scaling** — Automatically reduces context window on timeout, recovers on success
5. **Multi-Pass Prompt Engineering** — Modular layers (base reasoning → decision logic → safety → formatting) enable independent optimization

**Result:** A 20B (or even 14B) parameter model executes complex workflows that would typically require 30-70B models, running entirely on consumer GPUs.

### Core Capabilities

- **Voice AND chat interfaces** with identical LLM orchestration capabilities
- **Multi-intent natural language** processing (6+ commands in single utterance)
- **Fuzzy entity matching** ("light above desk" vs exact device names)
- **Adaptive performance tuning** based on real-time latency feedback
- **Hardware-validated presets** for 8GB to 24GB VRAM configurations
- **Complete offline operation** — no cloud APIs, no telemetry, full privacy

## Architecture & Features

### Intelligent Orchestration Layer

**Multi-Backend Coordination**
- Parallel execution across Home Assistant, PostgreSQL, web APIs
- Unified natural language interface for disparate services
- Single utterance can trigger 6+ independent backend operations
- Reflection-based function discovery via `command_schema.txt`

**Adaptive Context Management**
- Dynamic context windows (1000+→100 words) based on latency feedback
- Per-user conversation history with semantic memory search
- Configurable thresholds via preset system

**Multi-Pass Prompt Engineering**
- Modular composable layers: base → decision → safety → format + auxiliary
- Context injection tailored to each backend call
- Language detection and localization at response generation
- Independent A/B testing of prompt components
- Voice vs chat optimized processing paths

### Voice & Chat Pipelines

**Voice Pipeline** (State Machine based)
- Wake word detection using `OpenWakeWord`
- Adaptive noise floor detection for recording
- Whisper-based speech-to-text (model selection per preset)
- Piper TTS for natural language feedback

**Chat Pipeline** (Parallel Multi-User)
- Real-time WebSocket communication
- Per-user conversation history, context and memory
- Streaming LLM responses with Markdown rendering
- Role-based access control (admin, chat permissions)

### Smart Home Integration

**Fuzzy Entity Matching**
- Natural language device references ("light above desk" not "desk_lamp")
- Semantic understanding of device locations and functions
- Multilingual entity matching across languages
- Dynamic Home Assistant entity list integration

**Multi-Intent Execution**
- Single command handles multiple independent actions
- Parallel backend operations with unified response
- Example: "Turn off lights AND set alarm AND check weather, etc" in one request
- Custom function integration via reflection-based discovery, handled the same way as entities

**Multilingual Support** (English, French, Spanish, Italian, German, Russian, and potentially more)
- Automatically detects and responds in the language you speak
- Say "la lumière du salon" for "living room light" even if the device is called "Luz del divan"

**Calendar & Reminders**
- Set reminders, alarms, and appointments with natural language
- Per-user calendar with automatic notifications, both voical and in chat
- Unified interface for all event types; each users sees only their calendar, the admin can only see voice-created events.

**Semantic Memory Search**
- Vector-based conversation history search using Ollama embeddings
- Hybrid search combining semantic similarity with keyword matching
- Wikipedia falla back to memory when articles not found
- Per-user private memory with configurable similarity threshold

**Web & Information via Free/Open APIs**
- Real-time news via GDELT API
- Weather queries via Open-Meteo API
- Wikipedia API integration with memory fallback
- You can replace/add/change these with whatever you want

**Web Interface**
- Real-time chat with Markdown support (bold, italic, code blocks)
- Indication of current task and response streaming
- Calendar sidebar with event management
- Customizable model name for chat usage
- Admin panel with user, language, prompt, system, web settings and more.
- Role-based access control (admin, chat permission)

![Admin Prompt Page](screenshots/admin_window.png)

## Latest Additions

- **Semantic Memory Search** - Vector embeddings + keyword matching for conversational context retrieval
- **Dual-Pipeline Architecture** - Voice and chat both share LLM capabilities, optimized for their respective UX patterns
- **Real-time Chat Interface** - Multi-user WebSocket communication with persistent message history
- **Per-User Context** - Conversation history tracking (last 3 exchanges) for contextual, aware responses
- **Unified Calendar System** - Single consolidated API for reminders, appointments, and alarms
- **Admin Panel** - User management, permissions assignment, password reset
- **Markdown Chat Rendering** - Bold, italic, code blocks with syntax highlighting
- **Role-Based Access Control** - Admin and User permissions for web interface
- **Response Streaming and Optimized Context** - Context passing has been optimized to maintain proper command/context handling while keeping a reasonable length conversational context.


## System Requirements

**Middleware Orchestration Layer:**
- **CPU**: 4–8 cores (tested with Xeon E5-2640 v4 and i7 12700H)
- **RAM**: 8 GB for core system + PostgreSQL
- **GPU**: 8-24GB VRAM depending on preset (tested with RTX 4060ti 16GB (with and without RTX 2080Ti as secondary), RTX 4060 8GB Mobile)
- **OS**: Linux (Ubuntu 22.04+, tested on 24.04+)

**Required Services (leverage, not replace):**
- **Ollama Server**: Local or remote for LLM inference
- **Home Assistant**: Local or remote for smart home control
- **PostgreSQL**: For conversation history and embeddings

### Hardware-Validated Presets

Local_LLAMA uses a preset system to provide optimized configurations for different hardware setups. 
Presets are complete configuration packages that set LLM models, Whisper models, TTS languages, and performance parameters.

Configurations tested on real hardware with performance benchmarks:

| Preset | VRAM | Model | Languages | Use Case |
|--------|------|-------|-----------|----------|
| **english_only_small** | 8GB | Qwen2.5:8B | English | Entry-level, basic control |
| **english_only_large** | 16GB | GPT-OSS:20B | English | High-quality single language |
| **multi_lingual_small** | 16GB | Qwen2.5:14B | 6 languages | Balanced multilingual |
| **multi_lingual_large** | 24GB | GPT-OSS:20B | 6 languages | Maximum performance |

The Qwen family is being used because of how well they follow instructions and their size-availability. GPT-OSS is used as alternative for larger GPUS.
qwen3:30b-instruct works very well too but woudl be on edge of a 24GB card - recommned at least 28 GB+ VRAM for that model.


Each preset configures:
- LLM model selection and parameters
- Whisper model size
- Text-to-speech language models to use based on language
- ChatHandler settings (max_tokens, context window sizes, reduction factors, etc)

**Orchestration Performance:**
- Core middleware: ~3-4GB RAM overhead
- Multi-command latency: 2-5 seconds (simple) to 10-60 seconds (complex with web search)
- Context reduction triggers: Automatic based on response timeouts
- Tested configurations: Local Ollama, remote Ollama, VM + bare metal

**Scaling Options:**
- Single machine: All services on one system
- Distributed: Ollama on dedicated inference server, middleware on separate system
- Tested: Proxmox VM (middleware) + bare metal server (Ollama) via ethernet and all system on a single laptop.

## Installation

### Quick Install (Recommended)

```bash
git clone https://github.com/Nemesis533/Local_LLHAMA.git
cd Local_LLHAMA
./local_LLM_installer.sh
```

Follow the on-screen instructions to configure database and environment.

### Manual Install

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

Requires Python 3.10+ (3.12 recommended).

2. **Setup Database:**

See [DATABASE_SETUP.md](DATABASE_SETUP.md) for PostgreSQL configuration.

3. **Setup Ollama:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b  # or your preferred model
```

4. **Configure environment:**

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
- `HA_BASE_URL`: Home Assistant URL (e.g., `http://homeassistant.local:8123`)
- `HA_TOKEN`: Long-Lived Access Token from HA Profile settings
- `OLLAMA_IP`: Ollama server IP:port (e.g., `192.168.1.100:11434` or `localhost:11434`)
- `ALLOWED_IP_PREFIXES`: Comma-separated IP prefixes for web UI access

**Important:** Never commit `.env` to version control.

![Login Page](screenshots/login_window.png)

## Configuration

### Configuration Presets

**Applying Presets:**

Via CLI:
```bash
python preset_manager.py apply <preset_id>
```

Via Web UI:
1. Navigate to Admin Panel → Presets tab
2. Review preset details and requirements
3. Click "Apply This Preset"
4. Restart system for changes to take effect

Custom presets can be created through the web UI or by adding JSON files to `local_llhama/settings/presets/`.

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

Contains LLM model settings, ChatHandler configuration, TTS language mappings, and other non-sensitive configuration.
 Automatically updated when presets are applied. Modified via Settings_Loader.

**ChatHandler Configuration:**
- `max_tokens`: Maximum LLM response length (512-32768) - to keep things reasonably reactive and not overwhelm the context, reccommend staying at 6144 max for 20B, increase for bigger models.
- `default_context_words`: Initial conversation context window (50-2000) - to not overwhelm context, recommend staying around 800-1000 works max for 20B models; increase for bigger models.
- `min_context_words`: Minimum context before reduction (50-1000) 
- `context_reduction_factor`: Rate of context reduction when limits reached (0.1-0.9)

### web_search_config.json

Configures web information sources (news, Wikipedia, etc.) with allowed websites, max results, and timeout settings.
 
 
## Orchestration Flow

### Voice Pipeline (Sequential State Machine)

1. **Wake Word Detection** → OpenWakeWord monitors for trigger phrase
2. **Audio Capture** → Adaptive noise floor detection (3-10s recording)
3. **Speech-to-Text** → Whisper transcription (model size based on preset)
4. **Orchestration Layer** → Task decomposition and routing begins

### Chat Pipeline (Parallel Multi-User)

1. **WebSocket Input** → Real-time message from user
2. **Context Injection** → Per-user conversation history (last 3 exchanges) + previous memory search
3. **Orchestration Layer** → Immediate parallel processing

### Core Orchestration Process

**Phase 1: Intent Analysis**
- Natural language input → LLM via Ollama
- Multi-pass prompt: Base reasoning → Decision logic → Safety checks
- Output: Structured intents with backend routing information

**Phase 2: Parallel Backend Execution**
- **Home Assistant**: Device control via REST API (fuzzy entity matching)
- **Calendar Database**: Event CRUD operations (PostgreSQL)
- **Web Services**: Weather (Open-Meteo), News (GDELT), Knowledge (Wikipedia)
- **Custom Functions**: Reflection-based discovery via `command_schema.txt`

**Phase 3: Response Synthesis**
- Aggregate backend results
- Context-aware natural language generation
- Language detection and response localization
- Adaptive context window adjustment based on latency

**Phase 4: Output Delivery**
- **Voice**: Piper TTS synthesis + audio playback
- **Chat**: WebSocket streaming with Markdown rendering
- **Logging**: Comprehensive audit trail with dev mode

### Adaptive Context Management Example

```
Initial Request: 400 word context window
   ↓
[Latency > 20s detected]
   ↓
Context Reduction: 400 → 280 → 196 → 137 → 100 words
   ↓
[Success < 10s]
   ↓
Context Recovery: Gradual expansion on subsequent requests
```

**Why This Matters:** Prevents timeout cascades while maintaining conversation quality. System self-tunes based on hardware performance.
  
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

## Dependencies

Key libraries used in this project include:

Lowest supported python version is 3.10, but 3.12 is recommended.

- `torch` (required by openai-whisper for audio processing)
- `openai-whisper` (speech-to-text)
- `openwakeword` (wake word detection)
- `piper-tts` (text-to-speech)
- `pygame` (audio playback)
- `pyaudio` (audio I/O)
- `flask`, `flask-socketio` (web UI and real-time communication)
- `psycopg2-binary`, `asyncpg` (PostgreSQL integration)
- `requests` (HTTP client for Ollama and web APIs)

**Note:** While `torch` is required for Whisper's audio processing, the system uses Ollama for all LLM inference.

All dependencies are listed in `requirements.txt`.

## License

This project is licensed under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license.

You are free to:

- **Share** — copy and redistribute the material in any medium or format  
- **Adapt** — remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:

- **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made.

Read the full license here: [https://creativecommons.org/licenses/by/4.0/](https://creativecommons.org/licenses/by/4.0/)

## Acknowledgments

- OpenAI for Whisper [https://github.com/openai/whisper]
- Piper TTS by rhasspy [https://github.com/rhasspy/piper]
- OpenWakeWord by dscripka [https://github.com/dscripka/openWakeWord]
- Home Assistant open-source platform [https://www.home-assistant.io/]
- GDELT Project for real-time global event data [https://www.gdeltproject.org/]
- Developers of Pygame ([https://github.com/pygame/pygame]) and other community-driven tools

## Contributing

Contributions and suggestions welcome! See "Future Work" for ideas. Response time may vary due to limited availability.

Open discussions before submitting major PRs.

## Roadmap: Advancing Orchestration Patterns

### Completed Orchestration Features (v0.7)

**Core Middleware:**
- Multi-backend parallel execution (HA + Calendar + Web APIs)
- Adaptive context management with automatic scaling
- Multi-pass prompt engineering with modular layers
- Hardware-validated preset system (8-24GB VRAM)

**Production Features:**
- One-command installation with dependency resolution
- Interactive configuration wizard
- Dual pipeline architecture (voice + chat)
- Per-user context isolation and memory search
- Role-based access control
- Real-time WebSocket communication
- PostgreSQL with vector embeddings

### v0.8 — Enhanced Orchestration

**Based on feedback and testing, the scope of work was updated**

**Improved Backend Integration:**
- Streamlined custom function integration with examples 
- Automation creation via LLM function calling ✓
- Enhanced error recovery with retry logic ✓
- Backend health monitoring with real-time system metrics (CPU, RAM, GPU) ✓
- ADDED: improved memory search that now also include assistant replies and temporal information ✓

**Performance Optimization:**
- Context caching for repeated queries ✓
- Predictive context scaling/summaries based on intent complexity ✓
~~- Parallel intent execution benchmarking~~

### v0.85 — Coding Abilities
- Creation of dedicated fnctionality for a coding assistant that integrates with vscode.

### v0.9 — Advanced Capabilities

**Orchestration Expansion:**
- Vision capabilities with multimodal routing
- Contextual model swapping (task-specific model selection)
- Test coverage for orchestration patterns
- Performance regression testing

### v0.95 — Advanced Capabilities

**Additional API support:**
- ADDED: plex and jellyfin media control functions

### v1.0 — Production Release

**Goal:** Reference implementation for local LLM orchestration

- Package distribution (pip/apt installable)
- Comprehensive orchestration documentation
- Reusable patterns for custom deployments
- Community preset contributions


## Note

Developed to explore orchestration patterns that enable smaller LLMs to achieve production-grade capability on consumer hardware. This is not about replacing Ollama or Home Assistant—it's about intelligently coordinating them.

The patterns demonstrated here (adaptive context, multi-pass prompts, parallel backend routing) are reusable beyond smart home control. Contributions and suggestions welcome.