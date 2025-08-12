"""
TTS → MediaMTX (RTSP publisher)
"""
import os, subprocess, queue, threading, time, logging
from piper import PiperVoice

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TTS_VOICE_PATH = "./models/kusal_medium.onnx"
RTSP_SPEAKER_URL = os.getenv("RTSP_SPEAKER_URL", "rtsp://mediamtx.mediamtx.svc.cluster.local:8554/speak")

def resolve_mediamtx_host():
    """Resolve MediaMTX hostname and suggest alternatives"""
    import socket
    
    # Parse URL to get host and port
    url_parts = RTSP_SPEAKER_URL.replace("rtsp://", "").split(":")
    host = url_parts[0]
    port = int(url_parts[1].split("/")[0])
    
    logger.info(f"Attempting to resolve: {host}")
    
    # Try to resolve the hostname
    try:
        resolved_ip = socket.gethostbyname(host)
        logger.info(f"✓ Resolved {host} to {resolved_ip}")
        return host, port, resolved_ip
    except socket.gaierror as e:
        logger.error(f"✗ DNS resolution failed for {host}: {e}")
        
        # Suggest alternatives
        alternatives = [
            "localhost",
            "127.0.0.1", 
            "mediamtx",  # Docker container name
            "host.docker.internal",  # Docker Desktop
        ]
        
        logger.info("Trying alternative hostnames...")
        for alt_host in alternatives:
            try:
                resolved_ip = socket.gethostbyname(alt_host)
                logger.info(f"✓ Alternative {alt_host} resolves to {resolved_ip}")
                return alt_host, port, resolved_ip
            except socket.gaierror:
                logger.debug(f"✗ {alt_host} not resolvable")
        
        raise RuntimeError(f"Cannot resolve MediaMTX hostname: {host}")

def test_mediamtx_connectivity():
    """Test basic connectivity to MediaMTX server"""
    import socket
    try:
        host, port, resolved_ip = resolve_mediamtx_host()
        
        with socket.create_connection((resolved_ip, port), timeout=5) as sock:
            logger.info(f"✓ MediaMTX server at {host} ({resolved_ip}:{port}) is reachable")
            return True, host
    except Exception as e:
        logger.error(f"✗ Cannot reach MediaMTX server: {e}")
        return False, None

def get_working_rtsp_url():
    """Get a working RTSP URL by testing connectivity and hostname resolution"""
    global RTSP_SPEAKER_URL
    
    try:
        is_reachable, working_host = test_mediamtx_connectivity()
        if is_reachable and working_host:
            # Update URL with working hostname
            original_host = RTSP_SPEAKER_URL.split("://")[1].split(":")[0]
            if working_host != original_host:
                RTSP_SPEAKER_URL = RTSP_SPEAKER_URL.replace(original_host, working_host)
                logger.info(f"Updated RTSP URL to: {RTSP_SPEAKER_URL}")
            return RTSP_SPEAKER_URL
        else:
            # Try common local alternatives
            alternatives = [
                "rtsp://localhost:8554/speak",
                "rtsp://127.0.0.1:8554/speak",
                "rtsp://mediamtx:8554/speak",
                "rtsp://host.docker.internal:8554/speak",
            ]
            
            logger.info("Testing alternative RTSP URLs...")
            for alt_url in alternatives:
                try:
                    # Test this alternative
                    test_host = alt_url.split("://")[1].split(":")[0]
                    test_port = 8554
                    
                    import socket
                    with socket.create_connection((test_host, test_port), timeout=2) as sock:
                        logger.info(f"✓ Alternative URL works: {alt_url}")
                        RTSP_SPEAKER_URL = alt_url
                        return alt_url
                except Exception as e:
                    logger.debug(f"✗ {alt_url} failed: {e}")
            
            # If nothing works, provide guidance
            logger.error("No working MediaMTX server found!")
            logger.info("Please ensure MediaMTX is running and accessible. Try:")
            logger.info("  1. docker run --rm -p 8554:8554 bluenviron/mediamtx")
            logger.info("  2. Check your RTSP_SPEAKER_URL environment variable")
            logger.info(f"  3. Current URL: {RTSP_SPEAKER_URL}")
            
            raise RuntimeError("MediaMTX server not accessible")
            
    except Exception as e:
        logger.error(f"Failed to get working RTSP URL: {e}")
        raise
    """Initialize FFmpeg process for RTSP streaming"""
    if codec_config is None:
        codec_config = {"name": "pcm", "codec": "pcm_s16le", "extra_args": []}
    
