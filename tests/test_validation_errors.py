import json

from fastapi.testclient import TestClient

from src.app import app, summarize_validation_errors
from src.handlers import messages as messages_handler


def _thinking_request(stream: bool = False) -> dict:
    return {
        "model": "claude-sonnet-5",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": stream,
        "thinking": {"type": "enabled", "budget_tokens": 4096},
    }


def _haiku_thinking_request() -> dict:
    return {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "Hello"}],
        "thinking": {"type": "enabled", "budget_tokens": 31999},
    }


def _unsupported_system_tool_request(stream: bool = False) -> dict:
    return {
        "model": "claude-sonnet-5",
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "search",
                        "input": {"query": "example"},
                    }
                ],
            },
            {"role": "user", "content": "Hello"},
        ],
        "stream": stream,
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

    assert details == {
        "total_count": 1,
        "omitted_count": 0,
        "errors": [
            {
                "loc": ["body", "messages", 0],
                "msg": "bad",
                "type": "value_error",
            }
        ],
    }


def test_validation_error_details_are_bounded_and_safe() -> None:
    details = summarize_validation_errors(
        [
            {
                "loc": ("body", "messages", index),
                "msg": "secret " + ("x" * 500),
                "type": "value_error",
                "input": "do not expose",
            }
            for index in range(20)
        ]
    )

    assert details["total_count"] == 20
    assert details["omitted_count"] > 0
    assert len(details["errors"]) < 20
    assert all("input" not in error for error in details["errors"])
    assert all(len(error["msg"]) <= 200 for error in details["errors"])


def test_enabled_thinking_returns_anthropic_compatibility_error() -> None:
    response = TestClient(app).post("/v1/messages", json=_thinking_request())

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == "thinking"


def test_haiku_enabled_thinking_sends_luna_max_reasoning(monkeypatch) -> None:
    captured_payload: dict = {}

    async def fake_transport(payload: dict) -> dict:
        captured_payload.update(payload)
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Hi"}],
                }
            ],
        }

    monkeypatch.setattr(messages_handler, "create_openai_response", fake_transport)

    response = TestClient(app).post("/v1/messages", json=_haiku_thinking_request())

    assert response.status_code == 200
    assert captured_payload["model"] == "gpt-5.6-luna"
    assert captured_payload["reasoning"] == {"effort": "max"}


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


def test_system_tool_use_returns_compatibility_error_before_non_stream_transport(
    monkeypatch,
) -> None:
    async def unexpected_transport(_: dict) -> dict:
        raise AssertionError("transport must not be reached")

    monkeypatch.setattr(messages_handler, "create_openai_response", unexpected_transport)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/messages",
        json=_unsupported_system_tool_request(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == "messages"


def test_system_tool_use_stream_returns_sse_error_before_transport(monkeypatch) -> None:
    def unexpected_transport(_: dict):
        raise AssertionError("transport must not be reached")

    monkeypatch.setattr(messages_handler, "stream_openai_events", unexpected_transport)

    with TestClient(app, raise_server_exceptions=False).stream(
        "POST",
        "/v1/messages/stream",
        json=_unsupported_system_tool_request(stream=True),
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    data_lines = [line for line in body.splitlines() if line.startswith("data:")]
    assert data_lines
    payload = json.loads(data_lines[-1][len("data:") :].strip())
    assert payload["error"]["type"] == "invalid_request_error"
    assert payload["error"]["param"] == "messages"


def test_invalid_default_reasoning_effort_returns_anthropic_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_DEFAULT_REASONING_EFFORT", " invalid ")

    response = TestClient(app).post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-5",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )

    assert response.status_code == 400
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["param"] == "OPENAI_DEFAULT_REASONING_EFFORT"


def test_invalid_default_reasoning_effort_stream_returns_sse_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_DEFAULT_REASONING_EFFORT", " invalid ")

    with TestClient(app).stream(
        "POST",
        "/v1/messages/stream",
        json={
            "model": "claude-sonnet-5",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: error" in body
    data_lines = [line for line in body.splitlines() if line.startswith("data:")]
    payload = json.loads(data_lines[-1][len("data:") :].strip())
    assert payload["error"]["type"] == "invalid_request_error"
    assert payload["error"]["param"] == "OPENAI_DEFAULT_REASONING_EFFORT"
