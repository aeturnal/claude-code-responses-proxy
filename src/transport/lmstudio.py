"""LM Studio compatibility helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from src.config import OPENAI_BASE_URL


def is_lmstudio_base_url() -> bool:
    parsed = urlparse(OPENAI_BASE_URL)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if host in {"localhost", "127.0.0.1", "::1"} and port in {1234, None}:
        return True
    return False


def _extract_message_text(item: Dict[str, Any]) -> Tuple[str, str]:
    role = item.get("role") or "user"
    content = item.get("content")
    text_parts: List[str] = []
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            part_text = part.get("text")
            if isinstance(part_text, str) and part_text:
                text_parts.append(part_text)
    elif isinstance(content, str) and content:
        text_parts.append(content)
    merged_text = "\n\n".join(text_parts).strip()
    return str(role), merged_text


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    input_value = payload.get("input")
    if not isinstance(input_value, list):
        return normalized

    normalized_input: List[Dict[str, Any]] = []
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            normalized_input.append(item)
            continue

        role, merged_text = _extract_message_text(item)
        if role != "user":
            prefix = f"{role.capitalize()}: "
            merged_text = f"{prefix}{merged_text}" if merged_text else prefix.strip()

        normalized_input.append(
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": merged_text,
                    }
                ],
            }
        )

    if normalized_input:
        normalized["input"] = normalized_input
    return normalized


def collapse_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    collapsed = dict(payload)
    input_value = payload.get("input")
    if not isinstance(input_value, list):
        return collapsed

    transcript_parts: List[str] = []
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            role, text = _extract_message_text(item)
            if role:
                transcript_parts.append(f"[{role}]\n{text}".strip())
            elif text:
                transcript_parts.append(text)
            continue
        raw_text = item.get("text")
        if isinstance(raw_text, str) and raw_text:
            transcript_parts.append(raw_text)

    transcript = "\n\n".join(part for part in transcript_parts if part).strip()
    if not transcript:
        return collapsed

    collapsed["input"] = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": transcript,
                }
            ],
        }
    ]
    return collapsed


def fallback_payload_candidates(payload: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Return ordered LM Studio compatibility fallback payloads."""
    candidates: List[Tuple[str, Dict[str, Any]]] = []

    normalized = normalize_payload(payload)
    if normalized != payload:
        candidates.append(("normalized", normalized))

    collapsed = collapse_payload(payload)
    if collapsed != payload and all(collapsed != existing for _, existing in candidates):
        candidates.append(("collapsed", collapsed))

    return candidates
