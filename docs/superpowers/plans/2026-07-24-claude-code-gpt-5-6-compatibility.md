# Claude Code and GPT-5.6 Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Codex-mode proxy route current Claude model families to GPT-5.6 Sol, Terra, and Luna while preserving current Claude Code text, tool, streaming, error, and reasoning-control behavior.

**Architecture:** Keep provider-neutral translation in the Pydantic schemas and pure mapping modules. Keep ChatGPT Codex backend requirements in the two transport modules. Add a small compatibility-error path so a feature that cannot be translated is rejected in an Anthropic-shaped envelope instead of being silently changed or leaking raw validation data.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, HTTPX, structlog, pytest, uv.

## Global Constraints

- Preserve the existing layer order: validate -> map -> transport -> Anthropic envelope.
- Keep PII redaction at every logging sink; never log raw prompts, tool results, credentials, or Pydantic `input` values from validation errors.
- Do not buffer upstream SSE streams or alter the established message/content-block lifecycle.
- `MODEL_MAP_JSON` remains an operator override; its values must not be replaced by hard-coded routing.
- Do not fabricate Anthropic `thinking`/`redacted_thinking` blocks from OpenAI reasoning output.
- Reject manual Claude thinking budgets rather than converting token counts into guessed OpenAI reasoning effort.
- Use `uv run pytest -q` and `uv run python -m compileall -q src tests` for local verification.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/config.py` | Current Claude-family default routing and explicit reasoning fallback configuration. |
| `src/schema/anthropic.py` | Typed Claude Code reasoning-control request shapes. |
| `src/schema/openai.py` | Typed Responses `reasoning` request object. |
| `src/mapping/anthropic_to_openai.py` | Pure effort mapping and manual-thinking rejection. |
| `src/errors/anthropic_error.py` | Compatibility-error type and safe Anthropic envelope helper. |
| `src/app.py` | Redacted validation-error logging without request content. |
| `src/handlers/messages.py` | HTTP/SSE compatibility-error conversion using the existing error-envelope flow. |
| `src/handlers/count_tokens.py` | Same compatibility-error conversion for the token-count endpoint. |
| `src/transport/openai_client.py`, `src/transport/openai_stream.py` | Preserve the `reasoning` field in Codex-mode payloads and retain existing transport rewrites. |
| `scripts/verify_codex_gpt56.py` | Opt-in, live smoke test through the local proxy for model/effort backend acceptance. |
| `tests/test_model_map_config.py` | Default-family route, fallback, and override precedence tests. |
| `tests/test_anthropic_to_openai.py` | Reasoning translation and manual-thinking rejection tests. |
| `tests/test_missing_credentials.py`, `tests/test_missing_codex_credentials.py` | HTTP/SSE error-envelope regression patterns reused for compatibility errors. |
| `tests/test_validation_errors.py` | New redacted request-validation logging and HTTP envelope tests. |
| `README.md` | Supported-current-Claude-Code compatibility matrix, Codex setup, mapping, reasoning policy, and smoke-test instructions. |

## Task 1: Add default GPT-5.6 family routing

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_model_map_config.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `MODEL_MAP_JSON` and `OPENAI_DEFAULT_MODEL` environment values.
- Produces: `resolve_openai_model(anthropic_model: Any) -> str` with current-family defaults and user overrides.

- [ ] **Step 1: Write failing model-routing tests**

Add tests that establish the exact current-family policy and precedence:

```python
@pytest.mark.parametrize(
    ("anthropic_model", "expected"),
    [
        ("claude-fable-5", "gpt-5.6-sol"),
        ("claude-opus-5", "gpt-5.6-sol"),
        ("claude-sonnet-5", "gpt-5.6-terra"),
        ("claude-haiku-4-5-20251001", "gpt-5.6-luna"),
    ],
)
def test_current_claude_family_uses_gpt_5_6_defaults(
    monkeypatch, anthropic_model, expected
):
    monkeypatch.delenv("MODEL_MAP_JSON", raising=False)
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model(anthropic_model) == expected


def test_operator_model_map_overrides_current_family_default(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-sonnet-5": "gpt-5.6-sol"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-sonnet-5") == "gpt-5.6-sol"


