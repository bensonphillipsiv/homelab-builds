#!/usr/bin/env python3
import os
import struct
import socket
import threading
import pyaudio
import opuslib
import time
import numpy as np
from scipy import signal

# Network configuration
DEVICE_IP = "192.168.1.141"  # Your main device's IP
PI_IP = "0.0.0.0"  # Listen on all interfaces
SEND_PORT = 5004  # Port to send mic audio to device
RECV_PORT = 5005  # Port to receive TTS audio from device

# Audio configuration
CHANNELS = 1
OPUS_RATE = 16000  # Opus encoding rate (what your device expects)
DEVICE_RATE = 48000  # Anker's required rate
SAMPLES_PER_20MS_16K = 320  # 20ms at 16kHz
SAMPLES_PER_20MS_48K = 960  # 20ms at 48kHz

# Anker device
ANKER_DEVICE_INDEX = 0  # From your output

class PiAudioHandler:
    def __init__(self, device_ip=DEVICE_IP):
        print("Initializing Pi Audio Handler for Anker PowerConf S330...")
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Initialize Opus at 16kHz (matching your device)
        self.encoder = opuslib.Encoder(OPUS_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
        self.decoder = opuslib.Decoder(OPUS_RATE, CHANNELS)
        
        # Socket for receiving TTS from device
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.bind((PI_IP, RECV_PORT))
        self.recv_sock.settimeout(1.0)  # 1 second timeout for clean shutdown
        
        # Socket for sending mic audio to device
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.device_addr = (device_ip, SEND_PORT)
        
        # RTP state for sending
        self.seq_num = 0
        self.timestamp = 0
        self.ssrc = 54321
        
        # Open Anker microphone at 48kHz
        print(f"Opening Anker microphone at {DEVICE_RATE}Hz...")
        self.mic_stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=DEVICE_RATE,  # 48kHz
            input=True,
            frames_per_buffer=SAMPLES_PER_20MS_48K,  # 960 samples
            input_device_index=ANKER_DEVICE_INDEX
        )
        
        # Open Anker speaker at 48kHz
        print(f"Opening Anker speaker at {DEVICE_RATE}Hz...")
        self.speaker_stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=DEVICE_RATE,  # 48kHz
            output=True,
            frames_per_buffer=SAMPLES_PER_20MS_48K,  # 960 samples
            output_device_index=ANKER_DEVICE_INDEX
        )
        
        self.running = True
        print(f"\nPi Audio Handler initialized successfully!")
        print(f"  Sending mic audio to {device_ip}:{SEND_PORT}")
        print(f"  Receiving TTS audio on port {RECV_PORT}")
        print(f"  Using Anker PowerConf S330 at 48kHz")
    
    def resample_48k_to_16k(self, audio_48k):
        """Downsample from 48kHz to 16kHz for Opus encoding"""
        # Convert bytes to numpy array
        samples_48k = np.frombuffer(audio_48k, dtype=np.int16)
        
        # Downsample by factor of 3 (48k/16k = 3)
        # Simple method: take every 3rd sample
        samples_16k = samples_48k[::3]
        
        # Better method: use scipy resample
        # samples_16k = signal.resample(samples_48k, len(samples_48k) // 3)
        # samples_16k = np.clip(samples_16k, -32768, 32767).astype(np.int16)
        
        return samples_16k.astype(np.int16).tobytes()
    
    def resample_16k_to_48k(self, audio_16k):
        """Upsample from 16kHz to 48kHz for playback"""
        # Convert bytes to numpy array
        samples_16k = np.frombuffer(audio_16k, dtype=np.int16)
        
        # Upsample by factor of 3 (48k/16k = 3)
        # Use scipy for better quality
        samples_48k = signal.resample(samples_16k, len(samples_16k) * 3)
        samples_48k = np.clip(samples_48k, -32768, 32767).astype(np.int16)
        
        return samples_48k.tobytes()
    
    def create_rtp_header(self):
        """Create RTP header for outgoing packets"""
        header = struct.pack('!BBHII',
            0x80,  # V=2, P=0, X=0, CC=0
            111,   # PT=111 (Opus)
            self.seq_num,
            self.timestamp,
            self.ssrc
        )
        self.seq_num = (self.seq_num + 1) & 0xFFFF
        self.timestamp = (self.timestamp + SAMPLES_PER_20MS_16K) & 0xFFFFFFFF
        return header
    
    def send_mic_thread(self):
        """Thread to continuously send microphone audio to device"""
        print("Starting microphone capture from Anker...")
        
        errors = 0
        while self.running:
            try:
                # Read 20ms of 48kHz audio from Anker microphone (960 samples)
                pcm_48k = self.mic_stream.read(SAMPLES_PER_20MS_48K, 
                                               exception_on_overflow=False)
                
                # Downsample to 16kHz for Opus (320 samples)
                pcm_16k = self.resample_48k_to_16k(pcm_48k)
                
                # Encode to Opus at 16kHz
                opus_frame = self.encoder.encode(pcm_16k, SAMPLES_PER_20MS_16K)
                
                # Create RTP packet
                rtp_packet = self.create_rtp_header() + opus_frame
                
                # Send to device
                self.send_sock.sendto(rtp_packet, self.device_addr)
                
                errors = 0  # Reset error counter on success
                
            except Exception as e:
                errors += 1
                if errors < 5:  # Only print first few errors
                    print(f"Mic thread error: {e}")
                if errors > 100:
                    print("Too many mic errors, stopping...")
                    break
                time.sleep(0.01)
    
    def receive_speaker_thread(self):
        """Thread to receive and play TTS audio from device"""
        print("Starting speaker playback to Anker...")
        
        while self.running:
            try:
                # Receive RTP packet with timeout
                data, addr = self.recv_sock.recvfrom(2048)
                
                # Skip RTP header (12 bytes)
                if len(data) > 12:
                    opus_payload = data[12:]
                    
                    # Decode Opus to PCM (gives us 16kHz audio, 320 samples)
                    pcm_16k = self.decoder.decode(opus_payload, SAMPLES_PER_20MS_16K)
                    
                    # Upsample to 48kHz for Anker speaker (960 samples)
                    pcm_48k = self.resample_16k_to_48k(pcm_16k)
                    
                    # Play through Anker speaker
                    self.speaker_stream.write(pcm_48k)
                    
            except socket.timeout:
                # Normal timeout, just continue
                continue
            except Exception as e:
                if self.running:  # Only print if we're not shutting down
                    print(f"Speaker thread error: {e}")
                time.sleep(0.01)
    
    def run(self):
        """Start both audio threads"""
        # Start microphone thread
        mic_thread = threading.Thread(target=self.send_mic_thread, daemon=True)
        mic_thread.start()
        
        # Start speaker thread
        speaker_thread = threading.Thread(target=self.receive_speaker_thread, daemon=True)
        speaker_thread.start()
        
        print("\n" + "="*50)
        print("Pi Audio Handler running with Anker PowerConf S330")
        print("Press Ctrl+C to stop")
        print("="*50 + "\n")
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown"""
        self.running = False
        time.sleep(0.5)  # Let threads finish
        
        print("Closing audio streams...")
        try:
            self.mic_stream.stop_stream()
            self.mic_stream.close()
        except:
            pass
        
        try:
            self.speaker_stream.stop_stream()
            self.speaker_stream.close()
        except:
            pass
        
        print("Closing PyAudio...")
        self.audio.terminate()
        
        print("Closing sockets...")
        self.recv_sock.close()
        self.send_sock.close()
        
        print("Shutdown complete!")

def test_anker():
    """Test function to verify Anker device is working"""
    print("Testing Anker PowerConf S330...")
    p = pyaudio.PyAudio()
    
    try:
        # Test opening the device
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=48000,
            input=True,
            output=False,
            input_device_index=0,
            frames_per_buffer=960
        )
        print("✓ Anker microphone test successful")
        stream.close()
        
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=48000,
            input=False,
            output=True,
            output_device_index=0,
            frames_per_buffer=960
        )
        print("✓ Anker speaker test successful")
        stream.close()
        
    except Exception as e:
        print(f"✗ Anker test failed: {e}")
        return False
    finally:
        p.terminate()
    
    return True

if __name__ == "__main__":
    # First test the Anker device
    if not test_anker():
        print("\nAnker device test failed. Please check:")
        print("1. Anker PowerConf S330 is connected via USB")
        print("2. Device is powered on")
        print("3. No other application is using the device")
        exit(1)
    
    print("\n" + "="*50)
    
    # Install scipy if needed
    try:
        from scipy import signal
    except ImportError:
        print("Installing scipy for audio resampling...")
        import subprocess
        subprocess.check_call(["pip3", "install", "scipy"])
        from scipy import signal
    
    # Start the handler
    handler = PiAudioHandler(device_ip=DEVICE_IP)
    handler.run()