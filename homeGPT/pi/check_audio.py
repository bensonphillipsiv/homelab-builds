#!/usr/bin/env python3
import pyaudio

p = pyaudio.PyAudio()

print("=== Audio Devices ===")
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"\nDevice {i}: {info['name']}")
    print(f"  Max input channels: {info['maxInputChannels']}")
    print(f"  Max output channels: {info['maxOutputChannels']}")
    print(f"  Default sample rate: {info['defaultSampleRate']}")
    
    # Test common sample rates for input devices
    if info['maxInputChannels'] > 0:
        print("  Supported input rates:")
        for rate in [8000, 16000, 22050, 44100, 48000]:
            try:
                stream = p.open(format=pyaudio.paInt16,
                              channels=1,
                              rate=rate,
                              input=True,
                              input_device_index=i,
                              frames_per_buffer=1024,
                              start=False)
                stream.close()
                print(f"    {rate} Hz: ✓")
            except:
                print(f"    {rate} Hz: ✗")

p.terminate()