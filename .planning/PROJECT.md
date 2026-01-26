# OpenAI Responses Compatibility Proxy

## What This Is

A production-grade compatibility gateway that lets Claude Code (and other Anthropic-style clients) talk to OpenAI Responses. It translates Anthropic Messages API requests, tools, and streaming events into OpenAI Responses while preserving Anthropic semantics and ergonomics for open-source users.

## Core Value

Claude Code works seamlessly against OpenAI models as if it were talking to Anthropic.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Translate Anthropic Messages API requests to OpenAI Responses with semantic parity (roles, system, stop_reason).
- [ ] Stream Anthropic-compatible SSE events, including tool_use and input_json_delta behavior.
- [ ] Preserve tool schema fidelity and tool_choice semantics end-to-end.

### Out of Scope

- Audio / realtime endpoints — v1 is HTTP-only and text-focused.
- Vision / image support — defer to later release.

## Context

- Open-source users want Claude Code to run against OpenAI models without breaking Anthropic semantics.
- v1 scope includes /v1/messages, /v1/messages/stream, /v1/messages/count_tokens, /v1/messages/batches, /v1/files.
- Files API should store metadata and content locally with a configurable storage directory.
- Token counting should match OpenAI billing as closely as possible.

## Constraints

- **Runtime**: Single binary/CLI — local dev proxy runner is the initial target.
- **Stack**: Python + FastAPI — production-grade HTTP server.
- **Auth**: API key via env var only (`OPENAI_API_KEY`).
- **Reliability**: Prioritize stability and graceful failure handling over raw speed.
- **Observability**: Structured logs, metrics, and tracing required in v1.
- **Security**: Request size limits and PII redaction in logs.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Anthropic → OpenAI translation only | Keep scope tight and semantics accurate | — Pending |
| Explicit model mapping with env overrides | Default compatibility with flexible overrides | — Pending |
| Hybrid error shape | Anthropic envelope with OpenAI details for debuggability | — Pending |
| Local disk file storage | Simple, deterministic default for CLI | — Pending |

---
*Last updated: 2026-01-25 after initialization*
