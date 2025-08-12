"""
TTS → MediaMTX (RTSP publisher)
"""
import os, subprocess, queue, threading, time, logging
from piper import PiperVoice

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TTS_VOICE_PATH = "./models/kusal_medium.onnx"
RTSP_SPEAKER_URL = os.getenv("RTSP_SPEAKER_URL", "rtsp://mediamtx.media.svc.cluster.local:8554/speak")

def init_ffmpeg_publisher(sample_rate: int) -> subprocess.Popen:
    """Initialize FFmpeg process for RTSP streaming"""
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning",
        
        # Input configuration
        "-f", "s16le",           # 16-bit little endian PCM
        "-ac", "1",              # Mono audio
        "-ar", str(sample_rate), # Sample rate from TTS model
        "-i", "-",               # Read from stdin
        
        # Buffer and latency settings
        "-fflags", "+genpts+igndts", 
        "-avoid_negative_ts", "make_zero",
        "-use_wallclock_as_timestamps", "1",
        
        # Audio encoding for RTSP
        "-c:a", "aac",           # Use AAC instead of Opus for better RTSP compatibility
        "-b:a", "64k",           # Higher bitrate for better quality
        "-ar", "44100",          # Standard sample rate
        "-ac", "1",              # Mono output
        "-profile:a", "aac_low",
        
        # RTSP output settings
        "-f", "rtsp",
        "-rtsp_transport", "tcp", # Use TCP for more reliable streaming
        "-muxdelay", "0.1",
        RTSP_SPEAKER_URL
    ]
    
    try:
        process = subprocess.Popen(
            ffmpeg_cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered for real-time streaming
        )
        logger.info(f"FFmpeg process started with PID: {process.pid}")
        return process
    except Exception as e:
        logger.error(f"Failed to start FFmpeg process: {e}")
        raise

def tts_init():
    """Initialize TTS and FFmpeg"""
    tts = PiperVoice.load(TTS_VOICE_PATH)
    ff = init_ffmpeg_publisher(tts.config.sample_rate)
    return ff, tts

def check_ffmpeg_health(ff_process):
    """Check if FFmpeg process is still running and healthy"""
    if ff_process.poll() is not None:
        # Process has terminated
        stdout, stderr = ff_process.communicate(timeout=1)
        logger.error(f"FFmpeg process died. stderr: {stderr.decode() if stderr else 'No error output'}")
        return False
    return True

def restart_ffmpeg(tts):
    """Restart FFmpeg process"""
    logger.warning("Restarting FFmpeg process...")
    time.sleep(1)  # Brief pause before restart
    return init_ffmpeg_publisher(tts.config.sample_rate)

def speaker_thread(q_tts: queue.Queue):
    """Main speaker thread that processes TTS queue"""
    ff, tts = tts_init()
    logger.info("[Speaker started]")
    
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    while True:
        try:
            # Get text from queue with timeout to allow health checks
            try:
                text = q_tts.get(timeout=1.0)
            except queue.Empty:
                # Periodic health check
                if not check_ffmpeg_health(ff):
                    ff = restart_ffmpeg(tts)
                continue
            
            if not text or not text.strip():
                q_tts.task_done()
                continue
                
            logger.info(f"🔊 Speaking: {text[:50]}...")
            
            # Check FFmpeg health before processing
            if not check_ffmpeg_health(ff):
                ff = restart_ffmpeg(tts)
            
            # Generate and stream audio
            audio_written = False
            for chunk in tts.synthesize(text):
                if chunk.audio_int16_bytes:
                    try:
                        ff.stdin.write(chunk.audio_int16_bytes)
                        audio_written = True
                    except BrokenPipeError:
                        logger.warning("Broken pipe detected, restarting FFmpeg")
                        ff = restart_ffmpeg(tts)
                        # Try writing the chunk again with new process
                        ff.stdin.write(chunk.audio_int16_bytes)
                        audio_written = True
            
            if audio_written:
                try:
                    ff.stdin.flush()
                    consecutive_errors = 0  # Reset error counter on success
                except (BrokenPipeError, OSError) as e:
                    logger.warning(f"Error flushing FFmpeg stdin: {e}")
                    ff = restart_ffmpeg(tts)
            
            q_tts.task_done()
            
        except Exception as e:
            logger.error(f"Error in speaker thread: {e}")
            consecutive_errors += 1
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({consecutive_errors}), restarting FFmpeg")
                try:
                    ff.terminate()
                    ff.wait(timeout=2)
                except:
                    ff.kill()
                
                ff = restart_ffmpeg(tts)
                consecutive_errors = 0
            
            q_tts.task_done()
            time.sleep(0.5)  # Brief pause on error

def cleanup_ffmpeg(ff_process):
    """Clean shutdown of FFmpeg process"""
    if ff_process and ff_process.poll() is None:
        try:
            ff_process.stdin.close()
            ff_process.terminate()
            ff_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ff_process.kill()
            ff_process.wait()
        except:
            pass

