# import os, struct, queue, pyaudio, subprocess
# import pvporcupine, pvcobra
# from dotenv import load_dotenv


# load_dotenv()
# CHANNELS = 1
# RATE = 16000
# RTSP_URL = os.getenv("RTSP_URL", "rtsp://192.168.1.123:8554/mic") # "rtsp://mediamtx.mediamtx.svc.cluster.local:8554/mic"
# FRAME_BYTES = 2 * CHANNELS 
# PICOVOICE_KEY = os.getenv("PICOVOICE_KEY")
# WAKE_WORDS = ["jarvis", "bumblebee"]


# def init_ffmpeg():
#     ffmpeg_cmd = [
#         "ffmpeg", "-hide_banner", "-loglevel", "error",
#         "-rtsp_transport", "tcp",
#         "-fflags", "nobuffer", "-flags", "low_delay",
#         "-probesize", "32", "-analyzeduration", "0",
#         "-i", RTSP_URL,
#         "-ac", str(CHANNELS), "-ar", str(RATE),
#         "-f", "s16le", "-"
#     ]

#     ffmpeg_stream = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**6)
#     return ffmpeg_stream


# def init_wake_vad():
#     """Initialize the listener."""
#     # Initialize Picovoice
#     porcupine = pvporcupine.create(
#         access_key=PICOVOICE_KEY,
#         keywords=WAKE_WORDS,
#     )
#     cobra  = pvcobra.create(access_key=PICOVOICE_KEY)

#     RATE = porcupine.sample_rate
#     FRAME = porcupine.frame_length

#     # Initialize PyAudio Stream
#     # p = pyaudio.PyAudio()
#     # stream = p.open(rate=RATE,
#     #                 channels=1,
#     #                 format=pyaudio.paInt16,
#     #                 input=True,
#     #                 frames_per_buffer=FRAME)
    
#     return porcupine, cobra, FRAME


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


# def listener_thread(q_utterance: queue.Queue):
#     """
#     Owns the microphone:
#     - wake-word detection
#     - VAD segmentation producing an 'Utterance'
#     """
#     stream = init_ffmpeg()
#     porcupine, cobra, FRAME = init_wake_vad()

#     collecting = False   # are we buffering an utterance?
#     buf        = []
#     silence    = 0       # VAD silence counter

#     print("[Listener started]")
#     while True:
#         # pcm = stream.read(FRAME, exception_on_overflow=False)
#         # frame = struct.unpack_from(f"{FRAME}h", pcm)
#         frame = read_frames(FRAME, stream)

#         # Wake-word triggers collection
#         if not collecting and porcupine.process(frame) >= 0:
#             collecting, buf, silence = True, [], 0
#             print("🔔 Wake word detected")
#             continue

#         if collecting:
#             buf.extend(frame)
#             voice_prob = cobra.process(frame)

#             if voice_prob > 0.95:
#                 silence = 0                   # speaking
#             elif voice_prob < 0.5:
#                 silence += 1                  # silence frames
#                 if silence > 30:              # ≈0.4 s gap
#                     collecting = False
#                     q_utterance.put(buf.copy())     # hand over to ASR
#                     buf.clear()
#                     print("📨 Utterance queued")