def test_unknown_model_defaults_to_terra(monkeypatch):
    monkeypatch.delenv("MODEL_MAP_JSON", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-unknown-99") == "gpt-5.6-terra"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest -q tests/test_model_map_config.py`

Expected: failures for missing GPT-5.6 default routing and the old `gpt-5.2` fallback.

- [ ] **Step 3: Add the smallest default routing implementation**

In `src/config.py`, keep the JSON parser unchanged and add a separate constant plus merged map loader:

```python
DEFAULT_GPT_5_6_MODEL_MAP = {
    "claude-fable-5": "gpt-5.6-sol",
    "claude-opus-5": "gpt-5.6-sol",
    "claude-sonnet-5": "gpt-5.6-terra",
    "claude-haiku-4-5": "gpt-5.6-luna",
}


def get_openai_default_model() -> str:
    return os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5.6-terra")


def _load_model_map() -> Dict[str, str]:
    operator_map = _parse_model_map(os.getenv("MODEL_MAP_JSON"))
    return {**DEFAULT_GPT_5_6_MODEL_MAP, **operator_map}
```

Do not change `resolve_model_from_map`; its existing longest-prefix behavior remains the resolver.

- [ ] **Step 4: Update README configuration examples**

Replace stale model examples with the three GPT-5.6 IDs. Add a routing table and document that `MODEL_MAP_JSON` overrides the built-in current-family route. Include this runnable example:

```bash
export OPENAI_UPSTREAM_MODE=codex
export OPENAI_DEFAULT_MODEL=gpt-5.6-terra
export MODEL_MAP_JSON='{
  "claude-opus-5": "gpt-5.6-sol",
  "claude-sonnet-5": "gpt-5.6-terra",
  "claude-haiku-4-5": "gpt-5.6-luna"
}'
```

- [ ] **Step 5: Run focused tests and commit**

Run: `uv run pytest -q tests/test_model_map_config.py`

Expected: PASS.

Commit:

```bash
git add src/config.py tests/test_model_map_config.py README.md
git commit -m "feat: add GPT-5.6 Claude family routing"
```

## Task 2: Add explicit reasoning-control translation

**Files:**
- Modify: `src/config.py`
- Modify: `src/schema/anthropic.py`
- Modify: `src/schema/openai.py`
- Modify: `src/mapping/anthropic_to_openai.py`
- Modify: `tests/test_anthropic_to_openai.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Anthropic `output_config.effort` and `thinking` request objects.
- Produces: `OpenAIResponsesRequest.reasoning: ReasoningConfig | None`.
- Raises: `AnthropicCompatibilityError` for manual thinking after Task 3 introduces that type.

- [ ] **Step 1: Add the compatibility exception before mapper tests**

In `src/errors/anthropic_error.py`, define a provider-neutral local exception:

```python
class AnthropicCompatibilityError(ValueError):
    """Raised when an Anthropic request cannot be translated safely."""

    def __init__(self, message: str, param: str | None = None) -> None:
        super().__init__(message)
        self.param = param
```

Import this exception in the mapper. This type deliberately contains only the safe message and field path; it must never retain the raw request object.

- [ ] **Step 2: Write failing mapper tests**

Add exact assertions for effort, fallback, disabled thinking, and legacy manual thinking:

```python
def test_output_config_effort_maps_to_responses_reasoning():
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
        output_config=OutputConfig(effort="xhigh"),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "xhigh"


def test_disabled_thinking_maps_to_none_reasoning():
    request = MessagesRequest(
        model="claude-haiku-4-5-20251001",
        messages=[Message(role="user", content="Hi")],
        thinking=ThinkingConfig(type="disabled"),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "none"


def test_manual_thinking_budget_is_rejected():
    request = MessagesRequest(
        model="claude-haiku-4-5-20251001",
        messages=[Message(role="user", content="Hi")],
        thinking=ThinkingConfig(type="enabled", budget_tokens=4096),
    )

    with pytest.raises(AnthropicCompatibilityError, match="budget_tokens"):
        map_anthropic_request_to_openai(request)
```

Also add a test that no explicit Claude reasoning field uses the configured `OPENAI_DEFAULT_REASONING_EFFORT`, defaulting to `medium`.

- [ ] **Step 3: Run the focused mapper tests to verify failure**

Run: `uv run pytest -q tests/test_anthropic_to_openai.py`

Expected: import/model-field failures because `OutputConfig`, `ThinkingConfig`, and `reasoning` are absent.

- [ ] **Step 4: Add typed request and upstream schemas**

In `src/schema/anthropic.py`, add the effort literal and only the requested current Claude Code controls:

```python
ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max"]


class OutputConfig(BaseModel):
    effort: ReasoningEffort | None = None


class ThinkingConfig(BaseModel):
    type: Literal["adaptive", "enabled", "disabled"]
    budget_tokens: int | None = None
    display: Literal["summarized", "omitted"] | None = None
```

Add `output_config: OutputConfig | None = None` and `thinking: ThinkingConfig | None = None` to `MessagesRequest`.

In `src/schema/openai.py`, add:

```python
class ReasoningConfig(BaseModel):
    effort: Literal["none", "low", "medium", "high", "xhigh", "max"]


class OpenAIResponsesRequest(BaseModel):
    # Existing fields unchanged.
    reasoning: ReasoningConfig | None = None
```

- [ ] **Step 5: Implement the explicit mapping policy**

In `src/config.py`, add:

```python
def get_openai_default_reasoning_effort() -> str:
    return os.getenv("OPENAI_DEFAULT_REASONING_EFFORT", "medium")
```

In `src/mapping/anthropic_to_openai.py`, add a helper with this precedence:

```python
def _map_reasoning(request: MessagesRequest) -> ReasoningConfig:
    if request.thinking and request.thinking.type == "enabled":
        raise AnthropicCompatibilityError(
            "thinking.type 'enabled' with budget_tokens cannot be translated "
            "to OpenAI reasoning effort",
            param="thinking",
        )
    if request.thinking and request.thinking.type == "disabled":
        return ReasoningConfig(effort="none")
    if request.output_config and request.output_config.effort:
        return ReasoningConfig(effort=request.output_config.effort)
    return ReasoningConfig(effort=get_openai_default_reasoning_effort())
```

Set `reasoning=_map_reasoning(request)` in the existing `OpenAIResponsesRequest` construction. Do not add `reasoning.mode`, `reasoning.context`, persisted reasoning, or prompt-cache fields in this task.

- [ ] **Step 6: Document the policy and verify**

In README, state that effort values map directly, omitted effort uses `OPENAI_DEFAULT_REASONING_EFFORT=medium`, `thinking.type=disabled` maps to `none`, and manual `budget_tokens` requests return a compatibility error. State explicitly that OpenAI reasoning is not returned as Anthropic thinking blocks.

Run: `uv run pytest -q tests/test_anthropic_to_openai.py tests/test_model_map_config.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/schema/anthropic.py src/schema/openai.py \
  src/mapping/anthropic_to_openai.py src/errors/anthropic_error.py \
  tests/test_anthropic_to_openai.py README.md
git commit -m "feat: map Claude reasoning effort to GPT-5.6"
```

## Task 3: Return safe Anthropic errors and log validation failures safely

**Files:**
- Modify: `src/app.py`
- Modify: `src/handlers/messages.py`
- Modify: `src/handlers/count_tokens.py`
- Modify: `src/handlers/messages_common.py`
- Modify: `tests/test_validation_errors.py`
- Modify: `tests/test_anthropic_to_openai.py`

**Interfaces:**
- Consumes: `RequestValidationError` and `AnthropicCompatibilityError`.
- Produces: HTTP 400 Anthropic envelopes and streaming `event: error` envelopes.
- Produces: redacted validation-error logs that include only locations, types, and messages.

- [ ] **Step 1: Write failing HTTP validation and compatibility tests**

Create `tests/test_validation_errors.py` using `fastapi.testclient.TestClient`:

```python
from fastapi.testclient import TestClient

from src.app import app


def test_invalid_message_request_returns_anthropic_envelope():
    response = TestClient(app).post("/v1/messages", json={"model": "claude-sonnet-5"})

    assert response.status_code == 400
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert response.json()["error"]["message"] == "Invalid request"


def test_validation_error_log_data_excludes_raw_input():
    details = summarize_validation_errors(
        [{"loc": ("body", "messages", 0), "msg": "bad", "type": "value_error", "input": "secret"}]
    )

    assert details == [{"loc": ["body", "messages", 0], "msg": "bad", "type": "value_error"}]
```

Add a mapper/handler test that `thinking.type=enabled` returns a 400 `invalid_request_error` with `error.param == "thinking"`, and a streaming test that asserts the same envelope appears as `event: error`.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `uv run pytest -q tests/test_validation_errors.py tests/test_anthropic_to_openai.py`

Expected: import failures for `summarize_validation_errors` and uncaught compatibility exceptions.

- [ ] **Step 3: Add a safe validation-error summary helper**

In `src/app.py`, add:

```python
def summarize_validation_errors(errors: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in errors
    ]
```

In the existing `handle_validation_error`, log `event="request_validation_error"` with `errors=summarize_validation_errors(exc.errors())`. Keep the response message exactly `"Invalid request"`; do not embed Pydantic details in the client message.

- [ ] **Step 4: Convert mapper compatibility errors through the established handler flow**

Add a helper in `src/handlers/messages_common.py`:

```python
def build_compatibility_error(
    exc: AnthropicCompatibilityError,
) -> tuple[int, Dict[str, Any], Dict[str, Any]]:
    source = {"error": {"type": "invalid_request_error", "message": str(exc)}}
    return (
        400,
        build_anthropic_error(
            400,
            "invalid_request_error",
            str(exc),
            param=exc.param,
            openai_error=source,
        ),
        source,
    )
```

Wrap `map_anthropic_request_to_openai(request)` in both HTTP and stream paths in `src/handlers/messages.py`. For HTTP return `JSONResponse`; for streams yield `format_sse_error(error_payload)` from the generator. Apply the same HTTP conversion to `src/handlers/count_tokens.py`.

- [ ] **Step 5: Run error-focused tests**

Run: `uv run pytest -q tests/test_validation_errors.py tests/test_missing_credentials.py tests/test_missing_codex_credentials.py`

Expected: PASS. The existing missing-credential shapes must remain unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/app.py src/handlers/messages.py src/handlers/messages_common.py \
  src/handlers/count_tokens.py tests/test_validation_errors.py \
  tests/test_anthropic_to_openai.py
git commit -m "feat: report compatibility validation errors safely"
```

## Task 4: Preserve reasoning through Codex transport and add a live smoke test

**Files:**
- Modify: `src/transport/openai_client.py`
- Modify: `src/transport/openai_stream.py`
- Create: `tests/test_codex_reasoning_payload.py`
- Create: `scripts/verify_codex_gpt56.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: a normalized Responses payload containing `reasoning`.
- Produces: a Codex-mode payload that retains `reasoning`, `store=false`, `stream=true`, and the established assistant span rewrite.
- Produces: a manually run account/backend capability report for GPT-5.6 model IDs and reasoning levels.

- [ ] **Step 1: Write focused Codex payload tests**

Extract the duplicated Codex preparation logic from the two transport modules into `prepare_codex_payload(payload: Dict[str, Any]) -> Dict[str, Any>` in `src/transport/upstream_common.py`. Test the exact contract:

```python
def test_prepare_codex_payload_preserves_reasoning_and_rewrites_history():
    prepared = prepare_codex_payload(
        {
            "model": "gpt-5.6-terra",
            "reasoning": {"effort": "high"},
            "input": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "input_text", "text": "prior"}],
                }
            ],
            "max_output_tokens": 512,
            "max_tool_calls": 2,
        }
    )

    assert prepared["store"] is False
    assert prepared["stream"] is True
    assert prepared["reasoning"] == {"effort": "high"}
    assert prepared["input"][0]["content"][0]["type"] == "output_text"
    assert "max_output_tokens" not in prepared
    assert "max_tool_calls" not in prepared
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: `uv run pytest -q tests/test_codex_reasoning_payload.py`

