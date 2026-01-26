# OpenAI Responses Compatibility Proxy

## What This Is

A production-grade compatibility gateway that lets Claude Code (and other Anthropic-style clients) talk to OpenAI Responses. It translates Anthropic Messages API requests, tools, and streaming events into OpenAI Responses while preserving Anthropic semantics and ergonomics for open-source users.

## Core Value

Claude Code works seamlessly against OpenAI models as if it were talking to Anthropic.

## Current State

v1.0 MVP Compatibility shipped on 2026-01-26.

- `/v1/messages` parity (mapping, stop_reason, deterministic error envelopes)
- `/v1/messages/stream` SSE parity with tool_use + input_json_delta
- `/v1/messages/count_tokens` aligned to OpenAI billing with verification harness
- Privacy-first observability (PII redaction + correlation IDs)

## Next Milestone Goals

- Define v1.1 scope and requirements
- Evaluate post-MVP endpoints (/v1/files, /v1/messages/batches)
- Consider tracing hooks (OpenTelemetry-ready)

## Requirements

### Validated

- ✓ /v1/messages provides Anthropic Messages API parity (roles, system, stop_reason) against OpenAI Responses — v1.0
- ✓ /v1/messages/stream streams Anthropic-compatible SSE events with tool_use + input_json_delta behavior — v1.0
- ✓ /v1/messages/count_tokens matches OpenAI billing/token accounting as closely as possible — v1.0
- ✓ Tool schema fidelity and tool_choice semantics preserved end-to-end — v1.0
- ✓ Structured logs are PII-redacted by default — v1.0

### Active

- [ ] Define next milestone requirements (run /gsd-new-milestone)

### Out of Scope

- Audio / realtime endpoints — v1 is HTTP-only and text-focused.
- Vision / image support — defer to later release.
- /v1/files — defer to post-MVP.
- /v1/messages/batches — defer to post-MVP.

## Context

- Open-source users want Claude Code to run against OpenAI models without breaking Anthropic semantics.
- Shipped v1.0 with Python + FastAPI proxy, mapping layers, streaming translator, tiktoken token counting, and privacy-first logging.
- Verification harness compares proxy token counts to OpenAI Responses billing usage.
- Files API should store metadata and content locally with a configurable storage directory (post-MVP).

## Constraints

- **Runtime**: Single binary/CLI — local dev proxy runner is the initial target.
- **Stack**: Python + FastAPI — production-grade HTTP server.
- **Auth**: API key via env var only (`OPENAI_API_KEY`).
- **Reliability**: Prioritize stability and graceful failure handling over raw speed.
- **Observability**: Structured logs, metrics, and tracing required in v1.
- **Security**: PII redaction in logs; no request size limits or rate limiting in MVP.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Anthropic → OpenAI translation only | Keep scope tight and semantics accurate | ✓ Implemented v1.0 |
| Explicit model mapping with env overrides | Default compatibility with flexible overrides | ✓ Implemented v1.0 |
| Hybrid error shape | Anthropic envelope with OpenAI details for debuggability | ✓ Implemented v1.0 |
| Local disk file storage | Simple, deterministic default for CLI | ⚠ Deferred (post-MVP) |
| MVP excludes size limits/rate limiting | Reduce scope to core parity and streaming | ✓ Maintained for v1.0 |

---
*Last updated: 2026-01-26 after v1.0 milestone completion*
