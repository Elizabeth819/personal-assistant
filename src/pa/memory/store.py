"""Minimal in-process memory store. Replace with claude-mem bridge in V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class MemoryRecord:
    id: str
    text: str
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryStore:
    """Simplest possible store. Swap for sqlite/vector backend later."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    def add(self, record: MemoryRecord) -> MemoryRecord:
        self._records[record.id] = record
        return record

    def get(self, record_id: str) -> MemoryRecord | None:
        return self._records.get(record_id)

    def search(self, query: str, limit: int = 10) -> list[MemoryRecord]:
        q = query.lower()
        hits = [r for r in self._records.values() if q in r.text.lower()]
        return hits[:limit]

    def __len__(self) -> int:
        return len(self._records)
