from unittest.mock import patch

import numpy as np
import pytest

from pa.voice.realtime import _b64_pcm16, _decode_pcm16, _ws_url, run_realtime


def test_pcm_roundtrip() -> None:
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    decoded = _decode_pcm16(_b64_pcm16(samples))
    assert decoded.shape == samples.shape
    np.testing.assert_allclose(decoded, samples, atol=1e-3)


def test_ws_url_built_from_settings() -> None:
    fake = type(
        "S",
        (),
        {
            "azure_openai_endpoint": "https://x.openai.azure.com/",
            "azure_openai_api_version": "2024-10-01-preview",
            "azure_realtime_deployment": "gpt-4o-realtime-preview",
        },
    )()
    with patch("pa.voice.realtime.get_settings", return_value=fake):
        url = _ws_url()
    assert url.startswith("wss://x.openai.azure.com/openai/realtime")
    assert "deployment=gpt-4o-realtime-preview" in url


@pytest.mark.asyncio
async def test_run_realtime_requires_credentials() -> None:
    fake = type("S", (), {"azure_openai_endpoint": "", "azure_openai_api_key": ""})()
    with (
        patch("pa.voice.realtime.get_settings", return_value=fake),
        pytest.raises(RuntimeError, match="Azure"),
    ):
        await run_realtime()
