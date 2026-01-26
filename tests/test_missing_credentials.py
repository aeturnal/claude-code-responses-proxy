import json

from fastapi.testclient import TestClient

from src import config
from src.app import app


def _minimal_request() -> dict:
    return {
        "model": "claude-3-sonnet-20240229",
        "messages": [{"role": "user", "content": "Hello"}],
    }


def test_messages_missing_api_key(monkeypatch) -> None:
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    client = TestClient(app)

    response = client.post("/v1/messages", json=_minimal_request())

    assert response.status_code == 401
    payload = response.json()
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "authentication_error"
    assert (
        payload["error"]["openai"]["error"]["message"] == "OPENAI_API_KEY is required"
    )


def test_stream_missing_api_key(monkeypatch) -> None:
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
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
