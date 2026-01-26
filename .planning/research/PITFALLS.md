# Pitfalls Research

**Domain:** LLM API compatibility gateway (OpenAI Responses → Anthropic Messages parity)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Critical Pitfalls

### Pitfall 1: Streaming event translation doesn’t reconstruct Anthropic’s event flow

**What goes wrong:**
Clients hang or mis-render because the gateway forwards OpenAI streaming events without reconstituting Anthropic’s required sequence (`message_start` → content blocks → `message_delta` → `message_stop`).

**Why it happens:**
OpenAI Responses emits different event types (`response.*`, `response.output_text.delta`, `response.function_call_arguments.delta`) and doesn’t map 1:1 to Anthropic’s `content_block_*` model.

**How to avoid:**
Build a streaming translator that assembles OpenAI events into Anthropic message/content blocks with explicit start/stop events and correct indices. Add replay-based fixtures to validate full event ordering.

**Warning signs:**
- Streaming works for simple text but fails with tool-use.
- Clients wait forever for `message_stop`.
- Content blocks appear out of order or never close.

**Phase to address:**
Phase 2 — Streaming parity & SSE translator.

---

### Pitfall 2: `input_json_delta` handling emits invalid tool inputs

**What goes wrong:**
Partial tool arguments are emitted as completed JSON, causing parse errors or missing fields downstream.

**Why it happens:**
Anthropic’s `input_json_delta` is a partial JSON string stream that must be accumulated and parsed once the `content_block_stop` arrives.

**How to avoid:**
Buffer tool argument deltas per content block, validate JSON only at `content_block_stop`, and emit tool-use blocks only once complete. Include test fixtures with partial JSON deltas.

**Warning signs:**
- Tool calls fail only in streaming mode.
- Tool inputs are sometimes `{}` or missing required keys.
- Logs show JSON parse errors during streaming.

**Phase to address:**
Phase 2 — Tool-use streaming parity.

---

### Pitfall 3: Tool call correlation is broken (IDs and indices drift)

**What goes wrong:**
Tool results attach to the wrong tool call or are dropped because tool IDs/indices don’t align between providers.

**Why it happens:**
OpenAI Responses uses output item IDs and per-event indices, while Anthropic uses `tool_use` blocks with `id` and content indices. Naïve mapping loses stable identifiers.

**How to avoid:**
Create a deterministic ID mapping layer and keep a per-response registry of tool calls with indices and output item IDs. Validate that every tool_use has a matching tool_result.

**Warning signs:**
- Tool results appear under the wrong request.
- Some tool calls never receive results.
- Integration tests with multiple tool calls fail intermittently.

**Phase to address:**
Phase 2 — Tool-use parity + result mapping.

---

### Pitfall 4: Stream termination semantics are incorrect

**What goes wrong:**
Clients treat responses as incomplete because the gateway doesn’t emit `message_stop`, or emits it before all content blocks are closed.

**Why it happens:**
OpenAI has `response.completed`/`response.incomplete` events; Anthropic requires an explicit `message_stop` after all blocks and deltas.

**How to avoid:**
Track completion state and ensure `message_stop` is emitted only after all content blocks have `content_block_stop`. Map incomplete/failed states to Anthropic error or stop semantics.

**Warning signs:**
- Client SDKs never resolve stream completion.
- Downstream waits on stop reason that never arrives.
- Partial content is discarded due to premature stop.

**Phase to address:**
Phase 2 — Streaming completion correctness.

---

### Pitfall 5: Logging redaction is applied too late or only on happy paths

**What goes wrong:**
PII or API keys leak into logs/traces because redaction happens after logs are emitted or doesn’t cover error paths and streaming chunks.

**Why it happens:**
Logging is added for debugging, then redaction is bolted on in one middleware path. Streaming paths and error handlers often bypass it.

**How to avoid:**
Centralize log emission through a redaction layer with allowlists, apply to request/response bodies and headers, and ensure streaming chunks and error payloads are filtered. Add unit tests to assert redaction across all endpoints and stream paths.

**Warning signs:**
- Access logs contain raw prompts or tool inputs.
- Error logs include request bodies.
- Redaction coverage differs between streaming and non-streaming.

**Phase to address:**
Phase 1 — Logging/redaction baseline; Phase 2 — streaming paths.

---

### Pitfall 6: Proxy buffering breaks SSE streaming

**What goes wrong:**
Events arrive in large bursts or time out because a reverse proxy buffers the stream.

**Why it happens:**
Default proxy settings (e.g., Nginx, load balancers) buffer responses and don’t flush SSE events promptly.

