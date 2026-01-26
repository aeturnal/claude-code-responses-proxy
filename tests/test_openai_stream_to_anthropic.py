import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Tuple

from src.mapping.openai_stream_to_anthropic import translate_openai_events


async def _iter_events(events: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
    for event in events:
        yield event


def _collect_sse(events: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    async def _collect() -> List[str]:
        output: List[str] = []
        async for chunk in translate_openai_events(_iter_events(events)):
            output.append(chunk)
        return output

    chunks = asyncio.run(_collect())
    parsed: List[Tuple[str, Dict[str, Any]]] = []
    for chunk in chunks:
        for block in chunk.strip().split("\n\n"):
            if not block.strip():
                continue
            event = ""
            data: Dict[str, Any] = {}
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = json.loads(line.split(":", 1)[1].strip())
            if event:
                parsed.append((event, data))
    return parsed


def test_streaming_usage_is_always_present() -> None:
    events = [
        {
            "event": "response.created",
            "data": {
                "type": "response.created",
                "response": {"id": "resp_1", "model": "gpt-4o"},
            },
        },
        {
            "event": "response.completed",
            "data": {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Hi"}],
                        }
                    ],
                },
            },
        },
    ]

    parsed = _collect_sse(events)
    message_start = next(
        payload for event, payload in parsed if event == "message_start"
    )
    message_delta = next(
        payload for event, payload in parsed if event == "message_delta"
    )

    assert message_start["message"]["usage"] == {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    assert message_delta["usage"] == {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_streaming_usage_maps_cached_tokens() -> None:
    events = [
        {
            "event": "response.completed",
            "data": {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Hi"}],
                        }
                    ],
                    "usage": {
                        "input_tokens": 50,
                        "output_tokens": 12,
                        "input_tokens_details": {"cached_tokens": 8},
                    },
                },
            },
        }
    ]

    parsed = _collect_sse(events)
    message_delta = next(
        payload for event, payload in parsed if event == "message_delta"
    )

    assert message_delta["usage"] == {
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 8,
        "input_tokens": 42,
        "output_tokens": 12,
    }
