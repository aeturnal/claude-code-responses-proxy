from __future__ import annotations

import tiktoken

from src.schema.openai import (
    FunctionDefinition,
    FunctionTool,
    InputMessageItem,
    InputTextItem,
    OpenAIResponsesRequest,
)
from src.token_counting.openai_count import (
    count_openai_request_tokens,
    count_tool_tokens,
    get_encoding,
)

MODEL = "gpt-4o-mini-2024-07-18"


def _expected_message_tokens(messages: list[dict[str, str]], model: str) -> int:
    encoding = get_encoding(model)
    tokens_per_message = 3
    tokens_per_name = 1
    total = 0
    for message in messages:
        total += tokens_per_message
        for key, value in message.items():
            total += len(encoding.encode(str(value)))
            if key == "name":
                total += tokens_per_name
    total += 3
    return total


def test_counts_basic_message() -> None:
    request = OpenAIResponsesRequest(
        model=MODEL,
        input=[InputMessageItem(role="user", content=[InputTextItem(text="Hello")])],
    )
    expected = _expected_message_tokens(
        [{"role": "user", "content": "Hello"}],
        MODEL,
    )
    assert count_openai_request_tokens(request) == expected


def test_instructions_increase_count() -> None:
    instructions = "Be helpful."
    request = OpenAIResponsesRequest(
        model=MODEL,
        instructions=instructions,
        input=[InputMessageItem(role="user", content=[InputTextItem(text="Hello")])],
    )
    expected = _expected_message_tokens(
        [
            {"role": "system", "content": instructions},
            {"role": "user", "content": "Hello"},
        ],
        MODEL,
    )
    assert count_openai_request_tokens(request) == expected


def test_tools_increase_count() -> None:
    tool = FunctionTool(
        function=FunctionDefinition(
            name="lookup",
            description="Lookup data",
            parameters={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
        strict=False,
    )
    base_request = OpenAIResponsesRequest(
        model=MODEL,
        input=[InputMessageItem(role="user", content=[InputTextItem(text="Hello")])],
    )
    tool_request = OpenAIResponsesRequest(
        model=MODEL,
        input=[InputMessageItem(role="user", content=[InputTextItem(text="Hello")])],
        tools=[tool],
    )
    base_count = count_openai_request_tokens(base_request)
    with_tool_count = count_openai_request_tokens(tool_request)
    assert with_tool_count > base_count
    assert with_tool_count == base_count + count_tool_tokens([tool], MODEL)


def test_unknown_model_uses_fallback_encoding() -> None:
    encoding = get_encoding("made-up-model")
    assert encoding.name == tiktoken.get_encoding("o200k_base").name

    request = OpenAIResponsesRequest(
        model="made-up-model",
        input=[InputMessageItem(role="user", content=[InputTextItem(text="Hello")])],
    )
    assert count_openai_request_tokens(request) > 0