Expected: import failure because `prepare_codex_payload` does not exist.

- [ ] **Step 3: Centralize the existing rewrite without behavioral drift**

In `src/transport/upstream_common.py`, implement `prepare_codex_payload` by copying the current Codex branches exactly: shallow-copy payload, set `store` and `stream`, remove `max_output_tokens`, `max_tokens`, and `max_tool_calls`, inject `CODEX_DEFAULT_INSTRUCTIONS` if empty, and call `rewrite_codex_message_span_types`. Do not remove `reasoning`.

Replace the duplicated branches in `create_openai_response` and `stream_openai_events` with:

```python
request_payload = prepare_codex_payload(payload)
```

only when `config.require_upstream_mode() == "codex"`. Keep non-Codex payloads unchanged.

- [ ] **Step 4: Add the opt-in smoke script**

Create `scripts/verify_codex_gpt56.py`. It must:

1. Read `PROXY_BASE` with default `http://127.0.0.1:8000`.
2. POST one minimal streamed Anthropic request per pair:
   `("claude-opus-5", "high")`, `("claude-sonnet-5", "medium")`, and `("claude-haiku-4-5-20251001", "low")`.
3. Set each payload's `output_config` to `{"effort": effort}` and `max_tokens` to `64`.
4. Parse the response body as either JSON or SSE. Print a line containing the Claude model, requested effort, HTTP status, and an error message if any.
5. Exit 0 only when all three return a success response or an SSE stream without an `event: error`; otherwise exit 1.
6. Never inspect, print, or read `~/.codex/auth.json`; authentication remains the proxy's responsibility.

