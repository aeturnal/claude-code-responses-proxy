# Phase 4: Streaming + Tool Use Parity - Research

**Researched:** 2026-01-26
**Domain:** Anthropic-compatible SSE streaming, tool_use blocks, input_json_delta accumulation
**Confidence:** HIGH

## Summary

This phase requires a faithful Anthropic Messages streaming implementation: `/v1/messages/stream` must emit SSE events in the exact message/content block lifecycle order, including `tool_use` blocks and `input_json_delta` updates. Anthropic’s streaming docs define the canonical event sequence (`message_start`, per-block `content_block_start` → `content_block_delta` → `content_block_stop`, `message_delta`, `message_stop`) and specify how tool use inputs stream as **partial JSON strings** via `input_json_delta`. These partial JSON fragments must be accumulated and only parsed when the block stops.

Because this proxy integrates with OpenAI’s Responses API, the implementation must map OpenAI’s streaming events (e.g., `response.output_text.delta`, `response.function_call_arguments.delta/done`) into Anthropic SSE events, while preserving event ordering and index semantics. Use the existing FastAPI + HTTPX stack to stream upstream responses and emit SSE via `StreamingResponse` with `text/event-stream` media type. Ensure the handler is resilient to `ping` and unknown events (Anthropic may add new ones), and that token usage in `message_delta` is cumulative.

**Primary recommendation:** Implement an SSE translator that consumes OpenAI streaming events, tracks Anthropic content-block state (index/type/input accumulation), and emits the exact Anthropic message/content-block lifecycle events with tool-use `input_json_delta` accumulation finalized at `content_block_stop`.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | repo dependency | HTTP API + streaming responses | Provides `StreamingResponse` for SSE in ASGI apps. |
| Starlette `StreamingResponse` (via FastAPI) | bundled | Stream SSE events | FastAPI’s recommended streaming response type. |
| httpx | repo dependency | Upstream streaming HTTP client | Supports `stream()` and `Response.aiter_lines()` for SSE parsing. |
| Pydantic | repo dependency | Request/response models | Existing request schemas; use for structured streaming state if needed. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | repo dependency | Observability | Emit streaming diagnostics if Phase 3 logging is enabled. |
| asgi-correlation-id | repo dependency | Trace correlation | Forward correlation IDs to upstream during streaming. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `StreamingResponse` | Custom ASGI response | Unnecessary complexity; FastAPI already provides correct streaming behavior. |
| `httpx.AsyncClient.stream` + `aiter_lines()` | Raw `asyncio` socket parsing | Higher complexity; HTTPX handles buffering and line splitting. |

**Installation:**
```bash
pip install fastapi uvicorn httpx pydantic
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── handlers/        # API endpoints
├── transport/       # Upstream OpenAI client
├── mapping/         # Anthropic ↔ OpenAI translation
├── schema/          # Pydantic models
└── observability/   # Logging/redaction
```

### Pattern 1: SSE Event Translator (OpenAI → Anthropic)
**What:** Consume OpenAI Responses streaming events and emit Anthropic SSE events in strict order.
**When to use:** For `/v1/messages/stream` parity with Anthropic.
**Example:**
```python
# Source: https://docs.anthropic.com/en/api/messages-streaming
# Anthropic event sequence:
# 1) message_start
# 2) content_block_start
# 3) content_block_delta (text_delta | input_json_delta)
# 4) content_block_stop
# 5) message_delta
# 6) message_stop

yield sse_event("message_start", {"type": "message_start", "message": {..., "content": []}})
yield sse_event("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
yield sse_event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}})
yield sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
yield sse_event("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 15}})
yield sse_event("message_stop", {"type": "message_stop"})
```

### Pattern 2: Tool Use Streaming with Partial JSON Accumulation
**What:** Accumulate `input_json_delta.partial_json` fragments into a per-block buffer; parse only after `content_block_stop`.
**When to use:** Any `tool_use` block in streaming mode.
**Example:**
```python
# Source: https://docs.anthropic.com/en/api/messages-streaming

# On content_block_start for tool_use:
tool_input_buffer[index] = ""

# On each input_json_delta:
tool_input_buffer[index] += delta["partial_json"]

# On content_block_stop:
final_input_obj = json.loads(tool_input_buffer[index])
emit_tool_use_block_with_input(final_input_obj)
```

### Anti-Patterns to Avoid
- **Skipping content_block_stop:** Anthropic requires a stop event for each block; missing it breaks clients expecting lifecycle completion.
- **Parsing `partial_json` on every delta:** The JSON is intentionally partial; parse only once at block stop unless you use a partial JSON parser.
- **Assuming event set is fixed:** Anthropic may add new events; ignore or passthrough unknown events safely.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE streaming response | Custom ASGI streaming | `fastapi.responses.StreamingResponse` | Correct content-type + streaming semantics out of the box. |
| HTTP streaming client | Manual socket parsing | `httpx.AsyncClient.stream()` + `Response.aiter_lines()` | Handles chunking/backpressure cleanly. |

