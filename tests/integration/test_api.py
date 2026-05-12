from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_memory_roundtrip(client: TestClient) -> None:
    r = client.post("/memory", json={"id": "a", "text": "hello world", "tags": ["x"]})
    assert r.status_code == 200

    r = client.get("/memory/search", params={"q": "hello"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_execute(client: TestClient) -> None:
    r = client.post("/execute", json={"name": "ping", "target": "echo", "params": {}})
    assert r.status_code == 200
    assert r.json()["ok"] is True