Use this minimal payload shape:

```python
payload = {
    "model": model,
    "max_tokens": 64,
    "stream": True,
    "output_config": {"effort": effort},
    "messages": [{"role": "user", "content": "Reply with OK."}],
}
```

- [ ] **Step 5: Document the external validation boundary**

In README, document:

```bash
OPENAI_UPSTREAM_MODE=codex \
PROXY_BASE=http://127.0.0.1:8000 \
uv run python scripts/verify_codex_gpt56.py
```

State that the normal test suite is deterministic and that this smoke test confirms the user account and Codex backend allow the requested model/reasoning combinations.

- [ ] **Step 6: Run deterministic verification and commit**

Run: `uv run pytest -q tests/test_codex_reasoning_payload.py tests/test_codex_auth.py tests/test_missing_codex_credentials.py`

Expected: PASS.

Run: `uv run python -m compileall -q src tests scripts`

Expected: exit 0.

Commit:

```bash
git add src/transport/upstream_common.py src/transport/openai_client.py \
  src/transport/openai_stream.py tests/test_codex_reasoning_payload.py \
  scripts/verify_codex_gpt56.py README.md
git commit -m "feat: verify GPT-5.6 Codex compatibility"
```

## Task 5: Run the complete regression suite and perform the user-owned live check

