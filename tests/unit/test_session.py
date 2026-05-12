"""Tests for per-session conversation memory."""

from __future__ import annotations

from pa.agent import session as conv


def setup_function() -> None:
    conv._sessions.clear()  # type: ignore[attr-defined]


def test_empty_history():
    assert conv.get_history("nope") == []


def test_append_and_retrieve():
    conv.append("s1", "hi", "hello")
    h = conv.get_history("s1")
    assert h == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_cap_to_max_turns():
    for i in range(conv._MAX_TURNS + 5):  # type: ignore[attr-defined]
        conv.append("s2", f"u{i}", f"a{i}")
    h = conv.get_history("s2")
    assert len(h) == conv._MAX_TURNS * 2  # type: ignore[attr-defined]
    assert h[-1] == {"role": "assistant", "content": f"a{conv._MAX_TURNS + 4}"}  # type: ignore[attr-defined]


def test_reset():
    conv.append("s3", "u", "a")
    conv.reset("s3")
    assert conv.get_history("s3") == []


def test_isolation():
    conv.append("a", "x", "y")
    conv.append("b", "p", "q")
    assert conv.get_history("a")[0]["content"] == "x"
    assert conv.get_history("b")[0]["content"] == "p"


def test_blank_session_id_noop():
    conv.append("", "x", "y")
    assert conv.get_history("") == []
