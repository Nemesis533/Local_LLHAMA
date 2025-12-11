# Local_LLHAMA: System Architecture

## Introduction

Local_LLHAMA is a self-hosted AI assistant platform providing voice and chat interfaces for smart home control, calendar management, and conversational AI—all running locally without cloud dependencies. This document explains the architectural decisions, system design, and implementation philosophy behind the platform.

## Architectural Philosophy

### Core Design Principles

Three fundamental requirements shaped every architectural decision:

**Privacy by Architecture**: Rather than adding privacy features to a cloud-based design, Local_LLHAMA inverts the model—all processing happens locally by default. Internet access is opt-in and limited to specific functions (news, weather, Wikipedia). This isn't achieved through encryption or anonymization; it's fundamental to how data flows through the system.

**Hardware Pragmatism**: The architecture accommodates real-world hardware constraints, from 8GB GPUs running English-only models to multi-GPU setups supporting six languages. Configuration presets encode these hardware tradeoffs, allowing users to optimize for their specific setup without deep technical knowledge.

**Failure Isolation**: Component failures must not cascade. A crashed web interface shouldn't interrupt voice commands. An LLM timeout shouldn't freeze the microphone. This requirement drove process-based isolation and careful state management throughout the system.

### Process Separation

Early prototypes used a single-process Flask application handling both web and voice, which created immediate problems: blocking Flask handlers delayed voice processing, Socket.IO's event loop interfered with audio capture, and web server reloads killed the voice pipeline.

The solution: **process separation as first-class architecture**. The voice pipeline runs in the main process with direct hardware access. The web server runs in an isolated subprocess. Multiprocessing queues enable communication without shared state, ensuring a crash in one process leaves the other operational.

## System Architecture

### Component Hierarchy

```
Runtime Supervisor (main process)
├── System Controller
│   ├── Settings Loader (YAML configuration)
│   ├── Home Assistant Client (device control)
│   ├── Ollama Client (LLM inference)
│   └── State Machine (voice pipeline)
│       ├── Audio Components (Whisper, Piper, OpenWakeWord)
│       ├── Command Processor (function calling)
│       └── Worker Threads (non-blocking audio)
│
└── Web Server (subprocess)
    ├── Flask + SocketIO (HTTP/WebSocket)
    ├── Authentication Manager (users, sessions)
    ├── Route Blueprints (modular endpoints)
    └── Chat Handler (independent thread, chat pipeline)
```

**Runtime Supervisor**: System entry point and restart coordinator. Creates multiprocessing queues, initializes the System Controller, and spawns the Web Server subprocess. Coordinates configuration changes and system restarts without losing the web interface.

**System Controller**: Manages system lifecycle—loading YAML configuration, connecting to external services (Home Assistant, Ollama, PostgreSQL), and initializing the state machine. Serves as the dependency injection point for all major components.

**State Machine**: Voice interaction pipeline. Voice is inherently sequential (speak → listen → process → respond), making it a natural fit for finite state machine architecture. Each state handles a specific phase with clear transition conditions.

**Web Server**: Independent Flask process preventing blocking behavior from affecting voice. Handles HTTP/WebSocket for the web interface, manages user authentication, and runs the Chat Handler thread for concurrent chat processing.

### Dual-Pipeline Architecture

Local_LLHAMA recognizes that voice and chat are fundamentally different modalities:

| Aspect | Voice Pipeline | Chat Pipeline |
|--------|---------------|---------------|
| **Concurrency** | Sequential (one at a time) | Concurrent (multiple users) |
| **Latency** | Low (<5s total) | Higher acceptable (~10s) |
| **Hardware** | Exclusive (mic/speakers) | Network-based (browser) |
| **Context** | Temporal (last 3 exchanges) | Persistent (full history) |
| **Error Handling** | Disruptive (breaks flow) | Recoverable (retry button) |

