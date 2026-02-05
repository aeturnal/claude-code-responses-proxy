import json

from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.transport import openai_client, openai_stream


def _minimal_request() -> dict:
    return {
        "model": "claude-3-sonnet-20240229",
        "messages": [{"role": "user", "content": "Hello"}],
    }


def _reset_caches() -> None:
    openai_client._codex_manager.cache_clear()
    openai_stream._codex_manager.cache_clear()


def test_messages_missing_codex_auth_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "OPENAI_UPSTREAM_MODE", "codex")
    monkeypatch.setattr(config, "CODEX_AUTH_PATH", str(tmp_path / "auth.json"))
    _reset_caches()

    client = TestClient(app)
    response = client.post("/v1/messages", json=_minimal_request())

    assert response.status_code == 401
    payload = response.json()
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "authentication_error"
    assert "codex auth file" in payload["error"]["openai"]["error"]["message"].lower()


def test_stream_missing_codex_auth_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "OPENAI_UPSTREAM_MODE", "codex")
    monkeypatch.setattr(config, "CODEX_AUTH_PATH", str(tmp_path / "auth.json"))
    _reset_caches()

    client = TestClient(app)

    with client.stream(
        "POST", "/v1/messages/stream", json=_minimal_request()
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = "".join(response.iter_text())

    assert "event: error" in body
    data_lines = [line for line in body.splitlines() if line.startswith("data:")]
    assert data_lines
    error_payload = json.loads(data_lines[-1][len("data:") :].strip())
    assert error_payload["error"]["type"] == "authentication_error"
