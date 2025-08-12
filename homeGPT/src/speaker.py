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

def test_mediamtx_connectivity():
    """Test basic connectivity to MediaMTX server"""
    import socket
    try:
        # Parse URL to get host and port
        url_parts = RTSP_SPEAKER_URL.replace("rtsp://", "").split(":")
        host = url_parts[0]
        port = int(url_parts[1].split("/")[0])
        
        with socket.create_connection((host, port), timeout=5) as sock:
            logger.info(f"✓ MediaMTX server at {host}:{port} is reachable")
            return True
    except Exception as e:
        logger.error(f"✗ Cannot reach MediaMTX server: {e}")
        return False

def init_ffmpeg_publisher(sample_rate: int, codec_config: dict = None) -> subprocess.Popen:
    """Initialize FFmpeg process for RTSP streaming"""
    if codec_config is None:
        codec_config = {"name": "pcm", "codec": "pcm_s16le", "extra_args": []}
    
    base_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info",
        
        # Input configuration
        "-f", "s16le",           # 16-bit little endian PCM
        "-ac", "1",              # Mono audio
        "-ar", str(sample_rate), # Sample rate from TTS model
        "-i", "-",               # Read from stdin
        
        # Minimal flags for real-time streaming
        "-fflags", "nobuffer",
        "-flags", "low_delay",
    ]
    
    # Add codec-specific configuration
    if codec_config["codec"] == "pcm_s16le":
        audio_cmd = [
            "-c:a", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", "1",
        ]
    elif codec_config["codec"] == "aac":
        audio_cmd = [
            "-c:a", "aac",
            "-b:a", "64k",
            "-ar", "44100",  # Standard rate for AAC
            "-ac", "1",
            "-profile:a", "aac_low",
        ] + codec_config.get("extra_args", [])
    elif codec_config["codec"] == "pcm_alaw":
        audio_cmd = [
            "-c:a", "pcm_alaw",
            "-ar", "8000",   # Standard rate for G.711
            "-ac", "1",
        ]
    else:
        audio_cmd = ["-c:a", codec_config["codec"]] + codec_config.get("extra_args", [])
    
    # RTSP output settings
    rtsp_cmd = [
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        RTSP_SPEAKER_URL
    ]
    
    ffmpeg_cmd = base_cmd + audio_cmd + rtsp_cmd
    
    try:
        logger.info(f"Starting FFmpeg with {codec_config['name']} codec: {' '.join(ffmpeg_cmd)}")
        process = subprocess.Popen(
            ffmpeg_cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        logger.info(f"FFmpeg process started with PID: {process.pid}")
        
        # Give FFmpeg time to connect and check for immediate failures
        time.sleep(1.0)
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            error_msg = stderr.decode() if stderr else "No error output"
            logger.error(f"FFmpeg failed immediately with {codec_config['name']}: {error_msg}")
            raise RuntimeError(f"FFmpeg startup failed: {error_msg}")
            
        return process
    except Exception as e:
        logger.error(f"Failed to start FFmpeg with {codec_config['name']}: {e}")
        raise

def try_codec_configurations(sample_rate: int):
    """Try different codec configurations until one works"""
    configs = [
        {"name": "PCM_S16LE", "codec": "pcm_s16le", "extra_args": []},
        {"name": "AAC", "codec": "aac", "extra_args": ["-strict", "experimental"]},
        {"name": "PCM_ALAW", "codec": "pcm_alaw", "extra_args": []},
        {"name": "PCM_MULAW", "codec": "pcm_mulaw", "extra_args": []},
    ]
    
    for config in configs:
        try:
            logger.info(f"Attempting codec: {config['name']}")
            process = init_ffmpeg_publisher(sample_rate, config)
            logger.info(f"✓ Successfully initialized with {config['name']}")
            return process, config
        except Exception as e:
            logger.warning(f"✗ Failed with {config['name']}: {e}")
            continue
    
    raise RuntimeError("All codec configurations failed")

def tts_init():
    """Initialize TTS and FFmpeg with fallback codecs"""
    tts = PiperVoice.load(TTS_VOICE_PATH)
    logger.info(f"TTS loaded - Sample rate: {tts.config.sample_rate}")
    
    # Test connectivity first
    if not test_mediamtx_connectivity():
        logger.warning("MediaMTX connectivity test failed, but continuing...")
    
    # Try different codec configurations
    ff, codec_config = try_codec_configurations(tts.config.sample_rate)
    logger.info(f"Using codec configuration: {codec_config['name']}")
    return ff, tts, codec_config

def check_ffmpeg_health(ff_process):
    """Check if FFmpeg process is still running and healthy"""
    if ff_process.poll() is not None:
        try:
            stdout, stderr = ff_process.communicate(timeout=1)
            logger.error(f"FFmpeg died - stderr: {stderr.decode() if stderr else 'No stderr'}")
            logger.error(f"FFmpeg died - stdout: {stdout.decode() if stdout else 'No stdout'}")
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg died and communication timed out")
        except Exception as e:
            logger.error(f"Error checking FFmpeg output: {e}")
        return False
    return True

def restart_ffmpeg(tts, codec_config):
    """Restart FFmpeg process with same codec config"""
    logger.warning(f"Restarting FFmpeg with {codec_config['name']} codec...")
    time.sleep(2)  # Longer pause to let MediaMTX clean up
    try:
        return init_ffmpeg_publisher(tts.config.sample_rate, codec_config)
    except Exception:
        # If the same codec fails, try all configurations again
        logger.warning("Same codec failed, trying all configurations...")
        ff, new_config = try_codec_configurations(tts.config.sample_rate)
        return ff

def write_audio_chunk(ff_process, audio_data, chunk_num=0):
    """Safely write audio chunk to FFmpeg with detailed error handling"""
    try:
        if not audio_data:
            return True
            
        bytes_written = ff_process.stdin.write(audio_data)
        if chunk_num % 10 == 0:  # Log every 10th chunk
            logger.debug(f"Wrote chunk {chunk_num}: {len(audio_data)} bytes -> {bytes_written} bytes")
        return True
        
    except BrokenPipeError as e:
        logger.warning(f"Broken pipe on chunk {chunk_num}: {e}")
        return False
    except OSError as e:
        logger.warning(f"OS error writing chunk {chunk_num}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error writing chunk {chunk_num}: {e}")
        return False

def speaker_thread(q_tts: queue.Queue):
    """Main speaker thread that processes TTS queue"""
    ff, tts, codec_config = tts_init()
    logger.info("[Speaker thread started]")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    successful_writes = 0
    
    while True:
        try:
            # Get text from queue with timeout for periodic health checks
            try:
                text = q_tts.get(timeout=2.0)
            except queue.Empty:
                # Periodic health check during idle time
                if not check_ffmpeg_health(ff):
                    logger.info("Restarting FFmpeg during health check")
                    ff = restart_ffmpeg(tts, codec_config)
                continue
            
            if not text or not text.strip():
                q_tts.task_done()
                continue
                
            logger.info(f"🔊 Speaking: {text[:50]}{'...' if len(text) > 50 else ''}")
            
            # Pre-flight health check
            if not check_ffmpeg_health(ff):
                logger.info("FFmpeg unhealthy before synthesis, restarting")
                ff = restart_ffmpeg(tts, codec_config)
            
            # Generate and stream audio with chunk counting
            audio_written = False
            chunk_count = 0
            failed_chunk = None
            
            for chunk in tts.synthesize(text):
                if chunk.audio_int16_bytes:
                    chunk_count += 1
                    if not write_audio_chunk(ff, chunk.audio_int16_bytes, chunk_count):
                        failed_chunk = chunk_count
                        logger.warning(f"Failed to write chunk {chunk_count}, restarting FFmpeg")
                        ff = restart_ffmpeg(tts, codec_config)
                        
                        # Retry the failed chunk with new process
                        if write_audio_chunk(ff, chunk.audio_int16_bytes, chunk_count):
                            logger.info(f"Successfully retried chunk {chunk_count}")
                            audio_written = True
                        else:
                            logger.error(f"Failed to retry chunk {chunk_count}")
                            break
                    else:
                        audio_written = True
            
            # Flush and finalize
            if audio_written:
                try:
                    ff.stdin.flush()
                    successful_writes += 1
                    consecutive_errors = 0
                    
                    if successful_writes % 10 == 0:
                        logger.info(f"Successfully processed {successful_writes} TTS requests")
                        
                except (BrokenPipeError, OSError) as e:
                    logger.warning(f"Error flushing after {chunk_count} chunks: {e}")
                    ff = restart_ffmpeg(tts, codec_config)
            else:
                logger.error(f"No audio written for text: {text[:30]}")
            
            q_tts.task_done()
            
        except Exception as e:
            logger.error(f"Error in speaker thread: {e}")
            consecutive_errors += 1
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({consecutive_errors}), force restarting")
                try:
                    cleanup_ffmpeg(ff)
                except:
                    pass
                
                try:
                    ff, new_codec_config = try_codec_configurations(tts.config.sample_rate)
                    codec_config = new_codec_config
                    consecutive_errors = 0
                    logger.info(f"Force restart successful with {codec_config['name']}")
                except Exception as restart_error:
                    logger.error(f"Force restart failed: {restart_error}")
                    time.sleep(5)  # Longer pause before giving up
            
            try:
                q_tts.task_done()
            except:
                pass
            time.sleep(1.0)  # Pause on error

def cleanup_ffmpeg(ff_process):
    """Clean shutdown of FFmpeg process"""
    if ff_process and ff_process.poll() is None:
        try:
            logger.info("Cleaning up FFmpeg process...")
            ff_process.stdin.close()
            ff_process.terminate()
            ff_process.wait(timeout=5)
            logger.info("FFmpeg process cleaned up successfully")
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg didn't terminate gracefully, killing...")
            ff_process.kill()
            ff_process.wait()
        except Exception as e:
            logger.error(f"Error during FFmpeg cleanup: {e}")

def create_speaker_thread(q_tts: queue.Queue) -> threading.Thread:
    """Create and return speaker thread"""
    thread = threading.Thread(target=speaker_thread, args=(q_tts,), daemon=True, name="SpeakerThread")
    thread.start()
    logger.info("Speaker thread created and started")
    return thread

# Utility function for testing
def test_tts_to_file(text: str, output_file: str = "/tmp/tts_test.wav"):
    """Test TTS output to file instead of RTSP for debugging"""
    try:
        tts = PiperVoice.load(TTS_VOICE_PATH)
        
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
            "-f", "s16le", "-ac", "1", "-ar", str(tts.config.sample_rate),
            "-i", "-",
            "-c:a", "pcm_s16le",
            output_file
        ]
        
        with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE) as ff:
            for chunk in tts.synthesize(text):
                if chunk.audio_int16_bytes:
                    ff.stdin.write(chunk.audio_int16_bytes)
        
        logger.info(f"Test TTS output written to {output_file}")
        return True
    except Exception as e:
        logger.error(f"Test TTS failed: {e}")
        return False