Rather than compromising both in a single pipeline, Local_LLHAMA implements parallel paths sharing infrastructure (LLM, Home Assistant, database) but with independent control flow optimized for each interaction pattern.

## Data Flow and Communication

### Inter-Process Communication

Process isolation requires careful communication design using four unidirectional multiprocessing queues:

**`action_message_queue` (Web → State Machine)**: User text input from web interface intended for voice-style processing. State machine polls this while LISTENING, processes text as if from speech recognition.

**`web_server_message_queue` (State Machine → Web)**: Status updates, transcriptions, voice interaction progress. Enables web interface to display what the system heard and decided—critical for user confidence and debugging.

**`chat_message_queue` (Web → Chat Handler)**: Chat messages bypass state machine entirely, going directly to Chat Handler thread. Enables chat concurrent with voice without state conflicts.

**`preset_response_queue` (System Controller → Web)**: Configuration change confirmations, especially for preset applications requiring system restart.

Queues are deliberately unidirectional to eliminate deadlock possibilities (process A waits for B while B waits for A).

### Voice Interaction Flow

```
1. Wake Word Detection
   └─> OpenWakeWord (background thread) → flag → LISTENING → RECORDING

2. Audio Capture  
   └─> Record with adaptive noise floor → silence detected → save WAV → PROCESSING

3. Speech Transcription
   └─> Whisper STT → transcribed text + language → WAITING_LLM

4. LLM Query
   └─> Ollama (streaming) + function schemas → execute functions → generate response

5. Speech Synthesis & Playback
   └─> Piper TTS → audio file → playback (background thread) → LISTENING
```

Total system latency: 3-7 seconds depending on hardware and response complexity.

### Chat Interaction Flow

```
1. Message Receipt (WebSocket 'send_chat')
   └─> Queue message with client_id, conversation_id

2. Context Loading
   └─> Query PostgreSQL for conversation history (last 3 exchanges)

3. Streaming Response
   └─> Ollama streaming → emit chunks via WebSocket → execute functions inline

4. Persistence
   └─> Save user message + assistant response to PostgreSQL
```

Multiple concurrent chat sessions supported via thread pool with conversation isolation by user/conversation ID.

## Component Deep-Dive

### State Machine: Voice Pipeline Management

The state machine is a reliability mechanism, not just control flow. Voice involves hardware (microphone, speakers), external services (Ollama, Home Assistant), and user expectations (low latency, natural flow)—all of which can fail.

**State Isolation**: Each state has dedicated handler logic. Failures are caught, logged, and trigger ERROR state transition. ERROR plays error sound, then returns to LISTENING. System remains responsive despite failures.

**Non-Blocking Audio**: Worker threads handle wake word detection and audio playback independently. State machine only checks completion flags, preventing blocking that would make the system feel unresponsive.

**Adaptive Behavior**: Recording state monitors audio amplitude, maintains running noise floor average, and detects silence dynamically. Works in both quiet and noisy environments without configuration.

### Home Assistant Integration: Fuzzy Device Matching

Natural language device control without exact names is a key user-friendly feature. Users can say "turn on the lamp above the desk" or "la lumière du salon" instead of exact device names.

**HADeviceManager** maintains updated entity list from Home Assistant and uses fuzzy string matching (Levenshtein distance) across entity names, friendly names, and areas to find best matches.

Architecture cleanly separates concerns:
- **HAClientCore**: HTTP communication with Home Assistant REST API
- **HADeviceManager**: Entity management and fuzzy matching
- **HACommandExecutor**: Service call execution and result handling
- **HAValidators**: Input sanitization and validation

### LLM Integration: Function Calling

**Ollama Client** abstracts API details, presenting consistent interface regardless of model (Qwen, GPT-OSS, LLaMA, etc.).

**Function Calling**: System injects function schemas into prompt as JSON. Model returns structured JSON for function calls. Command Processor parses, routes to handlers, executes, and appends results to context. Model then generates natural language response.

