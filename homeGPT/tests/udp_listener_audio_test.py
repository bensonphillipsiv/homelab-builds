#!/usr/bin/env python3
"""
Bare bones RTP audio receiver for Opus-encoded audio
Receives audio stream and provides decoded PCM data
"""

import socket
import opuslib

# Configuration
LOCAL_IP = "192.168.1.141"
LOCAL_PORT = 5004
SAMPLE_RATE = 16000
CHANNELS = 1

class SimpleRTPReceiver:
    def __init__(self):
        self.decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((LOCAL_IP, LOCAL_PORT))
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
                    
                    # Decode Opus to PCM
                    pcm_data = self.decoder.decode(opus_payload, 320)  # 20ms frame
                    yield pcm_data
                    
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    def close(self):
        self.sock.close()


receiver = SimpleRTPReceiver()
try:
    for audio_chunk in receiver.get_audio_data():
        # Do something with audio_chunk (PCM data)
        print(f"Received {len(audio_chunk)} bytes of audio")
        
        # Your audio processing code goes here
        # audio_chunk is raw PCM data (16-bit signed integers)
        
except KeyboardInterrupt:
    print("Stopping...")
finally:
    receiver.close()
