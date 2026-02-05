"""Codex (ChatGPT OAuth) credential loading + refresh.

This mirrors the OpenAI Codex CLI behavior enough to support using
~/.codex/auth.json as a credential source for calling the ChatGPT Codex backend.

Key points (matching Codex CLI):
- Access token and optional ChatGPT account id are read from auth.json.
- Tokens are refreshed periodically (8 days) and also on 401 responses.
- Refresh is performed via https://auth.openai.com/oauth/token using the stored refresh_token.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx


TOKEN_REFRESH_INTERVAL_DAYS = 8
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_REFRESH_TOKEN_URL = "https://auth.openai.com/oauth/token"
REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR = "CODEX_REFRESH_TOKEN_URL_OVERRIDE"


class MissingCodexCredentialsError(ValueError):
    """Raised when Codex credentials are missing or incomplete."""


class CodexTokenRefreshError(RuntimeError):
    """Raised when a refresh attempt fails."""


@dataclass(frozen=True)
class CodexTokens:
    access_token: str
    refresh_token: str
    account_id: Optional[str] = None
    id_token: Optional[str] = None


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Assume unix seconds.
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        # Codex CLI uses chrono DateTime serialization (RFC3339).
        # Python's fromisoformat doesn't accept trailing Z.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    return None


def _format_dt(dt: datetime) -> str:
    # Keep RFC3339-ish format with Z.
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _refresh_token_endpoint() -> str:
    return os.getenv(REFRESH_TOKEN_URL_OVERRIDE_ENV_VAR, DEFAULT_REFRESH_TOKEN_URL).strip()


class CodexAuthStore:
    def __init__(self, path: Path):
        self.path = path

    def load_raw(self) -> Dict[str, Any]:
        if not self.path.exists():
            raise MissingCodexCredentialsError(
                f"Codex auth file not found at {self.path}. Run `codex login`."
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MissingCodexCredentialsError(
                f"Codex auth file at {self.path} is unreadable ({exc})."
            ) from exc
        if not isinstance(data, dict):
            raise MissingCodexCredentialsError(
                f"Codex auth file at {self.path} must contain a JSON object."
            )
        return data

    def save_raw(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write to avoid partial files.
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.write("\n")
            tmp_path.replace(self.path)
        finally:
            try:
                if tmp_path.exists() and tmp_path != self.path:
                    tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_tokens_and_last_refresh(self) -> Tuple[CodexTokens, Optional[datetime], Dict[str, Any]]:
        raw = self.load_raw()
        tokens_obj = raw.get("tokens")
        if not isinstance(tokens_obj, dict):
            raise MissingCodexCredentialsError(
                f"Codex auth file at {self.path} is missing 'tokens'. Run `codex login`."
            )

        access_token = tokens_obj.get("access_token")
        refresh_token = tokens_obj.get("refresh_token")
        account_id = tokens_obj.get("account_id")
        id_token = tokens_obj.get("id_token")

        if not isinstance(access_token, str) or not access_token.strip():
            raise MissingCodexCredentialsError(
                f"Codex auth file at {self.path} is missing tokens.access_token. Run `codex login`."
            )
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise MissingCodexCredentialsError(
                f"Codex auth file at {self.path} is missing tokens.refresh_token. Run `codex login`."
            )

        if account_id is not None and not isinstance(account_id, str):
            account_id = None
        if id_token is not None and not isinstance(id_token, str):
            id_token = None

        last_refresh = _parse_dt(raw.get("last_refresh"))

        return (
            CodexTokens(
                access_token=access_token.strip(),
                refresh_token=refresh_token.strip(),
                account_id=(account_id.strip() if isinstance(account_id, str) and account_id.strip() else None),
                id_token=(id_token.strip() if isinstance(id_token, str) and id_token.strip() else None),
            ),
            last_refresh,
            raw,
        )


class CodexAuthManager:
    def __init__(self, store: CodexAuthStore):
        self.store = store

    def _needs_periodic_refresh(self, last_refresh: Optional[datetime]) -> bool:
        if last_refresh is None:
            return True
        return datetime.now(tz=UTC) - last_refresh >= timedelta(days=TOKEN_REFRESH_INTERVAL_DAYS)

    async def ensure_fresh(self, client: httpx.AsyncClient) -> CodexTokens:
        tokens, last_refresh, raw = self.store.get_tokens_and_last_refresh()
        if not self._needs_periodic_refresh(last_refresh):
            return tokens
        return await self._refresh_and_persist(client, tokens, raw)

    async def refresh_on_unauthorized(self, client: httpx.AsyncClient) -> CodexTokens:
        tokens, _last_refresh, raw = self.store.get_tokens_and_last_refresh()
        return await self._refresh_and_persist(client, tokens, raw)

    async def _refresh_and_persist(
        self, client: httpx.AsyncClient, tokens: CodexTokens, raw: Dict[str, Any]
    ) -> CodexTokens:
        endpoint = _refresh_token_endpoint()
        payload = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "scope": "openid profile email",
        }

        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise CodexTokenRefreshError(f"Failed to refresh token ({exc}).") from exc

        if response.status_code >= 400:
            # Codex CLI classifies 401s into permanent failure reasons; we keep it simple but informative.
            text = response.text
            raise CodexTokenRefreshError(
                f"Failed to refresh token (HTTP {response.status_code}). {text}"
            )

        data: Any
        try:
            data = response.json()
        except ValueError as exc:
            raise CodexTokenRefreshError(
                f"Refresh response was not valid JSON (HTTP {response.status_code})."
            ) from exc

        if not isinstance(data, dict):
            raise CodexTokenRefreshError("Refresh response JSON was not an object.")

        new_access = data.get("access_token")
        new_refresh = data.get("refresh_token")
        new_id = data.get("id_token")

        if isinstance(new_access, str) and new_access.strip():
            tokens_obj = raw.setdefault("tokens", {})
            if isinstance(tokens_obj, dict):
                tokens_obj["access_token"] = new_access.strip()
        if isinstance(new_refresh, str) and new_refresh.strip():
            tokens_obj = raw.setdefault("tokens", {})
            if isinstance(tokens_obj, dict):
                tokens_obj["refresh_token"] = new_refresh.strip()
        if isinstance(new_id, str) and new_id.strip():
            tokens_obj = raw.setdefault("tokens", {})
            if isinstance(tokens_obj, dict):
                tokens_obj["id_token"] = new_id.strip()

        raw["last_refresh"] = _format_dt(datetime.now(tz=UTC))
        self.store.save_raw(raw)

        # Reload to pick up any other changes and normalize.
        refreshed, _last_refresh, _ = self.store.get_tokens_and_last_refresh()
        return refreshed
