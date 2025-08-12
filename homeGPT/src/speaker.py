"""
TTS → MediaMTX (RTSP publisher)
"""
import os, subprocess, queue, time
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
    sr = tts.config.sample_rate
    silence_20ms = b"\x00\x00" * int(sr * 0.02)  # s16le mono
    print("[Speaker started → RTSP]")
    while True:
        try:
            text = q_tts.get(timeout=0.02)  # 20 ms pacing
        except queue.Empty:
            ff.stdin.write(silence_20ms)
            continue

        try:
            for chunk in tts.synthesize(text):
                ff.stdin.write(chunk.audio_int16_bytes)
        except (BrokenPipeError, ValueError):
            ff.terminate(); ff.wait(timeout=2)
            ff, _ = tts_init()
