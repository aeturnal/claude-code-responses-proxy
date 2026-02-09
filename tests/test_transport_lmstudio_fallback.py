from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from src.transport import lmstudio, openai_client, openai_stream


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: Dict[str, Any] | None = None,
        text: str = "",
        headers: Dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {"content-type": "application/json"}

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> Dict[str, Any]:
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload

    async def aread(self) -> bytes:
        return self.text.encode("utf-8")

    async def aiter_lines(self):
        for line in self.text.splitlines():
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _invalid_union_error() -> Dict[str, Any]:
    return {
        "error": {
            "param": "input",
            "code": "invalid_union",
            "message": "invalid input union",
        }
    }


def _base_payload() -> Dict[str, Any]:
    return {
        "model": "gpt-4o-mini",
        "input": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "input_text", "text": "Tool output"}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hi"}],
            },
        ],
    }


def test_create_openai_response_lmstudio_fallback_sequence(monkeypatch) -> None:
    sent_payloads: List[Dict[str, Any]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self._responses = [
                _FakeResponse(status_code=400, payload=_invalid_union_error()),
                _FakeResponse(status_code=400, payload=_invalid_union_error()),
                _FakeResponse(status_code=200, payload={"id": "resp_ok"}),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str]):
            sent_payloads.append(json)
            return self._responses.pop(0)

    async def _build_request(_client):
        return "https://example.test/v1/responses", {}, False

    monkeypatch.setattr(openai_client.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(openai_client, "_build_upstream_request", _build_request)
    monkeypatch.setattr(openai_client.config, "require_upstream_mode", lambda: "openai")
    monkeypatch.setattr(openai_client, "is_lmstudio_base_url", lambda: True)

    payload = _base_payload()
    result = asyncio.run(openai_client.create_openai_response(payload))

    normalized = lmstudio.normalize_payload(payload)
    collapsed = lmstudio.collapse_payload(payload)

    assert result["id"] == "resp_ok"
    assert sent_payloads[0] == payload
    assert sent_payloads[1] == normalized
    assert sent_payloads[2] == collapsed


def test_stream_openai_events_lmstudio_fallback_sequence(monkeypatch) -> None:
    sent_payloads: List[Dict[str, Any]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            completed = json.dumps(
                {
                    "type": "response.completed",
                    "response": {"status": "completed", "output": []},
                }
            )
            self._responses = [
                _FakeResponse(status_code=400, payload=_invalid_union_error()),
                _FakeResponse(status_code=400, payload=_invalid_union_error()),
                _FakeResponse(
                    status_code=200,
                    payload={"ok": True},
                    text=f"event: response.completed\ndata: {completed}\n",
                ),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(
            self,
            method: str,
            url: str,
            json: Dict[str, Any],
            headers: Dict[str, str],
        ) -> _FakeStreamContext:
            sent_payloads.append(json)
            return _FakeStreamContext(self._responses.pop(0))

    async def _build_request(_client):
        return "https://example.test/v1/responses", {}, False

    monkeypatch.setattr(openai_stream.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(openai_stream, "_build_upstream_request", _build_request)
    monkeypatch.setattr(openai_stream.config, "require_upstream_mode", lambda: "openai")
    monkeypatch.setattr(openai_stream, "is_lmstudio_base_url", lambda: True)

    payload = _base_payload()

    async def _collect() -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        async for event in openai_stream.stream_openai_events(payload):
            output.append(event)
        return output

    events = asyncio.run(_collect())
    normalized = lmstudio.normalize_payload({**payload, "stream": True})
    collapsed = lmstudio.collapse_payload({**payload, "stream": True})

    assert events[-1]["event"] == "response.completed"
    assert sent_payloads[0]["input"] == payload["input"]
    assert sent_payloads[0]["stream"] is True
    assert sent_payloads[1] == normalized
    assert sent_payloads[2] == collapsed
