"""Voice I/O — ASR (speech→text) and TTS (text→speech)."""

from pa.voice.asr import transcribe
from pa.voice.tts import speak

__all__ = ["speak", "transcribe"]
