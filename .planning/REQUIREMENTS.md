# Requirements: OpenAI Responses Compatibility Proxy

**Defined:** 2026-01-25
**Core Value:** Claude Code works seamlessly against OpenAI models as if it were talking to Anthropic.

## Milestone v1.0 Requirements

Table-stakes MVP requirements for compatibility parity.

### Core Compatibility

- [ ] **CORE-01**: Proxy accepts Anthropic-style `/v1/messages` requests and maps roles + system content to OpenAI Responses.
- [ ] **CORE-02**: Proxy maps OpenAI Responses back to Anthropic response shape with correct `stop_reason` semantics.
- [ ] **CORE-03**: Proxy returns deterministic error shapes (Anthropic envelope with OpenAI details).

### Streaming + Tool Use

- [ ] **STREAM-01**: `/v1/messages/stream` emits Anthropic-compatible SSE events (message/content block lifecycle).
- [ ] **STREAM-02**: Tool use blocks are emitted in Anthropic format during streaming.
- [ ] **STREAM-03**: `input_json_delta` is accumulated correctly and finalized in tool blocks.

### Token Counting

- [ ] **TOK-01**: `/v1/messages/count_tokens` returns token counts aligned with OpenAI billing.
- [ ] **TOK-02**: Token counting normalizes system/tool content consistently with request mapping.

### Observability

- [ ] **OBS-01**: Structured logs are emitted for requests/responses with PII redaction by default.
- [ ] **OBS-02**: Each request/stream includes a correlation ID in logs.

## Future Requirements (Deferred)

### Differentiators

- **DIFF-01**: Canonical internal schema with explicit adapter layer.
- **DIFF-02**: Debug metadata for mapping discrepancies.
- **DIFF-03**: Replay fixtures for streaming parity.
- **DIFF-04**: Stream-aware logging redaction on deltas.
- **DIFF-05**: Edge-case token counting coverage (multi-tool, mixed content blocks).
- **DIFF-06**: OpenTelemetry-ready tracing hooks.

### Endpoints (Post-MVP)

- **EXT-01**: `/v1/files` API with local storage + metadata.
- **EXT-02**: `/v1/messages/batches` API for batch processing.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Audio / realtime endpoints | HTTP-only and text-focused MVP |
| Vision / image support | Defer to later release |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Pending |
| CORE-02 | Phase 1 | Pending |
| CORE-03 | Phase 1 | Pending |
| STREAM-01 | Phase 4 | Pending |
| STREAM-02 | Phase 4 | Pending |
| STREAM-03 | Phase 4 | Pending |
| TOK-01 | Phase 2 | Pending |
| TOK-02 | Phase 2 | Pending |
| OBS-01 | Phase 3 | Pending |
| OBS-02 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-01-25*
*Last updated: 2026-01-25 after milestone v1.0 definition*
