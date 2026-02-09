"""Shared state and helper functions for OpenAI->Anthropic stream translation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, cast

from .openai_to_anthropic import normalize_openai_usage


def format_sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@dataclass
class StreamState:
    message_started: bool = False
    next_block_index: int = 0
    block_index_by_key: Dict[Tuple[int, int, str], int] = field(default_factory=dict)
    tool_input_buffers: Dict[int, str] = field(default_factory=dict)
    last_usage: Optional[Dict[str, Any]] = None
    last_block_index: Optional[int] = None
    tool_metadata_by_index: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    tool_block_by_call_id: Dict[str, int] = field(default_factory=dict)
    completed_blocks: set[int] = field(default_factory=set)
    completed_text_blocks: set[int] = field(default_factory=set)
    started_text_blocks: set[int] = field(default_factory=set)
    started_tool_blocks: set[int] = field(default_factory=set)
    saw_tool_call: bool = False
    saw_function_call: bool = False
    web_search_calls: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    web_search_result_emitted: set[str] = field(default_factory=set)
    web_search_use_emitted: set[str] = field(default_factory=set)
    output_text_buffers: Dict[Tuple[int, int, str], str] = field(default_factory=dict)
    harmony_text_keys: set[Tuple[int, int, str]] = field(default_factory=set)
    harmony_consumed_keys: set[Tuple[int, int, str]] = field(default_factory=set)

    reasoning_text_by_key: Dict[Tuple[str, int, int], str] = field(default_factory=dict)

    def allocate_block_index(self, key: Optional[Tuple[int, int, str]] = None) -> int:
        index = self.next_block_index
        self.next_block_index += 1
        if key is not None:
            self.block_index_by_key[key] = index
        self.last_block_index = index
        return index

    def get_or_create_block_index(
        self, key: Optional[Tuple[int, int, str]]
    ) -> Tuple[int, bool]:
        if key is not None and key in self.block_index_by_key:
            return self.block_index_by_key[key], False
        if key is None and self.last_block_index is not None:
            return self.last_block_index, False
        return self.allocate_block_index(key), True

    def init_tool_input_buffer(self, index: int) -> None:
        self.tool_input_buffers[index] = ""

    def append_tool_input(self, index: int, partial_json: str) -> None:
        self.tool_input_buffers[index] = (
            self.tool_input_buffers.get(index, "") + partial_json
        )

    def finalize_tool_input(
        self, index: int, raw_override: Optional[Any] = None
    ) -> Any:
        raw = (
            raw_override
            if raw_override is not None
            else self.tool_input_buffers.get(index, "")
        )
        self.tool_input_buffers.pop(index, None)
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            return {}
        if not isinstance(raw, str):
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}


def extract_indices(event: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    output_index = event.get("output_index")
    content_index = event.get("content_index")

    for key in ("item", "part", "content", "delta"):
        nested = event.get(key)
        if isinstance(nested, dict):
            output_index = nested.get("output_index", output_index)
            content_index = nested.get("content_index", content_index)

    if content_index is None and isinstance(event.get("index"), int):
        content_index = event.get("index")

    if not isinstance(output_index, int):
        output_index = None
    if not isinstance(content_index, int):
        content_index = None

    return output_index, content_index


def key_for_event(event: Dict[str, Any], kind: str) -> Optional[Tuple[int, int, str]]:
    output_index, content_index = extract_indices(event)
    if output_index is None and content_index is None:
        return None
    return (
        output_index if output_index is not None else -1,
        content_index if content_index is not None else -1,
        kind,
    )


def build_message_start_payload(
    response: Dict[str, Any],
    initial_usage: Optional[Dict[str, Any]] = None,
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    usage_source = response.get("usage")
    if not isinstance(usage_source, dict):
        usage_source = initial_usage
    message: Dict[str, Any] = {
        "type": "message",
        "role": "assistant",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": normalize_openai_usage(
            usage_source if isinstance(usage_source, dict) else None
        ),
    }
    if response.get("id"):
        message["id"] = response["id"]
    if model_override:
        message["model"] = model_override
    elif response.get("model"):
        message["model"] = response["model"]
    return {"type": "message_start", "message": message}


def response_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    response = event.get("response")
    return response if isinstance(response, dict) else {}


def extract_tool_metadata(event: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    call_id = None
    name = None
    for key in ("call_id", "id", "tool_call_id", "item_id"):
        value = event.get(key)
        if isinstance(value, str):
            call_id = value
            break
    if isinstance(event.get("name"), str):
        name = event.get("name")

    for key in ("item", "delta"):
        nested = event.get(key)
        if not isinstance(nested, dict):
            continue
        if call_id is None and isinstance(nested.get("call_id"), str):
            call_id = nested.get("call_id")
        if call_id is None and isinstance(nested.get("id"), str):
            call_id = nested.get("id")
        if call_id is None and isinstance(nested.get("item_id"), str):
            call_id = nested.get("item_id")
        if name is None and isinstance(nested.get("name"), str):
            name = nested.get("name")
    return call_id, name


def extract_partial_json(event: Dict[str, Any]) -> str:
    event_partial = event.get("partial_json")
    if isinstance(event_partial, str):
        return cast(str, event_partial)
    delta = event.get("delta")
    if isinstance(delta, dict):
        delta_partial = delta.get("partial_json")
        if isinstance(delta_partial, str):
            return cast(str, delta_partial)
        delta_arguments = delta.get("arguments")
        if isinstance(delta_arguments, str):
            return cast(str, delta_arguments)
        delta_args = delta.get("arguments")
        if isinstance(delta_args, (dict, list)):
            return json.dumps(delta_args, ensure_ascii=False)
    event_arguments = event.get("arguments")
    if isinstance(event_arguments, str):
        return cast(str, event_arguments)
    event_args = event.get("arguments")
    if isinstance(event_args, (dict, list)):
        return json.dumps(event_args, ensure_ascii=False)
    return ""


def extract_final_arguments(event: Dict[str, Any]) -> Optional[Any]:
    if isinstance(event.get("arguments"), str):
        return event.get("arguments")
    if isinstance(event.get("arguments"), (dict, list)):
        return event.get("arguments")
    item = event.get("item")
    if isinstance(item, dict):
        if isinstance(item.get("arguments"), str):
            return item.get("arguments")
        if isinstance(item.get("arguments"), (dict, list)):
            return item.get("arguments")
    delta = event.get("delta")
    if isinstance(delta, dict):
        if isinstance(delta.get("arguments"), str):
            return delta.get("arguments")
        if isinstance(delta.get("arguments"), (dict, list)):
            return delta.get("arguments")
    return None


def tool_meta_complete(meta: Dict[str, Any]) -> bool:
    return isinstance(meta.get("id"), str) and isinstance(meta.get("name"), str)


def render_tool_input_json(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return ""


def web_search_input_from_action(action: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    query = action.get("query")
    if isinstance(query, str):
        return {"query": query}
    queries = action.get("queries")
    if isinstance(queries, list) and queries:
        first = queries[0]
        if isinstance(first, str):
            return {"query": first}
    return {}


def web_search_results_from_action(action: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = action.get("sources") if isinstance(action, dict) else None
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


def _emit_content_block_start(index: int, content_block: Dict[str, Any]) -> str:
    return format_sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": index,
            "content_block": content_block,
        },
    )


def _emit_content_block_stop(index: int) -> str:
    return format_sse(
        "content_block_stop",
        {"type": "content_block_stop", "index": index},
    )


def _emit_input_json_delta(index: int, partial_json: str) -> str:
    return format_sse(
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": index,
            "delta": {
                "type": "input_json_delta",
                "partial_json": partial_json,
            },
        },
    )


def emit_harmony_tool_calls(state: StreamState, tool_calls: List[Dict[str, Any]]) -> List[str]:
    events: List[str] = []
    for tool_call in tool_calls:
        index = state.allocate_block_index()
        tool_id = f"harmony_tool_{index}"
        state.saw_tool_call = True
        events.append(
            _emit_content_block_start(
                index,
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_call.get("name"),
                    "input": tool_call.get("arguments") or {},
                },
            )
        )
        events.append(_emit_content_block_stop(index))
    return events


def emit_web_search_for_call(
    state: StreamState,
    call_id: str,
    action: Dict[str, Any],
    key_payload: Optional[Dict[str, Any]] = None,
    emit_empty_results: bool = False,
) -> List[str]:
    events: List[str] = []

    if call_id not in state.web_search_use_emitted:
        key = key_for_event(key_payload, "web_search_use") if key_payload else None
        index = state.allocate_block_index(key)
        state.web_search_use_emitted.add(call_id)
        events.append(
            _emit_content_block_start(
                index,
                {
                    "type": "server_tool_use",
                    "id": call_id,
                    "name": "web_search",
                    "input": web_search_input_from_action(action),
                },
            )
        )
        events.append(_emit_content_block_stop(index))

    if call_id not in state.web_search_result_emitted:
        results = web_search_results_from_action(action)
        if results or emit_empty_results:
            key = (
                key_for_event(key_payload, "web_search_result")
                if key_payload
                else None
            )
            index = state.allocate_block_index(key)
            state.web_search_result_emitted.add(call_id)
            events.append(
                _emit_content_block_start(
                    index,
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": call_id,
                        "content": results,
                    },
                )
            )
            events.append(_emit_content_block_stop(index))

    return events


def bind_tool_block(
    state: StreamState,
    payload: Dict[str, Any],
    call_id: Optional[str],
) -> Tuple[int, bool]:
    key = key_for_event(payload, "tool_use")
    index = state.tool_block_by_call_id.get(call_id) if call_id else None
    if index is None:
        index, created = state.get_or_create_block_index(key)
    else:
        created = False
    if call_id and call_id not in state.tool_block_by_call_id:
        state.tool_block_by_call_id[call_id] = index
    return index, created


def merge_tool_meta(
    state: StreamState,
    index: int,
    call_id: Optional[str],
    name: Optional[str],
) -> Dict[str, Any]:
    meta = state.tool_metadata_by_index.setdefault(index, {})
    if call_id and "id" not in meta:
        meta["id"] = call_id
    if name and "name" not in meta:
        meta["name"] = name
    return meta


def ensure_tool_meta_defaults(
    meta: Dict[str, Any],
    index: int,
    call_id: Optional[str],
    name: Optional[str],
) -> None:
    if tool_meta_complete(meta):
        return
    if call_id and "id" not in meta:
        meta["id"] = call_id
    if "id" not in meta:
        meta["id"] = f"tool_call_{index}"
    if name and "name" not in meta:
        meta["name"] = name
    if "name" not in meta:
        meta["name"] = "unknown_tool"


def emit_tool_start_if_needed(
    state: StreamState,
    index: int,
    meta: Dict[str, Any],
    require_complete_meta: bool,
) -> List[str]:
    if require_complete_meta and not tool_meta_complete(meta):
        return []
    if index in state.started_tool_blocks:
        return []

    state.started_tool_blocks.add(index)
    events = [
        _emit_content_block_start(
            index,
            {
                "type": "tool_use",
                "id": meta.get("id"),
                "name": meta.get("name"),
                "input": {},
            },
        )
    ]
    buffered = state.tool_input_buffers.get(index, "")
    if buffered:
        events.append(_emit_input_json_delta(index, buffered))
    return events


def append_tool_partial_and_maybe_emit(
    state: StreamState,
    index: int,
    partial_json: str,
) -> List[str]:
    if not partial_json:
        return []
    state.append_tool_input(index, partial_json)
    if index in state.started_tool_blocks:
        return [_emit_input_json_delta(index, partial_json)]
    return []
