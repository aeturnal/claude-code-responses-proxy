# Phase 05: Credential Error Envelope Parity - Research

**Researched:** 2026-01-26
**Domain:** FastAPI error handling + Anthropic error envelope parity (HTTP + SSE)
**Confidence:** MEDIUM

## Summary

This phase targets missing `OPENAI_API_KEY` behavior in both `/v1/messages` and `/v1/messages/stream`. The current transport layer (`require_openai_api_key`) raises `ValueError` when the key is missing, which is not caught by the message handlers and results in a 500 response or broken stream. The repo already uses an Anthropic error envelope helper (`build_anthropic_error`) and maps upstream OpenAI errors via `OpenAIUpstreamError`, so the parity fix should reuse that error envelope, but must also handle locally-detected credential errors.

Anthropic’s official docs specify the error envelope shape and error types. For authentication failures (missing/invalid API key), Anthropic uses HTTP 401 with `authentication_error`. For streaming, Anthropic sends SSE `event: error` with the same envelope, even after a 200 response. Therefore, missing OpenAI credentials should be treated as an authentication error with the Anthropic envelope in both non-streaming and streaming paths, and should emit an SSE error event for the streaming endpoint.

**Primary recommendation:** Catch or re-raise missing-key errors as a 401 `authentication_error` and return/emit the Anthropic error envelope (with an `openai` field) in both `/v1/messages` and `/v1/messages/stream`.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | unpinned (requirements.txt) | ASGI API framework | Current app/router structure uses FastAPI throughout |
| httpx | unpinned | Async HTTP client for OpenAI upstream | Current transport layer uses `httpx.AsyncClient` |
| pydantic | unpinned | Request/response validation | Schemas in `src/schema/*` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | unpinned | Structured logging | Used in handlers for request/response/error logs |
| asgi-correlation-id | unpinned | Correlation IDs | Used to propagate/request correlation ID |
| pytest | unpinned | Test runner | Existing tests use pytest |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI exception handlers | Per-route try/except | Exception handler is global; route try/except allows custom SSE error emission |

**Installation:**
```bash
pip install -r requirements.txt
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── handlers/        # FastAPI route handlers
├── transport/       # OpenAI upstream HTTP/SSE
├── errors/          # Anthropic error envelope helpers
└── observability/   # Logging/redaction
```

### Pattern 1: Wrap upstream errors with `OpenAIUpstreamError`
**What:** Transport functions raise `OpenAIUpstreamError` when OpenAI returns non-2xx responses; handlers catch and convert to Anthropic error envelopes.
**When to use:** Any OpenAI upstream call (HTTP or SSE) that can return error responses.
**Example:**
```python
# Source: repo code (src/transport/openai_client.py)
if response.is_error:
    raise OpenAIUpstreamError(response.status_code, _safe_json(response))
```

### Pattern 2: Emit Anthropic SSE error events on stream failure
**What:** In streaming handlers, catch `OpenAIUpstreamError` and emit `event: error` with an Anthropic error envelope.
**When to use:** Streaming responses that fail after a 200 OK.
**Example:**
```python
# Source: repo code (src/handlers/messages.py)
yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
```

### Anti-Patterns to Avoid
- **Letting `ValueError` bubble out of transport:** This produces a 500 instead of an Anthropic envelope and breaks SSE error parity.
- **Returning raw OpenAI error JSON:** Requirements demand Anthropic envelope with OpenAI details.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Anthropic error envelope | Custom error dict | `build_anthropic_error` | Ensures consistent envelope fields and OpenAI details |
| SSE error formatting | Manual string concatenation in multiple places | `_format_sse_error` (messages handler) | Avoid inconsistent SSE framing |

**Key insight:** This repo already centralizes error envelope construction; extending that to missing credentials keeps parity consistent across endpoints.

## Common Pitfalls

### Pitfall 1: Missing API key cached at import time
**What goes wrong:** `OPENAI_API_KEY` is read into a module-level constant on import. Tests that only mutate `os.environ` after import won’t affect `require_openai_api_key`.
**Why it happens:** `OPENAI_API_KEY = os.getenv(...)` is evaluated when `src.config` is imported.
**How to avoid:** In tests, set `src.config.OPENAI_API_KEY = None` directly or reload the module after changing the environment.
**Warning signs:** Tests still see a key even after `monkeypatch.delenv("OPENAI_API_KEY")`.

### Pitfall 2: Wrong error type for authentication failures
**What goes wrong:** Using the default `api_error` type for missing API key instead of `authentication_error`.
**Why it happens:** `map_openai_error_type` falls back to `api_error` if no OpenAI error type is present.
**How to avoid:** Explicitly set `error_type="authentication_error"` when handling missing credentials.
**Warning signs:** `/v1/messages` returns 401 but error type is `api_error`.

### Pitfall 3: Streaming errors without proper SSE framing
**What goes wrong:** Streams close without emitting `event: error`, or malformed SSE formatting breaks clients.
**Why it happens:** Uncaught exceptions inside the stream generator or missing `\n\n` termination.
**How to avoid:** Catch the missing-key error inside the generator and emit `event: error` with the Anthropic envelope and proper SSE separators.
**Warning signs:** Client hangs or logs “Malformed event stream.”

## Code Examples

Verified patterns from official sources:

### Anthropic error envelope shape
```json
// Source: https://docs.anthropic.com/en/api/errors
{
  "type": "error",
  "error": {
    "type": "not_found_error",
    "message": "The requested resource could not be found."
  },
  "request_id": "req_..."
}
```

### Anthropic streaming error event
```text
# Source: https://docs.anthropic.com/en/api/streaming
event: error
data: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Uncaught local credential errors | Catch and map to Anthropic envelope | Phase 05 | Prevents 500s and preserves error parity across HTTP/SSE |

**Deprecated/outdated:**
- Letting `require_openai_api_key()` raise `ValueError` to the framework without mapping it to an Anthropic envelope.

## Open Questions

1. **What OpenAI error payload should be embedded for missing API key?**
   - What we know: Anthropic 401 uses `authentication_error`. OpenAI docs list 401 “Invalid Authentication,” but do not specify the exact JSON payload for missing key.
   - What's unclear: Whether to synthesize an OpenAI-style `{error:{type,message}}` payload or leave `openai` as a minimal object.
   - Recommendation: Use a small synthetic payload like `{"error": {"message": "OPENAI_API_KEY is required"}}` and set Anthropic `error.type="authentication_error"` explicitly.

## Sources

### Primary (HIGH confidence)
- https://docs.anthropic.com/en/api/errors — Error envelope shape and error types
- https://docs.anthropic.com/en/api/streaming — SSE error event format

### Secondary (MEDIUM confidence)
- https://platform.openai.com/docs/guides/error-codes — OpenAI 401 invalid authentication context

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — Derived from repo `requirements.txt` (versions unpinned)
- Architecture: HIGH — Directly from repo handlers/transport patterns
- Pitfalls: HIGH — Verified by current repo behavior (config import + handler exception flow)

**Research date:** 2026-01-26
**Valid until:** 2026-02-25
