import subprocess, numpy as np, sys, os

CHUNK = 1024
RATE = 16000
CHANNELS = 1
FRAME_BYTES = 2 * CHANNELS  # 16-bit PCM

RTSP_URL = os.getenv("RTSP_URL", "rtsp://mediamtx.mediamtx.svc.cluster.local:8554/mic")

ffmpeg_cmd = [
    "ffmpeg", "-hide_banner", "-loglevel", "error",
    "-rtsp_transport", "tcp",
    "-fflags", "nobuffer", "-flags", "low_delay",
    "-probesize", "32", "-analyzeduration", "0",
    "-i", RTSP_URL,
    "-ac", str(CHANNELS), "-ar", str(RATE),
    "-f", "s16le", "-"
]

proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**6)

def read_pcm_frames(n_frames: int) -> bytes:
    need = n_frames * FRAME_BYTES
    out = bytearray()
    while len(out) < need:
        chunk = proc.stdout.read(need - len(out))
        if not chunk:  # ffmpeg ended
            raise EOFError("FFmpeg/RTSP stream ended")
        out.extend(chunk)
    return bytes(out)

print("Listening from MediaMTX…")
try:
    while True:
        data = read_pcm_frames(CHUNK)
        samples = np.frombuffer(data, dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float32)**2)))
        print(f"RMS: {rms:6.0f}")  # newline for k8s logs
except EOFError as e:
    print(f"Stream ended: {e}", file=sys.stderr)
    sys.exit(1)
