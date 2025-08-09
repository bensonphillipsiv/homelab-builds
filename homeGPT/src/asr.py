import numpy as np
from faster_whisper import WhisperModel


def asr_init():
    whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    return whisper


def asr_process(whisper, request_audio):
    """
    Process audio data with ASR and return the transcribed text.
    """
    pcm_f32 = np.array(request_audio, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(pcm_f32, beam_size=5, vad_filter=False)
    request_text = " ".join(s.text for s in segments).strip()

    return request_text
