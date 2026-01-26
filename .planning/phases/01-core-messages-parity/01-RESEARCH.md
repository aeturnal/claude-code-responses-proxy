# Phase 1: Core Messages Parity - Research

**Researched:** 2026-01-25
**Domain:** Anthropic Messages API ↔ OpenAI Responses API compatibility mapping
**Confidence:** MEDIUM

## Summary

This phase requires a deterministic translation layer between Anthropic’s `/v1/messages` request/response format and OpenAI’s `/v1/responses` API. The core work is schema-level mapping: inputs (roles, system prompt, content blocks, tools) must be transformed into OpenAI Responses “input items” and tool definitions; outputs must be normalized back into the Anthropic message object, including correct `stop_reason` semantics and Anthropic error envelopes. The official Anthropic Messages docs define the response object (including `stop_reason` values and tool-use blocks), while OpenAI’s OpenAPI spec defines Responses input items, tool definitions, output item types, and error schemas.

Key recommendations: (1) base request mapping on the OpenAI Responses API input schema (`InputParam`, `InputMessage` roles `user/system/developer`) and Anthropic Messages request rules (no `system` role in messages; system content is top-level), (2) build a stop-reason mapping using OpenAI `response.status` and `incomplete_details.reason`, plus detection of function tool call output items, and (3) implement Anthropic error envelopes with OpenAI error details inside `error` (type/message/param/code) from OpenAI’s OpenAPI `ErrorResponse` schema.

**Primary recommendation:** Implement a dedicated “mapping layer” that normalizes Anthropic requests to OpenAI Responses input/tool schemas and maps OpenAI response output items back to Anthropic message content + `stop_reason`, with deterministic error envelope wrapping.

## Standard Stack

The established APIs/specs for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Anthropic Messages API | Current docs (2026-01-25) | Source-of-truth request/response schema (`/v1/messages`) | Defines Anthropic-compatible response shape, content blocks, and stop_reason semantics. |
| OpenAI Responses API | Current docs + OpenAPI spec v2.3.0 | Upstream model response generation | OpenAI’s recommended “most advanced” interface; schema defines input items, output items, and response status/incomplete details. |
| OpenAI OpenAPI spec | v2.3.0 | Error schema + tool definition schema | Authoritative error object (`ErrorResponse`) and tool schemas (`FunctionTool`, `FunctionToolCall`). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| OpenAI error codes guide | Current docs (2026-01-25) | Mapping HTTP errors and retry semantics | For mapping upstream error types to Anthropic error envelope types. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| OpenAI Responses API | OpenAI Chat Completions API | Responses API is explicitly positioned as the most advanced interface; Chat Completions is legacy and less aligned with modern tool/streaming formats. |

**Installation:**
```bash
# No SDK required; use direct HTTPS calls to /v1/responses
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── transport/           # HTTP client to OpenAI, retries, timeouts
├── mapping/             # Anthropic ↔ OpenAI request/response transforms
├── errors/              # Error normalization to Anthropic envelope
├── schema/              # JSON schema validation/helpers for input/output
└── handlers/            # /v1/messages endpoint handler
```

### Pattern 1: Request Normalization Pipeline
**What:** Convert Anthropic request into OpenAI Responses request by mapping system prompt, messages, and tools into `input` items and `tools`.
**When to use:** For every `/v1/messages` request.
**Example:**
```json
// Source: https://docs.anthropic.com/en/api/messages
// Anthropic request (system + messages)
{
  "model": "claude-3-7-sonnet-latest",
  "system": "You are helpful",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "max_tokens": 1024
}

// Source: https://platform.openai.com/docs/api-reference/responses
// OpenAI Responses request (instructions + input items)
{
  "model": "gpt-4.1",
  "instructions": "You are helpful",
  "input": [
    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
  ],
  "max_output_tokens": 1024
}
```

### Pattern 2: Output Normalization + Stop Reason Derivation
**What:** Convert OpenAI `response.output` items into Anthropic `content` blocks and set `stop_reason` based on response status, incomplete details, and tool call presence.
**When to use:** For every non-stream `/v1/messages` response.
**Example:**
```json
// Source: https://platform.openai.com/docs/api-reference/responses
// OpenAI response output (message + tool call)
{
  "status": "completed",
  "output": [
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]},
    {"type": "function_call", "call_id": "call_1", "name": "get_weather", "arguments": "{\"city\":\"SF\"}"}
  ]
}

// Source: https://docs.anthropic.com/en/api/messages
// Anthropic message response (tool_use => stop_reason=tool_use)
{
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Hi"},
    {"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"city": "SF"}}
  ],
  "stop_reason": "tool_use"
}
```

### Anti-Patterns to Avoid
- **Embedding `system` as a `messages` role in Anthropic requests:** Anthropic explicitly uses the top-level `system` field, not a `system` role message.
- **Assuming OpenAI provides a direct “finish reason”:** Responses API uses `status` and `incomplete_details` rather than a ChatCompletions-style finish reason; you must derive Anthropic `stop_reason`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAI error schema | Custom, ad-hoc error parsing | OpenAI OpenAPI `ErrorResponse` schema | Ensures inclusion of `type/message/param/code` with consistent nullability. |
| Tool definition schema | Custom tool JSON conventions | OpenAI `FunctionTool` schema (`type`, `name`, `description`, `parameters`, `strict`) | Avoids mismatched tool fields and downstream validation errors. |
| Stop reason list | Custom enums | Anthropic `stop_reason` enum values | Must match Anthropic semantics exactly. |

