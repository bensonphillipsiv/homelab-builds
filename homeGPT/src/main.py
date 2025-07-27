"""main.py
Voice pipeline:
  mic → Porcupine (wake) → Cobra (VAD) → Whisper (ASR) → GPT-4 (Home-Assistant)
"""

import os, struct, time, queue, threading, numpy as np, pyaudio
import pvporcupine, pvcobra, asyncio            # wake / VAD
from faster_whisper import WhisperModel         # ASR
from dotenv import load_dotenv
from gpt_client import chat_with_gpt            # LLM + MCP
load_dotenv()
PICOVOICE_KEY = os.getenv("PICOVOICE_KEY")

# Queues: mic → ASR
mic_q = queue.Queue(maxsize=100)   #  ~3 s ring-buffer (unused now but handy)
asr_q = queue.Queue()

# Porcupine (wake-word) & Cobra (voice activity)
porcupine = pvporcupine.create(
    access_key=PICOVOICE_KEY,
    keywords=["jarvis", "bumblebee"],
)
cobra  = pvcobra.create(access_key=PICOVOICE_KEY)
FRAME  = porcupine.frame_length
RATE   = porcupine.sample_rate

# Whisper ASR model
whisper = WhisperModel("base.en", device="cpu", compute_type="int8")

# Mic capture + wake-word thread
def listen_loop():
    """Continuously read mic frames, detect wake word, buffer speech."""
    p = pyaudio.PyAudio()
    stream = p.open(rate=RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=FRAME)

    collecting = False   # are we buffering an utterance?
    buf        = []
    silence    = 0       # VAD silence counter

    while True:
        pcm = stream.read(FRAME, exception_on_overflow=False)
        frame = struct.unpack_from(f"{FRAME}h", pcm)

        # Wake-word triggers collection
        if not collecting and porcupine.process(frame) >= 0:
            collecting, buf, silence = True, [], 0
            print("🔔 Wake word detected")
            continue

        if collecting:
            buf.extend(frame)
            voice_prob = cobra.process(frame)

            if voice_prob > 0.9:
                silence = 0                   # speaking
            elif voice_prob < 0.3:
                silence += 1                  # silence frames
                if silence > 20:              # ≈0.4 s gap
                    collecting = False
                    asr_q.put(buf.copy())     # hand over to ASR
                    buf.clear()
                    print("📨 Utterance queued")

threading.Thread(target=listen_loop, daemon=True).start()

# Whisper ASR → GPT worker thread
def asr_loop():
    """Transcribe queued audio and pass text to GPT."""
    while True:
        buf = asr_q.get()

        pcm_f32 = np.array(buf, dtype=np.int16).astype(np.float32) / 32768.0
        start   = time.perf_counter()
        segments, _ = whisper.transcribe(pcm_f32, beam_size=5, vad_filter=False)
        text = " ".join(s.text for s in segments).strip()
        print(f"🗣️  {text}  ({time.perf_counter()-start:.2f}s ASR)")

        reply = chat_with_gpt(text)
        print(f"🤖  {reply}")

threading.Thread(target=asr_loop, daemon=True).start()

# ──────────────────────────── Main loop ─────────────────────────────
threading.Event().wait()   # keep process alive (all work in daemons)
