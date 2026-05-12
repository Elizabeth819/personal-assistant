"""Embedding-backed long-term memory.

SQLite store: each row carries id, text, tags, created_at, embedding (BLOB float32).
Search = cosine similarity in pure numpy on the in-memory matrix (loaded lazily).

Embeddings come from Azure OpenAI text-embedding-3-small (1536 dim).
For corpora < ~50k records this is fast enough; swap for sqlite-vss / Qdrant later.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import httpx
import numpy as np

from pa.core import get_logger, get_settings

log = get_logger(__name__)

_DIM = 1536  # text-embedding-3-small


@dataclass(slots=True)
class RagHit:
    id: str
    text: str
    tags: list[str]
    score: float
    created_at: float


def _f32_to_blob(vec: np.ndarray) -> bytes:
    return struct.pack(f"{vec.size}f", *vec.astype(np.float32).tolist())


def _blob_to_f32(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


async def _embed(text: str) -> np.ndarray:
    s = get_settings()
    url = (
        f"{s.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
        f"{s.azure_embedding_deployment}/embeddings?api-version={s.azure_openai_api_version}"
    )
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            url,
            headers={"api-key": s.azure_openai_api_key, "Content-Type": "application/json"},
            json={"input": text},
        )
        r.raise_for_status()
        v = r.json()["data"][0]["embedding"]
    arr = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    return arr / n if n > 0 else arr


class RagStore:
    """SQLite-backed semantic memory."""

    def __init__(self, db_path: Path | None = None) -> None:
        s = get_settings()
        self.db_path = db_path or (s.data_dir / "rag.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._mat: np.ndarray | None = None
        self._ids: list[str] = []
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                  id TEXT PRIMARY KEY,
                  text TEXT NOT NULL,
                  tags TEXT NOT NULL DEFAULT '[]',
                  created_at REAL NOT NULL,
                  embedding BLOB NOT NULL
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_created ON records(created_at)")

    async def add(self, rec_id: str, text: str, tags: list[str] | None = None) -> None:
        vec = await _embed(text)
        with self._lock, sqlite3.connect(self.db_path) as c:
            c.execute(
                "INSERT OR REPLACE INTO records (id, text, tags, created_at, embedding) "
                "VALUES (?,?,?,?,?)",
                (rec_id, text, json.dumps(tags or []), time.time(), _f32_to_blob(vec)),
            )
            self._mat = None  # invalidate cache

    def _load_matrix(self) -> tuple[np.ndarray, list[tuple[str, str, str, float]]]:
        with sqlite3.connect(self.db_path) as c:
            rows = c.execute(
                "SELECT id, text, tags, created_at, embedding FROM records"
            ).fetchall()
        if not rows:
            return np.zeros((0, _DIM), dtype=np.float32), []
        meta = [(r[0], r[1], r[2], r[3]) for r in rows]
        mat = np.vstack([_blob_to_f32(r[4]) for r in rows])
        return mat, meta

    async def search(self, query: str, top_k: int = 4, min_score: float = 0.25) -> list[RagHit]:
        try:
            qv = await _embed(query)
        except Exception:
            log.exception("rag.embed_failed", query=query[:60])
            return []
        with self._lock:
            mat, meta = self._load_matrix()
        if mat.shape[0] == 0:
            return []
        scores = mat @ qv  # cosine since both are L2-normalised
        idx = np.argsort(-scores)[:top_k]
        hits: list[RagHit] = []
        for i in idx:
            s = float(scores[i])
            if s < min_score:
                continue
            mid, mtext, mtags, mts = meta[int(i)]
            hits.append(
                RagHit(
                    id=mid, text=mtext, tags=json.loads(mtags), score=s, created_at=float(mts)
                )
            )
        return hits

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as c:
            return int(c.execute("SELECT COUNT(*) FROM records").fetchone()[0])
