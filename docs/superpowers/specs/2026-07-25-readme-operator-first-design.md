# Operator-First README Design

**Date:** 2026-07-25

## Goal

Reorganize and polish `README.md` for people operating the proxy with Claude
Code. The README should lead readers from installation to a working local
Claude Code session before presenting detailed configuration, compatibility,
and contributor reference material.

The rewrite must preserve useful operator reference information while reducing
duplication and correcting stale or misleading behavior descriptions.

## Primary Audience

The primary reader wants to run Claude Code through this proxy. They need to:

1. Understand what the proxy does and its operating boundaries.
2. Choose Codex mode or OpenAI API mode.
3. Start the proxy safely on a local interface.
4. Point Claude Code at it.
5. Verify that the connection works.
6. Configure model routing, reasoning, and logging when needed.
7. Diagnose common failures.

Contributor setup and protocol-level details are secondary.

## Information Architecture

The README will use this order:

1. **Title and overview**
   - One-paragraph description.
   - Compact feature list.
   - Best-effort Codex compatibility statement.
   - Local-use security warning.
2. **Quick start with Codex mode**
   - Prerequisites: Python 3.13+, `uv`, and an authenticated Codex CLI.
   - Dependency installation.
   - Proxy startup on `127.0.0.1`.
   - `ANTHROPIC_BASE_URL` configuration.
   - Claude Code launch and a brief verification check.
3. **OpenAI API mode**
   - Alternative startup using `OPENAI_API_KEY`.
   - Shared steps referenced rather than duplicated.
4. **Model and reasoning routing**
   - Built-in Claude-to-GPT-5.6 routing table.
   - Default and operator override behavior.
   - Supported reasoning controls and manual-thinking compatibility.
5. **Configuration reference**
   - Environment variables grouped into upstream, routing, request logging,
     and telemetry tables.
6. **Compatibility and endpoints**
   - Supported endpoints.
   - Codex-mode request rewrites.
   - Streaming, token counting, and known limitations.
7. **Observability and privacy**
   - Safe logging defaults.
   - Partial-redaction setup.
   - Plaintext logging warning.
8. **Verification and development**
   - Deterministic tests.
   - Codex live smoke test.
   - Token-count alignment script.
9. **Troubleshooting**
   - Credentials.
   - Startup 400 responses.
   - SSE parsing.
   - Partial-redaction fallback.

A table of contents will be included only if the rewritten README remains long
enough that navigation materially benefits.

## Quick-Start Design

Codex mode will be the primary quick start because the README is optimized for
Claude Code operators. Commands must be directly copyable and should:

1. Install the project with `uv sync`.
2. Tell the reader to run `codex login` if Codex CLI credentials are not
   already available.
3. Start Uvicorn with `OPENAI_UPSTREAM_MODE=codex` on `127.0.0.1`.
4. Export `ANTHROPIC_BASE_URL=http://127.0.0.1:8000`.
5. Launch Claude Code from the configured shell.

The README must not imply that a process bound to `0.0.0.0` is accessible only
through localhost. Since the application has no inbound authentication layer,
the default examples will bind to `127.0.0.1`. A warning will explain that
network or public exposure requires a separate access-control layer.

OpenAI API mode will follow as a shorter alternative using
`OPENAI_UPSTREAM_MODE=openai` and `OPENAI_API_KEY`.

## Required Accuracy Corrections

The rewrite must reflect current repository behavior:

- Claude Haiku 4.5 requests with `thinking.type=enabled` and a manual
  `budget_tokens` value map to `reasoning.effort=max` when the resolved target
  is exactly `gpt-5.6-sol`, `gpt-5.6-terra`, or `gpt-5.6-luna`.
- Enabled manual thinking for other Claude families, or for Haiku routed to an
  unsupported model override, returns an Anthropic compatibility error.
- `thinking.type=disabled` maps to `reasoning.effort=none` for supported
  GPT-5.6 routing targets.
- `output_config.effort` maps directly for supported GPT-5.6 routing targets.
- OpenAI reasoning content is not returned as Anthropic thinking blocks.
- Examples will use current built-in Claude model identifiers instead of old
  Claude 3 identifiers that merely exercise default fallback behavior.
- Telemetry logging documentation will include
  `ANTHROPIC_TELEMETRY_LOG_ENABLED` and `ANTHROPIC_TELEMETRY_LOG_FILE`.
- The README will distinguish deterministic test coverage from live Codex
  account and backend model availability.

## Configuration Presentation

Environment variables will be consolidated into four tables:

| Group | Variables |
| --- | --- |
| Upstream | `OPENAI_UPSTREAM_MODE`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `CODEX_AUTH_PATH`, `CODEX_BASE_URL`, `CODEX_DEFAULT_INSTRUCTIONS`, and the development-only refresh URL override |
| Routing | `OPENAI_DEFAULT_MODEL`, `MODEL_MAP_JSON`, `OPENAI_DEFAULT_REASONING_EFFORT` |
| Request logs | `OBS_LOG_ENABLED`, `OBS_LOG_ALL`, `OBS_LOG_FILE`, `OBS_STREAM_LOG_ENABLED`, `OBS_STREAM_LOG_FILE`, `OBS_REDACTION_MODE`, `OBS_LOG_PRETTY` |
| Telemetry | `ANTHROPIC_TELEMETRY_LOG_ENABLED`, `ANTHROPIC_TELEMETRY_LOG_FILE` |

Each table will state defaults, whether a variable is required, and important
security implications. Longer rules such as model-map normalization, prefix
matching, and precedence will remain as prose immediately below the routing
table.

## Endpoint and Compatibility Presentation

The README will retain the existing endpoint coverage while reducing repeated
examples:

- Provide one complete `POST /v1/messages` example.
- Show normal streaming by adding `"stream": true` to `/v1/messages`.
- Describe `POST /v1/messages/stream` as a compatibility endpoint.
- Provide one token-count example.
- Use a compact table for aliases and the telemetry endpoint.

Codex compatibility rewrites will remain documented but will appear after the
basic operating workflow. The section will clearly label these rewrites as
best-effort compatibility behavior rather than guaranteed parity with the
OpenAI Platform Responses API.

## Observability and Privacy

Logging will remain documented as disabled by default. The README will:

- Explain the differences among full, partial, and no redaction.
- Retain the Presidio and spaCy installation instructions for partial
  redaction.
- State that partial redaction falls back to full redaction if initialization
  fails.
- Prominently warn that `OBS_REDACTION_MODE=none` writes prompts and outputs in
  plaintext.
- Avoid implying that redaction or local binding replaces access control.

## Editorial Rules

- Use “Codex mode” and “OpenAI API mode” consistently.
- Remove the redundant `Description` heading.
- Prefer short paragraphs, descriptive headings, and copyable command blocks.
- State a default in one authoritative location and link or refer back to it
  elsewhere.
- Clearly label examples, warnings, defaults, and known limitations.
- Avoid decorative badges unless meaningful CI, release, or package status is
  available.
- Preserve useful troubleshooting guidance while replacing duplicated setup
  text with references to the relevant configuration section.

## Verification

The README-only implementation will be checked by:

1. Comparing every documented environment variable and default against
   `src/config.py`.
2. Comparing routing and reasoning claims against `src/config_model_map.py` and
   `src/mapping/anthropic_to_openai.py`.
3. Comparing endpoint claims against the FastAPI routers.
4. Comparing commands against `pyproject.toml` and the scripts present in
   `scripts/`.
5. Running `git diff --check`.
6. Reviewing the rendered Markdown structure for heading order, tables, code
   fences, and link correctness.

No application behavior or test code is in scope for this README rewrite.