**Key insight:** Streaming correctness is mostly about consistent event framing and lifecycle ordering; leverage built-in streaming primitives to reduce errors.

## Common Pitfalls

### Pitfall 1: Breaking Anthropic Event Order
**What goes wrong:** Clients see `message_delta` or `message_stop` before all `content_block_stop` events.
**Why it happens:** OpenAI events are different; missing a state machine that enforces Anthropic ordering.
**How to avoid:** Maintain per-message state and emit Anthropic events only when you have all required parts for the current block.
**Warning signs:** Clients fail to render tool_use blocks, or missing text in streamed responses.

### Pitfall 2: Mishandling input_json_delta
**What goes wrong:** Tool inputs are invalid JSON or truncated.
**Why it happens:** Parsing partial JSON deltas prematurely or resetting buffers incorrectly.
**How to avoid:** Buffer `partial_json` per block index and parse only at `content_block_stop`.
**Warning signs:** JSON decode errors or empty `tool_use.input` in final block.

### Pitfall 3: Ignoring ping/error events
**What goes wrong:** Stream handling terminates on `ping` or upstream error frames.
**Why it happens:** Code assumes only text/tool events exist.
**How to avoid:** Recognize `ping` and `error` events; keep stream alive or map errors to Anthropic error format.
**Warning signs:** Random disconnects during long responses.

### Pitfall 4: Usage accounting mismatches
**What goes wrong:** Token usage fields regress or appear non-cumulative.
**Why it happens:** Anthropic `message_delta.usage` is cumulative; overwriting instead of emitting latest totals.
**How to avoid:** Pass through or compute cumulative usage and emit it only in `message_delta`.
**Warning signs:** Client token accounting goes negative or resets mid-stream.

## Code Examples

Verified patterns from official sources:

### Anthropic Streaming Event Flow
```json
// Source: https://docs.anthropic.com/en/api/messages-streaming
event: message_start
data: {"type": "message_start", "message": {"content": []}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 15}}

event: message_stop
data: {"type": "message_stop"}
```

### Tool Use Input JSON Delta
```json
// Source: https://docs.anthropic.com/en/api/messages-streaming
event: content_block_delta
data: {
  "type": "content_block_delta",
  "index": 1,
  "delta": {"type": "input_json_delta", "partial_json": "{\"location\": \"San Fra"}
}
```

### HTTPX Streaming API (async)
```python
# Source: https://www.python-httpx.org/api/
async with httpx.AsyncClient() as client:
    async with client.stream("POST", url, json=payload, headers=headers) as response:
        async for line in response.aiter_lines():
            handle_sse_line(line)
```

### FastAPI StreamingResponse
```python
# Source: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
from fastapi.responses import StreamingResponse

async def sse_generator():
    yield "event: ping\ndata: {\"type\": \"ping\"}\n\n"

return StreamingResponse(sse_generator(), media_type="text/event-stream")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tool inputs delivered only at completion | `input_json_delta` partial JSON streaming | Anthropic streaming docs (current) | Requires buffering + final parse on block stop. |
| Single text delta stream | Multi-content block streaming (text/tool/thinking) | Anthropic Messages streaming | Requires per-block indices and lifecycle events. |

**Deprecated/outdated:**
- **Assuming no new event types:** Anthropic explicitly notes they may add new event types; code should ignore unknown events rather than fail.

## Open Questions

1. **Exact mapping from OpenAI streaming events to Anthropic block indices**
   - What we know: OpenAI Responses emit `response.output_item.added/done`, `response.content_part.added/done`, and `response.function_call_arguments.delta/done`.
   - What's unclear: Whether current mapping code already preserves content indices and how it will handle parallel tool calls in streaming.
   - Recommendation: Inspect existing mapping layer for streaming and define a deterministic index assignment strategy (e.g., increment on each new content part) before implementation.

2. **SSE error propagation format**
   - What we know: Anthropic streaming can emit `event: error` with `type: "error"` payloads.
   - What's unclear: Whether OpenAI upstream streaming errors will map cleanly to Anthropic error types used elsewhere in the proxy.
   - Recommendation: Decide a canonical error mapping and ensure stream terminates cleanly with Anthropic-style error event.

## Sources

### Primary (HIGH confidence)
- https://docs.anthropic.com/en/api/messages-streaming — event flow, `input_json_delta`, tool-use streaming examples
- https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse — StreamingResponse usage
- https://www.python-httpx.org/api/ — `stream()` and `Response.aiter_lines()` for streaming reads
- https://platform.openai.com/docs/api-reference/responses-streaming — OpenAI Responses streaming event taxonomy

### Secondary (MEDIUM confidence)
- https://docs.anthropic.com/en/docs/tool-use — tool use overview (non-streaming details)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified in repo requirements + FastAPI/HTTPX official docs
- Architecture: HIGH — Anthropic streaming docs provide explicit event order and tool JSON deltas
- Pitfalls: MEDIUM — derived from documented event rules + typical SSE handling issues

**Research date:** 2026-01-26
**Valid until:** 2026-02-25
