# Haiku-to-Luna Maximum Thinking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate Claude Haiku 4.5 manual-thinking requests to GPT-5.6 Luna with maximum reasoning effort.

**Architecture:** Keep the special case in `_map_reasoning`, where Anthropic thinking controls are already translated. Detect the normalized Haiku 4.5 request model before the generic manual-budget rejection; return `ReasoningConfig(effort="max")` only when the resolved OpenAI target supports GPT-5.6 reasoning. Preserve explicit disabled-thinking handling and the current rejection for every non-Haiku manual budget.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest.

## Global Constraints

- Do not log raw user content or secrets.
- Preserve the existing validation -> map -> transport -> Anthropic-envelope layering.
- Keep `thinking: {"type": "disabled"}` mapped to `reasoning.effort: "none"`.
- Do not introduce a generic numeric budget-to-effort conversion.
- Run focused tests, the full pytest suite, and `python -m compileall src tests` before commit.
- Obtain an independent code review before committing application-code changes.

---

### Task 1: Map Haiku manual thinking to Luna max

**Files:**
- Modify: `src/mapping/anthropic_to_openai.py:51-75`
- Modify: `tests/test_anthropic_to_openai.py:219-242`
- Modify: `tests/test_validation_errors.py:7-15, 90-100`

**Interfaces:**
- Consumes: `MessagesRequest.model`, `MessagesRequest.thinking`, and the resolved OpenAI model passed to `_map_reasoning(request, openai_model)`.
- Produces: `ReasoningConfig(effort="max")` for a Claude Haiku 4.5 manual-thinking request routed to an exact GPT-5.6 reasoning model; otherwise preserves the existing return/error behavior.

- [ ] **Step 1: Replace the Haiku manual-thinking unit test with the expected mapping**

```python
def test_haiku_manual_thinking_maps_to_max_reasoning() -> None:
    request = MessagesRequest(
        model="claude-haiku-4-5-20251001",
        messages=[Message(role="user", content="Hi")],
        thinking=ThinkingConfig(type="enabled", budget_tokens=31999),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.model == "gpt-5.6-luna"
    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "max"
```

Add a separate `claude-sonnet-5` manual-thinking test retaining the existing
`AnthropicCompatibilityError` assertion, so the test no longer mistakenly
uses Haiku to verify generic rejection.

- [ ] **Step 2: Run the focused unit tests to verify the new Haiku test fails**

Run:

```bash
uv run pytest -q tests/test_anthropic_to_openai.py -k "haiku_manual_thinking or manual_thinking_budget"
```

Expected: the Haiku mapping assertion fails because `_map_reasoning` currently
raises `AnthropicCompatibilityError` for every `thinking.type == "enabled"`.

- [ ] **Step 3: Add the minimal Haiku exception in `_map_reasoning`**

Add a module-level normalized Anthropic model prefix constant:

```python
CLAUDE_HAIKU_4_5_PREFIX = "claude-haiku-4-5"
```

Before the generic enabled-thinking rejection, implement this narrow branch:

```python
if request.thinking and request.thinking.type == "enabled":
    if (
        request.model.startswith(CLAUDE_HAIKU_4_5_PREFIX)
        and _supports_gpt_5_6_reasoning(openai_model)
    ):
        return ReasoningConfig(effort="max")
    raise AnthropicCompatibilityError(
        "thinking.type 'enabled' with budget_tokens cannot be translated "
        "to OpenAI reasoning effort",
        param="thinking",
    )
```

This deliberately leaves `thinking.type == "disabled"` and
`output_config.effort` behavior untouched below the branch.

- [ ] **Step 4: Add API coverage for the accepted Haiku request**

In `tests/test_validation_errors.py`, add a Haiku request helper that uses
`thinking.type: "enabled"` and `budget_tokens: 31999`. Patch
`messages_handler.create_openai_response` to capture its payload and return a
minimal successful OpenAI Responses result:

```python
captured_payloads: list[dict] = []

async def fake_transport(payload: dict) -> dict:
    captured_payloads.append(payload)
    return {
        "id": "resp_haiku",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "OK"}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

monkeypatch.setattr(messages_handler, "create_openai_response", fake_transport)
response = TestClient(app).post("/v1/messages", json=haiku_request)

assert response.status_code == 200
assert captured_payloads[0]["model"] == "gpt-5.6-luna"
assert captured_payloads[0]["reasoning"] == {"effort": "max"}
```

Keep the existing Sonnet helper and compatibility-error test unchanged; it is
the API-level regression test for generic rejection.

- [ ] **Step 5: Run focused tests to verify the mapper and API behavior**

Run:

```bash
uv run pytest -q tests/test_anthropic_to_openai.py tests/test_validation_errors.py
```

Expected: all selected tests pass, including Haiku manual thinking mapped to
Luna `max`, explicit disabled thinking still mapped to `none`, and Sonnet
manual thinking still rejected.

- [ ] **Step 6: Run full verification**

Run:

```bash
uv run pytest -q
python -m compileall src tests
git diff --check
```

Expected: pytest exits 0, compilation exits 0, and `git diff --check` has no
output.

- [ ] **Step 7: Request independent review, address any findings, then commit**

Have an independent reviewer inspect only the mapper and tests against this
plan. If it identifies a valid defect, correct it and rerun Step 6. Stage only
the mapper and its tests, then commit:

```bash
git add src/mapping/anthropic_to_openai.py tests/test_anthropic_to_openai.py tests/test_validation_errors.py
git commit -m "fix: map Haiku thinking to Luna max"
```
