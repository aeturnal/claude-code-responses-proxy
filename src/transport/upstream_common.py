"""Shared upstream request helpers for OpenAI/Codex transports."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from asgi_correlation_id import correlation_id

from src import config
from src.codex_auth import (
    CodexAuthManager,
    CodexAuthStore,
    CodexTokenRefreshError,
    MissingCodexCredentialsError,
)


@lru_cache(maxsize=2)
def get_codex_manager() -> CodexAuthManager:
    path = (
        Path(config.CODEX_AUTH_PATH).expanduser()
        if config.CODEX_AUTH_PATH
        else Path("~/.codex/auth.json").expanduser()
    )
    return CodexAuthManager(CodexAuthStore(path))


async def build_upstream_request(
    client: httpx.AsyncClient,
) -> tuple[str, dict[str, str], bool]:
    """Return (url, headers, can_refresh_on_401)."""
    mode = config.require_upstream_mode()
    headers: dict[str, str] = {}

    upstream_correlation_id = correlation_id.get()
    if upstream_correlation_id:
        headers["X-Correlation-ID"] = upstream_correlation_id

    if mode == "openai":
        api_key = config.require_openai_api_key()
        headers["Authorization"] = f"Bearer {api_key}"
        return f"{config.OPENAI_BASE_URL}/responses", headers, False

    try:
        tokens = await get_codex_manager().ensure_fresh(client)
    except (MissingCodexCredentialsError, CodexTokenRefreshError) as exc:
        raise config.MissingUpstreamCredentialsError(
            str(exc) or "Codex credentials missing"
        ) from exc

    headers["Authorization"] = f"Bearer {tokens.access_token}"
    if tokens.account_id:
        headers["ChatGPT-Account-ID"] = tokens.account_id
    return f"{config.CODEX_BASE_URL}/responses", headers, True


def rewrite_codex_message_span_types(payload: dict[str, Any]) -> None:
    input_items = payload.get("input")
    if not isinstance(input_items, list):
        return

    for item in input_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        if item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for span in content:
            if not isinstance(span, dict):
                continue
            if span.get("type") == "input_text":
                span["type"] = "output_text"


def is_invalid_input_union(error_payload: Any) -> bool:
    if not isinstance(error_payload, dict):
        return False
    error = error_payload.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("param") != "input":
        return False
    if error.get("code") != "invalid_union":
        return False
    return True
