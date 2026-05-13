"""Tests for the ReAct loop. _ask_vlm and ios_wda are stubbed."""

from __future__ import annotations

from typing import Any

import pytest

from pa.agent import react as r


@pytest.mark.asyncio
async def test_react_simple_done(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot() -> str:
        return "AAAA"

    decisions = iter(
        [
            {"thought": "see home", "action": {"type": "tap_text", "text": "设置"}, "done": False},
            {"thought": "settings open", "action": None, "done": True, "answer": "完成"},
        ]
    )

    async def fake_ask(goal: str, shot: str, hist: str) -> dict[str, Any]:
        return next(decisions)

    async def fake_exec(action: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "action": action.get("type")}

    monkeypatch.setattr(r.ios_wda, "screenshot_b64", fake_shot)
    monkeypatch.setattr(r.ios_wda, "execute", fake_exec)
    monkeypatch.setattr(r, "_ask_vlm", fake_ask)

    run = await r.run("打开设置", max_steps=4)
    assert run.success is True
    assert run.final_answer == "完成"
    assert len(run.steps) == 2
    assert run.steps[0].action == {"type": "tap_text", "text": "设置"}


@pytest.mark.asyncio
async def test_react_max_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot() -> str:
        return "X"

    async def fake_ask(goal: str, shot: str, hist: str) -> dict[str, Any]:
        return {"thought": "loop", "action": {"type": "swipe", "direction": "up"}, "done": False}

    async def fake_exec(action: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(r.ios_wda, "screenshot_b64", fake_shot)
    monkeypatch.setattr(r.ios_wda, "execute", fake_exec)
    monkeypatch.setattr(r, "_ask_vlm", fake_ask)

    run = await r.run("永远滑下去", max_steps=2)
    assert run.success is False
    assert run.steps[-1].answer == "步数用完仍未完成"


@pytest.mark.asyncio
async def test_react_screenshot_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot() -> None:
        return None

    monkeypatch.setattr(r.ios_wda, "screenshot_b64", fake_shot)
    run = await r.run("anything", max_steps=3)
    assert run.success is False
    assert "WDA" in (run.steps[-1].answer or "")


def test_extract_json_strips_markdown() -> None:
    assert r._extract_json('```json\n{"a":1}\n```') == {"a": 1}
    assert r._extract_json('plain {"x": 2} trailing') == {"x": 2}
    assert r._extract_json("not json at all") is None


@pytest.mark.asyncio
async def test_react_stuck_triggers_press_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """3x same action in a row should auto-inject press_home rescue."""
    async def fake_shot() -> str:
        return "S"

    same = {"type": "tap_text", "text": "卡住的按钮"}
    decisions = iter([
        {"thought": "t1", "action": same, "done": False},
        {"thought": "t2", "action": same, "done": False},
        {"thought": "t3", "action": same, "done": False},
        {"thought": "fresh", "action": None, "done": True, "answer": "好了"},
    ])

    async def fake_ask(goal: str, shot: str, hist: str) -> dict[str, Any]:
        return next(decisions)

    executed: list[dict[str, Any]] = []

    async def fake_exec(action: dict[str, Any]) -> dict[str, Any]:
        executed.append(action)
        return {"ok": True}

    monkeypatch.setattr(r.ios_wda, "screenshot_b64", fake_shot)
    monkeypatch.setattr(r.ios_wda, "execute", fake_exec)
    monkeypatch.setattr(r, "_ask_vlm", fake_ask)

    run = await r.run("test", max_steps=8)
    assert any(a.get("type") == "press_home" for a in executed)
    assert run.success is True
