"""
TTS → MediaMTX (RTSP publisher)
"""
import os, subprocess, queue
from piper import PiperVoice

TTS_VOICE_PATH = "./models/kusal_medium.onnx"
RTSP_SPEAKER_URL = os.getenv("RTSP_SPEAKER_URL", "rtsp://mediamtx.media.svc.cluster.local:8554/speak")

def init_ffmpeg_publisher(sample_rate: int) -> subprocess.Popen:
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-fflags", "nobuffer", "-flags", "low_delay",
        "-re",                              # pace stdin in realtime
        "-f", "s16le", "-ac", 1, "-ar", str(sample_rate),
        "-i", "-",                          # read PCM from stdin
        "-c:a", "libopus", "-b:a", "32k",
        "-frame_duration", "20", "-application", "voip",
        "-f", "rtsp", RTSP_SPEAKER_URL
    ]

    return subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, bufsize=10**6)

def tts_init():
    tts = PiperVoice.load(TTS_VOICE_PATH)
    ff = init_ffmpeg_publisher(tts.config.sample_rate)
    return ff, tts

def speaker_thread(q_tts: queue.Queue):
    ff, tts = tts_init()
    print("[Speaker started]")
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
