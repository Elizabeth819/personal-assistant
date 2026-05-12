"""Azure OpenAI Realtime API client.

Bidirectional audio over WebSocket. Mic in -> server VAD -> model -> audio out.
Tested against `gpt-4o-realtime-preview` deployment.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import numpy as np
import sounddevice as sd
import websockets

from pa.core import get_logger, get_settings

log = get_logger(__name__)

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_MS = 40
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000


def _ws_url() -> str:
    s = get_settings()
    base = s.azure_openai_endpoint.rstrip("/").replace("https://", "wss://")
    return (
        f"{base}/openai/realtime"
        f"?api-version={s.azure_openai_api_version}"
        f"&deployment={s.azure_realtime_deployment}"
    )


def _headers() -> dict[str, str]:
    return {"api-key": get_settings().azure_openai_api_key}


def _b64_pcm16(samples: np.ndarray) -> str:
    pcm = (samples * 32767).clip(-32768, 32767).astype(np.int16).tobytes()
    return base64.b64encode(pcm).decode()


def _decode_pcm16(b64: str) -> np.ndarray:
    raw = base64.b64decode(b64)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


async def _mic_loop(ws: Any, stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

    def cb(indata: np.ndarray, _frames: int, _time: Any, _status: Any) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, indata.copy().reshape(-1))

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
        callback=cb,
    ):
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": _b64_pcm16(chunk),
                    }
                )
            )


async def _speaker_loop(events: asyncio.Queue[np.ndarray], stop: asyncio.Event) -> None:
    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32") as out:
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(events.get(), timeout=0.1)
            except TimeoutError:
                continue
            out.write(chunk.reshape(-1, 1))


async def run_realtime(
    *,
    instructions: str = "You are a concise voice assistant.",
    visual: bool = False,
) -> None:
    """Connect to Azure Realtime, stream mic, speak responses. Ctrl+C to stop."""
    s = get_settings()
    if not s.azure_openai_api_key or not s.azure_openai_endpoint:
        raise RuntimeError("Azure OpenAI not configured (PA_AZURE_OPENAI_*).")

    from pa.voice.visual import AgentView, Status, live

    view = AgentView()
    view.connection = s.azure_realtime_deployment
    view.set_status(Status.CONNECTING)

    url = _ws_url()
    log.info("realtime.connect", url=url)

    audio_q: asyncio.Queue[np.ndarray] = asyncio.Queue()
    stop = asyncio.Event()

    def emit(kind: str, detail: str = "") -> None:
        view.add_event(kind, detail)

    async def pump(ws: Any) -> None:
        async for raw in ws:
            evt = json.loads(raw)
            t = evt.get("type", "")
            if t == "session.created":
                emit(t, evt.get("session", {}).get("id", "")[:18])
                view.set_status(Status.IDLE)
            elif t == "response.audio.delta":
                await audio_q.put(_decode_pcm16(evt["delta"]))
                view.set_status(Status.SPEAKING)
            elif t == "response.audio_transcript.delta":
                delta = evt.get("delta", "")
                view.append_assistant(delta)
                if not visual:
                    print(delta, end="", flush=True)
            elif t == "conversation.item.input_audio_transcription.completed":
                view.append_user(evt.get("transcript", ""))
                emit(t, evt.get("transcript", "")[:60])
            elif t == "input_audio_buffer.speech_started":
                view.set_status(Status.LISTENING)
                emit(t)
            elif t == "input_audio_buffer.speech_stopped":
                view.set_status(Status.THINKING)
                emit(t)
            elif t == "response.done":
                view.end_assistant()
                view.set_status(Status.IDLE)
                emit(t)
                if not visual:
                    print()
            elif t == "error":
                view.set_status(Status.ERROR)
                emit(t, str(evt.get("error", ""))[:80])
                log.error("realtime.error", error=evt.get("error"))
            else:
                emit(t)

    async with websockets.connect(url, additional_headers=_headers(), max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "instructions": instructions,
                        "voice": "alloy",
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "input_audio_transcription": {"model": "whisper-1"},
                        "turn_detection": {"type": "server_vad"},
                    },
                }
            )
        )

        mic_task = asyncio.create_task(_mic_loop(ws, stop))
        spk_task = asyncio.create_task(_speaker_loop(audio_q, stop))

        async def render_loop() -> None:
            with live(view) as ui:
                while not stop.is_set():
                    ui.update(view.render())
                    await asyncio.sleep(0.08)

        ui_task = asyncio.create_task(render_loop()) if visual else None

        try:
            await pump(ws)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            stop.set()
            mic_task.cancel()
            spk_task.cancel()
            if ui_task:
                ui_task.cancel()
