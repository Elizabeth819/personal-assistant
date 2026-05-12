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


async def run_realtime(*, instructions: str = "You are a concise voice assistant.") -> None:
    """Connect to Azure Realtime, stream mic, speak responses. Ctrl+C to stop."""
    s = get_settings()
    if not s.azure_openai_api_key or not s.azure_openai_endpoint:
        raise RuntimeError("Azure OpenAI not configured (PA_AZURE_OPENAI_*).")

    url = _ws_url()
    log.info("realtime.connect", url=url)

    audio_q: asyncio.Queue[np.ndarray] = asyncio.Queue()
    stop = asyncio.Event()

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
                        "turn_detection": {"type": "server_vad"},
                    },
                }
            )
        )

        mic_task = asyncio.create_task(_mic_loop(ws, stop))
        spk_task = asyncio.create_task(_speaker_loop(audio_q, stop))

        try:
            async for raw in ws:
                evt = json.loads(raw)
                t = evt.get("type", "")
                if t == "response.audio.delta":
                    await audio_q.put(_decode_pcm16(evt["delta"]))
                elif t == "response.audio_transcript.delta":
                    print(evt.get("delta", ""), end="", flush=True)
                elif t == "response.done":
                    print()
                elif t == "input_audio_buffer.speech_started":
                    print("\n[listening...]")
                elif t == "error":
                    log.error("realtime.error", error=evt.get("error"))
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            stop.set()
            mic_task.cancel()
            spk_task.cancel()
