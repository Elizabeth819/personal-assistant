"""HTTP routes."""

from __future__ import annotations

import base64

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from pa import __version__
from pa.adapters import ios_devicectl
from pa.adapters.echo import EchoExecutor
from pa.agent import session as conv
from pa.agent.intent import plan_actions
from pa.agent.react import run as react_run
from pa.agent.react import to_dict as react_to_dict
from pa.core import get_settings
from pa.executor.base import Action, ActionResult
from pa.memory.rag import RagStore
from pa.memory.store import MemoryRecord, MemoryStore
from pa.voice.azure_openai import chat_reply, synthesize_to_wav, transcribe_audio

router = APIRouter()
_memory = MemoryStore()
_echo = EchoExecutor()
_rag = RagStore()


async def _rag_context(query: str) -> str | None:
    s = get_settings()
    if not s.rag_enabled or not s.azure_openai_api_key:
        return None
    try:
        hits = await _rag.search(query, top_k=s.rag_top_k, min_score=s.rag_min_score)
    except Exception:
        return None
    if not hits:
        return None
    return "\n".join(f"- ({h.score:.2f}) {h.text}" for h in hits)


class HealthResponse(BaseModel):
    ok: bool = True
    version: str = __version__


class MemoryAddRequest(BaseModel):
    id: str
    text: str
    tags: list[str] = []


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.post("/memory", response_model=MemoryRecord)
async def add_memory(req: MemoryAddRequest) -> MemoryRecord:
    return _memory.add(MemoryRecord(id=req.id, text=req.text, tags=req.tags))


@router.get("/memory/search")
async def search_memory(q: str, limit: int = 10) -> list[MemoryRecord]:
    return _memory.search(q, limit)


@router.post("/execute", response_model=ActionResult)
async def execute(action: Action) -> ActionResult:
    return await _echo.execute(action)


@router.post("/voice/turn")
async def voice_turn(
    audio: UploadFile = File(...),  # noqa: B008
    system: str | None = Form(default=None),
    audio_format: str = Form(default="b64"),  # "b64" | "binary" | "none"
    autorun: bool | None = Form(default=None),
    session_id: str = Form(default="default"),
) -> Response:
    raw = await audio.read()
    user_text = await transcribe_audio(raw, filename=audio.filename or "audio.m4a")
    history = conv.get_history(session_id)
    ctx = await _rag_context(user_text)
    reply_text = await chat_reply(user_text, system=system, history=history, rag_context=ctx)
    actions = plan_actions(user_text, reply_text)

    s = get_settings()
    do_run = s.ios_device_autorun if autorun is None else autorun
    device_results: list[dict[str, object]] = []
    if do_run and s.ios_device_udid:
        device_results = await ios_devicectl.run_actions(s.ios_device_udid, actions)
        reply_text = _augment_reply(reply_text, actions, device_results)
        for a in actions:
            if a.get("type") == "say":
                a["text"] = reply_text
    conv.append(session_id, user_text, reply_text)

    if audio_format == "binary":
        wav = await synthesize_to_wav(reply_text)
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={
                "X-User-Text": user_text.encode("utf-8", "replace").decode("latin-1", "replace"),
                "X-Reply-Text": reply_text.encode("utf-8", "replace").decode("latin-1", "replace"),
            },
        )

    payload: dict[str, object] = {
        "user_text": user_text,
        "reply_text": reply_text,
        "actions": actions,
        "device_results": device_results,
    }
    if audio_format == "b64":
        wav = await synthesize_to_wav(reply_text)
        payload["audio_wav_b64"] = base64.b64encode(wav).decode("ascii")
    return JSONResponse(payload)


@router.post("/voice/text")
async def voice_text(
    text: str = Form(...),
    system: str | None = Form(default=None),
    with_audio: bool = Form(default=False),
    autorun: bool | None = Form(default=None),
    session_id: str = Form(default="default"),
) -> JSONResponse:
    """Text-only path (skip ASR) — useful for testing the planner from a phone keyboard."""
    history = conv.get_history(session_id)
    ctx = await _rag_context(text)
    reply_text = await chat_reply(text, system=system, history=history, rag_context=ctx)
    actions = plan_actions(text, reply_text)
    s = get_settings()
    do_run = s.ios_device_autorun if autorun is None else autorun
    device_results: list[dict[str, object]] = []
    if do_run and s.ios_device_udid:
        device_results = await ios_devicectl.run_actions(s.ios_device_udid, actions)
        reply_text = _augment_reply(reply_text, actions, device_results)
        for a in actions:
            if a.get("type") == "say":
                a["text"] = reply_text
    conv.append(session_id, text, reply_text)
    payload: dict[str, object] = {
        "user_text": text,
        "reply_text": reply_text,
        "actions": actions,
        "device_results": device_results,
        "history_len": len(conv.get_history(session_id)),
    }
    if with_audio:
        wav = await synthesize_to_wav(reply_text)
        payload["audio_wav_b64"] = base64.b64encode(wav).decode("ascii")
    return JSONResponse(payload)


@router.post("/session/reset")
async def session_reset(session_id: str = Form(default="default")) -> JSONResponse:
    conv.reset(session_id)
    return JSONResponse({"ok": True, "session_id": session_id})


def _augment_reply(reply: str, actions: list, results: list) -> str:
    """If a result carries a textual payload (weather summary, screen explain),
    splice it into the spoken reply so the user hears the actual answer."""
    extras: list[str] = []
    for a, r in zip(actions, results):
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        if a.get("type") == "weather" and r.get("summary"):
            extras.append(str(r["summary"]))
        elif a.get("type") == "screen_explain" and r.get("text"):
            extras.append(str(r["text"]))
    if extras:
        return " ".join(extras)
    return reply


@router.get("/devices")
async def list_devices() -> JSONResponse:
    return JSONResponse({"devices": await ios_devicectl.list_devices()})


class RagAddRequest(BaseModel):
    id: str
    text: str
    tags: list[str] = []


@router.post("/rag/add")
async def rag_add(req: RagAddRequest) -> JSONResponse:
    await _rag.add(req.id, req.text, req.tags)
    return JSONResponse({"ok": True, "count": _rag.count()})


@router.get("/rag/search")
async def rag_search(q: str, top_k: int = 4) -> JSONResponse:
    hits = await _rag.search(q, top_k=top_k, min_score=0.0)
    return JSONResponse({"hits": [h.__dict__ for h in hits]})


@router.get("/rag/stats")
async def rag_stats() -> JSONResponse:
    return JSONResponse({"count": _rag.count()})


@router.post("/react/run")
async def react_endpoint(
    goal: str = Form(...),
    max_steps: int = Form(default=8),
) -> JSONResponse:
    """Run the visual ReAct loop on the connected iPhone."""
    res = await react_run(goal, max_steps=max_steps)
    return JSONResponse(react_to_dict(res))
