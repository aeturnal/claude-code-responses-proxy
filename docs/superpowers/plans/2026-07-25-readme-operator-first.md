# Operator-First README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `README.md` so a Claude Code operator can safely install, start, connect, verify, configure, and troubleshoot the proxy before encountering protocol or contributor details.

**Architecture:** Keep the documentation in one operator-first README. Replace the current reference-first sequence with a Codex-mode quick start, a shorter OpenAI API alternative, consolidated configuration tables, and later compatibility, observability, verification, and troubleshooting sections. Verify every behavioral claim against the current configuration, mapping, routing, and script sources.

**Tech Stack:** Markdown, Python 3.13+, `uv`, FastAPI/Uvicorn, Claude Code, OpenAI Responses API, Codex CLI credentials

## Global Constraints

- Modify `README.md` only; application behavior, tests, dependencies, and configuration defaults are out of scope.
- Optimize the README primarily for people operating the proxy with Claude Code.
- Use Codex mode as the primary quick start and OpenAI API mode as the shorter alternative.
- Bind default startup examples to `127.0.0.1`, because the application has no inbound authentication layer.
- State that exposing the proxy beyond the local machine requires a separate access-control layer.
- Use “Codex mode” and “OpenAI API mode” consistently.
- Preserve useful operator reference information while reducing duplication.
- Describe Codex backend compatibility as best-effort and distinguish deterministic tests from live account/backend availability.
- Do not add badges unless meaningful CI, release, or package status exists.

---

### Task 1: Rewrite and verify the operator-first README

**Files:**
- Modify: `README.md:1-336`
- Reference only: `pyproject.toml`
- Reference only: `src/config.py`
- Reference only: `src/config_model_map.py`
- Reference only: `src/mapping/anthropic_to_openai.py`
- Reference only: `src/handlers/messages.py`
- Reference only: `src/handlers/count_tokens.py`
- Reference only: `src/handlers/anthropic_telemetry.py`
- Reference only: `scripts/verify_codex_gpt56.py`
- Reference only: `scripts/verify_count_tokens.py`
- Reference only: `docs/superpowers/specs/2026-07-25-readme-operator-first-design.md`

**Interfaces:**
- Consumes: Current environment-variable defaults, model-resolution rules, reasoning translation behavior, FastAPI routes, and verification-script entry points from the reference files above.
- Produces: A single `README.md` whose authoritative section order is Overview, Quick start with Codex mode, OpenAI API mode, Model and reasoning routing, Configuration reference, Compatibility and endpoints, Observability and privacy, Verification and development, and Troubleshooting.

- [ ] **Step 1: Capture the implementation-time factual checklist**

Run:

```bash
rg -n \
  "OPENAI_UPSTREAM_MODE|OPENAI_API_KEY|OPENAI_BASE_URL|CODEX_AUTH_PATH|CODEX_BASE_URL|CODEX_DEFAULT_INSTRUCTIONS|CODEX_REFRESH_TOKEN_URL_OVERRIDE|OPENAI_DEFAULT_MODEL|MODEL_MAP_JSON|OPENAI_DEFAULT_REASONING_EFFORT|OBS_|ANTHROPIC_TELEMETRY_" \
  src/config.py src/codex_auth.py

rg -n \
  "DEFAULT_GPT_5_6_MODEL_MAP|thinking|output_config|reasoning|CLAUDE_HAIKU_4_5_PREFIX|GPT_5_6_REASONING_MODELS" \
  src/config.py src/config_model_map.py src/mapping/anthropic_to_openai.py

rg -n '@router\\.(post|get|put|delete)' \
  src/handlers/messages.py \
  src/handlers/count_tokens.py \
  src/handlers/anthropic_telemetry.py
```

Expected:

- Upstream modes are `openai` and `codex`, with `openai` as the application default.
- Default model is `gpt-5.6-terra`; default reasoning effort is `medium`.
- Built-in Claude routes target GPT-5.6 Sol, Terra, and Luna.
- Haiku 4.5 enabled manual thinking maps to `max` only for exact supported GPT-5.6 targets.
- The three public feature areas are messages, token counting, and the Anthropic telemetry sink.

- [ ] **Step 2: Replace the current README structure with the approved operator journey**

