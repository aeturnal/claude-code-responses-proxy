# Feature Research

**Domain:** API compatibility gateways/proxies (Anthropic Messages → OpenAI Responses)
**Researched:** 2026-01-25
**Confidence:** MEDIUM

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **OpenAI-compatible HTTP surface** (base_url + OpenAI client interoperability) | Gateways are expected to be drop-in for existing OpenAI clients | MEDIUM | vLLM and LocalAI both advertise OpenAI-compatible servers as a baseline capability. | 
| **Core endpoint coverage** (Responses/Chat/Completions equivalents as needed) | Users expect the proxy to implement the common OpenAI endpoints they already use | MEDIUM | vLLM lists supported APIs like `/v1/responses`, `/v1/chat/completions`, `/v1/completions` as part of compatibility. Scope to Anthropic Messages mapping. | 
| **Streaming (SSE)** | Real-time UX and tool-using flows assume streaming responses | MEDIUM | OpenAI Responses supports server-sent event streaming; proxies must pass/translate streaming events faithfully. | 
| **Schema translation (request + response)** | Compatibility requires field/shape mapping across providers | HIGH | Map Anthropic Messages (role/content blocks, tool use, system) to OpenAI Responses and back; preserve semantics. | 
| **Error translation + status codes** | Clients depend on stable error shapes and HTTP semantics | MEDIUM | Provide deterministic errors when upstream fails; avoid opaque provider errors. | 
| **Authentication handling** (API keys, env-based config) | Standard for API gateways/proxies | LOW | LiteLLM proxy exposes auth hooks; baseline support expected. | 
| **Rate limiting / throttling** | Protects upstream providers and avoids abuse | MEDIUM | LiteLLM proxy includes rate limiting as a standard gateway feature. | 
| **Observability hooks** (logging + metrics) | Operational visibility is expected in gateway products | MEDIUM | LiteLLM proxy highlights logging hooks and cost/usage tracking as core features. | 
| **Request size / token limits enforcement** | Prevents upstream failures and predictable errors | MEDIUM | Necessary when translating between providers with different hard limits. | 
| **Health endpoint + readiness** | Required for deployment + orchestration | LOW | Standard in gateways; not provider-specific but expected in production.

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Semantic fidelity to Anthropic Messages** (content blocks, tool use, system rules) | Minimizes behavioral drift for Claude Code users | HIGH | Go beyond field mapping; enforce Anthropic semantics even when OpenAI Responses structure differs. | 
| **Hybrid error shape (OpenAI-style + Anthropic detail)** | Improves debuggability while maintaining compatibility | MEDIUM | Helps developers without breaking compatibility clients. | 
| **Provider routing + fallback** | Higher availability and cost/perf optimization | HIGH | LiteLLM Router emphasizes retries/fallback across providers; gateway can apply to responses. | 
| **PII redaction in logs by default** | Privacy + compliance differentiator | MEDIUM | Especially valuable for enterprise/local usage. | 
| **Token accounting that matches Anthropic counting** | Predictable billing + UX parity | HIGH | Aligns with `count_tokens` behavior and message formatting rules. | 
| **Local file storage with file proxying** | Supports `/v1/files` without external dependencies | MEDIUM | Useful for dev + on-prem without S3/GCS. | 
| **Compatibility test suite / self-test CLI** | Confidence in upgrades, reduces regressions | MEDIUM | Differentiates from generic proxies that don’t guarantee semantic parity. | 
| **OpenTelemetry tracing** (logs+metrics+traces out of box) | Enterprise readiness and debugging | MEDIUM | Goes beyond basic logging hooks. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **“Support every OpenAI feature immediately”** | Perception of complete compatibility | Leads to constant churn; breaks Anthropic semantics; unsafe defaults | Ship a compatibility matrix + explicit “supported/not supported” responses. |
| **Silent parameter dropping** | Avoids client errors | Hides bugs and changes behavior unexpectedly | Return validation errors or explicit warnings in response metadata. |
| **Automatic prompt rewriting** | “Improve” results across providers | Changes user intent; hard to debug | Provide opt-in transformation hooks with clear audit logs. |
| **Stateful storage of user prompts by default** | Convenience for debugging | Privacy risk, compliance burden | Explicit opt-in storage with redaction + retention controls. |
| **Opaque provider failover** | Better uptime | Can change model behavior mid-session | Allow explicit routing policy; surface fallback in response metadata. |

