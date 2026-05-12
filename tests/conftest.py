"""Shared fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pa.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
