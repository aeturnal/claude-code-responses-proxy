import pytest

from src.config import (
    _clear_model_map_cache_for_tests,
    get_openai_default_model,
    resolve_openai_model,
)


def test_exact_map_hit(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus-4-5": "gpt-5.2-codex"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-opus-4-5") == "gpt-5.2-codex"


def test_whitespace_and_casefold(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus-4-5": "gpt-5.2-codex"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("Claude-Opus-4-5 ") == "gpt-5.2-codex"


def test_prefix_match(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus-4-5": "gpt-5.2-codex"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-opus-4-5-20250101") == "gpt-5.2-codex"


def test_longest_prefix_wins(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude": "gpt-a", "claude-opus-4-5": "gpt-b"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-opus-4-5-20250101") == "gpt-b"


def test_ambiguous_prefix_tie_raises(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus": "gpt-a", "claude-opus": "gpt-b"}',
    )
    # JSON cannot contain duplicate keys; create ambiguity via normalization collision
    # with different raw keys.
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"CLAUDE-OPUS": "gpt-a", "claude-opus": "gpt-b"}',
    )
    _clear_model_map_cache_for_tests()
    with pytest.raises(ValueError, match="duplicate keys after normalization"):
        resolve_openai_model("claude-opus-4-5")


def test_dynamic_reload(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus-4-5": "gpt-a"}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-opus-4-5") == "gpt-a"

    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"claude-opus-4-5": "gpt-b"}',
    )
    # no cache clear: should reload because cache key is env string
    assert resolve_openai_model("claude-opus-4-5") == "gpt-b"


def test_dynamic_default(monkeypatch):
    monkeypatch.delenv("MODEL_MAP_JSON", raising=False)
    _clear_model_map_cache_for_tests()

    monkeypatch.setenv("OPENAI_DEFAULT_MODEL", "gpt-a")
    assert get_openai_default_model() == "gpt-a"
    assert resolve_openai_model("unknown") == "gpt-a"

    monkeypatch.setenv("OPENAI_DEFAULT_MODEL", "gpt-b")
    assert resolve_openai_model("unknown") == "gpt-b"


def test_invalid_json_raises(monkeypatch):
    monkeypatch.setenv("MODEL_MAP_JSON", "{not json")
    _clear_model_map_cache_for_tests()
    with pytest.raises(ValueError, match="must be valid JSON"):
        resolve_openai_model("claude-opus-4-5")


def test_collision_after_normalization_raises(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"Claude-Opus-4-5": "gpt-a", " claude-opus-4-5 ": "gpt-b"}',
    )
    _clear_model_map_cache_for_tests()
    with pytest.raises(ValueError) as exc:
        resolve_openai_model("claude-opus-4-5")
    assert "Claude-Opus-4-5" in str(exc.value)
    assert " claude-opus-4-5 " in str(exc.value)


def test_nested_shape(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"models": {"claude-opus-4-5": "gpt-5.2-codex"}}',
    )
    _clear_model_map_cache_for_tests()
    assert resolve_openai_model("claude-opus-4-5") == "gpt-5.2-codex"


def test_nested_and_flat_is_rejected(monkeypatch):
    monkeypatch.setenv(
        "MODEL_MAP_JSON",
        '{"models": {"claude-opus-4-5": "gpt-a"}, "claude": "gpt-b"}',
    )
    _clear_model_map_cache_for_tests()
    with pytest.raises(ValueError, match="cannot contain both"):
        resolve_openai_model("claude-opus-4-5")
