from rich.console import Console

from pa.voice.visual import AgentView, Status, replay


def test_view_initial_state() -> None:
    v = AgentView()
    assert v.status == Status.IDLE
    assert not v.turns
    assert not v.events


def test_assistant_streaming_aggregates_into_one_turn() -> None:
    v = AgentView()
    v.append_assistant("hi")
    v.append_assistant("-")
    v.append_assistant("there")
    v.end_assistant()
    assert len(v.turns) == 1
    assert v.turns[0].role == "assistant"
    assert v.turns[0].text == "hi-there"


def test_user_chunks_merge() -> None:
    v = AgentView()
    v.append_user("hi ")
    v.append_user("there")
    assert len(v.turns) == 1
    assert v.turns[0].text == "hi there"


def test_event_buffer_capped() -> None:
    v = AgentView(max_events=3)
    replay(v, [("a", ""), ("b", ""), ("c", ""), ("d", "")])
    assert [e.kind for e in v.events] == ["b", "c", "d"]


def test_render_produces_output() -> None:
    v = AgentView()
    v.set_status(Status.LISTENING)
    v.connection = "gpt-realtime"
    v.append_assistant("hello")
    v.add_event("session.created", "sess_x")

    console = Console(record=True, width=120, force_terminal=True)
    console.print(v.render())
    out = console.export_text()
    assert "LISTENING" in out
    assert "hello" in out
    assert "session.created" in out
