# Stack Research

**Domain:** API compatibility proxy (Claude Code → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | >=3.9 | Runtime | Matches minimum versions required by FastAPI and OpenAI SDK (both require Python ≥3.9). Keeps runtime compatible with current ecosystem. **Confidence: HIGH** (PyPI requirements). |
| FastAPI | 0.128.0 | ASGI API framework | Standard for high‑throughput JSON APIs; strong typing and OpenAPI generation align with proxy schema translation. **Confidence: HIGH** (PyPI). |
| Uvicorn | 0.40.0 | ASGI server | Production-grade ASGI server; required for async streaming endpoints. **Confidence: HIGH** (PyPI). |
| OpenAI Python SDK | 2.15.0 | Upstream Responses client | Official client supports Responses API + streaming SSE, reducing manual protocol handling. **Confidence: HIGH** (PyPI). |
| tiktoken | 0.12.0 | Token counting | Canonical tokenizer for OpenAI models; needed for `/v1/messages/count_tokens`. **Confidence: HIGH** (PyPI). |
| sse-starlette | 3.2.0 | SSE streaming | Production-ready SSE response helper for `/v1/messages/stream` with client disconnect handling. **Confidence: HIGH** (PyPI). |
| structlog | 25.5.0 | Structured logging | Enables JSON logs + custom processors for deterministic PII redaction. **Confidence: HIGH** (PyPI). |
| orjson | 3.11.5 | Fast JSON serialization | High-throughput JSON encoding for proxy responses. **Confidence: HIGH** (PyPI). |
| OpenTelemetry SDK | 1.39.1 | Tracing | Vendor‑neutral tracing for reliability-first observability. **Confidence: HIGH** (PyPI). |
| opentelemetry-exporter-otlp | 1.39.1 | Trace export | OTLP exporter bundle for shipping traces to collectors. **Confidence: HIGH** (PyPI). |
| opentelemetry-instrumentation-fastapi | 0.60b1 (pre-release) | Auto instrumentation | Auto-traces FastAPI request lifecycle; standard OTel Python stack. **Confidence: MEDIUM** (pre‑release). |
| opentelemetry-instrumentation-httpx | 0.60b1 (pre-release) | Upstream tracing | Captures outbound HTTP spans if you use HTTPX directly. **Confidence: MEDIUM** (pre‑release). |
| httpx | 0.28.1 | Direct HTTP client (optional) | Use only if bypassing OpenAI SDK or for custom upstream calls. **Confidence: HIGH** (PyPI). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Custom PII redaction processor | N/A (custom) | Redact PII from logs by default | Implement deterministic regex-based redaction in structlog processors for MVP; avoid heavy ML dependencies. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| (None required for MVP) | — | Keep MVP dependencies minimal; add test/lint tooling in a later milestone if needed. |

## Installation

```bash
# Core runtime
pip install fastapi==0.128.0 uvicorn==0.40.0 openai==2.15.0 \
  tiktoken==0.12.0 sse-starlette==3.2.0 structlog==25.5.0 \
  orjson==3.11.5 opentelemetry-sdk==1.39.1 \
  opentelemetry-exporter-otlp==1.39.1 \
  opentelemetry-instrumentation-fastapi==0.60b1 \
  opentelemetry-instrumentation-httpx==0.60b1

# Optional (only if using raw HTTPX directly)
pip install httpx==0.28.1
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| OpenAI Python SDK | Raw HTTPX + manual SSE parsing | If you need full control over protocol or are targeting a non‑OpenAI upstream. |
| sse-starlette | Starlette StreamingResponse | If you want zero extra dependency and can manage SSE framing + disconnects manually. |
| OTel auto-instrumentation | Manual spans only | If you want to avoid pre‑release instrumentation packages in MVP. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| WSGI stacks (Flask + gunicorn) | WSGI blocks async streaming; SSE/backpressure are unreliable. | FastAPI + Uvicorn (ASGI). |
| Heavy PII ML stacks (e.g., Presidio with NLP models) | Adds model downloads, latency, and operational complexity to MVP. | Deterministic regex redaction in structlog processors. |
| Rate limiting middleware (SlowAPI, Redis-based limiters) | Out of MVP scope and introduces ops dependencies. | Defer to post‑MVP. |

## Stack Patterns by Variant

**If you must avoid pre‑release OTel instrumentation:**
- Use opentelemetry-sdk + exporter only.
- Add manual spans around request handlers and upstream calls.

**If you need to proxy to non‑OpenAI upstreams:**
- Use HTTPX directly and implement your own SSE parsing/translation.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| opentelemetry-sdk@1.39.1 | opentelemetry-exporter-otlp@1.39.1 | Keep same OTel minor version to avoid API mismatch. |
| opentelemetry-instrumentation-fastapi@0.60b1 | opentelemetry-sdk@1.39.1 | Instrumentation follows the OTel release train (pre‑release). |
| opentelemetry-instrumentation-httpx@0.60b1 | opentelemetry-sdk@1.39.1 | Same release train as SDK (pre‑release). |

## Sources

- https://pypi.org/project/fastapi/ — version 0.128.0
- https://pypi.org/project/uvicorn/ — version 0.40.0
- https://pypi.org/project/openai/ — version 2.15.0
- https://pypi.org/project/tiktoken/ — version 0.12.0
- https://pypi.org/project/sse-starlette/ — version 3.2.0
- https://pypi.org/project/structlog/ — version 25.5.0
- https://pypi.org/project/orjson/ — version 3.11.5
- https://pypi.org/project/opentelemetry-sdk/ — version 1.39.1
- https://pypi.org/project/opentelemetry-exporter-otlp/ — version 1.39.1
- https://pypi.org/project/opentelemetry-instrumentation-fastapi/ — version 0.60b1
- https://pypi.org/project/opentelemetry-instrumentation-httpx/ — version 0.60b1
- https://pypi.org/project/httpx/ — version 0.28.1

---
*Stack research for: API compatibility proxy (Claude Code → OpenAI Responses)*
*Researched: 2026-01-25*
