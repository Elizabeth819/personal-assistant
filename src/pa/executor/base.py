"""Executor abstraction — device-agnostic action contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class Action(BaseModel):
    """A single intent to be executed on a target device."""

    name: str = Field(..., description="Action identifier, e.g. 'order_coffee'")
    target: str = Field(..., description="Device/adapter, e.g. 'ios', 'android', 'web'")
    params: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    ok: bool
    output: str = ""
    error: str | None = None


class Executor(ABC):
    """Executors translate Actions to device-side calls."""

    target: str

    @abstractmethod
    async def execute(self, action: Action) -> ActionResult: ...
