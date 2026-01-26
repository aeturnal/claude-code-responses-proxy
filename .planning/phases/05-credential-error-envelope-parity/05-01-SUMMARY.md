---
phase: 05-credential-error-envelope-parity
plan: 01
subsystem: api
tags: [fastapi, sse, anthropic, openai, pytest]

# Dependency graph
requires:
  - phase: 01-core-messages-parity
    provides: Anthropic error envelope helpers and /v1/messages baseline handler
  - phase: 04-streaming-+-tool-use-parity
    provides: /v1/messages/stream SSE handler and error event formatting
provides:
  - Anthropic authentication_error envelopes for missing OPENAI_API_KEY
  - SSE error event parity for missing credential streams
  - Pytest coverage for missing-credential mapping
affects:
  - phase-06-token-count-billing-verification
  - error-envelope-parity

# Tech tracking
tech-stack:
  added: []
  patterns:
    - MissingOpenAIAPIKeyError mapped to Anthropic authentication_error
    - SSE error events emitted for local credential failures

key-files:
  created:
    - tests/test_missing_credentials.py
  modified:
    - src/config.py
    - src/handlers/messages.py
    - src/schema/openai.py
    - src/mapping/anthropic_to_openai.py

key-decisions:
  - "None - followed plan as specified"

patterns-established:
  - "Explicit auth error mapping for missing credentials in HTTP and streaming paths"

# Metrics
duration: 2 min
completed: 2026-01-26
---

# Phase 05 Plan 01: Credential Error Envelope Parity Summary

**Anthropic authentication_error envelopes now return for missing OpenAI API keys across HTTP and SSE paths with pytest coverage.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-26T11:37:38Z
- **Completed:** 2026-01-26T11:40:20Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added MissingOpenAIAPIKeyError and mapped it to Anthropic authentication_error envelopes for /v1/messages.
- Emitted SSE error events with the same envelope when streams fail due to missing credentials.
- Added pytest coverage for missing-key behavior across HTTP and streaming endpoints.

## Task Commits

Each task was committed atomically:

1. **Task 1: Map missing API key to Anthropic auth error (HTTP + SSE)** - `02e2f6c` (fix)
2. **Task 2: Add pytest coverage for missing credential envelopes** - `b7fe903` (test)

**Plan metadata:** _pending_

_Note: TDD tasks may have multiple commits (test → feat → refactor)_

## Files Created/Modified
- `src/config.py` - Introduced MissingOpenAIAPIKeyError for missing credential detection.
- `src/handlers/messages.py` - Returned authentication_error envelopes for HTTP and SSE paths.
- `src/schema/openai.py` - Added FunctionDefinition schema for tool payload compatibility.
- `src/mapping/anthropic_to_openai.py` - Constructed tool payloads using FunctionDefinition.
- `tests/test_missing_credentials.py` - HTTP and streaming tests for missing API key envelopes.

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added missing FunctionDefinition schema for tests**
- **Found during:** Task 1 (pytest verification)
- **Issue:** test_token_counting.py imported FunctionDefinition, but schema lacked it, blocking test collection
- **Fix:** Added FunctionDefinition and updated tool mapping to use the nested function payload
- **Files modified:** src/schema/openai.py, src/mapping/anthropic_to_openai.py
- **Verification:** pytest -q
- **Committed in:** 02e2f6c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Blocking fix required to run verification; no scope creep.

## Issues Encountered
- pytest initially failed due to missing local dependency installs; resolved by installing requirements.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 5 complete, ready for Phase 6 (06-01 token count billing verification).

---
*Phase: 05-credential-error-envelope-parity*
*Completed: 2026-01-26*
