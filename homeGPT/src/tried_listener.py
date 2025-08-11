# import os, struct, queue, pyaudio, subprocess, numpy as np
# import pvporcupine, pvcobra
# from dotenv import load_dotenv
# import webrtcvad
# from openwakeword.model import Model


# RATE = 16000
# FRAMES = 1280          # (80 ms @ 16 kHz)
# THRESHOLD_ON  = 0.80
# THRESHOLD_OFF = 0.60
# COOLDOWN_FRAMES = 5        # ~400 ms

# # VAD settings
# VAD_MODE = 2               # 0=loose .. 3=aggressive
# SILENCE_20MS_TO_END = 50   # 50 * 2000 ms = 2s
# SAVE_WAV = True            # set False to skip saving utterances

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
#     wake_word_model = Model()
#     vad = webrtcvad.Vad(VAD_MODE)
    
#     return wake_word_model, vad


# def split_20ms_frames(frame80_bytes: bytes):
#     """Yield four 20 ms (320-sample) s16le chunks from an 80 ms (1280-sample) frame."""
#     # 16-bit mono => 2 bytes/sample; 320 samples * 2 = 640 bytes
#     for i in range(4):
#         start = i * 640
#         yield frame80_bytes[start:start + 640]


# def read_frames(n_frames, stream) -> np.ndarray:
#     need = n_frames * FRAME_BYTES
#     buf = bytearray(need)
#     view = memoryview(buf)
#     got = 0
#     while got < need:
#         chunk = stream.stdout.read(need - got)
#         if not chunk:
#             raise EOFError("FFmpeg/RTSP stream ended")
#         view[got:got+len(chunk)] = chunk
#         got += len(chunk)
#     # Little-endian int16; mono shape (n_frames,) or reshape(-1, CHANNELS) for multi-channel
#     return np.frombuffer(buf, dtype=np.int16)


# def listener_thread(q_utterance: queue.Queue):
#     """
#     Owns the microphone:
#     - wake-word detection
#     - VAD segmentation producing an 'Utterance'
#     """
#     stream = init_ffmpeg()
#     ww_model, vad = init_wake_vad()

#     collecting = False   # are we buffering an utterance?
#     buf        = []
#     silence    = 0       # VAD silence counter

#     print("[Listener started]")
#     while True:
#         # pcm = stream.read(FRAME, exception_on_overflow=False)
#         # frame = struct.unpack_from(f"{FRAME}h", pcm)
#         frame = read_frames(FRAMES, stream)
#         frame80_i16 = np.frombuffer(frame, dtype=np.int16)


#         ww_scores = ww_model.predict(frame80_i16)
#         ww_score = ww_scores.get("hey_jarvis", 0.0) 

#         # Wake-word triggers collection
#         if not collecting and ww_score >= 0.5:
#             collecting, buf, silence = True, [], 0
#             print("🔔 Wake word detected")
#             continue

#         if collecting:
#             buf.extend(frame80_i16)

#             for sub in split_20ms_frames(frame):
#                 if vad.is_speech(sub, RATE):
#                     voiced_once = True
#                     silence_20ms = 0
#                 else:
#                     if voiced_once:  # only count silence after we heard voice
#                         silence_20ms += 1

#             # if voice_prob > 0.95:
#             #     silence = 0                   # speaking
#             # elif voice_prob < 0.5:
#             #     silence += 1                  # silence frames
#             #     if silence > 30:              # ≈0.4 s gap
#             #         collecting = False
#             #         q_utterance.put(buf.copy())     # hand over to ASR
#             #         buf.clear()
#             #         print("📨 Utterance queued")
