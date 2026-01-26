# Milestones

## v1.0 — MVP Compatibility

**Status:** In progress
**Started:** 2026-01-25
**Goal:** Ship the minimal compatibility layer that lets Claude Code use OpenAI models with core Anthropic semantics.

**Must ship:**
- /v1/messages
- /v1/messages/stream (tool_use + input_json_delta)
- /v1/messages/count_tokens
- PII-redacted structured logging

**Nice to have (defer if needed):**
- /v1/files
- /v1/messages/batches

**Notes:**
- No request size limits or rate limiting in MVP scope.
- Auth remains env var only (`OPENAI_API_KEY`).

**Phases:**
- TBD (roadmap pending)

---
*Milestones initialized: 2026-01-25*
