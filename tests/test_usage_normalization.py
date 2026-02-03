from src.mapping.openai_to_anthropic import normalize_openai_usage


def test_normalize_usage_subtracts_cached_tokens() -> None:
    usage = {
        "input_tokens": 100,
        "output_tokens": 7,
        "input_tokens_details": {"cached_tokens": 80},
    }
    normalized = normalize_openai_usage(usage)
    assert normalized["cache_read_input_tokens"] == 80
    assert normalized["input_tokens"] == 20
    assert normalized["output_tokens"] == 7


def test_normalize_usage_never_negative_input_tokens() -> None:
    usage = {
        "input_tokens": 10,
        "output_tokens": 0,
        "input_tokens_details": {"cached_tokens": 999},
    }
    normalized = normalize_openai_usage(usage)
    assert normalized["cache_read_input_tokens"] == 999
    assert normalized["input_tokens"] == 0


def test_normalize_usage_supports_chat_completion_fields() -> None:
    usage = {
        "prompt_tokens": 50,
        "completion_tokens": 5,
        "prompt_tokens_details": {"cached_tokens": 10},
    }
    normalized = normalize_openai_usage(usage)
    assert normalized["cache_read_input_tokens"] == 10
    assert normalized["input_tokens"] == 40
    assert normalized["output_tokens"] == 5
