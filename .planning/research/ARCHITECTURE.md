# Architecture Research

**Domain:** API compatibility gateway / proxy (provider-to-provider semantic adapter)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Edge / Ingress Layer                        │
├─────────────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ HTTP/S     │  │ Auth & Keys  │  │ Rate/Size    │  │ Request    │ │
│  │ Listener   │→ │ (API key)    │→ │ Limits       │→ │ Validation │ │
│  └────────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
│                                (ASGI middleware chain)              │
├─────────────────────────────────────────────────────────────────────┤
│                     Compatibility / Translation Layer               │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │ Canonical    │→ │ Request Mapper   │→ │ Upstream Connector    │  │
│  │ Model        │  │ (Anthropic→OA)   │  │ (HTTP client)         │  │
│  └──────────────┘  └──────────────────┘  └───────────────────────┘  │
│                                  │                                  │
│                                  ↓                                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │ Error Mapper │← │ Response Mapper  │← │ Stream Adapter (SSE)  │  │
│  └──────────────┘  └──────────────────┘  └───────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│                          Support Services Layer                     │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────────────────┐  │
│  │ Observability│  │ File Storage  │  │ Background Jobs         │  │
│  │ (logs/metrics│  │ (local disk)  │  │ (batches, cleanup)       │  │
│  │ /tracing)    │  └───────────────┘  └─────────────────────────┘  │
│  └──────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| HTTP Listener | Accepts requests, handles routing for `/v1/*` endpoints | FastAPI/ASGI app + APIRouter |
| Auth & Key Validation | Verifies API key in headers/env, rejects unauthorized | ASGI middleware + dependency injection |
| Rate/Size Limits | Protects upstream and local resources | ASGI middleware + in-memory counters; optional gateway proxy | 
| Request Validation | Validates input schema, headers, and content type | Pydantic models + request validators |
| Canonical Model | Internal neutral representation of request/response | Pydantic models / dataclasses |
| Request Mapper | Translates Anthropic Messages → OpenAI Responses | Adapter layer; explicit field mapping |
| Upstream Connector | Handles HTTP client, retries, timeouts | httpx/async client with circuit-breaker policies |
| Stream Adapter | Bridges upstream streaming to SSE/streamed responses | Async generator + incremental transform |
| Response Mapper | Converts upstream response back to Anthropic shape | Adapter layer + output schema validation |
| Error Mapper | Normalizes error payloads and status codes | Error taxonomy + response factory |
| File Storage | Stores uploaded files locally; lifecycle mgmt | Local disk + metadata index |
| Observability | Logs, metrics, tracing, redaction | OpenTelemetry + structured logging |
| Background Jobs | Batches, retries, cleanup of temp files | Background tasks / worker process |

## Recommended Project Structure

```
src/
├── api/                     # FastAPI routers/endpoints
│   ├── messages.py          # /v1/messages, /stream
│   ├── batches.py           # /v1/messages/batches
│   ├── files.py             # /v1/files
│   └── tokens.py            # /v1/messages/count_tokens
├── middleware/              # auth, size limits, logging
│   ├── auth.py
│   ├── limits.py
│   ├── request_id.py
│   └── redaction.py
├── adapters/                # provider compatibility layer
│   ├── canonical.py         # internal neutral schema
│   ├── anthropic.py         # Anthropic schema helpers
│   ├── openai.py            # OpenAI Responses schema helpers
│   └── mapping.py           # mapping rules and transformers
├── upstream/                # HTTP client and retry policy
│   ├── client.py
│   ├── streaming.py
│   └── errors.py
├── storage/                 # file storage and metadata
│   ├── filesystem.py
│   └── metadata.py
├── observability/           # logging/metrics/tracing
│   ├── logging.py
│   ├── metrics.py
│   └── tracing.py
├── config/                  # settings and env parsing
│   └── settings.py
└── main.py                  # app assembly
```

### Structure Rationale

