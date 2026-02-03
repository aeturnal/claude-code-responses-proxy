"""Harmony tag parsing helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple


HARMONY_TAG_RE = re.compile(r"<\|[^>]+?\|>")


def _extract_json_objects(text: str) -> List[str]:
    objects: List[str] = []
    depth = 0
    start_index: int | None = None
    in_string = False
    escape = False
    for index, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start_index is not None:
                objects.append(text[start_index : index + 1])
                start_index = None
    return objects


def parse_harmony_tool_calls(text: str) -> Tuple[bool, List[Dict[str, Any]]]:
    has_harmony = bool(HARMONY_TAG_RE.search(text))
    if not has_harmony:
        return False, []

    tool_calls: List[Dict[str, Any]] = []
    for raw in _extract_json_objects(text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        name = parsed.get("name")
        if not isinstance(name, str) or not name:
            continue
        arguments = parsed.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        tool_calls.append({"name": name, "arguments": arguments})
    return True, tool_calls
