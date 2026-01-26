# Phase 3: Privacy-First Observability - Research

**Researched:** 2026-01-25
**Domain:** FastAPI structured logging + PII redaction + correlation IDs
**Confidence:** MEDIUM

## Summary

This phase adds structured logging for requests/responses with PII redaction and per-request correlation IDs. The codebase is a FastAPI service; the most standard approach is to implement request-scoped logging via middleware plus structured JSON logs using `structlog` or `python-json-logger`, and to use a dedicated ASGI correlation-id middleware for consistent ID generation and propagation.

For privacy, the safest path is conservative redaction: default to redacting all content fields, and only allow partial redaction when an explicit debug flag is enabled. If partial redaction is enabled, use a dedicated PII detection/anonymization library such as Microsoft Presidio to replace detected spans with `[REDACTED]` rather than hand-rolled regexes.

**Primary recommendation:** Use `asgi-correlation-id` middleware to manage `x-correlation-id`, `structlog` + JSON rendering for request/response logs, and Presidio for optional PII detection/partial redaction in debug mode.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | ASGI framework | Current service is FastAPI-based. |
| structlog | latest (check PyPI) | Structured logging pipeline | Official docs show JSON rendering and stdlib integration. |
| asgi-correlation-id | latest (check PyPI) | Correlation ID middleware | Purpose-built ASGI middleware for correlation ID generation and logging integration. |
| presidio-analyzer + presidio-anonymizer | latest (check PyPI) | PII detection + anonymization | Official SDK supports replacing detected spans with custom values (e.g., `[REDACTED]`). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-json-logger | latest (check PyPI) | JSON formatting for stdlib loggers | If you want JSON for non-structlog loggers (uvicorn/httpx). |
| stdlib logging | builtin | Multi-handler output (stdout + file) | Required to emit logs to both stdout and file. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| structlog | python-json-logger only | Simpler, but lacks contextvars processors and richer structured pipeline. |
| asgi-correlation-id | custom middleware | More control, but re-implements header handling, validation, and logging filters. |
| Presidio | regex-based redaction | Faster to implement but high risk of missing PII; violates “when in doubt, redact” if detection is incomplete. |

**Installation:**
```bash
pip install structlog python-json-logger asgi-correlation-id presidio-analyzer presidio-anonymizer
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── observability/        # logging config, redaction utilities, schemas
├── middleware/           # correlation ID + request logging middleware
├── handlers/             # existing endpoints with request/response logging hooks
└── config.py             # env flags (log enable, redaction mode)
```

### Pattern 1: ASGI middleware for correlation ID + request timing
**What:** Add middleware that ensures a correlation ID is present and captures timing. Bind the ID into logging context for every log line.
**When to use:** All HTTP request/response cycles.
**Example:**
```python
# Source: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/middleware.md
from fastapi import FastAPI, Request
import time

app = FastAPI()

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

### Pattern 2: Correlation ID middleware (ASGI) with standard header name
**What:** Use `asgi-correlation-id` to read or generate IDs; configure to use `X-Correlation-ID` and expose it to logs.
**When to use:** Always, so each request/stream has a consistent ID.
**Example:**
```python
# Source: https://github.com/snok/asgi-correlation-id
from fastapi import FastAPI
from asgi_correlation_id import CorrelationIdMiddleware

app = FastAPI()
app.add_middleware(CorrelationIdMiddleware, header_name="X-Correlation-ID")
```

### Pattern 3: Structured JSON logging with structlog
**What:** Configure structlog with JSON rendering and stdlib integration; include contextvars to inject correlation ID into every log entry.
**When to use:** Any structured request/response logs.
**Example:**
```python
# Source: https://github.com/hynek/structlog/blob/main/docs/standard-library.md
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### Pattern 4: PII redaction with Presidio (replace spans with `[REDACTED]`)
**What:** Use Presidio Analyzer + Anonymizer to replace detected PII spans with a custom token.
**When to use:** When debug flag allows partial redaction; otherwise redact entire content fields.
**Example:**
```python
# Source: https://context7.com/microsoft/presidio/llms.txt
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

text = "His name is John Doe and his phone number is 123-456-7890"
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

results = analyzer.analyze(text=text, language="en")
redacted = anonymizer.anonymize(
    text=text,
    analyzer_results=results,
    operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})}
)
print(redacted.text)
```

