# Local_LLAMA: Offline, Multilingual Smart Home Voice Assistant

**Local_LLAMA** is a local-first, multilingual, LLaMA-powered voice assistant that integrates seamlessly with [Home Assistant](https://www.home-assistant.io/). Designed for privacy, flexibility, and natural interaction, it allows users to control smart home devices using natural language — all without relying on the cloud or requiring exact device names. Being an indipendent system that can run on base linux and interface with HA (or potentially other domotics systems) via API, it also bypasses many of the compatibility restrictions that running a similar system in HA have (such as smart-speaker compatibility).

## UPDATE - The system is currently being overhauled to improve both performance, maintenability and features; current development branch is 'refactor'

## Features

- Wake word detection using `OpenWakeWord`
- Voice recording with adaptive noise floor detection
- Whisper-based speech-to-text conversion
- NEW! Allows the use of either same-machine instanced model (tested using LLaMA 3.1 (8B) or using an Ollama server LLM for command parsing and entity resolution
- NEW! Allows the user to perform NL queries in addition to just giving HA commands 
- Optional PromptGuard safety layer (LLaMA 3.2 3B fine-tuned model)
- Multilingual support: English, French, Spanish, Italian, German, Russian
  This allows you to call the command in any of the supported languages and not have to worry about it - you can say "la lumière du salon" for "living room light"
- Fuzzy device/entity matching using dynamic Home Assistant entity list; for optmization purposes, a manual list of devices can also be assigned instead of filtering the full list from HA.
  This solves the problem of having to call devices by the exact name that they are saved under - you can now say "light above the desk" to call the "desk light".
- Execute multiple commands in a single sentence
- NEW! Web search integration - ask for news, Wikipedia articles, weather information
- NEW! Mixed command support - combine HA commands with information queries in a single request (e.g., "turn on the lights and tell me the weather")
- NEW! Web interface for controlling settings, interacting with the system via text, output monitoring and connection status
- Ability to integrate non-Home Assistant devices and commands with the same pipeline as the one used for Home Assistant.

## System Requirements

| Component | Recommended |
|----------|-------------|
| CPU      | 4–8 cores (tested with Xeon E5-2640 v4) |
| RAM      | 8 GB recommended |
| GPU      | NVIDIA RTX 4060 Ti or better (16GB+ VRAM) | for 12GB, see notes below.
| OS       | Linux (tested on Ubuntu 24.04) | Shoudl work fine on 22.04 as well.

- The system is GPU-accelerated; most of the computational load is handled on the GPU. The current setup uses about 14.5GB on the RTX 4060TI with everything loaded locally.
- When using an Ollama server, the core system uses about 6.5. GB of VRAM 
- You can potentially get away with 12GB VRAM if you disable the guard model and use the small whisper model. Prompt guard tooglign currently not implemented.
- CPU and RAM requirements are minimal as most of the work is done on the GPU.
- The system was tested in an Ubutnu VM in Proxmox with GPU passthru.
- Typical latency from command to execution: 1–4 seconds with a single machine and the above HW.
- Multi-machien system was tested with same CPUs but an RTX 2080ti for the main system and the RTX 4060ti for the Ollama server; command execution latency drops to about 1 second, NL queries depend on query lenght and response complexity.

## Installation

1. Clone the repository:

2. Run the install script:

```bash
chmod +x local_LLM_installer.sh
./local_LLM_installer.sh
```

This installs all dependencies listed in `requirements.txt` and prepares the environment.

3. Configure environment variables:

Copy the example environment file and edit it with your credentials:

```bash
cp .env.example .env
```

Edit `.env` and set the following variables:
- `HA_BASE_URL`: Your Home Assistant URL (e.g., `http://homeassistant.local:8123`)
- `HA_TOKEN`: Your Home Assistant Long-Lived Access Token (generate from Profile → Long-Lived Access Tokens)
- `OLLAMA_IP`: Your Ollama server IP and port (if using Ollama)
- `ALLOWED_IP_PREFIXES`: Comma-separated list of allowed IP prefixes for web UI access

**Important**: Never commit your `.env` file to version control. It contains sensitive credentials.

## Configuration

### Environment Variables (.env)

Security-sensitive configuration is stored in a `.env` file in the project root. This file should never be committed to version control.

Required environment variables:
- `HA_BASE_URL`: Your Home Assistant base URL
- `HA_TOKEN`: Your Home Assistant Long-Lived Access Token
- `OLLAMA_IP`: Ollama server IP and port (if using Ollama)
- `ALLOWED_IP_PREFIXES`: Comma-separated IP prefixes allowed to access the web UI

See `.env.example` for a template.

### object_settings.json 

This file contains json-stored values for non-sensitive configuration variables. When adding a user-settable variable, you'll have to create the variable in a class and add the class and the variable name/value/type to the file like so:

  "HomeAssistantClient": {
    "allowed_entities": {
      "value": [
        "light.kitchen_light",
        "light.desk_light",
        "light.couch_light",
        "climate.as35p",
        "climate.as25p"
      ],
      "type": "list"
    },
    "ALLOWED_DOMAINS":{
       "value": ["light", "climate", "switch", "fan", "media_player", "thermostat"],
        "type": "list"}
  },
  
 In addition to Home Assistant related values, you'll also see the path where to fetch the LLM from (in my setup, they are on a path different from the standard huggingface one) as well as settings for the LLM models and other non-sensitive configuration.
 
 **Note**: Sensitive values like API tokens and URLs are now stored in the `.env` file for security.
 
 You can get more details on how the file is used inside the Settings_Loader.py class.
 
### web_search_config.json

This file configures which websites can be accessed for information queries (news, Wikipedia, etc.). You can customize the allowed websites, maximum results, and timeout settings.
 

## How It Works

1. **Wake Word Detection**  
   The system continuously listens using `OpenWakeWord` until the designated wake word is detected. 
   The current wakeword is "Hey Jarvis", as this one worked best for me. The settings file as the "wakeword_thr" parameter to set the sensitivity to the wakeword.

2. **Speech Recording**  
   After the wake word is detected, audio is recorded for a minimum of 3 seconds and a maximum of 10 seconds. The recording may stop earlier if silence is detected based on the dynamic noise floor.

3. **Speech-to-Text (STT)**  
   Audio is transcribed into text using Whisper. Currently the "medium" model is used, which has a good balance for multilingua support while fitting into VRAM.
   Turbo model was not yet tested on this system, but if you just need english support, the "small" model should do.

4. **Command Parsing**  
   - If the guard model is used, the query will first be processed there, and only "safe" queries will be passed on. 
	 The model is based on Llama Guard 3 is a Llama-3.1-8B fine tuned for the specific task in the supported languages.
   - The transcribed text and a list of entities from Home Assistant are passed to the main LLM Model (wether local or an Ollama Server is irrelevant to the pipeline). By default same-machine models are loaded in 8bit.
   - Entities can be supplied manually or auto-fetched from Home Assistant (requires access token and URL in the `.env` file). You can also exclude devices from the entities list in the same manner.
   - The model identifies the appropriate devices, actions, and parameters, then generates a Home Assistant-compatible JSON command; if no entity can be identified, the model provide an NL response to the user query.
   - For information queries (weather, news, Wikipedia), the system can fetch real-time data from the web and provide accurate responses.

5. **Command Execution**  
   - If the generated JSON is valid, it is sent to Home Assistant via the API and executed.
   - If no actionable command is detected, and the user query doesn't "make sense" to the LLM, the system reports a failure.
   - For actions not supported by Home Assistant directly, you can place them in JSON format in the "command_schema.txt"; 
	 The actions will be matched via reflection to a function named the same as the action, and then executed via the command_queue

6. **Feedback and Output**  
   - The Coqui TTS engine provides spoken confirmation or failure text.
   - Output and logs are also available through the web UI for monitoring.
   - The language is automatically detected and returned by the LLM for multilingual support.
  
7. **FSM Diagram**

   Below you can see an FSm diagram of how the system functions

   ![alt text](https://github.com/Nemesis533/Local_LLHAMA/blob/main/FSM_diagram_0.png)

## Example Commands

```text
Turn off the kitchen lights and turn on the living room lamp.

Éteins la lumière du salon et allume la clim dans la chambre. (French)

Apaga la luz de la cocina y enciende la lámpara del salón. (Spanish)

Turn on the desk light and tell me the weather.

What's in the news today?

Tell me about the Eiffel Tower.
```

- Natural, free-form commands
- Multilingual input
- No need for exact device names
- Multiple commands per sentence
- Mixed commands (HA actions + information queries)
- NL queries on any topic
- Real-time web information (news, weather, Wikipedia)

## Dependencies

Key libraries used in this project include:

Lowest supported python version is 3.10, but 3.12 is recommended.

- `torch`, `transformers`, `accelerate` (LLaMA model support)
- `whisper` (OpenAI's STT)
- `openwakeword` (wake word detection)
- `TTS` (Coqui TTS engine)
- `pygame` (audio playback)
- `librosa`, `wave` (audio processing)
- `flask`, `flask-cors` (web UI and API)
- `requests`, `beautifulsoup4` (web search and scraping)
- `python-dotenv` (environment variable management)
- `psutil` (system monitoring)

All dependencies are listed in `requirements.txt`.

## Project Structure

```
.
├── dev/
│   ├── run-dev.py            # Script to run the project in dev mode
│   └── wikidoc_creator.py    # Script for auto-generation of wiki-doc style docs
├── local_llhama/
│   ├── command_schema.txt    # Contains commands outside of Home Assistant scope
│   ├── Home_Assistant_Interface.py  # Home Assistant API communication
│   ├── __init__.py           # Package initialization
│   ├── LLM_Handler.py        # Handles LLaMA LLMs and inference logic
│   ├── Shared_Logger.py      # Logging system used across the project
│   ├── Run_System.py         # Entry point for running the system
│   ├── Runtime_Supervisor.py # Manages web service and system orchestration
│   ├── System_Controller.py  # Main system controller and component orchestration
│   ├── Settings_Loader.py    # Loads settings and applies them using reflection
│   ├── Sound_And_Speech.py   # STT, TTS, wake word detection, audio playback
│   ├── State_Machine.py      # FSM for handling state transitions
│   ├── Web_Server.py         # Web service backend and API endpoints
│   ├── routes/               # Web UI route handlers
│   │   ├── __init__.py
│   │   ├── llm_routes.py
│   │   ├── main_routes.py
│   │   ├── settings_routes.py
│   │   ├── system_routes.py
│   │   └── user_routes.py
│   ├── settings/
│   │   ├── object_settings.json     # Non-sensitive configuration
│   │   └── web_search_config.json   # Web search configuration
│   ├── sounds/               # System sound files
│   └── static/               # Web UI assets (HTML, CSS, JS, images)
├── piper_voices/             # TTS voice models
├── local_LLM_installer.sh    # Setup script
├── .env.example              # Template for environment variables
├── README.md                 # This file
├── requirements.txt          # Python dependencies
└── SECURITY_MIGRATION.md     # Guide for .env migration
```

## WebUI

NEW! 

A webui has been implemented - it allows you to view the stdout of the system and loads the object_settings file values; these can be edited manually and saved for easier access. 
The newest version also allows for text-based interaction with the system, so you can send commands without using voice.


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

Contributions are welcome as well as suggestion on additional features! Take a look at the "Future Work" section too.
Currently I have very limited time to this particular process might be slow.

For significant changes, please open a discussion before submitting a pull request.

## Future Work

This is a basic implementation which I plan on expanding over time (when time permits) by adding:
- ~~Support for remote LLMs (passing commands to an LLM instanced elsewhere on the network)~~ - DONE!
- ~~Proper webUI with control (start/stop/etc) for the system~~ - DONE!
- ~~Prompt Guard toggle~~ - DONE!
- ~~Support for multiple LLMS (for instance one fine tuned on commands and another for NL responses)~~ - DONE!
- ~~Web search integration (news, Wikipedia, weather)~~ - DONE!
- Performance optimizations
- Improving TTS performance and flexibility
- Expanding web search capabilities
- Adding agents for RAG
- Simplify custom function integration
- Dynamic failure message generation
- Better error handling and recovery

- We'll see what else comes to mind!

## Please Note

This project was developed with the purpose of creating a more versatile and useful domotic assistant during spare time - suggestions to improve the system/code quality are welcome.
As my main field of expertise is not coding/AI, there will be things to improve, but I hope you find the basis usefule nonetheless.
Comments and markup will also be revised in a more..."human form" (most have been written with ChatGPT to save time).


---

Made to bring natural language control to smart homes — privately, locally, and powerfully.