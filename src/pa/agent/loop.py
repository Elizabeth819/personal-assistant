"""Minimal Claude-backed agent loop.

`chat_once` is pure (no I/O) — easy to unit-test.
`run_repl` wires it to ASR + TTS for the live demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pa.core import get_settings
from pa.voice import speak, transcribe

SYSTEM = (
    "You are a concise personal assistant. "
    "Reply in the user's language. Keep responses short — 1-3 sentences "
    "unless asked for detail."
)


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class ChatState:
    history: list[ChatTurn] = field(default_factory=list)


def _to_messages(state: ChatState) -> list[dict[str, str]]:
    return [{"role": t.role, "content": t.content} for t in state.history]


def chat_once(state: ChatState, user_text: str, client: Any | None = None) -> str:
    """Append user_text, call Claude, append + return assistant reply."""
    state.history.append(ChatTurn("user", user_text))

    if client is None:
        from anthropic import Anthropic

        client = Anthropic(api_key=get_settings().anthropic_api_key)

    resp = client.messages.create(
        model=get_settings().model,
        max_tokens=512,
        system=SYSTEM,
        messages=_to_messages(state),  # type: ignore[arg-type]
    )
    reply = "".join(getattr(b, "text", "") for b in resp.content)
    state.history.append(ChatTurn("assistant", reply))
    return reply


def run_repl(*, voice: bool = True) -> None:
    """Interactive loop. Type 'quit' to exit."""
    state = ChatState()
    print("personal-assistant — type 'quit' to exit, empty line to skip.")
    while True:
        user = transcribe("you> ")
        if not user:
            continue
        if user.lower() in {"quit", "exit", ":q"}:
            break
        reply = chat_once(state, user)
        print(f"pa> {reply}")
        if voice:
            speak(reply)
