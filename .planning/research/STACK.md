# Stack Research

**Domain:** API compatibility gateway/proxy (Anthropic Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12.x | Runtime | Strong ecosystem compatibility (FastAPI/Pydantic/AnyIO support 3.12) with solid async performance. **Confidence: MEDIUM** (version choice is opinionated but aligns with supported ranges on PyPI). |
| FastAPI | 0.128.0 | API framework (ASGI) | Modern ASGI framework with OpenAPI generation and Pydantic v2 integration; widely adopted for high-throughput JSON APIs. **Confidence: HIGH** (PyPI). |
| Uvicorn | 0.40.0 | ASGI server | Standard production ASGI server; supports HTTP/1.1 + WebSockets and `uvicorn[standard]` extras for performance. **Confidence: HIGH** (PyPI). |
| HTTPX | 0.28.1 | Async HTTP client (upstream calls) | Async/sync HTTP client with HTTP/2 optional extras; good fit for proxying with timeouts and streaming. **Confidence: HIGH** (PyPI). |
| Pydantic | 2.12.5 | Data validation/serialization | Schema validation and response shaping needed for compatibility translation. **Confidence: HIGH** (PyPI). |
| pydantic-settings | 2.12.0 | Env/config management | Canonical config system for env-based settings (API keys, limits, feature flags). **Confidence: HIGH** (PyPI). |
| OpenTelemetry SDK | 1.39.1 | Tracing + metrics | Standard vendor-neutral telemetry; required for reliability-first observability. **Confidence: HIGH** (PyPI). |
| opentelemetry-exporter-otlp | 1.39.1 | Trace/metric export | Default exporter bundle for OTLP to collector/backends. **Confidence: HIGH** (PyPI). |
| opentelemetry-instrumentation-fastapi | 0.60b1 (pre-release) | Auto instrumentation | FastAPI-specific auto instrumentation; still beta but standard in OTel Python stack. **Confidence: MEDIUM** (pre-release). |
| prometheus-client | 0.24.1 | Metrics endpoint | Prometheus-compatible metrics for local scraping or sidecar. **Confidence: HIGH** (PyPI). |
| structlog | 25.5.0 | Structured logging | JSON/logfmt logging with processors; enables PII redaction and consistent fields. **Confidence: HIGH** (PyPI). |
| orjson | 3.11.5 | Fast JSON serializer | Faster JSON for high-throughput proxy responses. **Confidence: HIGH** (PyPI). |
| sse-starlette | 3.2.0 | SSE streaming | Production-ready SSE response support for `/v1/messages/stream`. **Confidence: HIGH** (PyPI). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| AnyIO | 4.12.1 | Async primitives | For async task groups, timeouts, and cancellation in streaming + upstream calls. **Confidence: HIGH** (PyPI). |
| Typer | 0.21.1 | CLI runtime | For a first‑class CLI (`proxy run`, `proxy doctor`, etc.) aligned with FastAPI-style typing. **Confidence: HIGH** (PyPI). |
| Rich | 14.3.1 | CLI UX | Pretty CLI output, progress, and error rendering (pairs with Typer). **Confidence: HIGH** (PyPI). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Ruff 0.14.14 | Lint + format | Single fast linter/formatter; replace flake8/isort/black in one. |
| Pytest 9.0.2 | Test runner | Standard Python testing. |
| pytest-asyncio 1.3.0 | Async test support | Required for async endpoints and streaming tests. |
| mypy 1.19.1 | Type checking | Enforce strict typing across request/response models. |
| respx 0.22.0 | HTTPX mocking | Mock upstream OpenAI API in unit tests. |

## Installation

```bash
# Core runtime
pip install fastapi==0.128.0 uvicorn==0.40.0 httpx==0.28.1 \
  pydantic==2.12.5 pydantic-settings==2.12.0 orjson==3.11.5 \
  structlog==25.5.0 prometheus-client==0.24.1 \
  opentelemetry-sdk==1.39.1 opentelemetry-exporter-otlp==1.39.1 \
  opentelemetry-instrumentation-fastapi==0.60b1 sse-starlette==3.2.0

# Supporting
pip install anyio==4.12.1 typer==0.21.1 rich==14.3.1

# Dev dependencies
pip install -D ruff==0.14.14 pytest==9.0.2 pytest-asyncio==1.3.0 mypy==1.19.1 respx==0.22.0
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI | Starlette (bare) | If you want minimal framework surface and will hand-roll validation/OpenAPI. |
| Uvicorn | Hypercorn / Granian | If you require HTTP/2 server features or want Rust-based server performance. |
| HTTPX | aiohttp | If you need low-level HTTP client features or long-lived WebSocket client support beyond HTTPX. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Flask + WSGI servers | WSGI blocks async streaming and backpressure; SSE and upstream streaming suffer. | FastAPI + Uvicorn (ASGI). |
| requests (sync) for upstream | Blocking I/O limits concurrency and hurts latency under load. | HTTPX (async). |
| Unstructured logging (print/logging.basicConfig only) | Hard to redact PII and correlate requests. | structlog + OTel context fields. |

## Stack Patterns by Variant

**If streaming is heavy (SSE / long-lived connections):**
- Use `uvicorn[standard]` extras for `uvloop`/`httptools` performance.
- Enable HTTP/2 upstream with `httpx[http2]` if the provider supports it.

**If deploying in containerized production:**
- Prefer `uvicorn --workers N` for process concurrency and keep-alive tuning.
- Use OTel OTLP exporter to a local collector/agent.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastapi@0.128.0 | pydantic@2.12.x | FastAPI classifiers list Pydantic v2 support; keep in sync. |
| opentelemetry-sdk@1.39.1 | opentelemetry-exporter-otlp@1.39.1 | Keep same OTel minor version to avoid API mismatch. |
| opentelemetry-instrumentation-fastapi@0.60b1 | opentelemetry-sdk@1.39.1 | OTel instrumentation releases track SDK; this is pre-release. |
| respx@0.22.0 | httpx@0.28.1 | RESPX requires HTTPX ≥0.25. |

## Sources

- https://pypi.org/project/fastapi/ — version 0.128.0
- https://pypi.org/project/uvicorn/ — version 0.40.0
- https://pypi.org/project/httpx/ — version 0.28.1
- https://pypi.org/project/pydantic/ — version 2.12.5
- https://pypi.org/project/pydantic-settings/ — version 2.12.0
- https://pypi.org/project/anyio/ — version 4.12.1
- https://pypi.org/project/opentelemetry-sdk/ — version 1.39.1
- https://pypi.org/project/opentelemetry-exporter-otlp/ — version 1.39.1
- https://pypi.org/project/opentelemetry-instrumentation-fastapi/ — version 0.60b1
- https://pypi.org/project/prometheus-client/ — version 0.24.1
- https://pypi.org/project/structlog/ — version 25.5.0
- https://pypi.org/project/orjson/ — version 3.11.5
- https://pypi.org/project/sse-starlette/ — version 3.2.0
- https://pypi.org/project/typer/ — version 0.21.1
- https://pypi.org/project/rich/ — version 14.3.1
- https://pypi.org/project/ruff/ — version 0.14.14
- https://pypi.org/project/pytest/ — version 9.0.2
- https://pypi.org/project/pytest-asyncio/ — version 1.3.0
- https://pypi.org/project/mypy/ — version 1.19.1
- https://pypi.org/project/respx/ — version 0.22.0

---
*Stack research for: API compatibility gateway/proxy*
*Researched: 2026-01-25*
