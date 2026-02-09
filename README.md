# Claude Code -> OpenAI Responses Proxy

## Description

FastAPI service that accepts Anthropic-style `POST /v1/messages` requests (as sent by tools like Claude Code) and translates them into OpenAI Responses API calls, returning an Anthropic-compatible envelope.

Core features:

- Messages proxy: `POST /v1/messages` maps Anthropic Messages requests to OpenAI `POST /v1/responses` and maps the result back.
- Streaming (SSE): `POST /v1/messages/stream` streams Anthropic-style SSE translated from upstream OpenAI streaming.
- Token counting: `POST /v1/messages/count_tokens` (and alias `POST /v1/messages/token_count`) returns OpenAI-aligned `input_tokens` without calling the upstream.
- Model mapping: map Anthropic model names to OpenAI models via `MODEL_MAP_JSON`, with a default model fallback.
- Observability: optional structured JSON logs with prompt/output redaction.

High-level flow:

1. Handler receives an Anthropic Messages payload.
2. Anthropic payload is mapped to an OpenAI Responses request.
3. Request is sent upstream (OpenAI API key mode or Codex mode).
4. OpenAI response or events are mapped back to Anthropic-compatible envelopes.

## Installation

This repo uses [uv](https://docs.astral.sh/uv/).

Base runtime install:

```bash
uv sync
```

Optional extras:

- Tests/dev tools: `uv sync --extra dev`
- Partial PII redaction support (Presidio + spaCy): `uv sync --extra pii`
- Both: `uv sync --extra dev --extra pii`

## Configuration

### Upstream modes

This proxy supports two upstream authentication modes via `OPENAI_UPSTREAM_MODE`:

1. OpenAI Platform API key mode (`openai`, default)
2. Codex (ChatGPT account) mode (`codex`)

#### 1) OpenAI Platform API key mode (default)

Env vars:

- `OPENAI_UPSTREAM_MODE=openai`
- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional, default `https://api.openai.com/v1`)

Upstream request:

- Endpoint: `POST {OPENAI_BASE_URL}/responses`
- Header: `Authorization: Bearer ${OPENAI_API_KEY}`

#### 2) Codex (ChatGPT account) mode

This mode uses Codex CLI credentials from `~/.codex/auth.json` (or `CODEX_AUTH_PATH`) to call the ChatGPT Codex backend.

Env vars:

- `OPENAI_UPSTREAM_MODE=codex`
- `CODEX_AUTH_PATH` (optional, default `~/.codex/auth.json`)
- `CODEX_BASE_URL` (optional, default `https://chatgpt.com/backend-api/codex`)
- `CODEX_DEFAULT_INSTRUCTIONS` (optional, injected when `instructions` are missing)

Notes:

- This does not call `api.openai.com`. It calls the ChatGPT Codex backend.
- Tokens are refreshed using the stored refresh token.
- `CODEX_REFRESH_TOKEN_URL_OVERRIDE` exists for development, but the host is allowlisted for safety.

Codex compatibility shim:

The ChatGPT Codex backend is stricter than the OpenAI Platform API and differs in a few request fields. In codex mode, the proxy applies best-effort rewrites, including:

- Forces `store=false`.
- Forces `stream=true` upstream and extracts `response.completed` out of SSE for non-streaming `/v1/messages`.
- Injects default `instructions` when missing.
- Strips known unsupported parameters (`max_output_tokens`, `max_tokens`, `max_tool_calls`).
- Rewrites assistant history spans from `input_text` to `output_text`.

### Model selection

Env vars:

- `OPENAI_DEFAULT_MODEL` (default is `gpt-5.2` in code; recommended value is `gpt-5.1`)
- `MODEL_MAP_JSON` (optional)

Recommended up-to-date models (for examples):

- `gpt-5.1` (flagship)
- `gpt-5-mini` (faster/cost-optimized)
- `gpt-5-nano` (high-throughput)
- `gpt-5.1-codex` / `gpt-5.1-codex-mini` (coding-optimized variants)

### Model mapping (MODEL_MAP_JSON)

`MODEL_MAP_JSON` may be either:

1) Flat mapping:

```json
{
  "claude-3-sonnet-20240229": "gpt-5.1",
  "claude-3-haiku": "gpt-5-mini"
}
```

