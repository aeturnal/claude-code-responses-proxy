"""Translate OpenAI Responses streaming events into Anthropic SSE events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional, Tuple

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

    def finalize_tool_input(self, index: int) -> Any:
        raw = self.tool_input_buffers.get(index, "")
        self.tool_input_buffers.pop(index, None)
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


async def translate_openai_events(
    events: AsyncIterator[Dict[str, Any]],
) -> AsyncIterator[str]:
    state = StreamState()

    async for event in events:
        event_type = event.get("type") or event.get("event")

        if event_type == "ping":
            yield format_sse("ping", {"type": "ping"})
            continue

        if not state.message_started:
            response = _response_from_event(event)
            yield format_sse("message_start", _build_message_start_payload(response))
            state.message_started = True
            if event_type == "response.created":
                continue

        if event_type == "response.created":
            continue

        if event_type == "response.content_part.added":
            part = event.get("part", {})
            if part.get("type") == "output_text":
                key = _key_for_event(event, "text")
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
            delta = event.get("delta", {})
            text = delta.get("text") or event.get("text") or ""
            key = _key_for_event(event, "text")
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
                event.get("part", {})
                if event_type == "response.content_part.done"
                else {}
            )
            if (
                event_type == "response.output_text.done"
                or part.get("type") == "output_text"
            ):
                key = _key_for_event(event, "text")
                index, _ = state.get_or_create_block_index(key)
                yield format_sse(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": index},
                )
            continue

        if event_type == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                key = _key_for_event(event, "tool_use")
                index, _ = state.get_or_create_block_index(key)
                call_id = item.get("call_id")
                name = item.get("name")
                if call_id:
                    state.tool_block_by_call_id[call_id] = index
                state.tool_metadata_by_index[index] = {
                    "id": call_id,
                    "name": name,
                }
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

        if event_type == "response.function_call_arguments.delta":
            call_id = (
                event.get("call_id") if isinstance(event.get("call_id"), str) else None
            )
            key = _key_for_event(event, "tool_use")
            index = state.tool_block_by_call_id.get(call_id) if call_id else None
            if index is None:
                index, _ = state.get_or_create_block_index(key)
            partial_json = event.get("partial_json") or ""
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
            call_id = (
                event.get("call_id") if isinstance(event.get("call_id"), str) else None
            )
            key = _key_for_event(event, "tool_use")
            index = state.tool_block_by_call_id.get(call_id) if call_id else None
            if index is None:
                index, _ = state.get_or_create_block_index(key)
            tool_meta = state.tool_metadata_by_index.get(index) or {}
            tool_input = state.finalize_tool_input(index)
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

        if event_type == "response.completed":
            response = _response_from_event(event) or event
            stop_reason = derive_stop_reason(response)
            usage = response.get("usage") or event.get("usage")
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