### Anti-Patterns to Avoid
- **Reading request.body() in middleware without replaying the body:** consumes the stream and breaks downstream parsing. Prefer logging at handler level using parsed Pydantic models, or re-inject the body if you must read it in middleware.
- **Logging before redaction:** any log call that includes raw request/response payloads must pass through the redactor first.
- **Correlation ID only on success paths:** ensure IDs are attached in error paths and exception handlers too.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Correlation IDs | Custom header parsing + UUID generation | `asgi-correlation-id` middleware | Handles generation + header reuse; includes logging filter integration. |
| PII detection | Regex-only redaction | Presidio Analyzer/Anonymizer | Regex misses edge cases; Presidio supports configurable detection + replacement. |
| JSON log formatting | Manual `json.dumps` everywhere | structlog or python-json-logger | Centralized formatting, easier to add fields and handlers. |

**Key insight:** observability code is cross-cutting—use battle-tested middleware and logging frameworks to avoid silent PII leaks and inconsistent correlation IDs.

## Common Pitfalls

### Pitfall 1: Logging request/response bodies for streaming
**What goes wrong:** streaming responses can be consumed or buffered, causing broken streams or high memory use.
**Why it happens:** streaming bodies are iterators; reading them for logs drains content.
**How to avoid:** log metadata for streams (status, duration, sizes) or wrap the iterator carefully; avoid full body logging for streams.
**Warning signs:** stream endpoints return empty bodies or hang after logging is added.

### Pitfall 2: Context leakage across requests
**What goes wrong:** correlation IDs bleed across requests in async workloads.
**Why it happens:** contextvars not cleared/bound per request.
**How to avoid:** clear and bind contextvars at the top of each request (middleware).
**Warning signs:** logs show the same correlation ID across unrelated requests.

### Pitfall 3: “Opt-in” logging flag not enforced everywhere
**What goes wrong:** logs are emitted in some code paths even when disabled.
**Why it happens:** ad-hoc logging outside the central logger or config.
**How to avoid:** gate logging setup and handlers behind the env flag; use no-op logger or early return.
**Warning signs:** log files appear even when logging is disabled.

## Code Examples

Verified patterns from official sources:

### FastAPI middleware for timing
```python
# Source: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/middleware.md
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

### structlog JSON configuration
```python
# Source: https://github.com/hynek/structlog/blob/main/docs/standard-library.md
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

### python-json-logger basic setup
```python
# Source: https://github.com/nhairs/python-json-logger/blob/main/docs/quickstart.md
import logging
from pythonjsonlogger.json import JsonFormatter

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)
```

### Presidio custom replacement
```python
# Source: https://context7.com/microsoft/presidio/llms.txt
operators = {"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})}
anonymized = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Unstructured string logs | Structured JSON logs | Modern logging practice (current) | Enables reliable parsing, correlation, and PII redaction enforcement. |
| Ad-hoc request IDs | ASGI correlation-id middleware | Current ASGI practice | Consistent correlation IDs with header reuse/generation. |

**Deprecated/outdated:**
- Manual regex-only PII redaction without dedicated detection: high risk of leakage; use Presidio for detection when partial redaction is enabled.

## Open Questions

1. **Forward correlation ID to upstream OpenAI calls?**
   - What we know: `asgi-correlation-id` supports request header handling; upstream HTTP client is `httpx`.
   - What's unclear: whether upstream accepts/uses custom correlation headers.
   - Recommendation: add header propagation as optional feature; safe to include if upstream ignores it.

2. **Separate error logs to stderr or separate file?**
   - What we know: stdlib logging supports multiple handlers; structlog supports stdout/stderr configuration.
   - What's unclear: operator preference for error stream separation.
   - Recommendation: default to stderr for errors (standard practice), keep info to stdout + file.

## Sources

### Primary (HIGH confidence)
- /fastapi/fastapi - middleware docs (request/response middleware pattern)
- /hynek/structlog - JSON renderer + stdlib integration
- /nhairs/python-json-logger - JsonFormatter usage
- /microsoft/presidio - anonymizer replace with custom value
- https://github.com/snok/asgi-correlation-id - correlation ID middleware setup

### Secondary (MEDIUM confidence)
- None

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - based on official docs and common ASGI logging patterns, but versions not pinned.
- Architecture: MEDIUM - middleware + contextvars patterns validated; streaming logging details are contextual.
- Pitfalls: LOW-MEDIUM - based on typical ASGI behavior; validate against current code paths.

**Research date:** 2026-01-25
**Valid until:** 2026-02-24
