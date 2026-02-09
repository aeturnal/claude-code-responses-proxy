from __future__ import annotations

import pytest

from src import codex_auth


def test_refresh_token_endpoint_defaults_when_override_missing(monkeypatch) -> None:
    monkeypatch.delenv(codex_auth.REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR, raising=False)
    assert codex_auth._refresh_token_endpoint() == codex_auth.DEFAULT_REFRESH_TOKEN_URL


def test_refresh_token_endpoint_rejects_unknown_host(monkeypatch) -> None:
    monkeypatch.setenv(
        codex_auth.REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
        "https://evil.example.com/oauth/token",
    )
    with pytest.raises(ValueError, match="host is not allowed"):
        codex_auth._refresh_token_endpoint()


def test_refresh_token_endpoint_requires_https_for_openai_host(monkeypatch) -> None:
    monkeypatch.setenv(
        codex_auth.REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
        "http://auth.openai.com/oauth/token",
    )
    with pytest.raises(ValueError, match="must use https"):
        codex_auth._refresh_token_endpoint()


def test_refresh_token_endpoint_allows_localhost_http(monkeypatch) -> None:
    monkeypatch.setenv(
        codex_auth.REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR,
        "http://localhost:9000/oauth/token",
    )
    assert codex_auth._refresh_token_endpoint() == "http://localhost:9000/oauth/token"