This enables arbitrary functions without model retraining. Adding new capability requires:
1. Implement function handler
2. Add function schema to prompt  
3. Register handler in Command Processor

**Streaming**: For chat, Ollama client processes streaming chunks, detects complete JSON function calls mid-stream, executes them, and continues. Enables complex interactions like "turn off lights and tell me weather" to feel fluid.

### PostgreSQL: Persistence Layer

Three primary roles:

**Authentication & Authorization**: User credentials, sessions, role-based permissions (bcrypt password hashing, Flask-Login session management).

**Calendar & Reminders**: Unified event system (reminders, appointments, alarms) with recurrence, notifications, and per-user isolation.

**Conversation Persistence**: Chat conversations stored for context continuity. Chat Context Manager limits what's sent to LLM (last 3 exchanges) while preserving full history.

**PostgreSQL Client** wrapper provides sync (psycopg2) and async (asyncpg) interfaces, connection pooling (2-10 connections), and context managers for safe transactions. All queries use parameterized statements preventing SQL injection.

## Configuration and Adaptability

### Preset System

Hardware variability is a major challenge in self-hosted AI. Local_LLHAMA's preset system provides vetted configurations:

- **english_only_small** (8GB VRAM): Qwen3:8B, single English TTS, minimal footprint
- **english_only_large** (16GB VRAM): GPT-OSS:20B, higher quality
- **multi_lingual_small** (16GB VRAM): Qwen3:14B, six languages
- **multi_lingual_large** (2×24GB VRAM): GPT-OSS:20B, full multilingual

Applying a preset updates YAML, triggers system restart via Runtime Supervisor, reloads all components. Web server stays alive, active chats preserved—only main process restarts.

### Configuration Hierarchy

```
1. Environment Variables (.env)
   └─> Secrets, deployment-specific (DB credentials, API tokens)

2. YAML Configuration (settings.yaml)  
   └─> Model selection, feature flags, LLM parameters

3. Database Settings
   └─> User preferences, runtime state
```

**Settings Loader** reads YAML, validates, distributes configuration via dependency injection. Components receive only needed settings—audio manager doesn't know database credentials, web server doesn't know Whisper model selection.

## Performance Considerations

### Latency Optimization

- **Streaming**: LLM responses, TTS synthesis, audio playback all stream to minimize perceived wait time
- **Background Processing**: Wake word detection runs continuously in dedicated thread—no startup delay
- **Model Selection**: Whisper "turbo" vs "large", Piper quality levels—presets encode tradeoffs
- **Connection Pooling**: Database, Home Assistant, Ollama connections reused

### Memory Management

- **Lazy Loading**: TTS voice models loaded only when needed for a language
- **Context Window Management**: Chat context dynamically adjusted—reduces on timeout, enables graceful degradation
- **Process Isolation**: Independent memory per subprocess—web server memory growth doesn't impact voice

**Typical Memory Usage**:
- Core System: ~3-4 GB RAM
- Whisper Turbo: ~1 GB RAM
- Piper TTS: ~100-200 MB per language
- PostgreSQL: ~100-500 MB RAM
- **Total**: ~4-6 GB RAM

**VRAM by Preset**:
- english_only_small: ~8 GB
- english_only_large: ~14-16 GB
- multi_lingual_small: ~14 GB
- multi_lingual_large: ~14-16 GB per GPU

## Deployment Architecture

### Single-Machine Deployment

Most common: everything on one Linux server (Local_LLHAMA, PostgreSQL, Ollama, optionally Home Assistant). Hardware requirements: 4-8 CPU cores, 8-16GB RAM, 8-24GB VRAM depending on preset.

Process isolation ensures component failures are contained even on single machine. Ollama crash → voice pipeline enters ERROR state and waits. PostgreSQL unavailable → authentication error handling, system logs without crashing.

### Distributed Deployment

