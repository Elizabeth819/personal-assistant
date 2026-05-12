"""Azure OpenAI HTTP helpers for the iOS Shortcut bridge.

- transcribe(audio_bytes, mime): Whisper deployment -> text
- chat(user_text, history): chat deployment -> text reply
- synthesize(text): gpt-realtime over WS -> wav bytes
"""

from __future__ import annotations

import asyncio
import base64
import json
import wave
from io import BytesIO

import httpx
import websockets

from pa.core import get_logger, get_settings

log = get_logger(__name__)

SAMPLE_RATE = 24000


def _rest_url(deployment: str, route: str) -> str:
    s = get_settings()
    base = s.azure_openai_endpoint.rstrip("/")
    return f"{base}/openai/deployments/{deployment}/{route}?api-version={s.azure_openai_api_version}"


def _key_headers() -> dict[str, str]:
    return {"api-key": get_settings().azure_openai_api_key}


async def transcribe_audio(audio: bytes, *, filename: str = "audio.m4a") -> str:
    s = get_settings()
    url = _rest_url(s.azure_whisper_deployment, "audio/transcriptions")
    files = {"file": (filename, audio, "application/octet-stream")}
    data = {"response_format": "json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers=_key_headers(), files=files, data=data)
        r.raise_for_status()
        return str(r.json().get("text", "")).strip()


async def chat_reply(
    user_text: str,
    *,
    system: str | None = None,
    history: list[dict[str, str]] | None = None,
    rag_context: str | None = None,
) -> str:
    s = get_settings()
    url = _rest_url(s.azure_chat_deployment, "chat/completions")
    sys_msg = system or (
        "你是一个简洁的中文个人助理。你**已经**接入了用户的 iPhone："  # noqa: RUF001
        "可以打开任何 app、设置计时器、点击/输入/滑动屏幕、播放音乐、发起导航。"
        "用户的指令会被并行调度到设备执行——你只负责回复，不要再说"
        "「我无法操作你的设备」「请在手机上手动…」「请告诉我设备型号」之类的话。"
        "回复尽量短，1-2 句话，自然口语，**默认假设动作已经在执行**。"
        "对话有上下文,'那后天呢'、'再来一首'、'继续'指代前一轮的话题。"
    )
    if rag_context:
        sys_msg += (
            "\n\n以下是从用户的私人知识库中检索到的相关记忆，"
            "如果对回答有帮助就用它，否则忽略；不要把记忆原文复述给用户：\n"
            f"{rag_context}"
        )
    msgs: list[dict[str, str]] = [{"role": "system", "content": sys_msg}]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": user_text})
    body = {"messages": msgs, "max_tokens": 300}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers={**_key_headers(), "Content-Type": "application/json"},
                         json=body)
        r.raise_for_status()
        return str(r.json()["choices"][0]["message"]["content"]).strip()


async def describe_image(image_b64: str, instruction: str = "描述这张图片") -> str:
    """Send a base64 image to the chat deployment with vision and return the text answer."""
    s = get_settings()
    url = _rest_url(s.azure_chat_deployment, "chat/completions")
    body = {
        "messages": [
            {"role": "system", "content": "你是一个简洁的中文视觉助手,1-3句话回答。"},
            {"role": "user", "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ]},
        ],
        "max_tokens": 400,
    }
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers={**_key_headers(), "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        return str(r.json()["choices"][0]["message"]["content"]).strip()


def _pcm16_to_wav(pcm: bytes, sr: int = SAMPLE_RATE) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


async def synthesize_to_wav(text: str, *, voice: str = "alloy") -> bytes:
    """Use the realtime WS to turn text into a single audio response → wav bytes."""
    s = get_settings()
    base = s.azure_openai_endpoint.rstrip("/").replace("https://", "wss://")
    url = (
        f"{base}/openai/realtime"
        f"?api-version={s.azure_openai_api_version}"
        f"&deployment={s.azure_realtime_deployment}"
    )
    pcm_chunks: list[bytes] = []
    async with websockets.connect(url, additional_headers=_key_headers(), max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "voice": voice,
                "output_audio_format": "pcm16",
            },
        }))
        await ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }))
        await ws.send(json.dumps({
            "type": "response.create",
            "response": {"modalities": ["audio", "text"], "instructions": "把上面的文本朗读出来。"},
        }))
        try:
            async for raw in ws:
                evt = json.loads(raw)
                t = evt.get("type", "")
                if t == "response.audio.delta":
                    pcm_chunks.append(base64.b64decode(evt["delta"]))
                elif t == "response.done":
                    break
                elif t == "error":
                    log.error("tts.error", error=evt.get("error"))
                    break
        except asyncio.TimeoutError:
            pass
    return _pcm16_to_wav(b"".join(pcm_chunks))
