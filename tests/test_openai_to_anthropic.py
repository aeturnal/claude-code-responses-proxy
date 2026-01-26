from src.mapping.openai_to_anthropic import (
    derive_stop_reason,
    map_openai_response_to_anthropic,
)


def test_completed_message_maps_to_text_block_and_end_turn() -> None:
    response = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello"}],
            }
        ],
    }

    mapped = map_openai_response_to_anthropic(response)

    assert mapped["stop_reason"] == "end_turn"
    assert mapped["content"] == [{"type": "text", "text": "Hello"}]


def test_function_call_maps_to_tool_use_and_stop_reason() -> None:
    response = {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "get_weather",
                "arguments": '{"city":"SF"}',
            }
        ],
    }

    mapped = map_openai_response_to_anthropic(response)

    assert mapped["stop_reason"] == "tool_use"
    assert mapped["content"] == [
        {
            "type": "tool_use",
            "id": "call_1",
            "name": "get_weather",
            "input": {"city": "SF"},
        }
    ]


def test_incomplete_max_tokens_maps_stop_reason() -> None:
    response = {
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hi"}],
            }
        ],
    }

    assert derive_stop_reason(response) == "max_tokens"


def test_incomplete_content_filter_maps_refusal() -> None:
    response = {
        "status": "incomplete",
        "incomplete_details": {"reason": "content_filter"},
        "output": [],
    }

    assert derive_stop_reason(response) == "refusal"