For dedicated GPU servers, Ollama runs on separate machine. Ollama client uses HTTP—pointing to remote IP is configuration change. Enables:
- GPU server in datacenter/closet with powerful hardware
- Application server on lightweight VM/Raspberry Pi
- ~1 second additional latency over gigabit Ethernet (acceptable for most uses)

### Security Model

Assumes deployment on trusted local network:

- **IP Whitelisting**: Web server enforces IP prefix whitelist—only local network devices connect
- **Authentication**: Password-based with bcrypt, role-based permissions
- **Secure Communication**: HTTP within local network; supports HTTPS via reverse proxy (nginx, Caddy)
- **No Cloud Communication**: Except explicitly enabled web search, all communication stays local

## Error Handling and Reliability

### Failure Domains

- **Audio Hardware**: State machine → ERROR → play sound → LISTENING
- **LLM Timeout**: Chat reduces context and retries; voice uses fallback response
- **Home Assistant Unavailable**: Commands fail gracefully with notification; other functions continue
- **Database Loss**: Sessions continue from memory; writes queued and retried
- **Web Server Crash**: Voice pipeline continues; web server restarts don't affect voice

### Recovery Strategies

**Automatic Recovery**: Audio device errors reinitialize audio. LLM timeouts reduce context and retry. Connection failures use exponential backoff.

**Graceful Degradation**: Optional feature failures (web search APIs) don't affect core functionality. Embeddings unavailable → fall back to non-semantic matching.

**Manual Intervention**: Web interface "Restart System" button triggers coordinated restart via Runtime Supervisor—handles configuration changes and unrecoverable states without SSH access.

## Technology Stack

**Core**: Python 3.10+, Flask 3.0.3, SocketIO 5.11, PostgreSQL 13+, Ollama

**AI/ML**: OpenAI Whisper (STT), Piper TTS 1.2.0 (6 languages), OpenWakeWord 0.6.0, Ollama models (Qwen3, GPT-OSS)

**Audio**: PyAudio 0.2.14, Pygame 2.5.2, NumPy 1.26.4, Torch 2.1.2

**Database**: psycopg2-binary 2.9.9 (sync), asyncpg 0.29.0 (async)

**Web**: Flask-Login 0.6.3, Flask-CORS 4.0.1, Requests 2.31.0, BeautifulSoup4 4.12.3

**Utilities**: psutil 5.9.8, python-dotenv 1.0.1, BCrypt

## Future Architectural Directions

**Multi-Room Audio**: Multiple state machine instances coordinating shared resources (LLM, Home Assistant). Process-based architecture makes this feasible—each room becomes a process.

**Plugin System**: Function calling already supports arbitrary functions. Formal plugin API would enable third-party extensions registering schemas and handlers at runtime.

**Horizontal Scaling**: Web server could run multiple instances behind load balancer. Chat sessions are stateless beyond database.

**Mobile Client**: WebSocket-based chat is network-accessible—mobile app would be different frontend for same APIs.

## Conclusion

Local_LLHAMA's architecture demonstrates that privacy and capability are not opposing forces. Through careful consideration of failure modes, performance constraints, and interaction patterns, it's possible to build a fully-featured AI assistant running entirely on hardware you control.

Key architectural elements:
- **Process isolation** contains failures and prevents blocking
- **Queue-based communication** eliminates shared state bugs  
- **Dual-pipeline architecture** optimizes for voice vs. chat UX differences
- **Preset system** acknowledges hardware diversity
- **Function calling** enables extensibility without model retraining
- **Component-based design** ensures maintainability

This architecture isn't the simplest possible—a monolithic Flask app would be fewer lines. But it's built for reliability, privacy, and real-world deployment constraints. It demonstrates that local-first AI assistants can match cloud services in capability while exceeding them in privacy and user autonomy.

---

**For detailed API documentation, database schemas, route definitions, and code-level documentation, see the auto-generated wiki and API docs in the `dev/` directory and `Local_LLHAMA.wiki/`.**
