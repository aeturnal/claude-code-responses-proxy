# Roadmap: OpenAI Responses Compatibility Proxy

## Overview

Deliver a production-grade compatibility proxy that preserves Anthropic Messages semantics on top of OpenAI Responses. The v1.0 roadmap focuses on core request/response parity, token counting alignment, privacy-first observability, and streaming/tool-use parity so Claude Code can run without semantic breaks.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Core Messages Parity** - `/v1/messages` request/response parity with deterministic error shapes.
- [x] **Phase 2: Token Counting Alignment** - `/v1/messages/count_tokens` aligned with OpenAI billing semantics.
- [x] **Phase 3: Privacy-First Observability** - PII-redacted structured logs with correlation IDs.
- [ ] **Phase 4: Streaming + Tool Use Parity** - `/v1/messages/stream` SSE parity including tool_use and input_json_delta.

## Phase Details

### Phase 1: Core Messages Parity
**Goal**: Users can call `/v1/messages` and receive Anthropic-compatible responses and errors.
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03
**Success Criteria** (what must be TRUE):
  1. User can send an Anthropic-style `/v1/messages` request and receive a valid Anthropic response shape.
  2. Response `stop_reason` matches Anthropic semantics for typical completion and stop conditions.
  3. When upstream errors occur, user receives a deterministic Anthropic-style error envelope with OpenAI details included.
**Plans**: 4 plans

Plans:
- [x] 01-01-PLAN.md — Scaffold dependencies, config, and OpenAI transport
- [x] 01-02-PLAN.md — Define request schemas + Anthropic→OpenAI mapping
- [x] 01-03-PLAN.md — Normalize OpenAI responses + stop_reason derivation
- [x] 01-04-PLAN.md — Implement /v1/messages handler + error envelopes

### Phase 2: Token Counting Alignment
**Goal**: Users can preflight token usage with Anthropic-compatible counting aligned to OpenAI billing.
**Depends on**: Phase 1
**Requirements**: TOK-01, TOK-02
**Success Criteria** (what must be TRUE):
  1. User can call `/v1/messages/count_tokens` and receive token counts aligned to OpenAI billing behavior.
  2. System and tool content in the request are counted consistently with the mapping used by `/v1/messages`.
**Plans**: 1 plan

Plans:
- [x] 02-01-PLAN.md — Implement token counting utilities and /v1/messages/count_tokens endpoint

### Phase 3: Privacy-First Observability
**Goal**: Operators can observe requests and responses without exposing PII.
**Depends on**: Phase 1
**Requirements**: OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. Operator can see structured logs for requests and responses with PII redacted by default.
  2. Each request/response log entry includes a correlation ID that can be used to trace a single interaction.
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — Add observability config, logging setup, and correlation ID middleware
- [x] 03-02-PLAN.md — Redaction utilities + request/response logging with correlation propagation

### Phase 4: Streaming + Tool Use Parity
**Goal**: Users can stream Anthropic-compatible SSE events with tool_use and input_json_delta parity.
**Depends on**: Phase 1, Phase 3
**Requirements**: STREAM-01, STREAM-02, STREAM-03
**Success Criteria** (what must be TRUE):
  1. User can open `/v1/messages/stream` and receive Anthropic-compatible message/content block lifecycle events in order.
  2. Tool use blocks stream in Anthropic format and complete tool blocks are emitted at block stop.
  3. `input_json_delta` events are accumulated during streaming and appear as finalized input JSON in tool blocks.
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — Add OpenAI streaming transport + SSE parsing
- [ ] 04-02-PLAN.md — Translate OpenAI stream events to Anthropic SSE + tool_use deltas
- [ ] 04-03-PLAN.md — Implement /v1/messages/stream endpoint + logging/error handling

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Messages Parity | 4/4 | Complete | 2026-01-26 |
| 2. Token Counting Alignment | 1/1 | Complete | 2026-01-26 |
| 3. Privacy-First Observability | 2/2 | Complete | 2026-01-26 |
| 4. Streaming + Tool Use Parity | 1/3 | In progress | 2026-01-26 |
