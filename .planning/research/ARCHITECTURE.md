# Architecture Research

**Domain:** API compatibility proxy (Claude Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Ingress / API Layer                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌──────────────┐  ┌───────────────┐             │
│  │ HTTP Router   │→ │ Auth & Keys  │→ │ Schema/Size   │             │
│  │ (/v1/*)       │  │ Validation   │  │ Validation    │             │
│  └───────────────┘  └──────────────┘  └───────────────┘             │
│             │                         │                              │
├─────────────┴─────────────────────────┴──────────────────────────────┤
│                  Compatibility / Translation Core                    │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────┐ │
│  │ Canonical Model  │→ │ Request Mapper     │→ │ Tool Mapper      │ │
│  │ (neutral schema) │  │ (Claude→Responses) │  │ (tool use parity)│ │
│  └──────────────────┘  └────────────────────┘  └──────────────────┘ │
│               │                          │                           │
│               ↓                          ↓                           │
│  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────┐ │
│  │ Stream Adapter   │← │ Response Mapper    │← │ Error Mapper     │ │
│  │ (SSE transform)  │  │ (Responses→Claude) │  │ (status+shape)   │ │
│  └──────────────────┘  └────────────────────┘  └──────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│                         Upstream Connector                           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌────────────────────┐                        │
│  │ OpenAI Client    │  │ Token Count Client │                        │
│  │ (/v1/responses)  │  │ (/responses/input) │                        │
│  └──────────────────┘  └────────────────────┘                        │
├─────────────────────────────────────────────────────────────────────┤
│                       Observability & Logging                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌────────────────────┐                        │
│  │ PII Redaction    │→ │ Structured Logger  │                        │
│  │ (default on)     │  │ + Metrics/Tracing  │                        │
│  └──────────────────┘  └────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| HTTP Router | Route `/v1/messages`, `/stream`, `/count_tokens` | ASGI/HTTP router + handler functions |
| Auth & Key Validation | Enforce API key headers, map to upstream keys | Middleware + config-driven key store |
| Schema/Size Validation | Validate request JSON shape and size | Typed models + request guards |
| Canonical Model | Internal neutral request/response representation | Dataclasses/Pydantic models |
| Request Mapper | Convert Claude Messages request → OpenAI Responses | Pure mapping functions + tests |
| Tool Mapper | Ensure tool schema parity, map tool uses/results | Adapter functions + JSON schema checks |
| Stream Adapter | Transform streaming events (incl. input_json_delta) | Event transducer + incremental parser |
| Response Mapper | Convert OpenAI Responses → Claude Messages response | Pure mapping + output validation |
| Error Mapper | Normalize upstream errors into Claude-compatible errors | Error taxonomy + response factory |
| OpenAI Client | Calls `/v1/responses` (stream + non-stream) | HTTP client w/ timeouts |
| Token Count Client | Calls `/v1/responses/input_tokens` for `/count_tokens` | Separate HTTP call, same auth |
| PII Redaction | Scrub logs by default | Redaction pipeline w/ allowlist |
| Structured Logger | Emit structured logs + metrics/traces | JSON logger + OTLP exporter |

## Recommended Project Structure

```
src/
├── api/                       # HTTP handlers
│   ├── messages.py            # /v1/messages
│   ├── messages_stream.py     # /v1/messages/stream
│   └── count_tokens.py        # /v1/messages/count_tokens
├── middleware/                # cross-cutting concerns
│   ├── auth.py
│   ├── validation.py
│   ├── request_id.py
│   └── redaction.py
├── adapters/                  # compatibility layer
│   ├── canonical.py           # internal neutral schema
│   ├── claude.py              # Claude Messages helpers
│   ├── responses.py           # OpenAI Responses helpers
│   ├── mapping.py             # request/response mapping
│   └── tool_mapping.py        # tool use parity
├── streaming/                 # SSE/event translation
│   ├── parser.py              # upstream SSE parser
│   ├── transducer.py          # event mapping (incl input_json_delta)
│   └── accumulators.py        # partial JSON accumulation
├── upstream/                  # OpenAI HTTP clients
│   ├── responses_client.py
│   ├── input_tokens_client.py
│   └── errors.py
├── observability/             # logging/metrics/tracing
│   ├── logging.py
│   ├── redaction.py
│   └── metrics.py
├── config/                    # env and settings
│   └── settings.py
└── main.py                    # app assembly
```

### Structure Rationale

- **adapters/** isolates compatibility logic, enabling high-test coverage without HTTP concerns.
- **streaming/** isolates SSE/event handling and partial JSON accumulation for input_json_delta.
- **observability/** keeps logging consistent and ensures redaction is always enforced.
- **upstream/** keeps OpenAI-specific HTTP details contained (timeouts, headers, retry rules).

## Architectural Patterns

### Pattern 1: Canonical Model + Adapter

**What:** Normalize inbound Claude requests into a neutral internal model, then map to OpenAI Responses.
**When to use:** Any compatibility proxy where both sides evolve independently.
**Trade-offs:** More mapping code, but keeps API handlers stable and reduces churn.

**Example:**
```python
canonical = ClaudeToCanonical.from_messages(request)
upstream_payload = CanonicalToResponses.to_request(canonical)
```

### Pattern 2: Streaming Event Transducer

**What:** Consume upstream SSE events, translate them into Claude stream events incrementally.
**When to use:** `/v1/messages/stream` and tool-use streaming (input_json_delta).
**Trade-offs:** Requires careful incremental parsing; cannot buffer entire stream.

**Example:**
```python
async for event in openai_stream:
    for downstream_event in transduce_event(event):
        yield downstream_event
```

### Pattern 3: Redaction-as-Sink

**What:** Apply PII redaction at the last possible step before emission to logs/metrics.
**When to use:** Any request/response logging with privacy defaults.
**Trade-offs:** Redaction adds cost; must avoid double-redaction and preserve debug IDs.

## Data Flow

### Request Flow (non-stream)

```
Client
  ↓
HTTP Router → Auth → Schema/Size Validation
  ↓
Canonicalize → Map to OpenAI Responses → OpenAI Client
  ↓
OpenAI Response → Map to Claude Response → Error Mapper
  ↓
Client Response
```

### Request Flow (stream)

```
Client
  ↓
HTTP Router → Auth → Schema/Size Validation
  ↓
Canonicalize → Map to OpenAI Responses → OpenAI Client (stream)
  ↓
SSE Event Stream → Transducer (incl input_json_delta handling)
  ↓
Claude SSE Stream → Client
```

### Key Data Flows

1. **Tool use streaming:** input_json_delta events are accumulated per tool block index, parsed on block stop, and emitted as Claude-compatible tool_use deltas.
2. **Token counting:** `/v1/messages/count_tokens` maps request into OpenAI `/responses/input_tokens` call; returns only count to client.
3. **Logging:** request/response summaries pass through redaction pipeline before logging and metrics emission.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-1k req/day | Single service, in-memory rate limits, basic logs |
| 1k-100k req/day | External rate limiter, streaming concurrency tuning |
| 100k+ req/day | Dedicated streaming workers, shared config store |

### Scaling Priorities

1. **First bottleneck:** streaming concurrency and SSE backpressure → tune worker concurrency and upstream timeouts.
2. **Second bottleneck:** log volume and PII redaction cost → sampling + redaction cache/allowlist.

## Anti-Patterns

### Anti-Pattern 1: Buffering Streams for Translation

**What people do:** Read the full upstream stream, then emit once complete.
**Why it's wrong:** Breaks latency expectations and can exceed memory limits.
**Do this instead:** Translate and emit events incrementally.

### Anti-Pattern 2: Logging Raw Requests/Responses

**What people do:** Dump raw payloads to logs for debugging.
**Why it's wrong:** Violates privacy defaults and increases breach risk.
**Do this instead:** Redact at log sink, store only structured metadata.

### Anti-Pattern 3: Mixing Mapping Logic with HTTP Handlers

**What people do:** Perform mapping inline inside route handlers.
**Why it's wrong:** Hard to test and easy to regress across endpoints.
**Do this instead:** Keep mapping in adapters and unit-test thoroughly.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI Responses API | HTTP client (stream + non-stream) | Use SSE streaming for `/v1/messages/stream` parity. |
| OpenAI Input Tokens API | HTTP client | Drives `/v1/messages/count_tokens`. |
| Observability backend | OTLP/HTTP exporter | Redact before export. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API ↔ Adapters | Direct function calls | Keeps handlers thin and testable. |
| Adapters ↔ Streaming | Event DTOs | Avoid leaking SSE specifics into mapping. |
| API ↔ Observability | Logger interface | Centralized redaction. |

## MVP Build Order (Dependency-Driven)

1. **Canonical models + request/response mappers** → required before any endpoint can respond.
2. **OpenAI client (non-stream) + error mapping** → enables `/v1/messages` baseline.
3. **Token count client + mapper** → enables `/v1/messages/count_tokens`.
4. **Streaming parser/transducer (text deltas)** → enables `/v1/messages/stream` basic.
5. **Tool-use mapping + input_json_delta handling** → tool parity for streaming and non-stream.
6. **PII redaction + structured logging** → default-safe observability.
7. **Rate/size limits + request IDs** → production hardening.

## Sources

- OpenAI Responses API reference (streaming + input tokens): https://platform.openai.com/docs/api-reference/responses
- OpenAI Responses streaming events: https://platform.openai.com/docs/api-reference/responses-streaming
- Anthropic Messages streaming (content_block_delta + input_json_delta): https://docs.anthropic.com/en/api/messages-streaming
- Anthropic Messages API reference: https://docs.anthropic.com/en/api/messages

---
*Architecture research for: API compatibility proxy (Claude → OpenAI Responses)*
*Researched: 2026-01-25*
