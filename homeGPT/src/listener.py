import os, struct, queue, pyaudio, subprocess
from dotenv import load_dotenv
import webrtcvad
from openwakeword.model import Model


load_dotenv()
RTSP_URL = os.getenv("RTSP_URL", "rtsp://192.168.1.123:8554/mic") # "rtsp://mediamtx.mediamtx.svc.cluster.local:8554/mic"
CHANNELS = 1

RATE = 16000
MS = 80
FRAME_80MS = 1280          # (80 ms @ 16 kHz)
FRAME_BYTES = 2 * CHANNELS 
SAMPLES_PER_80MS = 16000 * 80 // 1000  # 1280
PICOVOICE_KEY = os.getenv("PICOVOICE_KEY")
WAKE_WORDS = ["jarvis", "bumblebee"]


def init_ffmpeg():
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-probesize", "32", "-analyzeduration", "0",
        "-i", RTSP_URL,
        "-ac", str(CHANNELS), "-ar", str(RATE),
        "-f", "s16le", "-"
    ]

    ffmpeg_stream = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**6)
    return ffmpeg_stream


def init_wake_vad():
    """Initialize the listener."""
    # Initialize Picovoice
    # porcupine = pvporcupine.create(
    #     access_key=PICOVOICE_KEY,
    #     keywords=WAKE_WORDS,
    # )
    # cobra  = pvcobra.create(access_key=PICOVOICE_KEY)

    # RATE = porcupine.sample_rate
    # FRAME = porcupine.frame_length
    ww_model = Model()
    vad_model = webrtcvad.Vad(2)


    # Initialize PyAudio Stream
    # p = pyaudio.PyAudio()
    # stream = p.open(rate=RATE,
    #                 channels=1,
    #                 format=pyaudio.paInt16,
    #                 input=True,
    #                 frames_per_buffer=FRAME)
    
    return ww_model, vad_model


# def read_frames(n_frames, stream) -> bytes:
#     need = n_frames * FRAME_BYTES  # FRAME_BYTES = 2 * CHANNELS (s16le mono)
#     out = bytearray()
#     while len(out) < need:
#         chunk = stream.stdout.read(need - len(out))
#         if not chunk:
#             raise EOFError("FFmpeg/RTSP stream ended")
#         out.extend(chunk)
#     # Convert s16le bytes -> tuple[int] of length n_frames
#     return struct.unpack_from(f"<{n_frames}h", out)


def read_frames(stream) -> bytes:
    """
    Read audio frames in exact multiples of the specified milliseconds (default 80ms)
    Returns: bytes object containing raw PCM data
    """
    samples_per_window = (RATE * MS) // 1000  # at 16kHz, 80ms = 1280 samples
    bytes_needed = samples_per_window * FRAME_BYTES  # 2 bytes per sample for s16le
    
    # Read the required number of bytes
    out = bytearray()
    while len(out) < bytes_needed:
        chunk = stream.stdout.read(bytes_needed - len(out))
        if not chunk:
            raise EOFError("FFmpeg/RTSP stream ended")
        out.extend(chunk)
    
    # Return raw bytes instead of unpacking
    return bytes(out)


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
    stream = init_ffmpeg()
    ww_model, vad_model = init_wake_vad()

    collecting = False   # are we buffering an utterance?
    buf        = []
    silence    = 0       # VAD silence counter

    print("[Listener started]")
    while True:
        # pcm = stream.read(FRAME, exception_on_overflow=False)
        # frame = struct.unpack_from(f"{FRAME}h", pcm)
        frame_bytes = read_frames(stream)
        frame = struct.unpack_from(f"<{SAMPLES_PER_80MS}h", frame_bytes)

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
            for sub in split_20ms_frames(frame_bytes):
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
