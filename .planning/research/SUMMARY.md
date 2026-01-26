# Project Research Summary

**Project:** OpenAI Responses Compatibility Proxy
**Domain:** LLM API compatibility gateway (Anthropic Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Executive Summary

This project is a compatibility proxy that lets Anthropic Messages clients (Claude Code) talk to OpenAI Responses without breaking Anthropic semantics. Experts build this by isolating request/response mapping behind a canonical model, translating streaming SSE events in real time, and enforcing privacy‑first observability so logs and traces never leak user content. The stack should be a lightweight ASGI service (FastAPI + Uvicorn) with the OpenAI SDK for upstream calls and explicit SSE translation to reconstruct Anthropic’s `message_*` and `content_block_*` event flow.

The recommended approach is to prioritize strict parity for `/v1/messages`, `/v1/messages/stream`, and `/v1/messages/count_tokens` first, then layer in optional compatibility modes and debug metadata after the core translation is stable. The biggest risks are streaming event translation (especially `input_json_delta`) and tool call correlation drift; both require deliberate streaming transducer logic, per‑tool buffers, and replayable fixtures to verify ordering and completion semantics. Privacy risks are the other major concern—redaction must be centralized and applied across all streaming/error paths from day one.

## Key Findings

### Recommended Stack

Build a minimal Python 3.9+ ASGI proxy using FastAPI + Uvicorn, the OpenAI Python SDK for Responses, and sse‑starlette for SSE streaming. Use structlog + orjson for structured, redacted logs and OpenTelemetry (SDK + OTLP exporter) for tracing. The OTel FastAPI/httpx auto‑instrumentation packages are pre‑release—consider manual spans if stability is a concern.

**Core technologies:**
- **Python 3.9+**: runtime compatibility with FastAPI/OpenAI SDK.
- **FastAPI 0.128.0**: high‑throughput JSON API with typed request validation.
- **Uvicorn 0.40.0**: ASGI server suitable for streaming.
- **OpenAI SDK 2.15.0**: upstream Responses + streaming support.
- **sse‑starlette 3.2.0**: SSE helper for `/v1/messages/stream`.
- **tiktoken 0.12.0**: token counting support for `/count_tokens`.
- **structlog 25.5.0 + orjson 3.11.5**: structured, fast JSON logging.
- **OpenTelemetry SDK + OTLP exporter 1.39.1**: vendor‑neutral tracing.

### Expected Features

The proxy must match Anthropic’s Messages schema and streaming semantics, including tool use blocks and `input_json_delta`. Token counting and Anthropic error shape parity are required to keep Claude Code stable. Differentiators are optional debug mapping metadata and compatibility strictness modes; defer complex APIs like `/v1/files` and `/v1/messages/batches` until after validation.

**Must have (table stakes):**
- `/v1/messages` request/response parity — schema, roles, system, tools, tool_choice.
- `/v1/messages/stream` SSE parity — correct event sequence + `input_json_delta`.
- Tool use block mapping — `tool_use` + `tool_result` round‑trip.
- `/v1/messages/count_tokens` — token preflight alignment.
- Error shape parity — Anthropic‑style error envelope and stream error events.
- PII‑redacted structured logging by default.

**Should have (competitive):**
- Compatibility strictness modes (strict vs permissive).
- Opt‑in debug mapping metadata for troubleshooting.

**Defer (v2+):**
- `/v1/files` and `/v1/messages/batches` (storage and batch semantics).

### Architecture Approach

Use a canonical internal model with dedicated adapters for request/response mapping and a streaming transducer that incrementally rebuilds Anthropic SSE events from OpenAI stream events. Keep mapping logic out of HTTP handlers for testability and apply redaction at the logging sink so error and streaming paths are always protected.

**Major components:**
1. **API layer** — routes `/v1/messages`, `/stream`, `/count_tokens` with validation.
2. **Adapters + canonical model** — Claude→canonical→OpenAI mapping and back.
3. **Streaming transducer** — SSE event translation + `input_json_delta` buffering.
4. **Upstream clients** — OpenAI Responses + input_tokens endpoint calls.
5. **Observability + redaction** — structured logs, traces, metrics with PII scrubbing.

### Critical Pitfalls

1. **Streaming event translation mismatch** — reconstruct full Anthropic event sequence with explicit start/stop; validate via replay fixtures.
2. **`input_json_delta` mishandling** — buffer per‑tool deltas, parse only at `content_block_stop`.
3. **Tool call correlation drift** — maintain deterministic ID mapping between OpenAI output items and Anthropic tool_use IDs.
4. **Incorrect stream termination** — emit `message_stop` only after all blocks close; map incomplete states to errors.
5. **Redaction gaps** — centralize redaction for success, error, and streaming paths to prevent PII leakage.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Core Parity (non‑stream + safety)
**Rationale:** Canonical models, mapping, error shape, and redaction are prerequisites for any endpoint and mitigate the highest privacy risk early.
**Delivers:** `/v1/messages` parity, `/v1/messages/count_tokens`, error translation, redacted logging.
**Addresses:** Messages schema parity, count_tokens, error shape, PII‑redacted logs.
**Avoids:** Redaction gaps, raw payload logging, mixing mapping logic into handlers.

### Phase 2: Streaming + Tool‑Use Parity
**Rationale:** Streaming and tool use are the hardest dependencies and the core risk to Claude Code UX; they should be built once the base mapping is stable.
**Delivers:** `/v1/messages/stream` SSE translator, `input_json_delta` handling, tool_use/tool_result streaming parity.
**Uses:** sse‑starlette, OpenAI SDK streaming; streaming transducer architecture.
**Avoids:** Event ordering mismatch, tool delta parse errors, missing `message_stop`.

### Phase 3: Hardening + DX
**Rationale:** After parity works, add operational features and optional differentiators without destabilizing core behavior.
**Delivers:** strict/permissive modes, debug mapping metadata, proxy buffering safeguards, observability tuning.
**Addresses:** Differentiators + deployment risks (SSE buffering) + performance traps.

### Phase Ordering Rationale

- Mapping + error parity are foundational; streaming builds on canonical models and stable responses.
- Tool‑use streaming depends on the streaming transducer and per‑tool buffers.
- Differentiators and deployment hardening should not block core parity validation.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Streaming event mapping across OpenAI→Anthropic semantics; needs fixture design and SSE edge cases.
- **Phase 3:** Deployment proxy configuration (buffering/flush behavior) and observability costs at scale.

Phases with standard patterns (skip research‑phase):
- **Phase 1:** FastAPI request validation, canonical mapping patterns, and structured logging are well‑documented.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified via PyPI and standard ASGI stack. |
| Features | MEDIUM | Based on official Anthropic/OpenAI docs, but Claude Code‑specific expectations need validation. |
| Architecture | MEDIUM | Standard proxy patterns; streaming transducer details are implementation‑sensitive. |
| Pitfalls | MEDIUM | Derived from doc‑implied mismatches and common SSE failures; needs integration testing. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Streaming event mapping edge cases:** Validate against real Claude Code clients and recorded OpenAI streams; add replay fixtures early.
- **Token counting fidelity:** Confirm OpenAI input token endpoint behavior vs Anthropic count_tokens semantics.
- **Tool ID correlation strategy:** Specify deterministic mapping rules for multi‑tool streams and cross‑event indexing.
- **Pre‑release OTel instrumentation:** Decide between manual spans or pre‑release packages before production.
- **Proxy buffering config:** Validate SSE behavior through actual deployment proxy/lb settings.

## Sources

### Primary (HIGH confidence)
- https://docs.anthropic.com/en/api/messages — request/response schema expectations
- https://docs.anthropic.com/en/api/messages-streaming — SSE event flow + input_json_delta
- https://docs.anthropic.com/en/api/messages-count-tokens — count_tokens behavior
- https://platform.openai.com/docs/api-reference/responses — Responses API behavior
- https://platform.openai.com/docs/api-reference/responses-streaming — OpenAI streaming event types
- https://pypi.org/project/fastapi/ — version 0.128.0
- https://pypi.org/project/uvicorn/ — version 0.40.0
- https://pypi.org/project/openai/ — version 2.15.0

### Secondary (MEDIUM confidence)
- https://pypi.org/project/sse-starlette/ — SSE helper implementation
- https://pypi.org/project/tiktoken/ — tokenizer implementation
- https://pypi.org/project/structlog/ — structured logging
- https://pypi.org/project/orjson/ — fast JSON encoding
- https://pypi.org/project/opentelemetry-sdk/ — tracing SDK
- https://pypi.org/project/opentelemetry-exporter-otlp/ — OTLP exporter
- https://pypi.org/project/opentelemetry-instrumentation-fastapi/ — pre‑release auto‑instrumentation
- https://pypi.org/project/opentelemetry-instrumentation-httpx/ — pre‑release auto‑instrumentation

---
*Research completed: 2026-01-25*
*Ready for roadmap: yes*
