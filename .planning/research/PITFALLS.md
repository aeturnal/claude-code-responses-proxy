# Pitfalls Research

**Domain:** API compatibility gateway (Anthropic Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Critical Pitfalls

### Pitfall 1: Semantic drift in message/content mapping

**What goes wrong:**
System/assistant/user roles, content blocks, and tool-use blocks are mapped loosely, causing subtle behavior changes (e.g., system instructions applied incorrectly, tool calls misframed, or assistant continuity broken).

**Why it happens:**
Anthropic Messages and OpenAI Responses model inputs/outputs differently (role handling, content block schemas, tool-use shape). A naïve “field rename” approach ignores semantic differences.

**How to avoid:**
Define a canonical internal schema and write explicit, versioned adapters for both sides. Include contract tests for role ordering, system prompts, tool_use/tool_result blocks, and partial assistant continuations. Document any intentional behavior deltas.

**Warning signs:**
- Test prompts behave differently between direct Anthropic and gateway usage.
- Tool calls appear in unexpected places or with malformed inputs.
- System prompt changes are ignored or bleed into user content.

**Phase to address:**
Phase 1 — Core request/response mapping & contract tests.

---

### Pitfall 2: Streaming event mismatch (SSE parity failure)

**What goes wrong:**
Streaming clients hang, mis-order content, or miss message termination because Anthropic’s SSE event flow (message_start/content_block_delta/message_stop) doesn’t align with OpenAI Responses streaming events and completion signals.

**Why it happens:**
Each API has distinct streaming event types and sequencing. Gateways often forward upstream events “as-is” without reconstituting the expected downstream flow.

**How to avoid:**
Implement a streaming event translator that reconstructs Anthropic’s event model from OpenAI Responses deltas. Include backpressure handling and explicit end-of-stream events. Maintain a compatibility test suite that replays recorded upstream streams.

**Warning signs:**
- Clients time out waiting for `message_stop`/final event.
- Partial text duplicated or out-of-order.
- Tool-use blocks never close.

**Phase to address:**
Phase 2 — Streaming parity & SSE translator.

---

### Pitfall 3: Token/limit semantics mismatch

**What goes wrong:**
Requests that should succeed fail, or truncation happens unexpectedly because `max_tokens`, context limits, and truncation behaviors differ between providers.

**Why it happens:**
Both APIs expose “max tokens” but apply limits differently and expose different error/usage fields. Gateways often map parameters directly without enforcing provider-specific constraints or returning consistent usage counts.

**How to avoid:**
Normalize limits in the gateway: preflight check input sizes, set conservative `max_output_tokens`, and return clear “incomplete” statuses when output is cut off. Keep a per-model policy map with limits and behavior flags.

**Warning signs:**
- Frequent 400/413 errors despite seemingly valid requests.
- Usage counters missing or inconsistent across endpoints.
- Responses ending mid-thought without clear stop reasons.

**Phase to address:**
Phase 2 — Token counting + truncation behavior.

---

### Pitfall 4: Error-shape drift and loss of actionable context

**What goes wrong:**
Downstream clients get errors that don’t match Anthropic’s schema (or are missing fields like request IDs, error types, or retry-ability), breaking client error handling or retries.

**Why it happens:**
OpenAI and Anthropic error shapes differ and streaming errors can appear mid-stream. Gateway teams often forward errors verbatim or over-normalize, losing needed detail.

**How to avoid:**
Define a strict error mapping matrix (HTTP status, error.type, error.message, request_id) and include original provider error as a nested field for debugging. Ensure streaming errors generate a final SSE error event plus a structured end state.

**Warning signs:**
- Client SDKs raise generic exceptions instead of expected error types.
- Debug logs require upstream inspection to understand failures.
- Retrying behavior is inconsistent or overly aggressive.

**Phase to address:**
Phase 1–2 — Error normalization + streaming errors.

---

### Pitfall 5: Tool-use delta handling breaks or leaks

**What goes wrong:**
Tool inputs are malformed or incomplete because partial JSON deltas are forwarded as full JSON, or partial tool-use blocks are exposed to clients that expect completed objects.

**Why it happens:**
Anthropic streams tool inputs as partial JSON deltas and requires accumulation; OpenAI Responses uses different function-call delta formats. Gateways that don’t buffer correctly emit invalid tool inputs.

**How to avoid:**
Implement tool-use buffering/assembly: accumulate partial JSON, validate, and emit only when complete. Provide a strict mode that disallows streaming tool blocks to clients that can’t handle them.

**Warning signs:**
- Tool-use JSON parse errors downstream.
- Tool inputs missing required keys.
- Sporadic failures only in streaming mode.

**Phase to address:**
Phase 2 — Streaming tool-use parity.

---

### Pitfall 6: File handling semantics diverge from expectations

**What goes wrong:**
Files appear uploaded but cannot be retrieved or are stored with incorrect metadata/encoding. File IDs are not stable across restarts.

**Why it happens:**
OpenAI Files API and Anthropic Messages file/document blocks differ in storage semantics and ID lifetimes. Local disk storage can break expectations around persistence, listability, and content types.

**How to avoid:**
Define a stable file ID scheme, keep metadata (content type, size, checksum), and document retention. Validate file types and sizes on upload, and map to Anthropic document/content block conventions consistently.

**Warning signs:**
- Uploaded file IDs stop working after restart.
- Content type mismatches in downstream requests.
- File list or retrieval returns inconsistent results.

**Phase to address:**
Phase 3 — Files subsystem & storage semantics.

---

### Pitfall 7: PII leakage through logs/metrics/tracing

**What goes wrong:**
Prompts, completions, or API keys leak into logs or tracing payloads, violating privacy or compliance expectations.

**Why it happens:**
Observability is often added late. Teams log full payloads for debugging and forget to redact across all layers (app logs, access logs, tracing spans).

**How to avoid:**
Implement centralized redaction middleware (headers + body), default to structured logs with allowlists, and provide opt-in debug mode with explicit warnings. Test redaction on streaming payloads and error cases.

**Warning signs:**
- Log lines include raw prompts, tool inputs, or API keys.
- Traces store request/response bodies.
- Redaction only applied to one logging path.

**Phase to address:**
Phase 1–2 — Observability baseline with redaction.

---

### Pitfall 8: Retries and idempotency gaps

**What goes wrong:**
Client retries cause duplicated responses or tool side effects, especially when the gateway retries upstream requests after timeouts.

**Why it happens:**
Providers differ in idempotency support and background processing semantics. Gateways often retry on network errors without preserving idempotency keys.

**How to avoid:**
Support idempotency keys for write-like requests and propagate them upstream when possible. Add a response cache for in-flight requests and configurable retry policies.

**Warning signs:**
- Duplicate responses for the same client request.
- Upstream rate limit spikes during network instability.
- Users report repeated tool executions.

**Phase to address:**
Phase 3 — Reliability & retry policies.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| “Just pass through” mapping of fields | Faster MVP | Hidden semantic drift; brittle clients | Never for core endpoints |
| Skip contract tests across providers | Shorter dev cycle | Regressions on provider changes | Only in prototype spikes |
| Treat streaming as “just chunked text” | Simpler SSE handling | Breaks tool-use/structured blocks | Never for production |
| Store files without metadata | Quick local disk support | Retrieval/validation issues | MVP only, with migration plan |
| Log full payloads for debugging | Easier troubleshooting | PII leakage risk | Never outside dev-only sandbox |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Anthropic Messages ↔ OpenAI Responses | Assuming role/system semantics are identical | Explicit mapping with tests for system, tool_use, and continuations |
| Streaming SSE | Forwarding upstream event types directly | Translate event flow to Anthropic-compatible `message_*` + block deltas |
| Token counting endpoints | Returning upstream counts verbatim | Normalize usage fields and document differences |
| Files API | Reusing upstream IDs without persistence | Stable IDs + metadata store + retrieval parity |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-chunk JSON parsing on every SSE event | High CPU, latency spikes | Buffer + incremental parsing | ~100+ concurrent streams |
| Synchronous redaction in hot path | Slow responses | Async/stream-aware redaction, allowlists | Moderate QPS with large payloads |
| No upstream connection pooling | Latency and rate-limit spikes | Use shared HTTP client + keep-alive | Low–mid QPS |
| Storing full prompts/responses in logs | Disk growth + slow IO | Sampled logs, truncation, redaction | Immediate at scale |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging raw prompts or API keys | PII/key leakage | Structured logging + redaction middleware |
| Accepting unbounded file uploads | Disk exhaustion / DoS | File size limits + quotas |
| Trusting URL-based content inputs | SSRF / data exfiltration | Block private IP ranges, allowlist domains |
| Passing client-provided headers upstream | Credential leakage | Strict header allowlist |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent feature drops (e.g., tool_use ignored) | Confusing model behavior | Return explicit errors or warnings |
| Inconsistent error codes across endpoints | Client retry logic fails | Centralized error mapping policy |
| Missing required Anthropic headers/version behavior | Client SDKs break | Enforce/validate headers and document defaults |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Streaming support:** Text works, but tool_use and message_stop semantics verified
- [ ] **Token counting:** Counts align with reported usage and truncation behavior
- [ ] **Files:** Upload, list, retrieve, and attach flows verified end-to-end
- [ ] **Errors:** Gateway returns Anthropic-shaped errors with request IDs
- [ ] **Observability:** Logs/metrics/traces redacted across success + error paths

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Semantic mapping drift | MEDIUM | Add contract tests, pin behavior, document deltas, re-run compatibility suite |
| Streaming mismatch | HIGH | Rebuild event translator, add replay-based tests, roll out behind feature flag |
| File ID instability | MEDIUM | Add migration layer, re-key files, publish deprecation plan |
| PII leakage | HIGH | Rotate keys, purge logs, add redaction + audit |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Semantic drift in mapping | Phase 1 | Contract tests comparing direct Anthropic vs gateway output |
| Streaming event mismatch | Phase 2 | Replay SSE fixtures; ensure message_stop appears and blocks close |
| Token/limit mismatch | Phase 2 | Golden tests for count_tokens + truncation outcomes |
| Error-shape drift | Phase 1–2 | Snapshot tests for error schema across endpoints |
| Tool-use delta handling | Phase 2 | Tool-use streaming fixtures with partial JSON deltas |
| File handling divergence | Phase 3 | Persisted file retrieval after restart; checksum checks |
| PII leakage | Phase 1–2 | Redaction audit on logs/traces |
| Retry/idempotency gaps | Phase 3 | Idempotency key tests with forced retry scenarios |

## Sources

- OpenAI Responses API Reference (streaming + response object): https://platform.openai.com/docs/api-reference/responses
- OpenAI Responses Streaming Events: https://platform.openai.com/docs/api-reference/responses-streaming
- Anthropic Messages API Reference: https://docs.anthropic.com/en/api/messages
- Anthropic Messages Streaming: https://docs.anthropic.com/en/api/messages-streaming
- Inference from project context + common gateway failure modes (LOW confidence; needs validation)

---
*Pitfalls research for: API compatibility gateway (Anthropic Messages → OpenAI Responses)*
*Researched: 2026-01-25*
