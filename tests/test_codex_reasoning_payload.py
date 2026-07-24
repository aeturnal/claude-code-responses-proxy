from __future__ import annotations

from src.transport.upstream_common import prepare_codex_payload


def test_prepare_codex_payload_preserves_reasoning_and_rewrites_history() -> None:
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
