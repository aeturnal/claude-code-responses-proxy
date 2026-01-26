---
phase: 01-core-messages-parity
verified: 2026-01-26T03:51:30Z
status: passed
score: 8/8 must-haves verified
human_verification:
  - test: "POST /v1/messages returns Anthropic response"
    expected: "Response body includes type=message, role=assistant, content blocks, stop_reason"
    why_human: "Requires running the API and observing runtime output"
  - test: "Upstream OpenAI error maps to Anthropic envelope"
    expected: "Non-2xx upstream returns type=error with error.openai populated and matching HTTP status"
    why_human: "Requires live upstream call or stubbed failure during server run"
  - test: "Validation errors map to invalid_request_error"
    expected: "Invalid payload returns 400 with type=error and error.type=invalid_request_error"
    why_human: "FastAPI request validation behavior requires runtime verification"
---

# Phase 1: Core Messages Parity Verification Report

**Phase Goal:** Users can call `/v1/messages` and receive Anthropic-compatible responses and errors.
**Verified:** 2026-01-26T03:51:30Z
**Status:** passed
**Re-verification:** Yes — human verification completed

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Operator can configure OpenAI credentials/base URL via env vars without code changes | ✓ VERIFIED | `src/config.py` loads `OPENAI_API_KEY` + `OPENAI_BASE_URL` and enforces key via `require_openai_api_key()` (lines 10-19). |
| 2 | Given an Anthropic model name, proxy deterministically resolves the OpenAI model used upstream | ✓ VERIFIED | `resolve_openai_model` uses `MODEL_MAP_JSON` or default model (lines 36-43). |
| 3 | Anthropic `/v1/messages` payloads can be normalized into OpenAI Responses requests | ✓ VERIFIED | `map_anthropic_request_to_openai` builds `OpenAIResponsesRequest` with mapped input/tools/max_tokens (lines 81-116). |
| 4 | System instructions are mapped to OpenAI instructions (not injected as system-role messages) | ✓ VERIFIED | `_system_to_instructions` produces `instructions` string, and mapping assigns `instructions` (lines 27-41, 109-115). |
| 5 | OpenAI Responses outputs are normalized into Anthropic message content blocks | ✓ VERIFIED | `map_openai_response_to_anthropic` converts message and function_call output to Anthropic content blocks (lines 40-71). |
| 6 | `stop_reason` is derived deterministically from OpenAI response status/details | ✓ VERIFIED | `derive_stop_reason` maps function_call / incomplete reasons / default (lines 22-37). |
| 7 | User can POST `/v1/messages` and receive Anthropic-compatible response shape | ✓ VERIFIED | FastAPI route `POST /v1/messages` returns `map_openai_response_to_anthropic` output (lines 39-61). |
| 8 | Upstream OpenAI errors return deterministic Anthropic error envelopes | ✓ VERIFIED | Handler catches `OpenAIUpstreamError` and returns `build_anthropic_error` via `JSONResponse` (lines 46-59) and `build_anthropic_error` builds envelope (lines 26-45). |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `requirements.txt` | FastAPI/httpx runtime dependencies | ✓ VERIFIED | 6 lines; includes `fastapi`, `httpx`, `uvicorn`, `pydantic`, `pytest`. |
| `src/config.py` | OpenAI config + model resolution | ✓ VERIFIED | 44 lines; `resolve_openai_model`, env var config, no stubs. |
| `src/transport/openai_client.py` | HTTP client for `/v1/responses` | ✓ VERIFIED | 41 lines; `create_openai_response` + `OpenAIUpstreamError` implemented. |
| `src/schema/anthropic.py` | Anthropic Messages request models | ✓ VERIFIED | 62 lines; `MessagesRequest` model defined. |
| `src/schema/openai.py` | OpenAI Responses request models | ✓ VERIFIED | 66 lines; `OpenAIResponsesRequest` model defined. |
| `src/mapping/anthropic_to_openai.py` | Request mapping function | ✓ VERIFIED | 118 lines; `map_anthropic_request_to_openai` implemented and used. |
| `src/mapping/openai_to_anthropic.py` | Response mapping + stop_reason logic | ✓ VERIFIED | 72 lines; `map_openai_response_to_anthropic`, `derive_stop_reason`. |
| `tests/test_openai_to_anthropic.py` | Stop-reason and tool_use mapping tests | ✓ VERIFIED | 75 lines; tests reference `derive_stop_reason`. |
| `src/handlers/messages.py` | `/v1/messages` FastAPI route | ✓ VERIFIED | 62 lines; `router` exported with POST handler. |
| `src/errors/anthropic_error.py` | Anthropic error envelope builder | ✓ VERIFIED | 47 lines; `build_anthropic_error` implemented. |
| `src/app.py` | FastAPI app wiring | ✓ VERIFIED | 29 lines; `FastAPI()` with router inclusion and validation handler. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `src/transport/openai_client.py` | `src/config.py` | base URL + API key resolution | ✓ WIRED | Imports `OPENAI_BASE_URL` + `require_openai_api_key`. |
| `src/mapping/anthropic_to_openai.py` | `src/schema/anthropic.py` | typed request parsing | ✓ WIRED | Imports `MessagesRequest`, `Message`, `TextBlock`, `ToolResultBlock`. |
| `src/mapping/anthropic_to_openai.py` | `src/schema/openai.py` | OpenAI request assembly | ✓ WIRED | Constructs `OpenAIResponsesRequest`, `InputMessageItem`, `FunctionTool`. |
| `src/handlers/messages.py` | `src/mapping/anthropic_to_openai.py` | request mapping | ✓ WIRED | `map_anthropic_request_to_openai` used for payload. |
| `src/handlers/messages.py` | `src/transport/openai_client.py` | OpenAI Responses call | ✓ WIRED | `create_openai_response` awaited. |
| `src/handlers/messages.py` | `src/mapping/openai_to_anthropic.py` | response mapping | ✓ WIRED | `map_openai_response_to_anthropic` used on success. |
| `src/handlers/messages.py` | `src/errors/anthropic_error.py` | error envelope builder | ✓ WIRED | `build_anthropic_error` used for upstream errors. |
| `src/app.py` | `src/handlers/messages.py` | router wiring | ✓ WIRED | `app.include_router(messages_router)`.
| `tests/test_openai_to_anthropic.py` | `src/mapping/openai_to_anthropic.py` | pytest verification | ✓ WIRED | Tests import and exercise mapping + stop_reason. |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
| --- | --- | --- |
| CORE-01 | ✓ COMPLETE | Endpoint behavior validated via live POST to /v1/messages. |
| CORE-02 | ✓ COMPLETE | stop_reason observed in live response for valid request. |
| CORE-03 | ✓ COMPLETE | Error envelope confirmed with invalid API key (401). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `src/config.py` | 26 | `return {}` | ℹ️ Info | Valid empty model map when env var absent. |
| `src/errors/anthropic_error.py` | 14 | `return {}` | ℹ️ Info | Valid empty dict when OpenAI error is not dict. |

### Human Verification Required

#### 1. POST /v1/messages returns Anthropic response

**Test:** Run the server and POST a minimal Anthropic Messages payload.
**Expected:** Response body includes `type=message`, `role=assistant`, `content` array with text blocks, and `stop_reason`.
**Why human:** Requires running the API and observing runtime output.

#### 2. Upstream OpenAI error maps to Anthropic envelope

**Test:** Configure an invalid `OPENAI_API_KEY` and POST `/v1/messages`.
**Expected:** HTTP status mirrors upstream, response includes `{type: "error"}` and `error.openai` payload.
**Why human:** Requires live upstream call or stubbed failure during server run.

#### 3. Validation errors map to invalid_request_error

**Test:** POST `/v1/messages` with an invalid payload (missing required fields).
**Expected:** HTTP 400 and `error.type=invalid_request_error`.
**Why human:** FastAPI validation behavior must be exercised in runtime.

### Gaps Summary

No structural gaps found in code. Endpoint behavior and error semantics require runtime confirmation.

---

_Verified: 2026-01-25T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
