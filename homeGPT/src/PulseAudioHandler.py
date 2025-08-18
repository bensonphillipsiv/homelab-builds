import socket
import threading
import queue
import time
import os
import numpy as np

AUDIO_DEVICE_IP = os.getenv("AUDIO_DEVICE_IP", "192.168.1.132")
AUDIO_LISTENER_PORT = os.getenv("AUDIO_LISTENER_PORT", 4713)
AUDIO_SPEAKER_PORT = os.getenv("AUDIO_SPEAKER_PORT", 4712)

SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2  # 16-bit
SAMPLES_PER_20MS = SAMPLE_RATE * 20 // 1000  # 320 samples
BYTES_PER_20MS = SAMPLES_PER_20MS * BYTES_PER_SAMPLE * CHANNELS  # 640 bytes
SAMPLES_PER_80MS = SAMPLE_RATE * 80 // 1000  # 1280 samples
BYTES_PER_80MS = SAMPLES_PER_80MS * BYTES_PER_SAMPLE * CHANNELS  # 2560 bytes


class PulseAudioHandler:
    """
    Handles bidirectional audio streaming using PulseAudio simple protocol.
    Receives microphone audio from Pi and sends TTS audio to Pi.
    """
    
    def __init__(self, 
                 pi_ip=AUDIO_DEVICE_IP,
                 tts_port=AUDIO_LISTENER_PORT,      # Port for sending TTS to Pi speakers
                 mic_port=AUDIO_SPEAKER_PORT):     # Port for receiving mic from Pi
        
        self.pi_ip = pi_ip
        self.tts_port = tts_port
        self.mic_port = mic_port
        
        # For sending TTS audio to Pi speakers
        self.tts_sock = None
        
        # For receiving microphone audio from Pi
        self.mic_sock = None
        self.mic_connected = False
        
        # Buffers for creating properly sized frames
        self.audio_buffer = bytearray()
        self.frame_20ms_queue = queue.Queue()
        self.frame_80ms_queue = queue.Queue()
        
        # Start receiver thread for microphone audio
        self.running = True
        self.receiver_thread = threading.Thread(target=self._receive_audio_thread, daemon=True)
        self.receiver_thread.start()

        self.bell_ding_audio = self._generate_alert_ding()

        print(f"PulseAudio Handler initialized:")
        print(f"  TTS → Pi speakers: {pi_ip}:{tts_port}")
        print(f"  Mic ← Pi microphone: connecting to {pi_ip}:{mic_port}")
    
    def _connect_to_mic(self):
        """Connect to Pi's microphone stream"""
        while self.running and not self.mic_connected:
            try:
                self.mic_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.mic_sock.settimeout(5.0)
                print(f"Connecting to Pi microphone at {self.pi_ip}:{self.mic_port}...")
                self.mic_sock.connect((self.pi_ip, self.mic_port))
                self.mic_sock.settimeout(None)  # Remove timeout after connection
                self.mic_connected = True
                print("✓ Connected to Pi microphone")
                return True
            except (socket.timeout, ConnectionRefusedError) as e:
                print(f"Waiting for Pi microphone... Make sure module is loaded on Pi")
                time.sleep(2)
            except Exception as e:
                print(f"Mic connection error: {e}")
                time.sleep(2)
        return False
    
    def _receive_audio_thread(self):
        """Thread that continuously receives audio from Pi microphone"""
        while self.running:
            if not self.mic_connected:
                if not self._connect_to_mic():
                    continue
            
            try:
                # Receive audio data from Pi
                data = self.mic_sock.recv(4096)
                if not data:
                    print("Pi microphone disconnected")
                    self.mic_connected = False
                    self.mic_sock.close()
                    continue
                
                # Add to buffer
                self.audio_buffer.extend(data)
                
                # Create 20ms frames
                while len(self.audio_buffer) >= BYTES_PER_20MS:
                    frame_20ms = bytes(self.audio_buffer[:BYTES_PER_20MS])
                    self.audio_buffer = self.audio_buffer[BYTES_PER_20MS:]
                    self.frame_20ms_queue.put(frame_20ms)
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receiver error: {e}")
                self.mic_connected = False
                if self.mic_sock:
                    self.mic_sock.close()
                time.sleep(1)

    def _generate_alert_ding(self, sample_rate=SAMPLE_RATE):
        """Generate a pleasant bell-like ding sound and cache it"""
        duration = 0.3
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        
        # Combine multiple frequencies for bell-like sound
        fundamental = 800
        bell_sound = (
            0.6 * np.sin(2 * np.pi * fundamental * t) +
            0.3 * np.sin(2 * np.pi * fundamental * 2 * t) +
            0.1 * np.sin(2 * np.pi * fundamental * 3 * t)
        )
        
        # Exponential decay envelope for bell effect
        envelope = np.exp(-3 * t)
        audio_signal = bell_sound * envelope * 0.2
        
        # Convert to 16-bit PCM
        audio_pcm = (audio_signal * 32767).astype(np.int16)
        return audio_pcm.tobytes()
    
    def play_alert_ding(self):
        """Play the pre-generated bell ding sound"""
        return self.send_tts_audio(self.bell_ding_audio)
    
    def get_80ms_frames(self):
        """
        Generator that yields 80ms audio frames for wake word detection.
        Blocks until enough data is available.
        """
        frame_buffer = []
        
        while self.running:
            try:
                # Get a 20ms frame (with timeout to allow checking self.running)
                frame_20ms = self.frame_20ms_queue.get(timeout=0.1)
                frame_buffer.append(frame_20ms)
                
                # When we have 4 x 20ms frames, combine into 80ms frame
                if len(frame_buffer) >= 4:
                    # Combine 4 frames into one 80ms frame
                    combined_pcm = b''.join(frame_buffer[:4])
                    frame_buffer = frame_buffer[4:]  # Remove used frames
                    yield combined_pcm
                    
            except queue.Empty:
                continue
    
    def get_20ms_frames(self):
        """
        Generator that yields 20ms audio frames.
        Blocks until data is available.
        """
        while self.running:
            try:
                frame_20ms = self.frame_20ms_queue.get(timeout=0.1)
                yield frame_20ms
            except queue.Empty:
                continue
    
    def send_audio(self, audio_data):
        """
        Send TTS audio to Pi speakers.
        
        Args:
            audio_data: Raw PCM audio (16-bit, 16kHz, mono)
        """
        # Connect to Pi speakers if not connected
        if self.tts_sock is None:
            try:
                self.tts_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tts_sock.connect((self.pi_ip, self.tts_port))
                print(f"✓ Connected to Pi speakers at {self.pi_ip}:{self.tts_port}")
            except Exception as e:
                print(f"Failed to connect to Pi speakers: {e}")
                self.tts_sock = None
                return False
        
        # Send audio
        try:
            self.tts_sock.send(audio_data)
            return True
        except (BrokenPipeError, ConnectionResetError):
            print("Lost connection to Pi speakers, reconnecting...")
            self.tts_sock.close()
            self.tts_sock = None
            return False
    
    def close(self):
        """Clean shutdown"""
        self.running = False
        
        if self.tts_sock:
            self.tts_sock.close()
        
        if self.mic_sock:
            self.mic_sock.close()
        
        print("PulseAudio Handler closed")

