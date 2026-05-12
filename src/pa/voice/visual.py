"""Live visualization of the realtime agent.

Renders three panels with rich.Live:
  - left:   streaming transcript (user + assistant turns)
  - right:  event timeline (each WS event becomes a line)
  - bottom: status bar (connection, listening/speaking, latency)

The visualizer is decoupled from any specific transport: it consumes
EventBus messages so the realtime loop and tests can drive it the same way.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class Status(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "system"
    text: str = ""
    started_at: float = field(default_factory=time.time)


@dataclass
class Event:
    kind: str  # ws event type, e.g. "response.audio.delta"
    detail: str = ""
    ts: float = field(default_factory=time.time)


class AgentView:
    """Holds all UI state. Pure data — render() turns it into a renderable."""

    def __init__(self, *, max_events: int = 30, max_turns: int = 20) -> None:
        self.status: Status = Status.IDLE
        self.connection: str = ""
        self.last_latency_ms: float | None = None
        self.turns: deque[Turn] = deque(maxlen=max_turns)
        self.events: deque[Event] = deque(maxlen=max_events)
        self.current_assistant: Turn | None = None

    # --- mutations ----------------------------------------------------------

    def set_status(self, status: Status) -> None:
        self.status = status

    def add_event(self, kind: str, detail: str = "") -> None:
        self.events.append(Event(kind=kind, detail=detail))

    def append_user(self, text: str) -> None:
        if self.turns and self.turns[-1].role == "user":
            self.turns[-1].text += text
        else:
            self.turns.append(Turn(role="user", text=text))

    def append_assistant(self, text: str) -> None:
        if self.current_assistant is None:
            self.current_assistant = Turn(role="assistant", text=text)
            self.turns.append(self.current_assistant)
        else:
            self.current_assistant.text += text

    def end_assistant(self) -> None:
        self.current_assistant = None

    # --- render -------------------------------------------------------------

    def _transcript_panel(self) -> Panel:
        body: list[Text] = []
        for t in self.turns:
            tag = {"user": "[bold cyan]you[/]", "assistant": "[bold green]pa[/]"}.get(
                t.role, f"[dim]{t.role}[/]"
            )
            body.append(Text.from_markup(f"{tag}  {t.text}"))
        if not body:
            body.append(Text("(no transcript yet — start speaking)", style="dim"))
        return Panel(Group(*body), title="transcript", border_style="cyan")

    def _events_panel(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="dim", no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(style="dim", overflow="ellipsis")
        for e in self.events:
            table.add_row(
                time.strftime("%H:%M:%S", time.localtime(e.ts)),
                self._event_color(e.kind),
                e.detail,
            )
        return Panel(table, title="events", border_style="magenta")

    @staticmethod
    def _event_color(kind: str) -> Text:
        color = {
            "session.created": "green",
            "input_audio_buffer.speech_started": "yellow",
            "input_audio_buffer.speech_stopped": "yellow",
            "response.audio.delta": "blue",
            "response.audio_transcript.delta": "blue",
            "response.done": "green",
            "error": "red bold",
        }.get(kind, "white")
        return Text(kind, style=color)

    def _status_bar(self) -> Panel:
        color = {
            Status.IDLE: "dim",
            Status.CONNECTING: "yellow",
            Status.LISTENING: "yellow bold",
            Status.THINKING: "cyan bold",
            Status.SPEAKING: "green bold",
            Status.ERROR: "red bold",
        }[self.status]
        parts = [f"[{color}]● {self.status.value.upper():10}[/]"]
        if self.connection:
            parts.append(f"[dim]conn:[/] {self.connection}")
        if self.last_latency_ms is not None:
            parts.append(f"[dim]rtt:[/] {self.last_latency_ms:.0f}ms")
        parts.append("[dim](Ctrl+C to quit)[/]")
        return Panel(Text.from_markup("   ".join(parts)), border_style=color)

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="main", ratio=1),
            Layout(self._status_bar(), name="status", size=3),
        )
        layout["main"].split_row(
            Layout(self._transcript_panel(), name="transcript", ratio=2),
            Layout(self._events_panel(), name="events", ratio=1),
        )
        return layout


def live(view: AgentView, *, refresh_per_second: int = 12) -> Live:
    """Create a rich.Live bound to the view. Use as a context manager."""
    return Live(view.render(), refresh_per_second=refresh_per_second, screen=True)


def replay(view: AgentView, events: Iterable[tuple[str, str]]) -> None:
    """Helper for tests: feed a list of (kind, detail) events into the view."""
    for kind, detail in events:
        view.add_event(kind, detail)
