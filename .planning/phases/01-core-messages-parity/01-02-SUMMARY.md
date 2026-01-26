---
phase: 01-core-messages-parity
plan: 02
subsystem: api
tags: [pydantic, anthropic-messages, openai-responses, mapping]

# Dependency graph
requires:
  - phase: 01-core-messages-parity/01-01
    provides: OpenAI transport/config foundation for model resolution
provides:
  - Anthropic Messages request schemas
  - OpenAI Responses request schemas
  - Deterministic Anthropic-to-OpenAI request mapping
affects:
  - 01-03 response normalization
  - 01-04 /v1/messages handler

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pydantic request schemas for API boundary validation
    - Deterministic request mapping with explicit unsupported-block errors

key-files:
  created:
    - src/schema/__init__.py
    - src/schema/anthropic.py
    - src/schema/openai.py
    - src/mapping/__init__.py
    - src/mapping/anthropic_to_openai.py
  modified: []

key-decisions:
  - "None - followed plan as specified"

patterns-established:
  - "Schema-first request validation using Pydantic models"
  - "System instructions mapped to OpenAI instructions field"

# Metrics
duration: 3 min
completed: 2026-01-26
---

# Phase 01 Plan 02: Request Schema + Mapping Summary

**Pydantic schemas for Anthropic messages and OpenAI responses with deterministic request translation including tools and max token mapping.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-26T03:16:06Z
- **Completed:** 2026-01-26T03:19:56Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Defined Anthropic Messages request schema with content blocks, tools, and tool_choice.
- Added OpenAI Responses request schema for input messages and function tools.
- Implemented deterministic mapping with system instructions and max tokens translation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define Anthropic Messages request models** - `891fdfe` (feat)
2. **Task 2: Implement OpenAI request schema + request mapping** - `d1a42f2` (feat)

**Plan metadata:** _pending_

_Note: TDD tasks may have multiple commits (test → feat → refactor)_

## Files Created/Modified
- `src/schema/anthropic.py` - Anthropic Messages request models and content blocks.
- `src/schema/openai.py` - OpenAI Responses request models for input and tools.
- `src/mapping/anthropic_to_openai.py` - Mapping from Anthropic requests to OpenAI payloads.
- `src/schema/__init__.py` - Schema package initializer.
- `src/mapping/__init__.py` - Mapping package initializer.

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added package initializers for schema/mapping imports**
- **Found during:** Task 1 (Define Anthropic Messages request models)
- **Issue:** New schema/mapping modules needed package initializers for reliable imports
- **Fix:** Added __init__.py files in src/schema and src/mapping
- **Files modified:** src/schema/__init__.py, src/mapping/__init__.py
- **Verification:** Module imports succeed in task verify commands
- **Commit:** 891fdfe (schema) and d1a42f2 (mapping)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Added required packaging for imports; no scope change.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Ready for 01-03 response normalization plan.

---
*Phase: 01-core-messages-parity*
*Completed: 2026-01-26*
