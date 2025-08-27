import numpy as np
import sounddevice as sd

sr = 48000
t = np.linspace(0, 2, 2*sr, endpoint=False)
tone = 0.1 * np.sin(2 * np.pi * 440 * t)

sd.play(tone, sr, device=0)
sd.wait()
