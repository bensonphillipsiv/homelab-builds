#!/usr/bin/env python3
"""
Simple UDP audio sender with Opus compression - sends a constant 440Hz tone
"""

import socket
import numpy as np
import time
import opuslib

# Configuration
RASPBERRY_PI_IP = "192.168.1.131"  # Change to your Pi's IP
PORT = 5005  # Using different port to avoid RTP complexity
SAMPLE_RATE = 16000
TONE_FREQ = 440  # 440 Hz (A note)

# Generate 20ms chunks of 440Hz sine wave (320 samples at 16kHz)
print("Generating tone...")
chunk_duration = 0.02  # 20ms
samples_per_chunk = int(SAMPLE_RATE * chunk_duration)  # 320 samples
t_start = 0

# Create Opus encoder
encoder = opuslib.Encoder(SAMPLE_RATE, 1, opuslib.APPLICATION_AUDIO)

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"Sending compressed tone to {RASPBERRY_PI_IP}:{PORT}")

try:
    while True:
        # Generate 20ms of sine wave
        t = np.linspace(t_start, t_start + chunk_duration, samples_per_chunk, False)
        sine_wave = np.sin(2 * np.pi * TONE_FREQ * t)
        audio_chunk = (sine_wave * 16000).astype(np.int16)
        
        # Compress with Opus
        compressed_data = encoder.encode(audio_chunk.tobytes(), samples_per_chunk)
        
        # Send compressed data
        sock.sendto(compressed_data, (RASPBERRY_PI_IP, PORT))
        print(f"Sent {len(compressed_data)} bytes (compressed from {len(audio_chunk) * 2})")
        
        t_start += chunk_duration
        time.sleep(chunk_duration)  # Real-time sending
        
except KeyboardInterrupt:
    print("\nStopping...")
finally:
    sock.close()