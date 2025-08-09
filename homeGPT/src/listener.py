import os, struct, queue, pyaudio
import pvporcupine, pvcobra
from dotenv import load_dotenv


load_dotenv()
PICOVOICE_KEY = os.getenv("PICOVOICE_KEY")
WAKE_WORDS = ["jarvis", "bumblebee"]


def init_listener():
    """Initialize the listener."""
    # Initialize Picovoice
    porcupine = pvporcupine.create(
        access_key=PICOVOICE_KEY,
        keywords=WAKE_WORDS,
    )
    cobra  = pvcobra.create(access_key=PICOVOICE_KEY)

    RATE = porcupine.sample_rate
    FRAME = porcupine.frame_length

    # Initialize PyAudio Stream
    p = pyaudio.PyAudio()
    stream = p.open(rate=RATE,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=FRAME)
    
    return stream, porcupine, cobra, FRAME


def listener_thread(q_utterance: queue.Queue):
    """
    Owns the microphone:
    - wake-word detection
    - VAD segmentation producing an 'Utterance'
    """
    stream, porcupine, cobra, FRAME = init_listener()

    collecting = False   # are we buffering an utterance?
    buf        = []
    silence    = 0       # VAD silence counter

    print("[Listener started]")
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

            if voice_prob > 0.95:
                silence = 0                   # speaking
            elif voice_prob < 0.5:
                silence += 1                  # silence frames
                if silence > 30:              # ≈0.4 s gap
                    collecting = False
                    q_utterance.put(buf.copy())     # hand over to ASR
                    buf.clear()
                    print("📨 Utterance queued")
