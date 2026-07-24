"""Opt-in smoke test for GPT-5.6 Codex model and reasoning availability."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROXY_BASE = os.environ.get("PROXY_BASE", "http://127.0.0.1:8000").rstrip("/")
REQUESTS = (
    ("claude-opus-5", "high"),
    ("claude-sonnet-5", "medium"),
    ("claude-haiku-4-5-20251001", "low"),
)
USER_CONTENT = "Reply with OK."
MAX_RESPONSE_BYTES = 64 * 1024
RESPONSE_READ_CHUNK_BYTES = 8 * 1024
MAX_ERROR_MESSAGE_CHARS = 500
ANSI_ESCAPE_SEQUENCE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _normalize_error_message(message: str) -> str:
    """Redact request content and make an error safe for one-line terminal output."""
    redacted = ANSI_ESCAPE_SEQUENCE.sub("", message).replace(
        USER_CONTENT, "[redacted]"
    )
    printable = "".join(
        character if character.isprintable() else " " for character in redacted
    )
    return " ".join(printable.split())[:MAX_ERROR_MESSAGE_CHARS]


def _read_response_body(response: object) -> tuple[bytes | None, str | None]:
    """Read a small smoke-test response without retaining an unbounded stream."""
    read = getattr(response, "read")
    body = bytearray()
    while len(body) <= MAX_RESPONSE_BYTES:
        remaining = MAX_RESPONSE_BYTES + 1 - len(body)
        chunk = read(min(RESPONSE_READ_CHUNK_BYTES, remaining))
        if not chunk:
            return bytes(body), None
        body.extend(chunk)
    return None, "response exceeded smoke-test size limit"


def _safe_error_message(body: bytes) -> str | None:
    """Return a concise structured error without emitting request or response content."""
    try:
        parsed = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        parsed = None

    if isinstance(parsed, Mapping):
        error = parsed.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str):
                return message

    text = body.decode("utf-8", errors="replace")
    for frame in text.split("\n\n"):
        if not any(line.strip() == "event: error" for line in frame.splitlines()):
            continue
        data = "\n".join(
            line[len("data:") :].lstrip()
            for line in frame.splitlines()
            if line.startswith("data:")
        )
        try:
            event_payload = json.loads(data)
        except json.JSONDecodeError:
            return "SSE error event"
        if isinstance(event_payload, Mapping):
            error = event_payload.get("error")
            if isinstance(error, Mapping) and isinstance(error.get("message"), str):
                return error["message"]
        return "SSE error event"
    return None


def _run_request(model: str, effort: str) -> tuple[int, str | None]:
    payload = {
        "model": model,
        "max_tokens": 64,
        "stream": True,
        "output_config": {"effort": effort},
        "messages": [{"role": "user", "content": USER_CONTENT}],
    }
    request = Request(
        f"{PROXY_BASE}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=300) as response:
            try:
                body, read_error = _read_response_body(response)
            except TimeoutError:
                return response.status, "proxy response timed out"
            except (OSError, HTTPException):
                return response.status, "proxy response read failed"
            if read_error:
                return response.status, read_error
            assert body is not None
            return response.status, _safe_error_message(body)
    except HTTPError as exc:
        try:
            body, read_error = _read_response_body(exc)
        except TimeoutError:
            return exc.code, "proxy error response timed out"
        except (OSError, HTTPException):
            return exc.code, "proxy error response read failed"
        if read_error:
            return exc.code, read_error
        assert body is not None
        return exc.code, _safe_error_message(body) or "HTTP error response"
    except TimeoutError:
        return 0, "proxy request timed out"
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            return 0, "proxy request timed out"
        return 0, f"proxy connection failed: {exc.reason}"


def main() -> int:
    all_succeeded = True
    for model, effort in REQUESTS:
        status, error = _run_request(model, effort)
        if error:
            error = _normalize_error_message(error)
        succeeded = 200 <= status < 300 and error is None
        all_succeeded = all_succeeded and succeeded
        result = f"model={model} effort={effort} status={status}"
        if error:
            result = f"{result} error={error}"
        print(result)
    return 0 if all_succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
