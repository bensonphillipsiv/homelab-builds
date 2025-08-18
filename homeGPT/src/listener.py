import os, struct, queue
from dotenv import load_dotenv
import webrtcvad
from openwakeword.model import Model


load_dotenv()
SAMPLE_RATE = 16000
SAMPLES_PER_80MS = SAMPLE_RATE * 80 // 1000  # 1280 samples @ 80ms
SAMPLES_PER_20MS = SAMPLE_RATE * 20 // 1000  # 320 samples @ 20ms

VAD_DELAY_SECONDS = 0.5 
VAD_DELAY_FRAMES = int(VAD_DELAY_SECONDS * 1000 / 20)  # Convert to 20ms frame count
VAD_SILENCE_SECONDS = 0.6  # Silence threshold for ending utterance
VAD_SILENCE_FRAMES = int(VAD_SILENCE_SECONDS * 1000 / 20)


def init_listener():
    """Initialize the listener."""
    ww_model = Model()
    vad_model = webrtcvad.Vad(2)

    return ww_model, vad_model


def split_20ms_frames(frame80_bytes: bytes):
    """Yield four 20 ms (320-sample) raw PCM chunks from an 80 ms (1280-sample) frame."""
    # 16-bit mono => 2 bytes/sample; 320 samples * 2 = 640 bytes
    bytes_per_20ms = SAMPLES_PER_20MS * 2  # 640 bytes
    for i in range(4):
        start = i * bytes_per_20ms
        yield frame80_bytes[start:start + bytes_per_20ms]


def listener_thread(q_utterance: queue.Queue, audio_handler):
    """
    Owns the microphone:
    - wake-word detection
    - VAD segmentation producing an 'Utterance'
    """
    ww_model, vad_model = init_listener()

    collecting = False   # are we buffering an utterance?
    buf = []
    silence = 0          # VAD silence counter

    delay_frames_counter = 0
    waiting_for_speech = True
    
    print("[Listener started]")
    try:
        while True:
            # Get 80ms frames for wake word detection
            for pcm_80ms in audio_handler.get_80ms_frames():
                # Convert PCM bytes to samples for wake word model
                frame = struct.unpack(f"{SAMPLES_PER_80MS}h", pcm_80ms)

                scores = ww_model.predict(frame)
                score = scores.get("hey_jarvis", 0.0)

                # Wake-word triggers collection
                if not collecting and score > 0.7:
                    collecting = True
                    buf = []
                    silence = 0
                    
                    # Reset state machine
                    delay_frames_counter = 0
                    waiting_for_speech = True
                    
                    print("🔔 Wake word detected - entering delay period")
                    continue

                if collecting:
                    buf.extend(frame)

                    # Run VAD over 4×20ms subframes
                    for sub_20ms in split_20ms_frames(pcm_80ms):
                        is_speech = vad_model.is_speech(sub_20ms, SAMPLE_RATE)
                        
                        if waiting_for_speech:
                            delay_frames_counter += 1
                            
                            # Still in delay period
                            if delay_frames_counter < VAD_DELAY_FRAMES:
                                continue  # Skip VAD processing during delay
                            
                            # Delay period over, now looking for first actual speech
                            if is_speech:
                                waiting_for_speech = False
                                silence = 0
                                print(f"✅ First speech detected after wakeword delay")
                        else:
                            # Normal VAD processing after first speech detected
                            if is_speech:
                                silence = 0
                            else:
                                silence += 1

                    # Only end utterance if we've detected speech and have enough silence
                    if not waiting_for_speech and silence > VAD_SILENCE_FRAMES:  # ≈0.6s gap (30 * 20ms)
                        collecting = False
                        q_utterance.put(buf.copy())
                        buf.clear()
                        print("📨 Utterance queued")

    except KeyboardInterrupt:
        print("Stopping listener...")
    finally:
        audio_handler.close()
