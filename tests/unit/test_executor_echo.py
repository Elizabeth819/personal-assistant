import pytest

from pa.adapters.echo import EchoExecutor
from pa.executor.base import Action


@pytest.mark.asyncio
async def test_echo_executor() -> None:
    e = EchoExecutor()
    result = await e.execute(Action(name="ping", target="echo", params={"x": 1}))
    assert result.ok
    assert "ping" in result.output
