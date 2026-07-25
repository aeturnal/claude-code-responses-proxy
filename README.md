# Claude Code → OpenAI Responses Proxy

This FastAPI proxy lets Claude Code use OpenAI Responses-compatible models. It
accepts Anthropic Messages API requests, translates them for either the
ChatGPT Codex backend or the OpenAI Platform API, and returns
Anthropic-compatible responses.

- Claude Code-compatible messages and tool calls
- Anthropic-style streaming and error envelopes
- Local input-token counting
- Configurable Claude-to-OpenAI model and reasoning routing
- Optional structured observability with redaction

> [!WARNING]
> Codex mode is a best-effort integration with the ChatGPT Codex backend.
> Model availability can vary by account and backend state. The proxy has no
> inbound authentication; keep it bound to localhost unless a separate
> access-control layer protects it.

## Quick start: Claude Code with Codex mode

Prerequisites: Python 3.13+, [uv](https://docs.astral.sh/uv/), and Codex CLI
credentials. If Codex CLI credentials are not already present, run `codex login`.

From the repository directory, install dependencies and start the proxy:

```bash
uv sync
codex login
OPENAI_UPSTREAM_MODE=codex \
  uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
```

In the shell where you run Claude Code, point it at the local proxy and launch
it separately:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
claude
```

Send a simple prompt in Claude Code to confirm the connection. If the proxy
returns an error, consult [Troubleshooting](#troubleshooting).

## OpenAI API mode

OpenAI API mode is the alternative upstream mode (and the application default).
Set an API key and start the proxy:

```bash
export OPENAI_UPSTREAM_MODE=openai
export OPENAI_API_KEY=sk-...
uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
```

Reuse the same `ANTHROPIC_BASE_URL` and Claude Code launch steps from the
[quick start](#quick-start-claude-code-with-codex-mode).

## Model and reasoning routing

The built-in routes target GPT-5.6 models:

| Anthropic model prefix | OpenAI model |
| --- | --- |
| `claude-fable-5` | `gpt-5.6-sol` |
| `claude-opus-5` | `gpt-5.6-sol` |
| `claude-sonnet-5` | `gpt-5.6-terra` |
| `claude-haiku-4-5` | `gpt-5.6-luna` |

`MODEL_MAP_JSON` is checked before built-in routes. Its keys are trimmed and
case-folded. Resolution uses exact matches first, then unambiguous prefixes,
then `OPENAI_DEFAULT_MODEL`.

Use either a flat map:

```bash
export MODEL_MAP_JSON='{
  "claude-opus-5": "gpt-5.6-sol",
  "claude-sonnet-5": "gpt-5.6-terra"
}'
```

or a nested map:

```bash
export MODEL_MAP_JSON='{
  "models": {
    "claude-opus-5": "gpt-5.6-sol",
    "claude-haiku-4-5": "gpt-5.6-luna"
  }
}'
```

For the exact supported GPT-5.6 routing targets (`gpt-5.6-sol`,
`gpt-5.6-terra`, and `gpt-5.6-luna`), `output_config.effort` maps directly to
`reasoning.effort`; `thinking.type=disabled` maps to
`reasoning.effort=none`. Haiku 4.5 with `thinking.type=enabled` and
`budget_tokens` maps to `reasoning.effort=max` when its resolved target is
exactly one of those three models. Other enabled manual-thinking requests
return an Anthropic compatibility error.

OpenAI reasoning content is not returned as Anthropic thinking blocks.
Non-GPT-5.6 operator overrides omit normal effort controls; unsupported Haiku
manual-thinking overrides return a compatibility error.

## Configuration reference

### Upstream

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_UPSTREAM_MODE` | `openai` | Optional. Selects `openai` (Platform API) or `codex` (ChatGPT Codex backend). |
| `OPENAI_API_KEY` | unset | Required in OpenAI API mode. Platform API credential. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Optional. OpenAI Platform API base URL. |
| `CODEX_AUTH_PATH` | unset | Optional. Overrides the Codex CLI credential path; the default credential location is `~/.codex/auth.json`. |
| `CODEX_BASE_URL` | `https://chatgpt.com/backend-api/codex` | Optional. ChatGPT Codex backend base URL. |
| `CODEX_DEFAULT_INSTRUCTIONS` | `You are a helpful assistant.` | Optional. Instructions injected for Codex requests that omit them. |
| `CODEX_REFRESH_TOKEN_URL_OVERRIDE` | unset | Optional, development-only refresh URL override; its host is allowlisted for safety. |

