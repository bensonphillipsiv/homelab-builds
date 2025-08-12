"""
TTS → MediaMTX (RTSP publisher)
"""
import os, subprocess, queue
from piper import PiperVoice

TTS_VOICE_PATH = "./models/kusal_medium.onnx"
RTSP_SPEAKER_URL = os.getenv("RTSP_SPEAKER_URL", "rtsp://mediamtx.media.svc.cluster.local:8554/speak")

def open_rtsp_publisher(sample_rate: int) -> subprocess.Popen:
    # Publishes s16le mono PCM to MediaMTX as low-latency Opus.
    return subprocess.Popen([
        "ffmpeg",
        "-nostdin", "-loglevel", "warning",
        "-re",                            # pace stdin to realtime
        "-f", "s16le", "-ac", "1", "-ar", str(sample_rate),
        "-i", "-",                        # read PCM from stdin
        "-c:a", "libopus", "-b:a", "32k",
        "-frame_duration", "20", "-application", "voip",
        "-rtsp_transport", "tcp",
        "-f", "rtsp", RTSP_SPEAKER_URL
    ], stdin=subprocess.PIPE)

def tts_init():
    tts = PiperVoice.load(TTS_VOICE_PATH)
    ff = open_rtsp_publisher(tts.config.sample_rate)
    return ff, tts

def speaker_thread(q_tts: queue.Queue):
    ff, tts = tts_init()
    print("[Speaker started → RTSP]")
    while True:
        text = q_tts.get()
        if not text:
            continue
        print(f"🔊  {text}")
        try:
            for chunk in tts.synthesize(text):
                # Piper gives 16-bit PCM frames as bytes
                ff.stdin.write(chunk.audio_int16_bytes)
            ff.stdin.flush()
        except (BrokenPipeError, ValueError):
            # Reconnect if MediaMTX dropped/restarted
            ff.terminate()
            ff.wait(timeout=2)
            ff, _ = tts_init()
