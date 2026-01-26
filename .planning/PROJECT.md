# OpenAI Responses Compatibility Proxy

## What This Is

A production-grade compatibility gateway that lets Claude Code (and other Anthropic-style clients) talk to OpenAI Responses. It translates Anthropic Messages API requests, tools, and streaming events into OpenAI Responses while preserving Anthropic semantics and ergonomics for open-source users.

## Core Value

Claude Code works seamlessly against OpenAI models as if it were talking to Anthropic.

## Current Milestone: v1.0 MVP Compatibility

**Goal:** Ship a minimal, production-grade compatibility layer that supports Claude Code’s core workflows on OpenAI models.

**Target features:**
- /v1/messages with Anthropic → OpenAI translation and error shape parity
- /v1/messages/stream with tool_use + input_json_delta streaming parity
- /v1/messages/count_tokens parity for cost/limit alignment
- PII-redacted structured logging by default

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] /v1/messages provides Anthropic Messages API parity (roles, system, stop_reason) against OpenAI Responses.
- [ ] /v1/messages/stream streams Anthropic-compatible SSE events with tool_use + input_json_delta behavior.
- [ ] /v1/messages/count_tokens matches OpenAI billing/token accounting as closely as possible.
- [ ] Tool schema fidelity and tool_choice semantics preserved end-to-end.
- [ ] Structured logs are PII-redacted by default.

### Out of Scope

- Audio / realtime endpoints — v1 is HTTP-only and text-focused.
- Vision / image support — defer to later release.
- /v1/files — defer to post-MVP.
- /v1/messages/batches — defer to post-MVP.

## Context

- Open-source users want Claude Code to run against OpenAI models without breaking Anthropic semantics.
- MVP scope includes /v1/messages, /v1/messages/stream, /v1/messages/count_tokens.
- Files API should store metadata and content locally with a configurable storage directory.
- Token counting should match OpenAI billing as closely as possible.

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
| Anthropic → OpenAI translation only | Keep scope tight and semantics accurate | — Pending |
| Explicit model mapping with env overrides | Default compatibility with flexible overrides | — Pending |
| Hybrid error shape | Anthropic envelope with OpenAI details for debuggability | — Pending |
| Local disk file storage | Simple, deterministic default for CLI | — Pending |
| MVP excludes size limits/rate limiting | Reduce scope to core parity and streaming | — Pending |

---
*Last updated: 2026-01-25 after milestone v1.0 kickoff*
