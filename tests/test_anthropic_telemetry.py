from __future__ import annotations

from fastapi.testclient import TestClient

from src.app import app
from src.observability.redaction import (
    LOG_ARRAY_LIMIT,
    REDACTION_TOKEN,
    redact_generic_payload,
)


def test_anthropic_telemetry_endpoint_returns_204() -> None:
    client = TestClient(app)
    response = client.post("/api/event_logging/batch", json={"ok": True})
    assert response.status_code == 204


def test_redact_generic_payload_redacts_sensitive_keys_and_truncates_lists() -> None:
    payload = {
        "token": "secret-token",
        "profile": {
            "email": "test@example.com",
            "name": "Ada Lovelace",
        },
        "items": list(range(LOG_ARRAY_LIMIT + 2)),
    }
    redacted = redact_generic_payload(payload)

    assert redacted["token"] == REDACTION_TOKEN
    assert redacted["profile"]["email"] == REDACTION_TOKEN
    assert redacted["profile"]["name"] == REDACTION_TOKEN
    assert len(redacted["items"]) == LOG_ARRAY_LIMIT
    assert redacted["payload_truncated"] is True
