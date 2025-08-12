import os, struct, queue, pyaudio
from dotenv import load_dotenv
import webrtcvad
from openwakeword.model import Model


load_dotenv()
CHANNELS = 1
RATE = 16000
MS = 80
FRAME_BYTES = 2 * CHANNELS
SAMPLES_PER_80MS = RATE * MS // 1000  # 1280 samples @ 80ms


def init_listener():
    """Initialize the listener."""
    ww_model = Model()
    vad_model = webrtcvad.Vad(2)

    p = pyaudio.PyAudio()
    stream = p.open(rate=RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=SAMPLES_PER_80MS
    )
    
    return stream, ww_model, vad_model

def split_20ms_frames(frame80_bytes: bytes):
    """Yield four 20 ms (320-sample) raw PCM chunks from an 80 ms (1280-sample) frame."""
    # 16-bit mono => 2 bytes/sample; 320 samples * 2 = 640 bytes
    for i in range(4):
        start = i * 640
        yield frame80_bytes[start:start + 640]


def listener_thread(q_utterance: queue.Queue):
    """
    Owns the microphone:
    - wake-word detection
    - VAD segmentation producing an 'Utterance'
    """
    stream, ww_model, vad_model = init_listener()

    voiced_once = False
    collecting = False   # are we buffering an utterance?
    buf        = []
    silence    = 0       # VAD silence counter

    print("[Listener started]")
    while True:
        # pcm = stream.read(FRAME, exception_on_overflow=False)
        # frame = struct.unpack_from(f"{FRAME}h", pcm)
        pcm = stream.read(SAMPLES_PER_80MS, exception_on_overflow=False)
        frame = struct.unpack_from(f"{SAMPLES_PER_80MS}h", pcm)

        scores = ww_model.predict(frame)
        score = scores.get("hey_jarvis", 0.0)  # or: max(scores.values(), default=0.0)

        # Wake-word triggers collection
        if not collecting and score > 0.7:
            collecting, buf, silence = True, [], 0
            print("🔔 Wake word detected")
            continue

        if collecting:
            buf.extend(frame)

            # run VAD over 4×20 ms subframes
            for sub in split_20ms_frames(pcm):
                if vad_model.is_speech(sub, RATE):
                    voiced_once = True
                    silence = 0
                else:
                    if voiced_once:  # only count silence after we heard voice
                        silence += 1

            if silence > 30:              # ≈0.4 s gap
                collecting = False
                voiced_once = False
                q_utterance.put(buf.copy())     # hand over to ASR
                buf.clear()
                print("📨 Utterance queued")
