# Project Research Summary

**Project:** OpenAI Responses Compatibility Proxy
**Domain:** API compatibility gateway/proxy (Anthropic Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Executive Summary

This project is a production-grade API compatibility gateway that lets Anthropic Messages clients (notably Claude Code) talk to OpenAI Responses with minimal behavioral drift. Expert implementations in this domain use an ASGI gateway with a strict middleware pipeline, a canonical internal schema, and explicit adapter layers to translate requests, responses, and streaming events while enforcing limits, auth, and observability.

The recommended approach is a Python 3.12 + FastAPI/HTTPX stack with structured logging and OpenTelemetry, centered around a canonical model + adapters for Anthropic ↔ OpenAI mappings and a stream translation layer for SSE parity. MVP should prioritize semantic fidelity, deterministic error mapping, and streaming correctness; optional enhancements (files, batches, routing, PII redaction) can follow once core compatibility is stable.

The key risks are semantic drift in message/tool mappings, streaming event mismatches, and token/limit inconsistencies. Mitigation requires explicit mapping rules, contract tests against direct Anthropic behavior, stream replay fixtures, and policy-driven limit normalization. Observability must be redacted by default to avoid PII leakage.

## Key Findings

### Recommended Stack

The stack favors a modern async Python gateway with FastAPI, HTTPX, and Pydantic v2 for typed schema translation and compatibility endpoints, plus OpenTelemetry and Prometheus metrics for production observability. Streaming support (SSE) and high-throughput JSON serialization are critical for real-time responses and tool use flows. See `.planning/research/STACK.md` for full versions and rationale.

**Core technologies:**
- **Python 3.12.x**: runtime — strong async ecosystem support and broad library compatibility.
- **FastAPI 0.128.0**: API framework — OpenAPI generation + Pydantic v2 for schema-driven validation.
- **Uvicorn 0.40.0**: ASGI server — standard production-grade async server.
- **HTTPX 0.28.1**: upstream HTTP client — async streaming and timeouts for proxying.
- **Pydantic 2.12.5**: schema validation — enforce canonical and mapped schemas.
- **OpenTelemetry SDK 1.39.1**: tracing/metrics — reliability-first telemetry.
- **structlog 25.5.0**: structured logging — supports redaction and correlation.
- **orjson 3.11.5**: fast JSON — throughput for large/streamed payloads.
- **sse-starlette 3.2.0**: SSE streaming — `/v1/messages/stream` parity.

### Expected Features

Core expectations revolve around OpenAI-compatible endpoints, faithful schema translation, and streaming parity. Differentiators emphasize semantic fidelity to Anthropic Messages and enterprise-grade observability. See `.planning/research/FEATURES.md` for full prioritization.

**Must have (table stakes):**
- OpenAI-compatible HTTP surface (base_url + client interoperability).
- Core endpoint coverage mapped to Anthropic Messages (`/v1/messages`, stream, count_tokens).
- Streaming (SSE) with faithful event translation.
- Schema translation for requests + responses.
- Deterministic error mapping + stable status codes.
- Auth via env key, request size limits, logging + metrics.

**Should have (competitive):**
- Semantic fidelity to Anthropic Messages (tool use, content blocks, system rules).
- Hybrid error shape (compatibility + upstream detail).
- PII redaction in logs by default.
- Token accounting that matches Anthropic behavior.
- Compatibility test suite / self-test CLI.
- Optional routing/fallback.

**Defer (v2+):**
- Full OpenAI surface parity (audio/image).
- Advanced policy/guardrail engine.
- Multi-tenant billing/budget controls (if SaaS).

### Architecture Approach

Adopt an API gateway pattern with a strict middleware pipeline (auth, limits, validation, redaction) and a canonical model + adapter layer for translation. Streaming should be handled via incremental transform adapters rather than buffering. See `.planning/research/ARCHITECTURE.md` for reference structure and data flows.

**Major components:**
1. **API layer + middleware** — routing, auth, rate/size limits, request validation.
2. **Canonical schema + adapters** — explicit Anthropic ↔ OpenAI mappings with tests.
3. **Upstream connector + streaming adapter** — HTTPX client, retries, SSE translation.
4. **Observability** — structured logs, metrics, tracing with redaction.
5. **Storage + background jobs** — local files, batch processing (post-MVP).

### Critical Pitfalls

1. **Semantic drift in message/content mapping** — avoid by canonical schema + contract tests.
2. **Streaming event mismatch** — avoid by explicit SSE translator + replay fixtures.
3. **Token/limit semantics mismatch** — avoid by limit normalization + count_tokens tests.
4. **Error-shape drift** — avoid by strict mapping matrix and streaming error handling.
5. **PII leakage in logs/metrics** — avoid by centralized redaction middleware.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Core Compatibility MVP
**Rationale:** Everything depends on canonical mapping and stable error/limit behavior; this validates the gateway’s core promise. 
**Delivers:** `/v1/messages`, deterministic error mapping, request validation/limits, auth via env, structured logs + metrics, canonical model + adapters, contract tests.
**Addresses:** OpenAI-compatible surface, schema translation, auth, error mapping, observability, request size limits.
**Avoids:** Semantic drift, error-shape drift, PII leakage (baseline redaction).

### Phase 2: Streaming + Token Parity
**Rationale:** Streaming and token semantics are highest risk and critical for Claude Code parity; must be isolated with dedicated fixtures and tests.
**Delivers:** `/v1/messages/stream`, SSE translation adapter, tool-use delta handling, `/v1/messages/count_tokens`, truncation/limit normalization, stream-aware redaction.
**Uses:** HTTPX streaming + sse-starlette; canonical model + stream adapter.
**Implements:** Streaming Translation Adapter pattern + token policy map.
**Avoids:** Streaming mismatch, tool-use delta errors, token/limit mismatch.

### Phase 3: Files, Batches, Reliability Enhancements
**Rationale:** File storage and batch jobs depend on stable core semantics and are operationally heavier; reliability controls are needed after traffic grows.
**Delivers:** `/v1/files` with local storage + metadata, `/v1/messages/batches`, idempotency keys, retry policy, optional routing/fallback.
**Addresses:** File handling semantics, retry/idempotency gaps, optional availability improvements.
**Avoids:** File ID instability, duplicate responses on retry.

### Phase Ordering Rationale

- Canonical mapping and error normalization are prerequisites for all endpoints and streaming parity.
- Streaming/tool-use translation is complex and should be isolated after non-stream baseline is stable.
- Files/batches rely on storage and background jobs best layered once core API behavior is verified.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Streaming event translation and tool-use deltas require fixture-driven validation and spec reconciliation.
- **Phase 3:** Files/batches semantics and idempotency require policy decisions and migration strategy.

Phases with standard patterns (skip research-phase):
- **Phase 1:** API gateway middleware + canonical model is well-documented and broadly understood.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions grounded in PyPI releases and common ASGI patterns. |
| Features | MEDIUM | Based on competitor docs and domain inference; needs validation with target users. |
| Architecture | MEDIUM | Standard gateway patterns; not yet validated against real traffic. |
| Pitfalls | MEDIUM | Some items inferred from domain experience; requires testing. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **Streaming semantics parity:** Validate with real OpenAI Responses streaming traces and Claude Code expectations.
- **Token counting rules:** Confirm exact token accounting alignment and truncation semantics.
- **File semantics:** Define retention, ID stability, and metadata mapping policies before implementing `/v1/files`.
- **Routing/fallback policy:** Decide when and how to surface fallback behavior without breaking compatibility.

## Sources

### Primary (HIGH confidence)
- https://pypi.org/project/fastapi/ — FastAPI versions and support.
- https://pypi.org/project/httpx/ — async HTTP client for upstream calls.
- https://pypi.org/project/pydantic/ — schema validation v2.
- https://platform.openai.com/docs/api-reference/responses — OpenAI Responses API.
- https://docs.anthropic.com/en/docs/api/messages — Anthropic Messages API.
- https://fastapi.tiangolo.com/advanced/middleware/ — ASGI middleware pipeline.

### Secondary (MEDIUM confidence)
- https://docs.litellm.ai/ — proxy feature expectations (rate limits, logging, routing).
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html — compatibility surface expectations.
- https://localai.io/ — OpenAI-compatible server patterns.
- https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/arch_overview — gateway architecture concepts.

### Tertiary (LOW confidence)
- Inference from common gateway failure modes (streaming/tool-use pitfalls, retries/idempotency). Needs validation.

---
*Research completed: 2026-01-25*
*Ready for roadmap: yes*
