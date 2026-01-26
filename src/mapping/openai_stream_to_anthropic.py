"""Translate OpenAI Responses streaming events into Anthropic SSE events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Tuple, cast

from .openai_to_anthropic import derive_stop_reason


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
            return None
        if isinstance(raw, (dict, list)):
            return raw
        if not isinstance(raw, str):
            return raw
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw


def _extract_indices(event: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
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


def _key_for_event(event: Dict[str, Any], kind: str) -> Optional[Tuple[int, int, str]]:
    output_index, content_index = _extract_indices(event)
    if output_index is None and content_index is None:
        return None
    return (
        output_index if output_index is not None else -1,
        content_index if content_index is not None else -1,
        kind,
    )


def _build_message_start_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "type": "message",
        "role": "assistant",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
    }
    if response.get("id"):
        message["id"] = response["id"]
    if response.get("model"):
        message["model"] = response["model"]
    return {"type": "message_start", "message": message}


def _response_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    response = event.get("response")
    return response if isinstance(response, dict) else {}


def _extract_tool_metadata(
    event: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
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


def _extract_partial_json(event: Dict[str, Any]) -> str:
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


def _extract_final_arguments(event: Dict[str, Any]) -> Optional[Any]:
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


async def translate_openai_events(
    events: AsyncIterator[Dict[str, Any]],
) -> AsyncIterator[str]:
    state = StreamState()

    async for event in events:
        data = event.get("data")
        payload: Dict[str, Any] = data if isinstance(data, dict) else event
        event_type = payload.get("type")
        if not event_type:
            event_type = event.get("event") or event.get("type")

        if event_type == "ping":
            yield format_sse("ping", {"type": "ping"})
            continue

        if not state.message_started:
            response = _response_from_event(payload)
            yield format_sse("message_start", _build_message_start_payload(response))
            state.message_started = True
            if event_type == "response.created":
                continue

        if event_type == "response.created":
            continue

        if event_type == "response.content_part.added":
            part = payload.get("part", {})
            if part.get("type") == "output_text":
                key = _key_for_event(payload, "text")
                index, _ = state.get_or_create_block_index(key)
                yield format_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            continue

        if event_type == "response.output_text.delta":
            delta = payload.get("delta", {})
            text = delta.get("text") or payload.get("text") or ""
            key = _key_for_event(payload, "text")
            index, created = state.get_or_create_block_index(key)
            if created:
                yield format_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            yield format_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": text},
                },
            )
            continue

        if event_type in {"response.output_text.done", "response.content_part.done"}:
            part = (
                payload.get("part", {})
                if event_type == "response.content_part.done"
                else {}
            )
            if (
                event_type == "response.output_text.done"
                or part.get("type") == "output_text"
            ):
                key = _key_for_event(payload, "text")
                index, _ = state.get_or_create_block_index(key)
                yield format_sse(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": index},
                )
            continue

        if event_type == "response.output_item.added":
            item = payload.get("item", {})
            if item.get("type") == "function_call":
                key = _key_for_event(payload, "tool_use")
                index, _ = state.get_or_create_block_index(key)
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                if call_id:
                    state.tool_block_by_call_id[call_id] = index
                meta = state.tool_metadata_by_index.setdefault(index, {})
                if call_id and "id" not in meta:
                    meta["id"] = call_id
                if name and "name" not in meta:
                    meta["name"] = name
                state.init_tool_input_buffer(index)
                yield format_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": call_id,
                            "name": name,
                            "input": {},
                        },
                    },
                )
            continue

        if event_type == "response.output_item.delta":
            item = payload.get("item", {})
            if item.get("type") == "function_call":
                key = _key_for_event(payload, "tool_use")
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                index = state.tool_block_by_call_id.get(call_id) if call_id else None
                if index is None:
                    index, created = state.get_or_create_block_index(key)
                else:
                    created = False
                if call_id and call_id not in state.tool_block_by_call_id:
                    state.tool_block_by_call_id[call_id] = index
                if name or call_id:
                    meta = state.tool_metadata_by_index.setdefault(index, {})
                    if call_id and "id" not in meta:
                        meta["id"] = call_id
                    if name and "name" not in meta:
                        meta["name"] = name
                if created:
                    meta = state.tool_metadata_by_index.get(index, {})
                    state.init_tool_input_buffer(index)
                    yield format_sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {
                                "type": "tool_use",
                                "id": meta.get("id"),
                                "name": meta.get("name"),
                                "input": {},
                            },
                        },
                    )
                arguments = item.get("arguments")
                partial_json = ""
                if isinstance(arguments, str):
                    partial_json = arguments
                elif isinstance(arguments, (dict, list)):
                    partial_json = json.dumps(arguments, ensure_ascii=False)
                if partial_json:
                    state.append_tool_input(index, partial_json)
                    yield format_sse(
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
            continue

        if event_type == "response.function_call_arguments.delta":
            call_id, name = _extract_tool_metadata(payload)
            key = _key_for_event(payload, "tool_use")
            index = state.tool_block_by_call_id.get(call_id) if call_id else None
            if index is None:
                index, created = state.get_or_create_block_index(key)
            else:
                created = False
            if call_id and call_id not in state.tool_block_by_call_id:
                state.tool_block_by_call_id[call_id] = index
            if name or call_id:
                meta = state.tool_metadata_by_index.setdefault(index, {})
                if call_id and "id" not in meta:
                    meta["id"] = call_id
                if name and "name" not in meta:
                    meta["name"] = name
            if created:
                meta = state.tool_metadata_by_index.get(index, {})
                state.init_tool_input_buffer(index)
                yield format_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": meta.get("id"),
                            "name": meta.get("name"),
                            "input": {},
                        },
                    },
                )
            partial_json = _extract_partial_json(payload)
            state.append_tool_input(index, partial_json)
            yield format_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": partial_json},
                },
            )
            continue

        if event_type == "response.function_call_arguments.done":
            call_id, name = _extract_tool_metadata(payload)
            key = _key_for_event(payload, "tool_use")
            index = state.tool_block_by_call_id.get(call_id) if call_id else None
            if index is None:
                index, created = state.get_or_create_block_index(key)
            else:
                created = False
            if call_id and call_id not in state.tool_block_by_call_id:
                state.tool_block_by_call_id[call_id] = index
            if name or call_id:
                meta = state.tool_metadata_by_index.setdefault(index, {})
                if call_id and "id" not in meta:
                    meta["id"] = call_id
                if name and "name" not in meta:
                    meta["name"] = name
            if created:
                meta = state.tool_metadata_by_index.get(index, {})
                state.init_tool_input_buffer(index)
                yield format_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": meta.get("id"),
                            "name": meta.get("name"),
                            "input": {},
                        },
                    },
                )
            tool_meta = state.tool_metadata_by_index.get(index) or {}
            final_args = _extract_final_arguments(payload)
            tool_input = state.finalize_tool_input(index, raw_override=final_args)
            state.completed_blocks.add(index)
            yield format_sse(
                "content_block_stop",
                {
                    "type": "content_block_stop",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": tool_meta.get("id") or call_id,
                        "name": tool_meta.get("name"),
                        "input": tool_input,
                    },
                },
            )
            continue

        if event_type == "response.output_item.done":
            item = payload.get("item", {})
            if item.get("type") == "function_call":
                call_id = (
                    item.get("call_id")
                    if isinstance(item.get("call_id"), str)
                    else None
                )
                if call_id is None and isinstance(item.get("id"), str):
                    call_id = item.get("id")
                name = item.get("name") if isinstance(item.get("name"), str) else None
                key = _key_for_event(payload, "tool_use")
                index = state.tool_block_by_call_id.get(call_id) if call_id else None
                if index is None:
                    index, created = state.get_or_create_block_index(key)
                else:
                    created = False
                if index in state.completed_blocks:
                    continue
                if call_id and call_id not in state.tool_block_by_call_id:
                    state.tool_block_by_call_id[call_id] = index
                if name or call_id:
                    meta = state.tool_metadata_by_index.setdefault(index, {})
                    if call_id and "id" not in meta:
                        meta["id"] = call_id
                    if name and "name" not in meta:
                        meta["name"] = name
                if created:
                    meta = state.tool_metadata_by_index.get(index, {})
                    state.init_tool_input_buffer(index)
                    yield format_sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {
                                "type": "tool_use",
                                "id": meta.get("id"),
                                "name": meta.get("name"),
                                "input": {},
                            },
                        },
                    )
                tool_meta = state.tool_metadata_by_index.get(index) or {}
                final_args = None
                if isinstance(item.get("arguments"), str):
                    final_args = item.get("arguments")
                elif isinstance(item.get("arguments"), (dict, list)):
                    final_args = item.get("arguments")
                tool_input = state.finalize_tool_input(index, raw_override=final_args)
                state.completed_blocks.add(index)
                yield format_sse(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": tool_meta.get("id") or call_id,
                            "name": tool_meta.get("name") or name,
                            "input": tool_input,
                        },
                    },
                )
            continue

        if event_type == "response.completed":
            response = _response_from_event(payload) or payload
            stop_reason = derive_stop_reason(response)
            usage = response.get("usage") or payload.get("usage")
            if usage is not None:
                state.last_usage = usage
            payload: Dict[str, Any] = {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            }
            if usage is not None:
                payload["usage"] = usage
            yield format_sse("message_delta", payload)
            yield format_sse("message_stop", {"type": "message_stop"})
            continue

        # Unknown event types are ignored to keep stream resilient.
