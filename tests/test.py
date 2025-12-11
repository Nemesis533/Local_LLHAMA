import wave
from pathlib import Path

from piper import PiperVoice

# Base directory for voices
voice_dir = Path.home() / "/home/llhama-usr/Local_LLHAMA/piper_voices"

# Define voice models and longer sample texts
languages = {
    "English": {
        "voice": "en_US-amy-medium",
        "text": "Hello, how are you doing today? I hope everything is going well and that you are having a wonderful day.",
    },
    "French": {
        "voice": "fr_FR-siwis-medium",
        "text": "Bonjour, comment ça va aujourd'hui ? J'espère que vous passez une excellente journée et que tout se déroule pour le mieux.",
    },
    "German": {
        "voice": "de_DE-thorsten-high",
        "text": "Hallo, wie geht es dir heute? Ich hoffe, dass alles gut läuft und du einen fantastischen Tag hast.",
    },
    "Italian": {
        "voice": "it_IT-paola-medium",
        "text": "Ciao, come stai oggi? Spero che tutto stia andando bene e che tu stia passando una giornata meravigliosa.",
    },
    "Spanish": {
        "voice": "es_AR-daniela-high",
        "text": "Hola, ¿cómo estás hoy? Espero que todo esté yendo muy bien y que estés disfrutando de un día increíble.",
    },
    "Russian": {
        "voice": "ru_RU-ruslan-medium",
        "text": "Привет, как дела сегодня? Я надеюсь, что у тебя всё хорошо и что твой день проходит замечательно.",
    },
}

# Synthesize speech for each language
for lang, info in languages.items():
    print(f"Generating speech for {lang}...")

    # Load the voice (.onnx and .json must be in the same folder)
    voice_path = voice_dir / f"{info['voice']}.onnx"
    voice = PiperVoice.load(voice_path)

    # Create WAV output
    output_file = f"{lang}_output.wav"
    with wave.open(output_file, "wb") as wav_file:
        voice.synthesize_wav(info["text"], wav_file)

    print(f"Saved {output_file}\n")
