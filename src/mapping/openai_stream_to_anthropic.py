"""Translate OpenAI Responses streaming events into Anthropic SSE events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


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
