from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig
from TTS.config.shared_configs import BaseDatasetConfig
from TTS.tts.models.xtts import XttsArgs
import torch
from TTS.api import TTS
import os

os.environ["COQUI_TOS_AGREED"] = "1"

device = "cuda" if torch.cuda.is_available() else "cpu"

# Allow the custom config safely
torch.serialization.add_safe_globals([XttsConfig])
torch.serialization.add_safe_globals([XttsAudioConfig])
torch.serialization.add_safe_globals([BaseDatasetConfig])
torch.serialization.add_safe_globals([XttsArgs])

# Initialize TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Run TTS
wav = tts.tts(
    text="Hello world!", 
    speaker_wav="my/cloning/audio.wav", 
    language="en"
)

tts.tts_to_file(
    text="Hello world!", 
    speaker_wav="my/cloning/audio.wav", 
    language="en", 
    file_path="output.wav"
)