## Feature Dependencies

```
OpenAI-compatible HTTP surface
    └──requires──> Schema translation (Anthropic Messages ↔ OpenAI Responses)
                           └──requires──> Deterministic error mapping

Streaming (SSE)
    └──requires──> Schema translation (for event types + deltas)

Count tokens endpoint
    └──requires──> Tokenizer integration + message formatting rules

Files API (upload/list/get)
    └──requires──> Local file storage + path validation + size limits

Batch requests
    └──requires──> Files API + job orchestration

Observability (metrics/traces)
    └──requires──> Request IDs + structured logging

PII redaction
    └──requires──> Logging pipeline + configurable redaction rules

Routing + fallback
    └──requires──> Provider abstraction + retry/backoff
```

### Dependency Notes

- **OpenAI-compatible HTTP surface requires schema translation:** compatibility is impossible without request/response mapping.
- **Streaming requires schema translation:** SSE events must be converted without breaking client expectations.
- **Count tokens requires tokenizer + format rules:** Anthropic token counting is sensitive to message formatting.
- **Files API requires local storage:** file endpoints are meaningless without a stable storage layer.
- **Batch requires Files:** batch input typically references uploaded files.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] **/v1/messages** (Anthropic input shape) → OpenAI Responses translation — core compatibility
- [ ] **/v1/messages/stream** streaming translation — required for real-time tooling
- [ ] **/v1/messages/count_tokens** — Claude Code parity
- [ ] **Deterministic error mapping** — avoids client breakage
- [ ] **Basic auth via env var** — minimum security
- [ ] **Structured logging + metrics** — operational baseline
- [ ] **Request size limits** — predictable failures

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **/v1/files** with local disk storage — enables file workflows
- [ ] **/v1/messages/batches** — async throughput + cost control
- [ ] **PII redaction in logs** — privacy for shared environments
- [ ] **Fallback routing (multi-provider)** — higher availability

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Full OpenAI surface area parity** (audio, image, etc.) — large scope
- [ ] **Advanced policy/guardrail engine** — only needed for enterprise deployments
- [ ] **Multi-tenant billing + budget controls** — if proxy is hosted SaaS

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| /v1/messages translation | HIGH | HIGH | P1 |
| Streaming translation | HIGH | MEDIUM | P1 |
| count_tokens endpoint | HIGH | MEDIUM | P1 |
| Error mapping | HIGH | MEDIUM | P1 |
| Auth via env var | MEDIUM | LOW | P1 |
| Logging + metrics | HIGH | MEDIUM | P1 |
| Request size limits | MEDIUM | LOW | P1 |
| Files API (local) | MEDIUM | MEDIUM | P2 |
| Batches API | MEDIUM | HIGH | P2 |
| PII redaction | MEDIUM | MEDIUM | P2 |
| Routing + fallback | MEDIUM | HIGH | P2 |
| Full OpenAI parity | LOW | HIGH | P3 |
| Advanced policy engine | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | LiteLLM Proxy | vLLM OpenAI-Compatible Server | LocalAI | Our Approach |
|---------|---------------|-------------------------------|---------|--------------|
| OpenAI-compatible HTTP surface | Yes (proxy server) | Yes (OpenAI-compatible server) | Yes (drop-in replacement) | Yes (compatibility gateway) |
| Routing/fallback | Yes (router + retries) | Not core | Not core | Optional (post-MVP) |
| Logging/observability hooks | Yes (callbacks) | Not emphasized | Not emphasized | Built-in logs+metrics+tracing |
| Rate limiting | Yes | Not emphasized | Not emphasized | Basic rate limiting |
| Anthropic Messages semantic fidelity | Not explicit | Not explicit | Not explicit | **Primary differentiator** |

## Sources

- LiteLLM docs (proxy/gateway features, logging hooks, rate limiting, routing): https://docs.litellm.ai/ (Getting Started + proxy sections)
- vLLM OpenAI-compatible server (supported APIs like /v1/responses, /v1/chat/completions, /v1/completions): https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- LocalAI (OpenAI-compatible drop-in replacement): https://localai.io/
- OpenAI Responses API (streaming + responses surface): https://platform.openai.com/docs/api-reference/responses
- Anthropic Messages API (message/content block semantics): https://docs.anthropic.com/en/docs/api/messages

---
*Feature research for: API compatibility gateways/proxies (Anthropic Messages → OpenAI Responses)*
*Researched: 2026-01-25*
