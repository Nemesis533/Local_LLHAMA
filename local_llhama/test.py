import torch
from chatterbox.tts import ChatterboxTTS
import os

# Agree to Coqui TTS terms
os.environ["COQUI_TOS_AGREED"] = "1"

# Select device
device = "cuda" if torch.cuda.is_available() else "cpu"


# Load the XTTS-2 TTS model
model = ChatterboxTTS.from_pretrained(device=device)

speaker_wav_path = "/home/llhama-usr/Local_LLHAMA/local_llhama/sounds/female.wav"
if not os.path.isfile(speaker_wav_path):
    raise FileNotFoundError(f"Speaker audio not found: {speaker_wav_path}")

text = "Hello world!"

# Generate waveform in memory
wav = model.generate(text, audio_prompt_path=speaker_wav_path)

print("TTS output saved to output.wav")