**Files:**
- Modify: `README.md` only if actual smoke-test output exposes an inaccurate instruction or model name.

**Interfaces:**
- Consumes: all committed deterministic changes and a locally running proxy configured with Codex credentials.
- Produces: complete test evidence and, if the user runs it, a live backend acceptance result.

- [ ] **Step 1: Run the complete deterministic suite**

Run: `uv run pytest -q`

Expected: all tests pass, including existing token counting, streaming tool lifecycle, redaction, LM Studio fallback, and Codex credential tests.

- [ ] **Step 2: Run syntax verification**

Run: `uv run python -m compileall -q src tests scripts`

Expected: exit 0 with no compile errors.

- [ ] **Step 3: Start the current checkout in Codex mode**

Run in a dedicated terminal:

```bash
OPENAI_UPSTREAM_MODE=codex \
OPENAI_DEFAULT_MODEL=gpt-5.6-terra \
uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
```

Expected: Uvicorn listens on `127.0.0.1:8000` from `/Users/aeturnal/projects/claude-code-responses-proxy`.

- [ ] **Step 4: Run the user-owned live smoke test**

Run: `PROXY_BASE=http://127.0.0.1:8000 uv run python scripts/verify_codex_gpt56.py`

Expected: one success line each for Opus/Sol, Sonnet/Terra, and Haiku/Luna. If any model is rejected, retain the exact redacted error and report it as an account/backend capability limitation; do not replace the rejected ID automatically.

- [ ] **Step 5: Commit only a necessary documentation correction**

If and only if the live check revealed an inaccurate README instruction, make the smallest documentation correction and commit it:

```bash
git add README.md
git commit -m "docs: clarify Codex GPT-5.6 validation"
```

Otherwise, do not create an empty commit.

## Plan Self-Review

- **Spec coverage:** Task 1 covers current-family model routing and overrides. Task 2 covers safe reasoning controls and intentional manual-thinking rejection. Task 3 covers Anthropic error envelopes and redacted diagnostics. Task 4 preserves Codex transport behavior while exposing a live capability test. Task 5 verifies regression safety and account-specific behavior.
- **Out-of-scope preservation:** No task adds image/document/realtime/MCP functionality or provider-native thinking block conversion.
- **Type consistency:** `AnthropicCompatibilityError` is defined before it is raised; `ThinkingConfig`, `OutputConfig`, and `ReasoningConfig` are defined before mapper use; `prepare_codex_payload` is defined before both transports consume it.
