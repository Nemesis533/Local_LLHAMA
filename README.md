# Local_LLAMA: Offline, Multilingual Smart Home Voice Assistant

**Local_LLAMA** is a local-first, multilingual, LLaMA-powered voice assistant that integrates seamlessly with [Home Assistant](https://www.home-assistant.io/). Designed for privacy, flexibility, and natural interaction, it allows users to control smart home devices using natural language — all without relying on the cloud or requiring exact device names. Being an indipendent system that can run on base linux and interface with HA (or potentially other domotics systems) via API, it also bypasses many of the compatibility restrictions that running a similar system in HA have (such as smart-speaker compatibility).

## Features

- Wake word detection using `OpenWakeWord`
- Voice recording with adaptive noise floor detection
- Whisper-based speech-to-text conversion
- LLaMA 3.1 (8B) LLM for command parsing and entity resolution
- Optional PromptGuard safety layer (LLaMA 3.2 3B fine-tuned model)
- Multilingual support: English, French, Spanish, Italian, German, Russian
  This allows you to call the command in any of the supported languages and not have to worry about it - you can say "la lumière du salon" for "living room light"
- Fuzzy device/entity matching using dynamic Home Assistant entity list; for optmization purposes, a manual list of devices can also be assigned instead of filtering the full list from HA.
  This solves the problem of having to call devices by the exact name that they are saved under - you can now say "light above the desk" to call the "desk light".
- Execute multiple commands in a single sentence
- Basic web interface for output monitoring and connection status (expansion and system control planned)
- Ability to integrate non-Home Assistant devices and commands with the same pipeline as the one used for Home Assistant.

## System Requirements

| Component | Recommended |
|----------|-------------|
| CPU      | 4–8 cores (tested with Xeon E5-2640 v4) |
| RAM      | 8 GB recommended |
| GPU      | NVIDIA RTX 4060 Ti or better (16GB+ VRAM) | for 12GB, see notes below.
| OS       | Linux (tested on Ubuntu 24.04) | Shoudl work fine on 22.04 as well.

- The system is GPU-accelerated; most of the computational load is handled on the GPU. The current setup uses about 14.5GB on the RTX 4060TI
- You can potentially get away with 12GB VRAM if you disable the guard model and use the small whisper model. Prompt guard tooglign currently not implemented.
- CPU and RAM requirements are minimal as most of the work is done on the GPU.
- The system was tested in an Ubutnu VM in Proxmox with GPU passthru.
- Typical latency from command to execution: 1–4 seconds.

## Installation

1. Clone the repository:

2. Run the install script:

```bash
chmod +x install.sh
./install.sh
```

This installs all dependencies listed in `requirements.txt` and prepares the environment.

## object_settings.json 

This file contains json-stored values for the variables that can be changed in the program. When adding a user-settable variable, you'll have to create the variable in 
a class and add the class and the variable name/value/type to the file like so:

  "HomeAssistantClient": {
    "base_url": {"value": "http://homeassistant.local:8123", "type": "str"},
    "token": {"value": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9[...]2RYjfAyJ3MxKo9VLQXlE",
     "type": "str"},
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
  
 In addition to Home Assistant related values, you'll also see the path where to fetch the LLM from (in my setup, they are on a path different from the standard huggingface one) 
 as well as settings for the webui and the wakeword sensitivity.
 
 You can get more details on how the file is used inside the SettingsLoader.py class.
 

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
   - The transcribed text and a list of entities from Home Assistant are passed to a LLaMA 3.1 (8B) model. By default models are loaded in 8bit.
   - Entities can be supplied manually or auto-fetched from Home Assistant (requires access token and URL in the settings file). You can also exclude devices from the entities list in the same manner.
   - The model identifies the appropriate devices, actions, and parameters, then generates a Home Assistant-compatible JSON command.

5. **Command Execution**  
   - If the generated JSON is valid, it is sent to Home Assistant via the API and executed.
   - If no actionable command is detected, the system reports a failure.
   - For actions not supported by Home Assistant directly, you can place them in JSON format in the "command_schema.txt"; 
	 The actions will be matched via reflection to a function named the same as the action, and then executed via the command_queue

6. **Feedback and Output**  
   - A TTS engine provides spoken confirmation or failure.
   - Output and logs are also available through a simple web UI for basic monitoring.
  
7. **FSM Diagram**

   Below you can see an FSm diagram of how the system functions

   ![alt text](https://github.com/Nemesis533/Local_LLHAMA/blob/main/FSM_diagram_0.png)

## Example Commands

```text
Turn off the kitchen lights and turn on the living room lamp.

Éteins la lumière du salon et allume la clim dans la chambre. (French)

Apaga la luz de la cocina y enciende la lámpara del salón. (Spanish)
```

- Natural, free-form commands
- Multilingual input
- No need for exact device names
- Multiple commands per sentence

## Dependencies

Key libraries used in this project include:

Lowest supported python version is 3.10, but 3.12 is recommended.

- `torch`, `transformers` (LLaMA model support)
- `whisper` (OpenAI's STT)
- `openwakeword` (wake word detection)
- `TTS` (Coqui TTS engine)
- `pygame` (audio playback)
- `librosa`, `wave` (audio processing)
- `flask` (basic web UI)

All dependencies are listed in `requirements.txt`.

## Project Structure

```
.
├── dev/
│   ├── run-dev.py            # script to run the project in dev mode, preparign to create the pip installer
│   └── wikidoc_creator.py    # script for auto-generation of wiki-doc style docs from comments
├── FSM_diagram_0.png         # FSR diagram 
├── local_llhama/
│   ├── command_schema.txt    # Contains commands that are outside of Home Assistant scope
│   ├── HA_Interfacer.py      # Home Assistant API communication
│   ├── __init__.py           # 
│   ├── LLM.py                # Class to handle LLAMA LLMs and inference logic
│   ├── logger.py             # Used for logging across the system
│   ├── Runtime.py            # Entry point
│   ├── settings/             # Contains the .json settings files for the system, with object_settings.json beign the main one
│   ├── SettingsLoader.py     # Class dedicated to loading settings and applying them using reflection
│   ├── Sound_And_Speech.py   # Contains all the sound-related elements, such as STT, TTS, sound player, etc
│   ├── sounds/               # Folder containing system sounds 
│   ├── StateMachine.py       # SFM which handles state transition
│   ├── static/               # Contains the webui elements
│   └── WebService.py         # WebService for webui backend and other web services for the system
├── local_LLM_installer.sh    # Setup script
├── README.md                 # Readme
├── requirements.txt          # Dependency list
└── wiki_docs/                # wiki-doc style documentation folder.
```

## WebUI

A basic webui has been implemented - it allows to the stdout of the system and loads the object_settings file values; these can eb adited manually and saved for easier access. 
Currently there is no input control, ability to restart the system has been implemented.

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
- Support for remote LLMs (passing commands to an LLM instanced elsewhere on the network)
- Current WIP: Proper webUI with control (start/stop/etc) for the system - restart implemented.
- Current WIP: Prompt Guard toogle.
- Perfomance optimizations
- Support for multiple LLMS (for instance one fine tuned on commands and another for NL responses).

- We'll see what else comes to mind!

## Please Note

This project was developed with the purpose of creating a more versatile and useful domotic assistant during spare time - suggestions to improve the system/code quality are welcome.
As my main field of expertise is not coding/AI, there will be things to improve, but I hope you find the basis usefule nonetheless.
Comments and markup will also be revised in a more..."human form" (most have been written with ChatGPT to save time).


---

Made to bring natural language control to smart homes — privately, locally, and powerfully.
