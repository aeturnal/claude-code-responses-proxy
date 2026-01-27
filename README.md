# Claude Code -> OpenAI Responses Proxy

FastAPI service that accepts Anthropic-style `/v1/messages` requests and translates
them into OpenAI Responses API calls, returning an Anthropic-compatible envelope.

This is useful when you have a client or SDK that speaks the Anthropic Messages
API shape, but you want to run it against OpenAI models.

## What It Does

- **Messages proxy:** `POST /v1/messages` (non-streaming) maps Anthropic Messages
  requests to OpenAI `/responses` and maps the response back.
- **Streaming (SSE):** `POST /v1/messages/stream` streams Anthropic-style SSE
  events translated from OpenAI streaming.
- **Token counting:** `POST /v1/messages/count_tokens` (and alias
  `POST /v1/messages/token_count`) returns OpenAI-aligned `input_tokens` for an
  Anthropic request without calling OpenAI.
- **Model mapping:** map Anthropic model names to OpenAI model names via
  `MODEL_MAP_JSON` (with a default model fallback).
- **Observability:** optional JSON logs with PII-safe redaction.

## Quickstart

Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Run the API:

```bash
export OPENAI_API_KEY=sk-...
python -m uvicorn src.app:app --reload
```

The server will be available at `http://localhost:8000`.

## Endpoints

### POST /v1/messages

Non-streaming by default. Returns an Anthropic-style response envelope:

- `type: "message"`
- `role: "assistant"`
- `content: [...]` (text + tool blocks)
- `stop_reason` derived from OpenAI response status
- `usage` normalized from OpenAI usage

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

Streams Anthropic-compatible SSE events (text/event-stream).

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

On streaming failures, the server emits `event: error` with an Anthropic error
envelope as the `data:` payload.

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

### OpenAI upstream

- `OPENAI_API_KEY` (required for upstream calls)
- `OPENAI_BASE_URL` (default `https://api.openai.com/v1`)
- `OPENAI_DEFAULT_MODEL` (default `gpt-5.2`)

If `OPENAI_API_KEY` is missing, `/v1/messages` returns a 401 Anthropic error
envelope, and streaming emits `event: error`.

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

Keys are normalized (trimmed + casefolded). If there is no exact match, the
resolver can use an unambiguous prefix match; otherwise it falls back to
`OPENAI_DEFAULT_MODEL`.

### Observability logs

Logging is off by default. Enable it with:

- `OBS_LOG_ENABLED=true`
- `OBS_LOG_FILE=./logs/requests.log`
- `OBS_REDACTION_MODE=full|partial` (default: `full`)
- `OBS_LOG_PRETTY=true|false`

Streaming-only logs can be controlled separately via:

- `OBS_STREAM_LOG_ENABLED=true`
- `OBS_STREAM_LOG_FILE=./logs/streaming.log`

Redaction uses Presidio when `OBS_REDACTION_MODE=partial`; if Presidio is
unavailable or errors, the implementation falls back to full redaction.

## Development

Run tests:

```bash
pytest -q
```

Run a single test:

```bash
pytest -q tests/test_token_counting.py::test_counts_basic_message
```

Quick syntax sanity check:

```bash
python -m compileall src tests
```

## Verification Script

`scripts/verify_count_tokens.py` compares the proxy's `/v1/messages/count_tokens`
results against OpenAI `usage.input_tokens` for a set of fixture cases.

```bash
OPENAI_API_KEY=... python scripts/verify_count_tokens.py
```

By default it expects the proxy at `http://localhost:8000`. Override with:

```bash
PROXY_BASE=http://localhost:8000 OPENAI_API_KEY=... python scripts/verify_count_tokens.py
```

## How it works (architecture)

At a high level, the service is an adapter layer:

1. **FastAPI app wiring**: `src/app.py` configures logging and middleware and
   registers the API routers.
2. **HTTP handlers**: `src/handlers/messages.py` implements `/v1/messages` and
   `/v1/messages/stream`; `src/handlers/count_tokens.py` implements token count
   endpoints.
3. **Mapping (Anthropic → OpenAI)**: `src/mapping/anthropic_to_openai.py` builds
   an OpenAI Responses request from an Anthropic Messages payload (messages,
   tools/tool_choice, etc.).
4. **Transport**: `src/transport/openai_client.py` posts to OpenAI
   `{OPENAI_BASE_URL}/responses` using `OPENAI_API_KEY`.
5. **Mapping (OpenAI → Anthropic)**: `src/mapping/openai_to_anthropic.py`
   converts OpenAI `output` items into an Anthropic-compatible envelope
   (`content`, `stop_reason`, `usage`).

### Streaming (SSE)

Streaming is implemented as translated server-sent events:

- Upstream stream reader: `src/transport/openai_stream.py` reads OpenAI SSE
  frames.
- Translator: `src/mapping/openai_stream_to_anthropic.py` converts OpenAI stream
  events into Anthropic-style SSE events (`message_start`, `message_delta`,
  `message_end`, etc.).
- On streaming failures, the server emits `event: error` containing an Anthropic
  error envelope as the `data:` payload.

### Observability and redaction

- Logging is `structlog`-based (`src/observability/logging.py`) and is off by
  default.
- Redaction helpers live in `src/observability/redaction.py`. When
  `OBS_REDACTION_MODE=partial`, redaction uses Presidio; if Presidio is
  unavailable or errors, the implementation falls back to full redaction.