**How to avoid:**
Disable proxy buffering for streaming routes, set correct `Content-Type: text/event-stream`, and flush after each event. Add an integration test through the deployed proxy.

**Warning signs:**
- Streaming works locally but not in staging/prod.
- Clients receive chunks every few seconds instead of continuous stream.
- SSE pings are not visible to clients.

**Phase to address:**
Phase 2 — Deployment/infra streaming validation.

---

### Pitfall 7: Tool-use parity stops at “non-streaming only”

**What goes wrong:**
MVP supports tool calls in non-streaming mode but streaming tool-use is missing, breaking clients that expect `input_json_delta` and streaming tool events.

**Why it happens:**
Streaming tool-use is complex and often deferred, but the project requirement explicitly requires input_json_delta parity.

**How to avoid:**
Treat streaming tool-use as MVP-critical: build it alongside text streaming and include dedicated fixtures that simulate partial tool input.

**Warning signs:**
- Integration tests pass for tool-use only when `stream=false`.
- Clients report tool calls only visible at the end.
- `content_block_delta` for tool use never appears.

**Phase to address:**
Phase 2 — Streaming tool-use parity.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Forward OpenAI SSE events “as-is” | Faster implementation | Breaks Anthropic client expectations | Never |
| Disable streaming for tool calls | Simplifies MVP | Violates required parity | Never |
| Log raw payloads during debugging | Easy troubleshooting | PII leakage risk | Dev-only, isolated sandbox |
| Skip SSE replay tests | Faster CI | Regressions go unnoticed | MVP-only, if manual validation exists |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Anthropic streaming | Ignoring required `message_*` event flow | Reconstruct full `message_start` → `message_stop` sequence |
| OpenAI Responses streaming | Assuming content deltas are only text | Handle function/tool argument deltas and output item events |
| Reverse proxy (Nginx/ALB) | Buffering SSE responses | Disable buffering, flush events, verify headers |
| Client SDKs | Not supporting unknown event types | Pass through or safely ignore unknown events |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-chunk JSON parsing for tool deltas | High CPU usage | Buffer deltas and parse once at block end | ~50–100 concurrent streams |
| Redacting by deep-copying large payloads | Latency spikes | Use streaming-safe redaction + allowlists | Moderate QPS with large prompts |
| No backpressure handling on SSE | Memory growth | Drop or throttle slow clients | Long-running streams |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging raw prompts or tool inputs | PII leakage | Central redaction + allowlist logging |
| Passing client headers upstream | Credential leakage | Strict header allowlist |
| Storing tool inputs unredacted in traces | Sensitive data exposure | Redact at tracing layer |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent tool-use drops | Clients see incorrect behavior | Emit explicit error explaining unsupported feature |
| Inconsistent stop reasons | Client logic breaks | Normalize stop_reason fields and document behavior |
| Missing `message_stop` | Clients hang waiting | Always emit stop event even on error (with error payload) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Streaming parity:** `message_start`, `content_block_*`, `message_stop` sequence verified
- [ ] **Tool-use streaming:** `input_json_delta` accumulation validated with partial JSON fixtures
- [ ] **Error streaming:** error events mapped and still terminate with stop
- [ ] **Redaction:** verified on streaming chunks + error logs + access logs
- [ ] **Proxy config:** SSE not buffered in production

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Event translation mismatch | HIGH | Roll out a fixed translator behind feature flag; replay captured streams in CI |
| Tool delta parsing errors | MEDIUM | Add buffering + JSON validation, re-run integration tests |
| PII leakage in logs | HIGH | Rotate keys, purge logs, patch redaction; audit logging paths |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Streaming event translation mismatch | Phase 2 | SSE replay fixtures validate full event ordering |
| `input_json_delta` handling | Phase 2 | Fixture with partial JSON deltas parses correctly |
| Tool correlation drift | Phase 2 | Multi-tool integration tests verify tool_use_id mapping |
| Incorrect stream termination | Phase 2 | Ensure `message_stop` always emitted after final block |
| Logging redaction gaps | Phase 1–2 | Redaction tests across success + error + streaming |
| Proxy buffering | Phase 2 | Staging test via real proxy shows incremental events |

## Sources

- OpenAI Responses Streaming Events: https://platform.openai.com/docs/api-reference/responses-streaming
- Anthropic Messages Streaming: https://docs.anthropic.com/en/api/messages-streaming
- Anthropic tool-use streaming (`input_json_delta`): https://docs.anthropic.com/en/api/messages-streaming

---
*Pitfalls research for: LLM API compatibility gateway (OpenAI Responses → Anthropic Messages parity)*
*Researched: 2026-01-25*
