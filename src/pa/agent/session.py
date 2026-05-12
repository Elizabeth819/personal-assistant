"""Per-session conversation memory.

Stores the last N turns per session_id, with a TTL so dead sessions
don't accumulate. In-memory; persistence is out of scope for now.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

_MAX_TURNS = 10  # user+assistant pairs
_TTL_SECONDS = 30 * 60
_MAX_SESSIONS = 100

_lock = Lock()
_sessions: OrderedDict[str, tuple[float, list[dict[str, str]]]] = OrderedDict()


def _gc() -> None:
    now = time.time()
    dead = [k for k, (ts, _) in _sessions.items() if now - ts > _TTL_SECONDS]
    for k in dead:
        _sessions.pop(k, None)
    while len(_sessions) > _MAX_SESSIONS:
        _sessions.popitem(last=False)


def get_history(session_id: str) -> list[dict[str, str]]:
    if not session_id:
        return []
    with _lock:
        _gc()
        rec = _sessions.get(session_id)
        if not rec:
            return []
        # touch
        _sessions.move_to_end(session_id)
        _sessions[session_id] = (time.time(), rec[1])
        return list(rec[1])


def append(session_id: str, user: str, assistant: str) -> None:
    if not session_id:
        return
    with _lock:
        _gc()
        ts, hist = _sessions.get(session_id, (time.time(), []))
        hist.append({"role": "user", "content": user})
        hist.append({"role": "assistant", "content": assistant})
        # cap to last 2*N entries
        cap = _MAX_TURNS * 2
        if len(hist) > cap:
            hist = hist[-cap:]
        _sessions[session_id] = (time.time(), hist)
        _sessions.move_to_end(session_id)


def reset(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)


def stats() -> dict[str, int]:
    with _lock:
        return {"sessions": len(_sessions)}
