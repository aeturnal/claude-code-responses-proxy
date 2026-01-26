"""Map OpenAI Responses outputs to Anthropic Messages responses."""

from __future__ import annotations

import json
from typing import Any, Dict, List


def _parse_tool_input(arguments: Any) -> Any:
    if arguments is None:
        return None
    if isinstance(arguments, (dict, list)):
        return arguments
    if not isinstance(arguments, str):
        return arguments
    try:
        return json.loads(arguments)
    except (TypeError, json.JSONDecodeError):
        return arguments


def derive_stop_reason(response: Dict[str, Any]) -> str:
    """Derive Anthropic stop_reason from OpenAI Responses payload."""

    output_items = response.get("output", [])
    if any(item.get("type") == "function_call" for item in output_items):
        return "tool_use"

    incomplete_reason = None
    if response.get("status") == "incomplete":
        incomplete_reason = response.get("incomplete_details", {}).get("reason")

    if incomplete_reason == "max_output_tokens":
        return "max_tokens"
    if incomplete_reason == "content_filter":
        return "refusal"
    return "end_turn"


def map_openai_response_to_anthropic(response: Dict[str, Any]) -> Dict[str, Any]:
    """Convert OpenAI Responses output into Anthropic message response."""

    content_blocks: List[Dict[str, Any]] = []
    for item in response.get("output", []):
        item_type = item.get("type")
        if item_type == "message":
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    content_blocks.append(
                        {
                            "type": "text",
                            "text": content_item.get("text", ""),
                        }
                    )
            continue
        if item_type == "function_call":
            content_blocks.append(
                {
                    "type": "tool_use",
                    "id": item.get("call_id"),
                    "name": item.get("name"),
                    "input": _parse_tool_input(item.get("arguments")),
                }
            )
            continue
    return {
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "stop_reason": derive_stop_reason(response),
    }
