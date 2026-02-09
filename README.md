# Claude Code -> OpenAI Responses Proxy

FastAPI service that accepts Anthropic-style `/v1/messages` requests and translates them into OpenAI Responses API calls, returning an Anthropic-compatible envelope.

This is useful when you have a client or SDK that speaks the Anthropic Messages API shape (for example, Claude Code), but you want to run it against OpenAI models.

## What it does

- Messages proxy: `POST /v1/messages` maps Anthropic Messages requests to OpenAI `POST /responses` and maps the response back.
- Streaming (SSE, Server-Sent Events): `POST /v1/messages/stream` streams Anthropic-style SSE events translated from upstream OpenAI-style streaming.
- Token counting: `POST /v1/messages/count_tokens` (and alias `POST /v1/messages/token_count`) returns OpenAI-aligned `input_tokens` for an Anthropic request without calling the upstream.
- Model mapping: map Anthropic model names to OpenAI model names via `MODEL_MAP_JSON` (with a default model fallback).
- Observability: optional JSON logs with redaction.

## Quickstart

Install dependencies using [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Optional extras:

- `uv sync --extra dev` installs test dependencies.
- `uv sync --extra pii` installs Presidio/spaCy dependencies for partial PII redaction mode.

### Install Modes

- Base runtime: `uv sync`
- Runtime + tests: `uv sync --extra dev`
- Runtime + partial-PII redaction support: `uv sync --extra pii`
- Runtime + tests + partial-PII redaction support: `uv sync --extra dev --extra pii`

Run the API (OpenAI Platform API key mode):

```bash
export OPENAI_UPSTREAM_MODE=openai
export OPENAI_API_KEY=sk-...
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

The server will be available at `http://localhost:8000`.

### Point Claude Code at the proxy

Claude Code is an Anthropic client. To route its `/v1/messages` calls to this service:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8000
```

## Upstream modes

This proxy supports two upstream authentication modes:

### 1) OpenAI Platform API key mode (default)

- Upstream URL: `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- Endpoint: `POST {OPENAI_BASE_URL}/responses`
- Auth header: `Authorization: Bearer ${OPENAI_API_KEY}`

Env vars:

- `OPENAI_UPSTREAM_MODE=openai`
- `OPENAI_API_KEY` (required)

### 2) Codex (ChatGPT account) mode

This mode lets you use your ChatGPT Codex login credentials instead of an OpenAI Platform API key.

Important notes:

- This does not call `api.openai.com`. It calls the ChatGPT Codex backend.
- You must have Codex CLI installed and logged in at least once.

Setup steps:

1) Log in with Codex CLI:

```bash
codex login
```

2) Start the proxy in codex mode:

```bash
export OPENAI_UPSTREAM_MODE=codex
# Optional: override where the proxy reads Codex credentials
export CODEX_AUTH_PATH="$HOME/.codex/auth.json"

uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

What codex mode does under the hood:

- Reads `~/.codex/auth.json` (or `CODEX_AUTH_PATH`) and uses `tokens.access_token`.
- Sends requests to `https://chatgpt.com/backend-api/codex/responses`.
- Adds `ChatGPT-Account-ID` header if `tokens.account_id` exists.
- Refreshes tokens using the stored `tokens.refresh_token` via `https://auth.openai.com/oauth/token`.
- Retries once on 401 after forcing a refresh.

Codex backend compatibility shim (implemented by this repo):

The ChatGPT Codex backend is stricter than the OpenAI Platform API and differs in a few request fields. In codex mode, the proxy applies best-effort rewrites to stay compatible, including:

- Forces `store=false`.
- Forces `stream=true` and parses `response.completed` out of SSE when using the non-streaming `/v1/messages` endpoint.
- Injects default `instructions` when missing (Claude Code sends a minimal startup probe that otherwise fails).
- Strips known unsupported parameters (`max_output_tokens`, `max_tokens`, `max_tool_calls`).
- Rewrites assistant history message spans from `input_text` to `output_text`.

You can set the injected default instructions with:

- `CODEX_DEFAULT_INSTRUCTIONS` (default: `You are a helpful assistant.`)

## Endpoints

### POST /v1/messages

Non-streaming by default. Returns an Anthropic-style response envelope:

- `type: "message"`
- `role: "assistant"`
- `content: [...]` (text and tool blocks)
- `stop_reason` derived from upstream status
- `usage` normalized from upstream usage

Minimal request example:

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

### POST /v1/messages/stream

Streams Anthropic-compatible SSE events (`text/event-stream`).

Notes:

