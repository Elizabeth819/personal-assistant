"""HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from pa import __version__
from pa.adapters.echo import EchoExecutor
from pa.executor.base import Action, ActionResult
from pa.memory.store import MemoryRecord, MemoryStore

router = APIRouter()
_memory = MemoryStore()
_echo = EchoExecutor()


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
