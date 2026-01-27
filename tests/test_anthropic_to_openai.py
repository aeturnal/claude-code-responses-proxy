from src.mapping.anthropic_to_openai import map_anthropic_request_to_openai
from src.schema.anthropic import Message, MessagesRequest


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