- **api/** keeps endpoint definitions thin and declarative.
- **adapters/** isolates compatibility logic so upstream changes don’t bleed into API handlers.
- **upstream/** centralizes HTTP client behavior (timeouts, retries, streaming).
- **middleware/** enforces cross-cutting concerns early (auth, limits, redaction).
- **observability/** keeps logging and metrics consistent across all paths.

## Architectural Patterns

### Pattern 1: Middleware Pipeline (API Gateway Pattern)

**What:** Sequential middleware steps for auth, limits, logging, and validation.
**When to use:** Any API gateway/proxy where cross-cutting controls must be applied consistently.
**Trade-offs:** Simple and testable, but order-sensitive and can hide control flow.

**Example:**
```python
# pseudo-code
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RedactionMiddleware)
```

### Pattern 2: Canonical Model + Adapter

**What:** Normalize inbound requests to a neutral internal model, then map to upstream schema.
**When to use:** When bridging incompatible APIs and needing stable internal semantics.
**Trade-offs:** Extra mapping code but reduces churn from upstream changes.

**Example:**
```python
canonical = AnthropicToCanonical.from_request(req)
upstream_payload = CanonicalToOpenAI.to_response(canonical)
```

### Pattern 3: Streaming Translation Adapter

**What:** Stream upstream events through a transformer that emits the downstream stream format.
**When to use:** Any SSE or chunked streaming compatibility endpoint.
**Trade-offs:** Harder to retry; must avoid buffering full streams.

## Data Flow

### Request Flow

```
Client
  ↓
HTTP Listener → Auth → Rate/Size Limits → Validation
  ↓
Canonicalize → Map to Upstream → HTTP Client
  ↓
Stream/Response → Map to Downstream → Error Mapper
  ↓
Client Response
```

### Key Data Flows

1. **Messages (non-stream):** request → canonical → map → upstream → response map → client.
2. **Messages (stream):** request → upstream stream → incremental transform → SSE to client.
3. **File upload:** request → local disk store → metadata index → response.
4. **Batch job:** request → enqueue background job → poll status → response mapping.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-1k users | Single FastAPI service, in-memory rate limits, local disk storage |
| 1k-100k users | External rate limit store, shared file storage, structured logs + metrics |
| 100k+ users | Separate streaming workers, distributed storage, multi-region upstream routing |

### Scaling Priorities

1. **First bottleneck:** streaming concurrency and upstream timeouts → tune HTTP client, increase worker count.
2. **Second bottleneck:** file storage and batch jobs → move to shared storage and background worker queue.

## Anti-Patterns

### Anti-Pattern 1: Pass-through Without Canonicalization

**What people do:** Directly proxy requests to upstream and patch responses ad-hoc.
**Why it's wrong:** Any upstream schema change causes widespread breakage and inconsistent semantics.
**Do this instead:** Normalize to a canonical model then map in/out.

### Anti-Pattern 2: Buffering Streams for Transformation

**What people do:** Collect full upstream stream, then emit response at end.
**Why it's wrong:** Breaks latency expectations and increases memory pressure.
**Do this instead:** Transform and emit incrementally.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI Responses API | HTTP client with retries/timeouts | Preserve streaming semantics; avoid buffering |
| Observability backend | OTLP exporter | Redact PII before export |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API layer ↔ Adapter layer | Direct function calls | Keep adapters pure and unit-testable |
| Adapter ↔ Upstream client | Typed request objects | Avoid leaking upstream SDK types |
| API layer ↔ Storage | Service interface | Enables local disk now, swap later |

## Sources

- Envoy architecture overview (listeners, filters, upstream clusters, observability): https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/arch_overview
- Kong Gateway overview (API gateway as reverse proxy; plugins for auth/limits/observability): https://docs.konghq.com/gateway/latest/
- NGINX proxy module (proxying and buffering behavior): https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- FastAPI middleware (ASGI middleware pipeline): https://fastapi.tiangolo.com/advanced/middleware/

---
*Architecture research for: API compatibility gateway / proxy*
*Researched: 2026-01-25*