def init_ffmpeg_publisher(sample_rate: int, codec_config: dict = None) -> subprocess.Popen:
    """Initialize FFmpeg process for RTSP streaming"""
    if codec_config is None:
        codec_config = {"name": "pcm", "codec": "pcm_s16le", "extra_args": []}
    
    # Ensure we have a working RTSP URL
    working_url = get_working_rtsp_url()
    
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
    
    # Add codec-specific configuration with MediaMTX compatibility focus
    if codec_config["codec"] == "pcm_s16le":
        # PCM is problematic with RTSP/SDP - avoid for now
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
        # G.711 A-law - well supported by RTSP
        audio_cmd = [
            "-c:a", "pcm_alaw",
            "-ar", "8000",   # G.711 standard rate
            "-ac", "1",
        ]
    elif codec_config["codec"] == "pcm_mulaw":
        # G.711 μ-law - well supported by RTSP  
        audio_cmd = [
            "-c:a", "pcm_mulaw",
            "-ar", "8000",   # G.711 standard rate
            "-ac", "1",
        ]
    elif codec_config["codec"] == "libopus":
        # Opus - modern, efficient
        audio_cmd = [
            "-c:a", "libopus",
            "-ar", "48000",  # Opus standard rate
            "-ac", "1",
            "-frame_duration", "20",  # 20ms frames
        ] + codec_config.get("extra_args", [])
    else:
        audio_cmd = ["-c:a", codec_config["codec"]] + codec_config.get("extra_args", [])
    
    # RTSP output settings - simplified
    rtsp_cmd = [
        "-f", "rtsp",
        "-rtsp_transport", "tcp",
        working_url
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
        # Start with more compatible formats for RTSP
        {"name": "AAC_LOW", "codec": "aac", "extra_args": ["-profile:a", "aac_low", "-strict", "experimental"]},
        {"name": "G711_ALAW", "codec": "pcm_alaw", "extra_args": []},
        {"name": "G711_MULAW", "codec": "pcm_mulaw", "extra_args": []},
        {"name": "PCM_S16LE", "codec": "pcm_s16le", "extra_args": []},
        {"name": "OPUS", "codec": "libopus", "extra_args": ["-b:a", "32k", "-application", "voip"]},
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
    
    # Test and get working MediaMTX URL first
    try:
        working_url = get_working_rtsp_url()
        logger.info(f"Using MediaMTX URL: {working_url}")
    except RuntimeError as e:
        logger.error(f"MediaMTX setup failed: {e}")
        raise
    
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

# Add a function to create proper SDP for PCM streams
def create_custom_sdp(sample_rate: int, stream_url: str) -> str:
    """Create a proper SDP file for PCM streams to help MediaMTX"""
    # Parse URL to get connection info
    url_parts = stream_url.replace("rtsp://", "").split(":")
    host = url_parts[0]
    port = url_parts[1].split("/")[0]
    
    sdp_content = f"""v=0
o=- 0 0 IN IP4 {host}
s=TTS Audio Stream
c=IN IP4 {host}
t=0 0
m=audio {port} RTP/AVP 96
a=rtpmap:96 L16/{sample_rate}/1
a=recvonly
"""
    
    try:
        with open("/tmp/stream.sdp", "w") as f:
            f.write(sdp_content)
        logger.info(f"Created SDP file for sample rate {sample_rate}")
        return "/tmp/stream.sdp"
    except Exception as e:
        logger.warning(f"Failed to create SDP file: {e}")
        return None

def generate_silence(sample_rate: int, duration_seconds: float = 1.0) -> bytes:
    """Generate silence as PCM bytes"""
    num_samples = int(sample_rate * duration_seconds)
    # 16-bit signed integers (all zeros = silence)
    silence_data = struct.pack('<' + 'h' * num_samples, *([0] * num_samples))
    return silence_data

def keep_stream_alive(ff_process, sample_rate: int, codec_config: dict):
    """Send periodic silence to keep stream alive, adapted for codec"""
    try:
        if codec_config["codec"] in ["pcm_alaw", "pcm_mulaw"]:
            # For G.711 codecs, use their standard 8kHz rate
            silence_chunk = generate_silence(8000, 0.1)  # 100ms of silence
        elif codec_config["codec"] == "libopus":
            # Opus expects 48kHz
            silence_chunk = generate_silence(48000, 0.1)
        elif codec_config["codec"] == "aac":
            # AAC expects 44.1kHz  
            silence_chunk = generate_silence(44100, 0.1)
        else:
            # Use original sample rate for PCM
            silence_chunk = generate_silence(sample_rate, 0.1)
        
        ff_process.stdin.write(silence_chunk)
        ff_process.stdin.flush()
        logger.debug(f"Sent keep-alive silence for {codec_config['name']} ({len(silence_chunk)} bytes)")
        return True
    except (BrokenPipeError, OSError):
        logger.warning("Keep-alive failed - stream may be down")
        return False

def speaker_thread(q_tts: queue.Queue):
    """Main speaker thread that processes TTS queue"""
    ff, tts, codec_config = tts_init()
    logger.info("[Speaker thread started]")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    successful_writes = 0
    last_keepalive = time.time()
    keepalive_interval = 3.0  # Send silence every 3 seconds when idle
    
    while True:
        try:
            # Get text from queue with timeout for periodic health checks
            try:
                text = q_tts.get(timeout=1.0)  # Shorter timeout for more responsive keepalive
            except queue.Empty:
                # Periodic health check and keep-alive
                current_time = time.time()
                
                if not check_ffmpeg_health(ff):
                    logger.info("Restarting FFmpeg during health check")
                    ff = restart_ffmpeg(tts, codec_config)
                    last_keepalive = current_time
                elif current_time - last_keepalive >= keepalive_interval:
                    # Send keep-alive silence
                    if keep_stream_alive(ff, tts.config.sample_rate, codec_config):
                        last_keepalive = current_time
                    else:
                        logger.info("Keep-alive failed, restarting FFmpeg")
                        ff = restart_ffmpeg(tts, codec_config)
                        last_keepalive = current_time
                
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
                    last_keepalive = time.time()  # Reset keepalive timer after speech
                    
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
                    last_keepalive = time.time()
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

# Utility function for dedicated keep-alive stream
def start_keepalive_stream(sample_rate: int = 22050, stream_path: str = "keepalive") -> subprocess.Popen:
    """Start a dedicated keep-alive stream with minimal audio"""
    keepalive_url = RTSP_SPEAKER_URL.replace("speak", stream_path)
    
    # Generate very quiet tone instead of complete silence (some systems prefer this)
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-re",
        "-f", "lavfi", "-i", f"sine=frequency=20:sample_rate={sample_rate}:volume=0.001",
        "-c:a", "pcm_s16le", "-ar", str(sample_rate), "-ac", "1",
        "-f", "rtsp", "-rtsp_transport", "tcp",
        keepalive_url
    ]
    
    try:
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        logger.info(f"Keep-alive stream started at {keepalive_url}")
        return process
    except Exception as e:
        logger.error(f"Failed to start keep-alive stream: {e}")
        return None
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