**Key insight:** Compatibility depends on strict schema parity—lean on official schemas to avoid subtle client breakage.

## Common Pitfalls

### Pitfall 1: Incorrect `stop_reason` mapping
**What goes wrong:** Responses return `status`/`incomplete_details`, but Anthropic clients expect `stop_reason` such as `end_turn`, `max_tokens`, or `tool_use`.
**Why it happens:** OpenAI Responses API does not expose a ChatCompletions-style finish reason.
**How to avoid:** Derive from: (a) `response.status` + `incomplete_details.reason` (`max_output_tokens` → `max_tokens`), (b) presence of function tool call items → `tool_use`, else default to `end_turn`.
**Warning signs:** Client expects `stop_reason` but receives null/unknown or mismatched values.

### Pitfall 2: System prompt placement mismatch
**What goes wrong:** System text is treated as a user message or merged into messages array.
**Why it happens:** Anthropic uses top-level `system`, while OpenAI Responses allows `instructions` or `system`-role input items.
**How to avoid:** Prefer `instructions` for Anthropic `system` content; keep `messages` only for user/assistant turns.
**Warning signs:** Unexpected model behavior or reduced adherence to system instructions.

### Pitfall 3: Tool calls not surfaced in Anthropic content
**What goes wrong:** Tool calls are returned as OpenAI `function_call` items but not translated into Anthropic `tool_use` blocks.
**Why it happens:** OpenAI output uses `OutputItem` variants rather than embedding tool calls inside assistant messages.
**How to avoid:** Scan `response.output` for `function_call` items and convert into `tool_use` blocks with `id/name/input`.
**Warning signs:** Client never sees tool calls; downstream tool execution chain breaks.

## Code Examples

Verified patterns from official sources:

### Anthropic `stop_reason` semantics
```json
// Source: https://docs.anthropic.com/en/api/messages
// stop_reason enum: end_turn | max_tokens | stop_sequence | tool_use | pause_turn | refusal
```

### OpenAI ErrorResponse schema
```yaml
# Source: https://app.stainless.com/api/spec/documented/openai/openapi.documented.yml
ErrorResponse:
  type: object
  properties:
    error:
      $ref: '#/components/schemas/Error'
  required: [error]

Error:
  type: object
  properties:
    code: {anyOf: [string, 'null']}
    message: {type: string}
    param: {anyOf: [string, 'null']}
    type: {type: string}
  required: [type, message, param, code]
```

### OpenAI Responses input message schema (roles)
```yaml
# Source: https://app.stainless.com/api/spec/documented/openai/openapi.documented.yml
InputMessage:
  type: object
  properties:
    type: {enum: [message]}
    role: {enum: [user, system, developer]}
    content: { $ref: '#/components/schemas/InputMessageContentList' }
  required: [role, content]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chat Completions API | Responses API | Current docs (2025–2026) | Responses API is the “most advanced interface,” aligning with tool calls and unified output items. |

**Deprecated/outdated:**
- **Chat Completions for new integrations:** OpenAI positions Responses API as the primary interface for new builds (see Responses API docs).

## Open Questions

1. **Exact mapping for `stop_reason = refusal` and `pause_turn` in non-streaming**
   - What we know: Anthropic enumerates `refusal` and `pause_turn`; OpenAI Responses includes `incomplete_details.reason` (`content_filter`, `max_output_tokens`).
   - What's unclear: Whether OpenAI provides a direct signal for Anthropic `refusal`/`pause_turn` in non-stream responses.
   - Recommendation: Map `content_filter` to `refusal` tentatively; log and flag for validation tests.

2. **System prompt mapping: `instructions` vs `system` role items**
   - What we know: OpenAI supports both `instructions` and `system` role input items; Anthropic uses top-level `system`.
   - What's unclear: Best semantic match for Anthropic system content in all cases (especially with tool use).
   - Recommendation: Use `instructions` for system content and avoid `system` role unless future testing shows a mismatch.

## Sources

### Primary (HIGH confidence)
- https://docs.anthropic.com/en/api/messages — Anthropic Messages API schema (content blocks, `stop_reason`, tools, tool_choice)
- https://docs.anthropic.com/en/api/errors — Anthropic error envelope + error types
- https://platform.openai.com/docs/api-reference/responses — OpenAI Responses API object + request/response examples
- https://app.stainless.com/api/spec/documented/openai/openapi.documented.yml — OpenAI OpenAPI spec v2.3.0 (ErrorResponse, InputMessage, Response, OutputItem, FunctionTool)

### Secondary (MEDIUM confidence)
- https://platform.openai.com/docs/guides/error-codes — OpenAI error code semantics (status → error handling)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — backed by official Anthropic/OpenAI docs and OpenAPI spec
- Architecture: MEDIUM — derived from schema mappings; needs validation with integration tests
- Pitfalls: MEDIUM — based on known schema mismatches and stop_reason semantics

**Research date:** 2026-01-25
**Valid until:** 2026-02-24
