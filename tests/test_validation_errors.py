import json

from fastapi.testclient import TestClient

from src.app import app, summarize_validation_errors


def _thinking_request(stream: bool = False) -> dict:
    return {
        "model": "claude-sonnet-5",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": stream,
        "thinking": {"type": "enabled", "budget_tokens": 4096},
    }


def test_invalid_message_request_returns_anthropic_envelope() -> None:
    response = TestClient(app).post("/v1/messages", json={"model": "claude-sonnet-5"})

    assert response.status_code == 400
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["message"] == "Invalid request"


def test_validation_error_log_data_excludes_raw_input() -> None:
    details = summarize_validation_errors(
        [
            {
                "loc": ("body", "messages", 0),
                "msg": "bad",
                "type": "value_error",
                "input": "secret",
            }
        ]
    )

    assert details == [
        {"loc": ["body", "messages", 0], "msg": "bad", "type": "value_error"}
    ]


def test_enabled_thinking_returns_anthropic_compatibility_error() -> None:
    response = TestClient(app).post("/v1/messages", json=_thinking_request())

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == "thinking"


def test_enabled_thinking_stream_returns_sse_error() -> None:
    with TestClient(app).stream(
        "POST", "/v1/messages/stream", json=_thinking_request(stream=True)
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    data_lines = [line for line in body.splitlines() if line.startswith("data:")]
    assert data_lines
    payload = json.loads(data_lines[-1][len("data:") :].strip())
    assert payload["error"]["type"] == "invalid_request_error"
    assert payload["error"]["param"] == "thinking"
