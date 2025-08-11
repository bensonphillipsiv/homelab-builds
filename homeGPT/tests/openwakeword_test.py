import time, wave
import pyaudio, numpy as np, struct
import webrtcvad
from openwakeword.model import Model

RATE = 16000
FRAME_80MS = 1280          # (80 ms @ 16 kHz)
THRESHOLD_ON  = 0.80
THRESHOLD_OFF = 0.60
COOLDOWN_FRAMES = 5        # ~400 ms

# VAD settings
VAD_MODE = 2               # 0=loose .. 3=aggressive
SILENCE_20MS_TO_END = 50   # 50 * 2000 ms = 2s
SAVE_WAV = True            # set False to skip saving utterances

def split_20ms_frames(frame80_bytes: bytes):
    """Yield four 20 ms (320-sample) s16le chunks from an 80 ms (1280-sample) frame."""
    # 16-bit mono => 2 bytes/sample; 320 samples * 2 = 640 bytes
    for i in range(4):
        start = i * 640
        yield frame80_bytes[start:start + 640]

def save_wav(pcm_bytes: bytes, path: str):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm_bytes)

model = Model()
vad = webrtcvad.Vad(VAD_MODE)

pa = pyaudio.PyAudio()
stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                 input=True, frames_per_buffer=FRAME_80MS)

prev_score = 0.0
cooldown = 0

# Recording state
recording = False
rec_buf = bytearray()
voiced_once = False
silence_20ms = 0
utt_idx = 0

print("Listening...")
while True:
    # read one 80 ms frame
    frame80_bytes = stream.read(FRAME_80MS, exception_on_overflow=False)
    frame80_i16 = np.frombuffer(frame80_bytes, dtype=np.int16)

    # wake-word score
    scores = model.predict(frame80_i16)
    score = scores.get("hey_jarvis", 0.0)  # or: max(scores.values(), default=0.0)

    # cooldown to prevent double fires
    if cooldown > 0:
        cooldown -= 1

    # trigger recording on rising edge
    if (not recording) and cooldown == 0 and score >= THRESHOLD_ON and prev_score < THRESHOLD_OFF:
        recording = True
        rec_buf.clear()
        voiced_once = False
        silence_20ms = 0
        print("🔔 Wakeword detected — recording started")
        # short cooldown so immediate second detections don't retrigger
        cooldown = COOLDOWN_FRAMES

    if recording:
        # append current 80 ms to recording
        rec_buf.extend(frame80_bytes)

        # run VAD over 4×20 ms subframes
        for sub in split_20ms_frames(frame80_bytes):
            if vad.is_speech(sub, RATE):
                voiced_once = True
                silence_20ms = 0
            else:
                if voiced_once:  # only count silence after we heard voice
                    silence_20ms += 1

        # stop when we've seen enough trailing silence
        if voiced_once and silence_20ms >= SILENCE_20MS_TO_END:
            recording = False
            print("📨 Utterance complete")
            if SAVE_WAV:
                path = f"utterance_{utt_idx:03d}.wav"
                save_wav(bytes(rec_buf), path)
                print(f"💾 Saved {path} ({len(rec_buf)//2} samples)")
                utt_idx += 1
            rec_buf.clear()
            voiced_once = False
            silence_20ms = 0
            # small cooldown so a new wake can't immediately re-fire on tail noise
            cooldown = COOLDOWN_FRAMES

    prev_score = score
