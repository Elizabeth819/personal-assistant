"""Echo adapter — for tests and harness sanity checks."""

from __future__ import annotations

from pa.executor.base import Action, ActionResult, Executor


class EchoExecutor(Executor):
    target = "echo"

    async def execute(self, action: Action) -> ActionResult:
        return ActionResult(ok=True, output=f"echo:{action.name}:{action.params}")
