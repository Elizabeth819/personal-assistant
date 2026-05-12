"""Text-to-speech. Uses macOS `say` for zero-dep demo."""

from __future__ import annotations

import shutil
import subprocess


def speak(text: str, voice: str = "Tingting", rate: int = 220) -> None:
    """Speak text. Falls back to print() if `say` unavailable."""
    if not shutil.which("say"):
        print(f"[TTS] {text}")
        return
    subprocess.run(
        ["say", "-v", voice, "-r", str(rate), text],
        check=False,
    )
