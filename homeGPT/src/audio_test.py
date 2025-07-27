import pyaudio, numpy as np, time

CHUNK    = 1024          # frames per read
RATE     = 16000         # Hz
CHANNELS = 1
FORMAT   = pyaudio.paInt16  # 16‑bit signed

pa = pyaudio.PyAudio()
stream = pa.open(format=FORMAT,
                 channels=CHANNELS,
                 rate=RATE,
                 input=True,
                 frames_per_buffer=CHUNK)

print("Listening…  Ctrl‑C to quit")
try:
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16)

        # simple level estimate (root‑mean‑square)
        rms = np.sqrt(np.mean(samples.astype(np.float32)**2))
        print(f"RMS: {rms:6.0f}", end="\r")

        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
