import json

import pytest

from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.schema.anthropic import (
    Message,
    MessagesRequest,
    OutputConfig,
    TextBlock,
    ThinkingConfig,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
)
from src.errors.anthropic_error import AnthropicCompatibilityError
from src.schema.openai import (
    FunctionTool,
    FunctionCallItem,
    FunctionCallOutputItem,
    InputMessageItem,
    WebSearchTool,
)


def test_assistant_role_is_preserved() -> None:
    req = MessagesRequest(
        model="claude-test",
        messages=[Message(role="assistant", content="hi")],
        max_tokens=10,
    )

    mapped = map_anthropic_request_to_openai(req)
    assert mapped.input[0].type == "message"
    assert mapped.input[0].role == "assistant"


def test_developer_role_is_preserved() -> None:
    req = MessagesRequest(
        model="claude-test",
        messages=[Message(role="developer", content="hi")],
        max_tokens=10,
    )

    mapped = map_anthropic_request_to_openai(req)

    assert mapped.input[0].type == "message"
    assert mapped.input[0].role == "developer"


def test_in_band_system_string_merges_with_top_level_instructions_and_is_omitted() -> None:
    req = MessagesRequest(
        model="claude-test",
        system="Top-level instruction",
        messages=[
            Message(role="system", content="In-band instruction"),
            Message(role="user", content="hi"),
        ],
        max_tokens=10,
    )

    mapped = map_anthropic_request_to_openai(req)

    assert mapped.instructions == "Top-level instruction\nIn-band instruction"
    assert all(
        not isinstance(item, InputMessageItem) or item.role != "system"
        for item in mapped.input
    )
    assert isinstance(mapped.input[0], InputMessageItem)
    assert mapped.input[0].role == "user"


def test_in_band_system_text_blocks_become_instructions() -> None:
    req = MessagesRequest(
        model="claude-test",
        messages=[
            Message(
                role="system",
                content=[TextBlock(text="First"), TextBlock(text="Second")],
            ),
        ],
        max_tokens=10,
    )

    mapped = map_anthropic_request_to_openai(req)

    assert mapped.instructions == "First\nSecond"
    assert mapped.input == []


def test_multiple_in_band_system_messages_preserve_order_without_empty_delimiters() -> None:
    req = MessagesRequest(
        model="claude-test",
        system="Top-level instruction",
        messages=[
            Message(role="system", content="First in-band instruction"),
            Message(role="system", content=""),
            Message(role="system", content=[TextBlock(text="Second in-band instruction")]),
            Message(role="system", content=""),
            Message(role="user", content="hi"),
        ],
        max_tokens=10,
    )

    mapped = map_anthropic_request_to_openai(req)

    assert mapped.instructions == (
        "Top-level instruction\n"
        "First in-band instruction\n"
        "Second in-band instruction"
    )
    assert all(
        not isinstance(item, InputMessageItem) or item.role != "system"
        for item in mapped.input
    )


def test_max_output_tokens_omitted_below_minimum() -> None:
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[Message(role="user", content="Hi")],
        max_tokens=1,
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.max_output_tokens is None


def test_max_output_tokens_preserved_at_minimum() -> None:
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[Message(role="user", content="Hi")],
        max_tokens=16,
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.max_output_tokens == 16


def test_output_config_effort_maps_to_responses_reasoning() -> None:
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
        output_config=OutputConfig(effort="xhigh"),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "xhigh"


def test_omitted_reasoning_uses_configured_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_DEFAULT_REASONING_EFFORT", " high ")
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "high"


def test_omitted_reasoning_defaults_to_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_DEFAULT_REASONING_EFFORT", raising=False)
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "medium"


def test_omitted_reasoning_is_not_sent_to_non_gpt_5_6_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_MAP_JSON", '{"claude-sonnet-5": "gpt-4o"}')
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.model == "gpt-4o"
    assert mapped.reasoning is None


def test_reasoning_is_not_sent_to_gpt_5_6_lookalike_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-sonnet-5": "gpt-5.6-sol-custom"}',
    )
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
        output_config=OutputConfig(effort="max"),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.model == "gpt-5.6-sol-custom"
    assert mapped.reasoning is None


