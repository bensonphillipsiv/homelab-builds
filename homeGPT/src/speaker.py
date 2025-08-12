"""
Text-to-Speech (TTS) using PiperVoice.
"""
import pyaudio, queue
from piper import PiperVoice


TTS_VOICE_PATH = "./models/kusal_medium.onnx"


def speaker_init():
    """Initialize the tts."""

    tts = PiperVoice.load(TTS_VOICE_PATH)

    pa     = pyaudio.PyAudio()
    stream = pa.open(
        format     = pyaudio.paInt16,
        channels   = 1,
        rate       = tts.config.sample_rate,
        output     = True
    )

    return stream, tts


def speaker_thread(q_tts: queue.Queue):
    """
    Owns the text-to-speech:
    - receives text from the orchestrator
    - outputs using Piper
    """

    stream, tts = speaker_init()

    print("[Speaker started]")
    while True:
        text = q_tts.get()
        if not text:
            continue

        for chunk in tts.synthesize(text):
            stream.write(chunk.audio_int16_bytes)