### Routing

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_DEFAULT_MODEL` | `gpt-5.6-terra` | Optional. Fallback OpenAI model after mapping misses. |
| `MODEL_MAP_JSON` | unset | Optional. Flat JSON map or a JSON object with a `models` map; takes precedence over built-in routes. |
| `OPENAI_DEFAULT_REASONING_EFFORT` | `medium` | Optional. Default effort for exact supported GPT-5.6 targets when no request effort is supplied. |

### Request and stream logging

| Variable | Default | Purpose |
| --- | --- | --- |
| `OBS_LOG_ENABLED` | `false` | Optional. Enables request/response structured logging. |
| `OBS_LOG_ALL` | `false` | Optional. Enables request logging and forces stream logging on. |
| `OBS_LOG_FILE` | `./logs/requests.log` | Optional. Request/response log file. |
| `OBS_STREAM_LOG_ENABLED` | value of `OBS_LOG_ENABLED` | Optional. Enables structured stream logging. |
| `OBS_STREAM_LOG_FILE` | `./logs/streaming.log` | Optional. Stream log file. |
| `OBS_REDACTION_MODE` | `full` | Optional. Redaction mode: `full`, `partial`, or `none`. |
| `OBS_LOG_PRETTY` | `true` | Optional. Pretty-prints structured logs. |

### Anthropic telemetry logging

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_TELEMETRY_LOG_ENABLED` | `false` | Optional. Logs redacted Anthropic telemetry batches. |
| `ANTHROPIC_TELEMETRY_LOG_FILE` | `./logs/anthropic_telemetry.log` | Optional. Telemetry log file. |

## Compatibility and endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/messages` | Non-streaming messages, or Anthropic-style SSE when `"stream": true` |
| `POST /v1/messages/stream` | Compatibility streaming endpoint |
| `POST /v1/messages/count_tokens` | Locally computed OpenAI-aligned input-token count |
| `POST /v1/messages/token_count` | Alias for token counting |
| `POST /api/event_logging/batch` | Anthropic client telemetry sink; returns `204` |

Send a non-streaming message request with a current built-in Claude identifier:

```bash
curl -s http://127.0.0.1:8000/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-sonnet-5",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

Normal streaming uses the same endpoint with `"stream": true`.

Count input tokens locally:

```bash
curl -s http://127.0.0.1:8000/v1/messages/count_tokens \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "claude-sonnet-5",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

```json
{ "input_tokens": 7 }
```

Streaming `message_start` reports the Anthropic model name and includes a
locally computed initial input usage value. Streaming failures emit an
Anthropic `event: error` envelope.

### Codex compatibility rewrites

In Codex mode, the proxy applies best-effort compatibility rewrites: it sets
`store=false`, forces upstream streaming and extracts `response.completed` for
non-streaming requests, injects default instructions when missing, strips
unsupported maximum fields (`max_output_tokens`, `max_tokens`, and
`max_tool_calls`), and rewrites assistant history from `input_text` to
`output_text`.

## Observability and privacy

Logging is disabled by default. `full` redaction removes logged content,
`partial` uses Presidio and spaCy to redact detected sensitive content, and
`none` performs no content redaction.

> [!WARNING]
> `OBS_REDACTION_MODE=none` stores prompts and outputs in plaintext.

For partial redaction, install the optional dependencies and spaCy model:

```bash
uv sync --extra pii
uv run python -m spacy download en_core_web_sm
```

If Presidio or spaCy initialization fails, the proxy falls back to full
redaction. See [Request and stream logging](#request-and-stream-logging) for
the logging controls.

## Verification and development

Run the deterministic test and syntax checks:

```bash
uv sync --extra dev
uv run pytest -q
uv run python -m compileall src tests
```

After starting the proxy in Codex mode, this opt-in smoke test checks live
account and backend availability rather than deterministic application behavior:

```bash
OPENAI_UPSTREAM_MODE=codex \
PROXY_BASE=http://127.0.0.1:8000 \
uv run python scripts/verify_codex_gpt56.py
```

For token-count alignment against the proxy and OpenAI:

```bash
OPENAI_API_KEY=... uv run python scripts/verify_count_tokens.py
```

## Troubleshooting

### Immediate startup 400 responses in Codex mode

Claude Code can send an initial probe request. Codex mode injects default
instructions for requests that omit them; review
[Upstream](#upstream) and enable redacted logs from
[Request and stream logging](#request-and-stream-logging) to inspect an
upstream rejection.

### Missing credentials

In OpenAI API mode, set `OPENAI_API_KEY`. In Codex mode, run `codex login` or
set `CODEX_AUTH_PATH`; see [Upstream](#upstream).

### SSE parsing failures for non-streaming Codex requests

Codex mode forces upstream streaming and extracts `response.completed` for a
non-streaming `/v1/messages` response. Capture redacted upstream response
headers (especially `content-type`) and a redacted body snippet when diagnosing
the failure.

### Partial redaction falls back to full redaction

Install the optional dependencies and spaCy model in
[Observability and privacy](#observability-and-privacy). The fallback is
expected when Presidio or spaCy cannot initialize.
