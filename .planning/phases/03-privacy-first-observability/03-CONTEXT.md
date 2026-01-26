# Phase 3: Privacy-First Observability - Context

**Gathered:** 2026-01-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Add structured logging for requests/responses with PII redaction by default and correlation IDs for tracing. This phase does not add new endpoints or streaming behavior.

</domain>

<decisions>
## Implementation Decisions

### Log schema + fields
- Emit both request and response logs.
- Include redacted content fields rather than metadata-only or hashes.
- Include tool definitions and tool calls, but redacted.
- Include timing/latency and token usage fields.

### PII redaction rules
- Redact all content fields by default.
- Redaction style: replace detected spans with `[REDACTED]`.
- Provide a debug override via environment flag to reduce redaction (for local dev).
- When in doubt for unstructured text, redact anyway (conservative).

### Correlation ID behavior
- Generate a correlation ID when missing; preserve incoming ID when provided.
- Correlation ID appears in logs only (not in responses).
- Header name: `x-correlation-id`.

### Log destinations + format
- Emit logs to both stdout and file.
- Log format: pretty JSON.
- Logging is opt-in via environment flag.

### Claude's Discretion
- Whether correlation ID is forwarded to upstream OpenAI calls.
- Whether error logs are separated from info logs (stderr or separate file).

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-privacy-first-observability*
*Context gathered: 2026-01-26*
