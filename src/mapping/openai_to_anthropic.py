"""Map OpenAI Responses outputs to Anthropic Messages responses."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _parse_tool_input(arguments: Any) -> Any:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, list):
        return {}
    if not isinstance(arguments, str):
        return {}
    try:
        parsed = json.loads(arguments)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _web_search_sources_to_results(action: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = action.get("sources")
    if not isinstance(sources, list):
        return []
    results: List[Dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if not isinstance(url, str):
            continue
        result: Dict[str, Any] = {"type": "web_search_result", "url": url}
        title = source.get("title")
        if isinstance(title, str):
            result["title"] = title
        page_age = source.get("page_age")
        if isinstance(page_age, str):
            result["page_age"] = page_age
        results.append(result)
    return results


def _citations_from_annotations(
    text: str, annotations: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    if not annotations:
        return None
    citations: List[Dict[str, Any]] = []
    for annotation in annotations:
        if annotation.get("type") != "url_citation":
            continue
        url = annotation.get("url")
        if not isinstance(url, str):
            continue
        citation: Dict[str, Any] = {
            "type": "web_search_result_location",
            "url": url,
        }
        title = annotation.get("title")
        if isinstance(title, str):
            citation["title"] = title
        start = annotation.get("start_index")
        end = annotation.get("end_index")
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and start >= 0
            and end > start
        ):
            citation["cited_text"] = text[start:end]
        citations.append(citation)
    return citations or None


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


def normalize_openai_usage(usage: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens")
    if not isinstance(input_tokens, int):
        input_tokens = 0
    output_tokens = usage.get("output_tokens")
    if not isinstance(output_tokens, int):
        output_tokens = 0
    details = usage.get("input_tokens_details")
    cached_tokens = 0
    if isinstance(details, dict):
        cached_value = details.get("cached_tokens")
        if isinstance(cached_value, int):
            cached_tokens = cached_value
    uncached_input_tokens = input_tokens - cached_tokens
    if uncached_input_tokens < 0:
        uncached_input_tokens = 0
    return {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cached_tokens,
        "input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
    }


def map_openai_response_to_anthropic(response: Dict[str, Any]) -> Dict[str, Any]:
    """Convert OpenAI Responses output into Anthropic message response."""

    content_blocks: List[Dict[str, Any]] = []
    for item in response.get("output", []):
        item_type = item.get("type")
        if item_type == "web_search_call":
            call_id = item.get("id")
            if isinstance(call_id, str):
                content_blocks.append(
                    {
                        "type": "server_tool_use",
                        "id": call_id,
                        "name": "web_search",
                        "input": {},
                    }
                )
                action = item.get("action")
                if isinstance(action, dict):
                    results = _web_search_sources_to_results(action)
                    content_blocks.append(
                        {
                            "type": "web_search_tool_result",
                            "tool_use_id": call_id,
                            "content": results,
                        }
                    )
            continue
        if item_type == "message":
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    text = content_item.get("text", "")
                    annotations = content_item.get("annotations")
                    citations = None
                    if isinstance(annotations, list):
                        citations = _citations_from_annotations(text, annotations)
                    block: Dict[str, Any] = {
                        "type": "text",
                        "text": text,
                    }
                    if citations:
                        block["citations"] = citations
                    content_blocks.append(block)
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
        "usage": normalize_openai_usage(response.get("usage")),
    }
