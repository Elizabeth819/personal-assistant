from pa.voice.asr import typed_transcriber
from pa.voice.tts import speak


def test_typed_transcriber(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "  hello world  ")
    assert typed_transcriber() == "hello world"


def test_speak_no_say_falls_back(monkeypatch, capsys) -> None:
    monkeypatch.setattr("pa.voice.tts.shutil.which", lambda _: None)
    speak("hi")
    assert "[TTS] hi" in capsys.readouterr().out