Edit `README.md` with `apply_patch`. Use exactly these top-level sections and purposes:

```markdown
# Claude Code → OpenAI Responses Proxy

This FastAPI proxy lets Claude Code use OpenAI Responses-compatible models. It
accepts Anthropic Messages API requests, translates them for either the
ChatGPT Codex backend or the OpenAI Platform API, and returns
Anthropic-compatible responses.

- Claude Code-compatible messages and tool calls
- Anthropic-style streaming and error envelopes
- Local input-token counting
- Configurable Claude-to-OpenAI model and reasoning routing
- Optional structured observability with redaction

> [!WARNING]
> Codex mode is a best-effort integration with the ChatGPT Codex backend.
> Model availability can vary by account and backend state. The proxy has no
> inbound authentication; keep it bound to localhost unless a separate
> access-control layer protects it.

## Quick start: Claude Code with Codex mode
## OpenAI API mode
## Model and reasoning routing
## Configuration reference
## Compatibility and endpoints
## Observability and privacy
## Verification and development
## Troubleshooting
```

Within `Quick start: Claude Code with Codex mode`, provide this complete
operator sequence:

```bash
uv sync
codex login
OPENAI_UPSTREAM_MODE=codex \
  uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
```

Then show the Claude Code shell setup separately so it is clear that it runs in
the operator's Claude Code shell:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000
claude
```

Explain that `codex login` is needed only when Codex CLI credentials are not
already present. Include Python 3.13+ and `uv` as prerequisites. Add a short
success check that tells the reader to send a simple prompt in Claude Code and
use the troubleshooting section if the proxy returns an error.

Within `OpenAI API mode`, provide the nonduplicative alternative:

```bash
export OPENAI_UPSTREAM_MODE=openai
export OPENAI_API_KEY=sk-...
uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
```

Tell the reader to reuse the same `ANTHROPIC_BASE_URL` and Claude Code launch
steps from the quick start.

- [ ] **Step 3: Add the exact routing and reasoning rules**

Under `Model and reasoning routing`, retain the built-in routing table:

| Anthropic model prefix | OpenAI model |
| --- | --- |
| `claude-fable-5` | `gpt-5.6-sol` |
| `claude-opus-5` | `gpt-5.6-sol` |
| `claude-sonnet-5` | `gpt-5.6-terra` |
| `claude-haiku-4-5` | `gpt-5.6-luna` |

Document all of these rules without broadening them:

- `MODEL_MAP_JSON` is checked before built-in routes.
- Keys are trimmed and case-folded.
- Resolution uses exact matches first, then unambiguous prefixes, then
  `OPENAI_DEFAULT_MODEL`.
- `output_config.effort` maps directly only for the exact supported GPT-5.6
  routing targets.
- `thinking.type=disabled` maps to `reasoning.effort=none` for those targets.
- Haiku 4.5 with `thinking.type=enabled` and `budget_tokens` maps to
  `reasoning.effort=max` when its resolved target is exactly
  `gpt-5.6-sol`, `gpt-5.6-terra`, or `gpt-5.6-luna`.
- Other enabled manual-thinking requests return an Anthropic compatibility
  error.
- OpenAI reasoning content is not returned as Anthropic thinking blocks.
- Non-GPT-5.6 operator overrides omit normal effort controls; unsupported
  Haiku manual-thinking overrides return a compatibility error.

Retain one flat and one nested `MODEL_MAP_JSON` example. Use current Claude
identifiers in all request examples; do not use `claude-3-sonnet-20240229`.

- [ ] **Step 4: Consolidate the configuration reference**

Create four Markdown tables with columns `Variable`, `Default`, and `Purpose`.
Populate them with the current values from `src/config.py`:

1. **Upstream**
   - `OPENAI_UPSTREAM_MODE`
   - `OPENAI_API_KEY`
   - `OPENAI_BASE_URL`
   - `CODEX_AUTH_PATH`
   - `CODEX_BASE_URL`
   - `CODEX_DEFAULT_INSTRUCTIONS`
   - `CODEX_REFRESH_TOKEN_URL_OVERRIDE` as development-only and host-allowlisted
2. **Routing**
   - `OPENAI_DEFAULT_MODEL`
   - `MODEL_MAP_JSON`
   - `OPENAI_DEFAULT_REASONING_EFFORT`
3. **Request and stream logging**
   - `OBS_LOG_ENABLED`
   - `OBS_LOG_ALL`
   - `OBS_LOG_FILE`
   - `OBS_STREAM_LOG_ENABLED`
   - `OBS_STREAM_LOG_FILE`
   - `OBS_REDACTION_MODE`
   - `OBS_LOG_PRETTY`
4. **Anthropic telemetry logging**
   - `ANTHROPIC_TELEMETRY_LOG_ENABLED`
   - `ANTHROPIC_TELEMETRY_LOG_FILE`

State required/optional status in the Purpose text. Do not invent a default for
variables that default to unset.

- [ ] **Step 5: Compress endpoint and compatibility documentation**

Under `Compatibility and endpoints`, add this endpoint table:

| Endpoint | Purpose |
| --- | --- |
| `POST /v1/messages` | Non-streaming messages, or Anthropic-style SSE when `"stream": true` |
| `POST /v1/messages/stream` | Compatibility streaming endpoint |
| `POST /v1/messages/count_tokens` | Locally computed OpenAI-aligned input-token count |
| `POST /v1/messages/token_count` | Alias for token counting |
| `POST /api/event_logging/batch` | Anthropic client telemetry sink; returns `204` |

Retain:

- One complete `/v1/messages` `curl` example using a current built-in Claude
  identifier.
- A short note that normal streaming uses the same endpoint with
  `"stream": true`.
- One token-count request and response example.
- The facts that streaming `message_start` reports the Anthropic model name,
  includes locally computed initial input usage, and streaming failures emit an
  Anthropic `event: error` envelope.

Move the Codex compatibility rewrites into a subsection after the endpoint
table. Preserve the current list: `store=false`, forced upstream streaming with
`response.completed` extraction for non-streaming requests, default
instructions injection, unsupported maximum-field stripping, and assistant
history rewriting.

- [ ] **Step 6: Preserve privacy, verification, and troubleshooting details without repetition**

Under `Observability and privacy`:

- State that logging is disabled by default.
- Explain `full`, `partial`, and `none` redaction briefly.
- Retain the `uv sync --extra pii` and spaCy model installation commands.
- State that failed Presidio/spaCy initialization falls back to full
  redaction.
- Add a prominent warning that `OBS_REDACTION_MODE=none` stores prompts and
  outputs in plaintext.

Under `Verification and development`, include:

```bash
uv sync --extra dev
uv run pytest -q
uv run python -m compileall src tests
```

Retain the Codex GPT-5.6 smoke-test command and explicitly state that it checks
live account/backend availability rather than deterministic application
behavior. Retain the token-count alignment command:

```bash
OPENAI_API_KEY=... uv run python scripts/verify_count_tokens.py
```

Under `Troubleshooting`, retain concise entries for:

- Immediate startup 400 responses in Codex mode.
- Missing credentials in each upstream mode.
- SSE parsing failures for non-streaming Codex requests.
- Partial redaction falling back to full redaction.

Link or refer back to the relevant configuration or observability subsection
instead of repeating complete setup instructions.

- [ ] **Step 7: Validate documentation accuracy and Markdown hygiene**

Run:

```bash
rg -n \
  "claude-3-sonnet|0\\.0\\.0\\.0|Legacy manual|manual thinking requests.*return|Server default is" \
  README.md
```

Expected: no matches.

Run:

```bash
rg -n \
  "127\\.0\\.0\\.1|ANTHROPIC_TELEMETRY_LOG_ENABLED|ANTHROPIC_TELEMETRY_LOG_FILE|claude-haiku-4-5|reasoning\\.effort=max|best-effort|no inbound authentication" \
  README.md
```

Expected: every required operator-safety and accuracy term is present.

Run:

```bash
git diff --check
git diff -- README.md
uv run pytest -q
```

Expected:

- `git diff --check` exits successfully.
- The diff changes only `README.md`.
- The complete deterministic test suite passes.
- A manual rendered-Markdown review confirms heading order, table rendering,
  balanced code fences, copyable shell commands, and working relative links.

- [ ] **Step 8: Commit the README rewrite**

```bash
git add README.md
git commit -m "docs: reorganize README for Claude Code operators"
```

Expected: the commit contains only `README.md`.