def test_disabled_thinking_maps_to_none_reasoning() -> None:
    request = MessagesRequest(
        model="claude-sonnet-5",
        messages=[Message(role="user", content="Hi")],
        thinking=ThinkingConfig(type="disabled"),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "none"


def test_haiku_manual_thinking_budget_maps_to_max_reasoning() -> None:
    request = MessagesRequest(
        model="claude-haiku-4-5-20251001",
        messages=[Message(role="user", content="Hi")],
        thinking=ThinkingConfig(type="enabled", budget_tokens=31999),
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.model == "gpt-5.6-luna"
    assert mapped.reasoning is not None
    assert mapped.reasoning.effort == "max"


def test_tool_schema_prefers_input_schema() -> None:
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    parameters = {
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
    }
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[Message(role="user", content="Hi")],
        tools=[
            ToolDefinition(
                name="search",
                description="Search tool",
                input_schema=input_schema,
                parameters=parameters,
                strict=True,
            )
        ],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.tools is not None
    assert isinstance(mapped.tools[0], FunctionTool)
    assert mapped.tools[0].parameters == input_schema
    assert mapped.tools[0].strict is True


def test_tool_schema_adds_empty_properties() -> None:
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[Message(role="user", content="Hi")],
        tools=[
            ToolDefinition(
                name="noop",
                input_schema={"type": "object"},
            )
        ],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.tools is not None
    assert isinstance(mapped.tools[0], FunctionTool)
    assert mapped.tools[0].parameters == {"type": "object", "properties": {}}


def test_tool_use_and_result_preserve_order() -> None:
    assistant_message = Message(
        role="assistant",
        content=[
            TextBlock(text="Preparing"),
            ToolUseBlock(id="toolu_1", name="search", input={"query": "spurs"}),
            TextBlock(text="After"),
        ],
    )
    user_message = Message(
        role="user",
        content=[
            TextBlock(text="Got it"),
            ToolResultBlock(tool_use_id="toolu_1", content="ok"),
            TextBlock(text="done"),
        ],
    )
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[assistant_message, user_message],
    )

    mapped = map_anthropic_request_to_openai(request)
    input_items = mapped.input

    assert isinstance(input_items[0], InputMessageItem)
    assert input_items[0].role == "assistant"
    assert input_items[0].content[0].text == "Preparing"
    assert isinstance(input_items[1], FunctionCallItem)
    assert input_items[1].call_id == "toolu_1"
    assert input_items[1].name == "search"
    assert json.loads(input_items[1].arguments) == {"query": "spurs"}
    assert isinstance(input_items[2], InputMessageItem)
    assert input_items[2].role == "assistant"
    assert input_items[2].content[0].text == "After"
    assert isinstance(input_items[3], InputMessageItem)
    assert input_items[3].role == "user"
    assert input_items[3].content[0].text == "Got it"
    assert isinstance(input_items[4], FunctionCallOutputItem)
    assert input_items[4].call_id == "toolu_1"
    assert input_items[4].output == "ok"
    assert isinstance(input_items[5], InputMessageItem)
    assert input_items[5].role == "user"
    assert input_items[5].content[0].text == "done"


def test_web_search_tool_maps_to_builtin() -> None:
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[Message(role="user", content="Search")],
        tools=[
            ToolDefinition(
                name="web_search",
                parameters={},
            )
        ],
    )

    mapped = map_anthropic_request_to_openai(request)

    assert mapped.tools is not None
    assert isinstance(mapped.tools[0], WebSearchTool)
    assert mapped.include == ["web_search_call.action.sources"]


def test_tool_result_dict_stringified() -> None:
    user_message = Message(
        role="user",
        content=[
            ToolResultBlock(
                tool_use_id="toolu_1",
                content={"a": 1, "b": "ok"},
            )
        ],
    )
    request = MessagesRequest(
        model="claude-sonnet-4-5-20250929",
        messages=[user_message],
    )

    mapped = map_anthropic_request_to_openai(request)
    input_items = mapped.input

    assert isinstance(input_items[0], FunctionCallOutputItem)
    assert input_items[0].call_id == "toolu_1"
    assert json.loads(input_items[0].output) == {"a": 1, "b": "ok"}
