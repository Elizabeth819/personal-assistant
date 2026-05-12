"""Tests for the embedding-backed RAG store. _embed is monkey-patched
so we don't need an Azure key in CI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pa.memory import rag as rag_mod


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> rag_mod.RagStore:
    """Deterministic toy embeddings driven by hash so similar words cluster."""

    rng = np.random.default_rng(0)
    cache: dict[str, np.ndarray] = {}

    async def fake_embed(text: str) -> np.ndarray:
        if text in cache:
            return cache[text]
        seed = sum(ord(c) for c in text) % (2**31)
        v = np.random.default_rng(seed).standard_normal(rag_mod._DIM).astype(np.float32)
        v += 0.1 * rng.standard_normal(rag_mod._DIM).astype(np.float32)
        v = v / np.linalg.norm(v)
        cache[text] = v
        return v

    monkeypatch.setattr(rag_mod, "_embed", fake_embed)
    return rag_mod.RagStore(db_path=tmp_path / "rag.sqlite3")


@pytest.mark.asyncio
async def test_add_and_count(store: rag_mod.RagStore) -> None:
    await store.add("a", "你好", ["greeting"])
    await store.add("b", "再见", ["farewell"])
    assert store.count() == 2


@pytest.mark.asyncio
async def test_search_returns_hits(store: rag_mod.RagStore) -> None:
    await store.add("a", "我喜欢吃北京烤鸭", ["food"])
    await store.add("b", "上次去三里屯的火锅店不错", ["food"])
    await store.add("c", "下周二要交季度汇报", ["work"])
    hits = await store.search("好吃的餐厅", top_k=3, min_score=-1.0)
    assert len(hits) == 3
    for h in hits:
        assert h.score >= -1.0 and h.score <= 1.0


@pytest.mark.asyncio
async def test_replace_same_id(store: rag_mod.RagStore) -> None:
    await store.add("a", "v1")
    await store.add("a", "v2")
    assert store.count() == 1


@pytest.mark.asyncio
async def test_empty_store_returns_no_hits(store: rag_mod.RagStore) -> None:
    assert await store.search("anything") == []


@pytest.mark.asyncio
async def test_min_score_filter(store: rag_mod.RagStore) -> None:
    await store.add("a", "hello world")
    hits = await store.search("hello world", top_k=5, min_score=0.99)
    assert all(h.score >= 0.99 for h in hits)
