---
phase: 02-token-counting-alignment
plan: 01
subsystem: api
tags: [tiktoken, fastapi, token-counting, openai, anthropic]

# Dependency graph
requires:
  - phase: 01-core-messages-parity
    provides: Anthropic-to-OpenAI request normalization and /v1/messages mapping
provides:
  - OpenAI-aligned token counting utilities with fallback encoding
  - /v1/messages/count_tokens endpoint returning input_tokens
  - Token counting tests covering instructions, tools, and unknown models
affects:
  - 03-privacy-first-observability
  - 04-streaming-tool-use-parity

# Tech tracking
tech-stack:
  added: [tiktoken]
  patterns:
    - Shared normalization via map_anthropic_request_to_openai
    - OpenAI cookbook token counting with fallback encoding

key-files:
  created:
    - src/token_counting/openai_count.py
    - src/handlers/count_tokens.py
    - tests/test_token_counting.py
  modified:
    - requirements.txt
    - src/schema/anthropic.py
    - src/app.py

key-decisions:
  - "None - followed plan as specified"

patterns-established:
  - "OpenAI-aligned message + tool token counting with model fallback"
  - "Count tokens endpoint reuses shared normalization pipeline"

# Metrics
duration: 4 min
completed: 2026-01-26
---

# Phase 2 Plan 1: Token Counting Alignment Summary

**OpenAI-aligned token counting via tiktoken with a /v1/messages/count_tokens endpoint and tool/instruction coverage.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-01-26T04:19:02Z
- **Completed:** 2026-01-26T04:23:27Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added OpenAI-aligned token counting utilities with model fallback and tool schema accounting.
- Implemented /v1/messages/count_tokens endpoint reusing shared Anthropic→OpenAI normalization.
- Added tests covering base messages, instructions, tools, and unknown-model fallback.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add OpenAI-aligned token counting utilities + tests** - `9f2f6cd` (feat)
2. **Task 2: Implement /v1/messages/count_tokens endpoint** - `5baf93d` (feat)

**Plan metadata:** _pending_

## Files Created/Modified
- `src/token_counting/openai_count.py` - OpenAI-aligned token counting helpers with fallback encoding.
- `tests/test_token_counting.py` - Token counting coverage for base, instructions, tools, and unknown models.
- `src/handlers/count_tokens.py` - /v1/messages/count_tokens handler using shared normalization.
- `requirements.txt` - Adds tiktoken dependency.
- `src/schema/anthropic.py` - Adds CountTokensResponse schema.
- `src/app.py` - Wires count_tokens router into FastAPI app.

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 2 is complete. Ready to move to Phase 3 (Privacy-First Observability).

---
*Phase: 02-token-counting-alignment*
*Completed: 2026-01-26*
