"""Speech-to-text.

Strategy:
  1. If sounddevice + OpenAI/Anthropic ASR is available → record + transcribe.
  2. Else fall back to typed input (keeps demo runnable everywhere).

For the MVP we keep it dead simple: typed input by default, with a hook for
real audio later.
"""

from __future__ import annotations

from typing import Protocol


class Transcriber(Protocol):
    def __call__(self, prompt: str = "you> ") -> str: ...


def typed_transcriber(prompt: str = "you> ") -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def transcribe(prompt: str = "you> ") -> str:
    """Default transcriber. Swap with a real ASR backend later."""
    return typed_transcriber(prompt)