2) Nested mapping under `models`:

```json
{
  "models": {
    "claude-3": "gpt-5.1",
    "claude-3-sonnet": "gpt-5-mini"
  }
}
```

Keys are normalized (trimmed + casefolded). If there is no exact match, the resolver can use an unambiguous prefix match; otherwise it falls back to `OPENAI_DEFAULT_MODEL`.

### Observability logs

Logging is off by default. Useful env vars:

- `OBS_LOG_ENABLED=true`
- `OBS_LOG_ALL=true` (enables request + stream logging)
- `OBS_LOG_FILE=./logs/requests.log`
- `OBS_STREAM_LOG_ENABLED=true`
- `OBS_STREAM_LOG_FILE=./logs/streaming.log`
- `OBS_REDACTION_MODE=full|partial|none` (default `full`)
- `OBS_LOG_PRETTY=true|false`

Caution: `OBS_REDACTION_MODE=none` will log prompts and outputs in plaintext.

### Partial redaction (spaCy model)

If you enable `OBS_REDACTION_MODE=partial`, install the extra and a spaCy language model:

```bash
uv sync --extra pii
uv run python -m spacy download en_core_web_sm
```

If Presidio/spaCy cannot initialize, the proxy falls back to full redaction.

## Usage

### Run the API

OpenAI API key mode:

```bash
export OPENAI_UPSTREAM_MODE=openai
export OPENAI_API_KEY=sk-...
export OPENAI_DEFAULT_MODEL=gpt-5.1
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

Codex mode:

```bash
export OPENAI_UPSTREAM_MODE=codex
export OPENAI_DEFAULT_MODEL=gpt-5.1-codex
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

Server default is `http://localhost:8000`.

### Point Claude Code at the proxy

Claude Code is an Anthropic client. To route its `/v1/messages` calls to this service:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8000
```

### POST /v1/messages (non-streaming)

```bash
curl -s http://localhost:8000/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-3-sonnet-20240229",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

Streaming via `/v1/messages` is supported by setting `"stream": true`.

### POST /v1/messages/stream (SSE)

```bash
curl -N http://localhost:8000/v1/messages/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-3-sonnet-20240229",
    "messages": [
      {"role": "user", "content": "Write a haiku about proxies."}
    ]
  }'
```

Notes:

- `message_start` reports the Anthropic model name (not the resolved OpenAI model).
- `message_start` includes a locally computed `usage.input_tokens` value so clients can display prompt progress early.

On streaming failures, the server emits `event: error` with an Anthropic error envelope as the `data:` payload.

### POST /v1/messages/count_tokens

```bash
curl -s http://localhost:8000/v1/messages/count_tokens \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-3-sonnet-20240229",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

Response:

```json
{ "input_tokens": 7 }
```

`POST /v1/messages/token_count` is an alias.

### Telemetry endpoint

The proxy includes a telemetry sink compatible with Anthropic client telemetry:

- `POST /api/event_logging/batch` returns `204`.
- If telemetry logging is enabled, the request body is logged in a redacted form.

### Development

```bash
uv sync --extra dev
uv run pytest -q
uv run python -m compileall src tests
```

## Troubleshooting

### Claude Code shows a 400 immediately on launch (codex mode)

Claude Code sends an initial probe request at startup. In codex mode, the upstream backend is strict. This proxy injects default `instructions` in codex mode to satisfy that requirement.

Enable logs to see what the upstream rejected:

```bash
OBS_LOG_ALL=1 OBS_REDACTION_MODE=full OPENAI_UPSTREAM_MODE=codex \
  uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### Missing credentials errors

- OpenAI mode: set `OPENAI_API_KEY`.
- Codex mode: ensure `~/.codex/auth.json` exists (run `codex login`) or set `CODEX_AUTH_PATH`.

### Non-streaming requests fail with SSE parsing (codex mode)

In codex mode, the proxy forces `stream=true` upstream and extracts `response.completed` for the non-streaming `/v1/messages` endpoint. If you see parsing errors, capture:

- upstream response headers (especially `content-type`)
- a redacted snippet of the upstream body

### Partial redaction looks like full redaction

If `OBS_REDACTION_MODE=partial` but Presidio/spaCy cannot initialize (missing packages or missing spaCy model), the proxy will fall back to full redaction.
