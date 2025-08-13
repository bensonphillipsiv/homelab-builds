import os, struct, queue, pyaudio, socket
from dotenv import load_dotenv
import opuslib
import webrtcvad
from openwakeword.model import Model

load_dotenv()
LOCAL_IP = "192.168.1.141"
LOCAL_PORT = 5004

CHANNELS = 1
SAMPLE_RATE = 16000
FRAME_BYTES = 2 * CHANNELS
SAMPLES_PER_80MS = SAMPLE_RATE * 80 // 1000  # 1280 samples @ 80ms
SAMPLES_PER_20MS = SAMPLE_RATE * 20 // 1000  # 320 samples @ 20ms

class SimpleRTPReceiver:
    def __init__(self):
        self.decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((LOCAL_IP, LOCAL_PORT))
        self.frame_buffer = []  # Buffer to accumulate 20ms frames into 80ms
        print(f"Listening on {LOCAL_IP}:{LOCAL_PORT}")
    
    def get_audio_data(self):
        """Generator that yields decoded PCM audio data"""
        while True:
            try:
                # Receive packet
                data, addr = self.sock.recvfrom(2048)
                
                # Skip RTP header (12 bytes minimum)
                if len(data) > 12:
                    opus_payload = data[12:]  # Simple header skip
                    
                    # Decode Opus to PCM (20ms frame = 320 samples)
                    pcm_data = self.decoder.decode(opus_payload, SAMPLES_PER_20MS)
                    yield pcm_data
                    
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    def get_80ms_frames(self):
        """Buffer 20ms frames and yield 80ms frames for wake word detection"""
        for pcm_20ms in self.get_audio_data():
            self.frame_buffer.append(pcm_20ms)
            
            # When we have 4 x 20ms frames, combine into 80ms frame
            if len(self.frame_buffer) >= 4:
                # Combine 4 frames into one 80ms frame
                combined_pcm = b''.join(self.frame_buffer[:4])
                self.frame_buffer = self.frame_buffer[4:]  # Remove used frames
                yield combined_pcm
    
    def close(self):
        self.sock.close()

def init_listener():
    """Initialize the listener."""
    ww_model = Model()
    vad_model = webrtcvad.Vad(2)
    stream = SimpleRTPReceiver()

    return stream, ww_model, vad_model


def split_20ms_frames(frame80_bytes: bytes):
    """Yield four 20 ms (320-sample) raw PCM chunks from an 80 ms (1280-sample) frame."""
    # 16-bit mono => 2 bytes/sample; 320 samples * 2 = 640 bytes
    bytes_per_20ms = SAMPLES_PER_20MS * 2  # 640 bytes
    for i in range(4):
        start = i * bytes_per_20ms
        yield frame80_bytes[start:start + bytes_per_20ms]


def listener_thread(q_utterance: queue.Queue):
    """
    Owns the microphone:
    - wake-word detection
    - VAD segmentation producing an 'Utterance'
    """
    stream, ww_model, vad_model = init_listener()

    voiced_once = False
    collecting = False   # are we buffering an utterance?
    buf        = []
    silence    = 0       # VAD silence counter

    print("[Listener started]")
    try:
        while True:
            # Get 80ms frames for wake word detection
            for pcm_80ms in stream.get_80ms_frames():
                # Convert PCM bytes to samples for wake word model
                frame = struct.unpack(f"{SAMPLES_PER_80MS}h", pcm_80ms)

                scores = ww_model.predict(frame)
                score = scores.get("hey_jarvis", 0.0)

                # Wake-word triggers collection
                if not collecting and score > 0.7:
                    collecting, buf, silence = True, [], 0
                    print("🔔 Wake word detected")
                    continue

                if collecting:
                    buf.extend(frame)

                    # Run VAD over 4×20ms subframes
                    for sub_20ms in split_20ms_frames(pcm_80ms):
                        if vad_model.is_speech(sub_20ms, SAMPLE_RATE):
                            voiced_once = True
                            silence = 0
                        else:
                            if voiced_once:  # only count silence after we heard voice
                                silence += 1

                    if silence > 30:              # ≈0.6s gap (30 * 20ms)
                        collecting = False
                        voiced_once = False
                        q_utterance.put(buf.copy())     # hand over to ASR
                        buf.clear()
                        print("📨 Utterance queued")
                    
    except KeyboardInterrupt:
        print("Stopping listener...")
    finally:
        stream.close()
