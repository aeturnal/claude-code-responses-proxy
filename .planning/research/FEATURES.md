# Feature Research

**Domain:** OpenAI Responses → Anthropic Messages compatibility proxy (Claude Code target)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **/v1/messages request/response parity** | Claude Code speaks Anthropic Messages; proxy must accept same schema and return expected Message object | HIGH | Must support `messages` array with `role` + `content` (string or blocks), top-level `system`, `max_tokens`, `model`, `tools`, `tool_choice`, `stream`. Consecutive roles coalesce; `assistant` final message continues response. Map to OpenAI Responses inputs; preserve `content` block types. Source: Anthropic Messages API. | 
| **/v1/messages/stream SSE event sequence** | Streaming is core to Claude Code UX | HIGH | SSE events must follow Anthropic streaming flow: `message_start` → content block start/delta/stop → `message_delta` → `message_stop`, plus optional `ping` and `error`. Ensure event `type` fields match. Source: Anthropic streaming docs. |
| **Tool use content blocks** | Claude Code relies on tool invocations | HIGH | Responses must emit `tool_use` content blocks with `id`, `name`, `input` and accept `tool_result` blocks in subsequent user messages. Should map OpenAI tool calls to Anthropic tool blocks. Source: Anthropic Messages API + tool use docs. |
| **`input_json_delta` streaming for tool inputs** | Claude Code expects partial tool input emission | HIGH | Streaming must emit `content_block_delta` with `delta.type = input_json_delta` and `partial_json` fragments for tool input; final `tool_use.input` is object at `content_block_stop`. Must accumulate partial JSON. Source: Anthropic streaming docs (input_json_delta). |
| **/v1/messages/count_tokens** | Claude Code uses token preflight to avoid 400s | MEDIUM | Must accept same message schema as `/v1/messages` and return token count object. Map to OpenAI input token counting if available, otherwise approximate. Source: Anthropic count_tokens API. |
| **Error shape + HTTP status parity** | Client error handling expects Anthropic-style errors | MEDIUM | Translate OpenAI errors into Anthropic error envelope; emit `error` SSE events during stream. Source: Anthropic streaming error events. |
| **PII-redacted structured logging (default)** | Required in milestone context; also enterprise expectation | MEDIUM | Log requests/responses with redaction of user content and tool inputs by default; allow opt-out via config. Ensure no raw PII in logs. (No direct API source; requirement from milestone context.) |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Deterministic mapping report** | Debugging across two APIs becomes transparent | MEDIUM | Optional debug header/flag to include mapping metadata (e.g., OpenAI response IDs, translated tool calls). Keep off by default to avoid leaking data. |
| **Stream resilience helpers** | Better developer experience in flaky networks | MEDIUM | Buffer + resume suggestions to emulate Anthropic guidance on recovery; can emit client hints on reconnect strategy. (Derived from streaming docs.) |
| **Compatibility strictness modes** | Lets users choose strict Anthropic parity vs pragmatic fallback | MEDIUM | Strict mode rejects unsupported features; permissive mode maps best-effort and annotates `metadata` for mismatches. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **“Support every OpenAI Responses feature immediately”** | Users want full OpenAI surface area | Mismatch with Claude Code needs; increases scope and breaks parity expectations | Focus on `/v1/messages` + streaming + count_tokens first; add OpenAI extras later behind flags. |
| **Passing through raw tool inputs/outputs to logs** | Easier debugging | Violates PII/redaction requirement and increases risk | Provide redacted logs + opt-in secure debug mode. |
| **Non-Anthropic streaming shape** | Simpler implementation | Breaks Claude Code parsing (expects Anthropic event types) | Keep Anthropic SSE event flow; adapt OpenAI stream to match. |

## Feature Dependencies

```
/v1/messages schema parity
    └──requires──> Tool use block mapping
                       └──requires──> input_json_delta streaming

Streaming SSE support
    └──requires──> error event translation

/v1/messages/count_tokens
    └──requires──> shared request validation (messages/system/tools)

PII-redacted structured logging
    └──enhances──> All endpoints (request/response auditability)
```

### Dependency Notes

- **/v1/messages schema parity requires tool block mapping:** tool blocks are part of `content` and must round-trip through proxy.
- **Tool block mapping requires input_json_delta streaming:** Claude Code expects partial JSON deltas for tool inputs when streaming.
- **count_tokens requires shared validation:** same message schema and tool definitions must be accepted to count tokens reliably.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] **/v1/messages endpoint parity** — core compatibility for Claude Code.
- [ ] **/v1/messages/stream SSE with input_json_delta** — required for tool-use streaming semantics.
- [ ] **/v1/messages/count_tokens** — required for client-side token budgeting.
- [ ] **PII-redacted structured logging by default** — explicit milestone requirement.

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **Strict vs permissive compatibility modes** — add after basic stability.
- [ ] **Debug mapping metadata (opt-in)** — add once basic parity is verified.

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **/v1/files** — listed as nice-to-have; requires storage and policy work.
- [ ] **/v1/messages/batches** — batch semantics are complex; defer.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| /v1/messages parity | HIGH | HIGH | P1 |
| /v1/messages/stream SSE parity | HIGH | HIGH | P1 |
| input_json_delta streaming for tools | HIGH | HIGH | P1 |
| /v1/messages/count_tokens | MEDIUM | MEDIUM | P1 |
| PII-redacted structured logging | HIGH | MEDIUM | P1 |
| Strict/permissive compatibility modes | MEDIUM | MEDIUM | P2 |
| Debug mapping metadata | MEDIUM | MEDIUM | P2 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Competitor A | Competitor B | Our Approach |
|---------|--------------|--------------|--------------|
| Messages endpoint | Anthropic Messages API | OpenAI Responses API | Accept Anthropic schema, translate to OpenAI Responses.
| Streaming events | Anthropic SSE events w/ `content_block_*` | OpenAI Responses streaming events | Emit Anthropic SSE event types regardless of upstream.
| Tool use | `tool_use` + `tool_result` blocks | OpenAI function/tool calls | Map OpenAI tool calls to Anthropic tool blocks.
| Token counting | `/v1/messages/count_tokens` | `/v1/responses/input_tokens` | Provide Anthropic endpoint; use OpenAI input token count when possible.

## Sources

- Anthropic Messages API: https://docs.anthropic.com/en/api/messages
- Anthropic Streaming Messages (SSE, input_json_delta): https://docs.anthropic.com/en/api/messages-streaming
- Anthropic Count Tokens: https://docs.anthropic.com/en/api/messages-count-tokens
- OpenAI Responses API: https://platform.openai.com/docs/api-reference/responses
- OpenAI Responses Streaming: https://platform.openai.com/docs/api-reference/responses-streaming

---
*Feature research for: OpenAI Responses Compatibility Proxy*
*Researched: 2026-01-25*