- `message_start` includes the Anthropic model name (not the OpenAI model), so clients can map context windows correctly.
- `message_start` includes a locally computed `usage.input_tokens` value to support prompt progress indicators before the upstream stream emits final usage totals.

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

On streaming failures, the server emits `event: error` with an Anthropic error envelope as the `data:` payload.

### POST /v1/messages/count_tokens

Returns OpenAI-aligned input token counts for the mapped OpenAI payload.

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

## Configuration

### Model selection

- `OPENAI_DEFAULT_MODEL` (default `gpt-5.2`)

In codex mode, some models may not be available for your ChatGPT account. If you see an upstream error like "model is not supported when using Codex with a ChatGPT account", change `OPENAI_DEFAULT_MODEL` and or your mapping.

### Model mapping (MODEL_MAP_JSON)

`MODEL_MAP_JSON` can be either:

1) A flat mapping:

```json
{
  "claude-3-sonnet-20240229": "gpt-4o-mini",
  "claude-3-haiku": "gpt-4o-mini"
}
```

2) Or a nested mapping under `models`:

```json
{
  "models": {
    "claude-3": "gpt-4o",
    "claude-3-sonnet": "gpt-4o-mini"
  }
}
```

Keys are normalized (trimmed plus casefolded). If there is no exact match, the resolver can use an unambiguous prefix match; otherwise it falls back to `OPENAI_DEFAULT_MODEL`.

### Observability logs

Logging is off by default. Enable it with:

- `OBS_LOG_ENABLED=true`
- `OBS_LOG_ALL=true` (enables request plus stream logging)
- `OBS_LOG_FILE=./logs/requests.log`
- `OBS_REDACTION_MODE=full|partial|none` (default: `full`)
- `OBS_LOG_PRETTY=true|false`

Streaming-only logs can be controlled separately:

- `OBS_STREAM_LOG_ENABLED=true`
- `OBS_STREAM_LOG_FILE=./logs/streaming.log`

Caution: `OBS_REDACTION_MODE=none` will log prompts and outputs in plaintext.

### Installing spaCy models (optional)

If you enabled the `pii` extra:

```bash
uv sync --extra pii
```

For partial PII (Personally Identifiable Information) redaction (`OBS_REDACTION_MODE=partial`), you need a spaCy language model:

```bash
uv run python -m spacy download en_core_web_sm
```

The proxy works without a model installed; it falls back to full redaction if Presidio cannot initialize.

## Development

Install dev dependencies:

```bash
uv sync --extra dev
```

Run tests:

```bash
uv run pytest -q
```

Run a single test:

```bash
uv run pytest -q tests/test_token_counting.py::test_counts_basic_message
```

Quick syntax sanity check:

```bash
uv run python -m compileall src tests
```

## Troubleshooting

### Claude Code shows a 400 immediately on launch (codex mode)

Claude Code sends an initial probe request at startup. In codex mode, the upstream backend is strict. This repo injects default `instructions` in codex mode to satisfy that requirement.

If you still see a 400, enable logs and check the upstream `detail`:

```bash
OBS_LOG_ALL=1 OBS_REDACTION_MODE=full OPENAI_UPSTREAM_MODE=codex \
  uv run uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### Non-streaming requests fail with SSE or JSON parsing

In codex mode, the proxy forces `stream=true` upstream and then extracts the `response.completed` event to return a non-streaming response. If you see parsing errors, file an issue with the upstream response headers and a redacted snippet of the response body.

## Architecture

At a high level, the service is an adapter layer:

1) FastAPI app wiring: `src/app.py` configures logging and middleware and registers the routers.
2) HTTP handlers: `src/handlers/messages.py` implements `/v1/messages` and `/v1/messages/stream`; `src/handlers/count_tokens.py` implements token count endpoints.
3) Mapping (Anthropic to OpenAI): `src/mapping/anthropic_to_openai.py` builds an OpenAI Responses request from an Anthropic Messages payload.
4) Transport: `src/transport/openai_client.py` posts to the configured upstream.
5) Mapping (OpenAI to Anthropic): `src/mapping/openai_to_anthropic.py` converts upstream `output` items into an Anthropic-compatible envelope.

### Streaming (SSE)

Streaming is implemented as translated server-sent events:

- Upstream stream reader: `src/transport/openai_stream.py` reads upstream SSE frames.
- Translator: `src/mapping/openai_stream_to_anthropic.py` converts upstream stream events into Anthropic-style SSE events (`message_start`, `message_delta`, `message_end`, etc.).
- On streaming failures, the server emits `event: error` containing an Anthropic error envelope as the `data:` payload.
