import subprocess, pyaudio, numpy as np, time, sys, os, signal

CHUNK    = 1024          # frames per read
RATE     = 16000         # Hz
CHANNELS = 1
FORMAT   = pyaudio.paInt16  # 16‑bit signed

RTSP_URL = "rtsp://192.168.1.123:8554/mic"

# --- Derive frame size in bytes ---
pa = pyaudio.PyAudio()
SAMPLE_SIZE = pa.get_sample_size(FORMAT)      # 2 bytes for paInt16
FRAME_BYTES = SAMPLE_SIZE * CHANNELS          # bytes per frame

ffmpeg_cmd = [
    "ffmpeg",
    "-hide_banner", "-loglevel", "error",
    "-rtsp_transport", "tcp",
    "-fflags", "nobuffer",
    "-flags", "low_delay",
    "-probesize", "32",
    "-analyzeduration", "0",
    # If your build supports it, uncomment the next two for read timeouts (µs):
    # "-rw_timeout", "1500000",
    "-i", RTSP_URL,
    "-ac", str(CHANNELS),
    "-ar", str(RATE),
    "-f", "s16le", "-"
]

proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, bufsize=10**6)


def read_pcm_frames(n_frames: int) -> bytes:
    """Read exactly n_frames of PCM bytes from ffmpeg stdout (blocking)."""
    need = n_frames * FRAME_BYTES
    out = bytearray()
    while len(out) < need:
        chunk = proc.stdout.read(need - len(out))
        if not chunk:
            raise EOFError("FFmpeg/RTSP stream ended")
        out.extend(chunk)
    return bytes(out)


def cleanup():
    try:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass
    pa.terminate()


print("Listening from MediaMTX…")
try:
    while True:
        data = read_pcm_frames(CHUNK)  # bytes length == CHUNK * FRAME_BYTES
        samples = np.frombuffer(data, dtype=np.int16)

        # simple level estimate (root-mean-square)
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        print(f"RMS: {rms:6.0f}", end="\r")

        time.sleep(0.05)

except KeyboardInterrupt:
    pass
except EOFError as e:
    print("\nStream ended:", e, file=sys.stderr)
finally:
    print()
    cleanup() 
