# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-25)

**Core value:** Claude Code works seamlessly against OpenAI models as if it were talking to Anthropic.
**Current focus:** Milestone v1.0 MVP Compatibility

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-01-25 — Milestone v1.0 started

## Decisions Made

- MVP endpoints: /v1/messages, /v1/messages/stream, /v1/messages/count_tokens.
- Tool use parity required, including input_json_delta streaming.
- PII-redacted structured logging by default.
- No request size limits or rate limiting in MVP.

## Blockers / Concerns

- None logged

---
*State initialized: 2026-01-25*
