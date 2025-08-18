"""
Text-to-Speech (TTS) using PiperVoice.
"""
import queue
from piper import PiperVoice


TTS_VOICE_PATH = "./models/lessac_low.onnx"


def speaker_init():
    """Initialize the tts."""

    tts = PiperVoice.load(TTS_VOICE_PATH)
    # Send audio anytime:

    # pa     = pyaudio.PyAudio()
    # stream = pa.open(
    #     format     = pyaudio.paInt16,
    #     channels   = 1,
    #     rate       = tts.config.sample_rate,
    #     output     = True
    # )

    return tts


def speaker_thread(q_tts: queue.Queue, audio_handler):
    """
    Owns the text-to-speech:
    - receives text from the orchestrator
    - outputs using Piper
    """

    tts = speaker_init()

    print("[Speaker started]")
    while True:
        text = q_tts.get()
        if not text:
            continue

        for chunk in tts.synthesize(text):
            audio_handler.send_audio(chunk.audio_int16_bytes)
        
