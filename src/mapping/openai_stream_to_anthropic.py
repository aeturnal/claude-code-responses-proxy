"""Translate OpenAI Responses streaming events into Anthropic SSE events."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

import logging

from .harmony import parse_harmony_tool_calls
from .openai_stream_helpers import (
    StreamState,
    append_tool_partial_and_maybe_emit as _append_tool_partial_and_maybe_emit,
    bind_tool_block as _bind_tool_block,
    build_message_start_payload as _build_message_start_payload,
    _emit_content_block_stop,
    emit_harmony_tool_calls as _emit_harmony_tool_calls,
    emit_tool_start_if_needed as _emit_tool_start_if_needed,
    emit_web_search_for_call as _emit_web_search_for_call,
    ensure_tool_meta_defaults as _ensure_tool_meta_defaults,
    extract_final_arguments as _extract_final_arguments,
    extract_indices as _extract_indices,
    extract_partial_json as _extract_partial_json,
    extract_tool_metadata as _extract_tool_metadata,
    format_sse,
    key_for_event as _key_for_event,
    merge_tool_meta as _merge_tool_meta,
    render_tool_input_json as _render_tool_input_json,
    response_from_event as _response_from_event,
)
from .openai_to_anthropic import derive_stop_reason, normalize_openai_usage

logger = logging.getLogger(__name__)

async def translate_openai_events(
    events: AsyncIterator[Dict[str, Any]],
    initial_usage: Optional[Dict[str, Any]] = None,
    model_override: Optional[str] = None,
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
            yield format_sse(
                "message_start",
                _build_message_start_payload(
                    response,
                    initial_usage=initial_usage,
                    model_override=model_override,
                ),
            )
            state.message_started = True
            if event_type == "response.created":
                continue

        if event_type == "response.created":
            continue

        if event_type in {
            "response.reasoning_text.delta",
            "response.reasoning_text.done",
            "response.reasoning_summary_part.added",
            "response.reasoning_summary_part.delta",
            "response.reasoning_summary_part.done",
        }:
            item_id = payload.get("item_id")
            if not isinstance(item_id, str):
                item_id = "unknown_item"
            output_index, content_index = _extract_indices(payload)
            oi = output_index if output_index is not None else -1
            ci = content_index if content_index is not None else -1
            key = (item_id, oi, ci)

            if event_type == "response.reasoning_text.delta":
                delta = payload.get("delta")
                if isinstance(delta, str) and delta:
                    state.reasoning_text_by_key[key] = (
                        state.reasoning_text_by_key.get(key, "") + delta
                    )
            elif event_type == "response.reasoning_text.done":
                final_text = payload.get("text")
                if isinstance(final_text, str):
                    state.reasoning_text_by_key[key] = final_text
                logger.info(
                    "upstream_reasoning_text",
                    extra={
                        "response_id": payload.get("response_id"),
                        "item_id": item_id,
                        "output_index": oi,
                        "content_index": ci,
                        "text": state.reasoning_text_by_key.get(key, ""),
                    },
                )
            else:
                logger.info(
                    "upstream_reasoning_summary",
                    extra={
                        "response_id": payload.get("response_id"),
                        "item_id": item_id,
                        "output_index": oi,
                        "content_index": ci,
                        "payload": payload,
                    },
                )
            continue

        if event_type == "response.content_part.added":
            part = payload.get("part", {})
            if part.get("type") == "output_text":
                continue
            continue

        if event_type == "response.output_text.delta":
            delta = payload.get("delta")
            if isinstance(delta, str):
                text = delta
            elif isinstance(delta, dict):
                text = delta.get("text") or payload.get("text") or ""
            else:
                text = payload.get("text") or ""
            key = _key_for_event(payload, "text") or (-1, -1, "text")
            buffered = state.output_text_buffers.get(key, "") + text
            has_harmony, tool_calls = parse_harmony_tool_calls(buffered)
            if has_harmony:
                state.harmony_text_keys.add(key)
                state.output_text_buffers[key] = buffered
                if state.saw_function_call:
                    continue
                if tool_calls and key not in state.harmony_consumed_keys:
                    for sse_event in _emit_harmony_tool_calls(state, tool_calls):
                        yield sse_event
                    state.harmony_consumed_keys.add(key)
                    state.output_text_buffers.pop(key, None)
                continue
            if key in state.harmony_text_keys:
                state.output_text_buffers[key] = buffered
                continue
            state.output_text_buffers.pop(key, None)
            index, created = state.get_or_create_block_index(key)
            if created:
                state.started_text_blocks.add(index)
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
                key = _key_for_event(payload, "text") or (-1, -1, "text")
                if key in state.harmony_text_keys:
                    buffered = state.output_text_buffers.get(key, "")
                    has_harmony, tool_calls = parse_harmony_tool_calls(buffered)
                    if (
                        has_harmony
                        and tool_calls
                        and not state.saw_function_call
                        and key not in state.harmony_consumed_keys
                    ):
                        for sse_event in _emit_harmony_tool_calls(state, tool_calls):
                            yield sse_event
                        state.harmony_consumed_keys.add(key)
                    state.output_text_buffers.pop(key, None)
                    continue
                index, _ = state.get_or_create_block_index(key)
                if (
                    index not in state.completed_text_blocks
                    and index in state.started_text_blocks
                ):
                    state.completed_text_blocks.add(index)
                    yield format_sse(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": index},
                    )
            continue

        if event_type == "response.output_item.added":
            item = payload.get("item", {})
            if item.get("type") == "web_search_call":
                call_id = item.get("id") if isinstance(item.get("id"), str) else None
                if call_id:
                    action = item.get("action")
                    if isinstance(action, dict):
                        state.web_search_calls[call_id] = action
                    for sse_event in _emit_web_search_for_call(
                        state,
                        call_id,
                        state.web_search_calls.get(call_id, {}),
                        key_payload=payload,
                    ):
                        yield sse_event
                continue
            if item.get("type") == "function_call":
                state.saw_tool_call = True
                state.saw_function_call = True
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                index, _ = _bind_tool_block(state, payload, call_id)
                meta = _merge_tool_meta(state, index, call_id, name)
                state.init_tool_input_buffer(index)
                for sse_event in _emit_tool_start_if_needed(
                    state,
                    index,
                    meta,
                    require_complete_meta=True,
                ):
                    yield sse_event
            continue

        if event_type == "response.output_item.delta":
            item = payload.get("item", {})
            if item.get("type") == "web_search_call":
                call_id = item.get("id") if isinstance(item.get("id"), str) else None
                if call_id:
                    action = item.get("action")
                    if isinstance(action, dict):
                        state.web_search_calls[call_id] = action
                    for sse_event in _emit_web_search_for_call(
                        state,
                        call_id,
                        state.web_search_calls.get(call_id, {}),
                        key_payload=payload,
                    ):
                        yield sse_event
                continue
            if item.get("type") == "function_call":
                state.saw_tool_call = True
                state.saw_function_call = True
                call_id = item.get("call_id") or item.get("id")
                name = item.get("name")
                index, created = _bind_tool_block(state, payload, call_id)
                meta = _merge_tool_meta(state, index, call_id, name)
                if created:
                    state.init_tool_input_buffer(index)
                for sse_event in _emit_tool_start_if_needed(
                    state,
                    index,
                    meta,
                    require_complete_meta=True,
                ):
                    yield sse_event
                arguments = item.get("arguments")
                partial_json = ""
                if isinstance(arguments, str):
                    partial_json = arguments
                elif isinstance(arguments, (dict, list)):
                    partial_json = json.dumps(arguments, ensure_ascii=False)
                for sse_event in _append_tool_partial_and_maybe_emit(
                    state, index, partial_json
                ):
                    yield sse_event
            continue

        if event_type == "response.function_call_arguments.delta":
            call_id, name = _extract_tool_metadata(payload)
            state.saw_tool_call = True
            index, created = _bind_tool_block(state, payload, call_id)
            meta = _merge_tool_meta(state, index, call_id, name)
            if created:
                state.init_tool_input_buffer(index)
            for sse_event in _emit_tool_start_if_needed(
                state,
                index,
                meta,
                require_complete_meta=True,
            ):
                yield sse_event
            partial_json = _extract_partial_json(payload)
            for sse_event in _append_tool_partial_and_maybe_emit(
                state, index, partial_json
            ):
                yield sse_event
            continue

        if event_type == "response.function_call_arguments.done":
            call_id, name = _extract_tool_metadata(payload)
            state.saw_tool_call = True
            index, created = _bind_tool_block(state, payload, call_id)
            meta = _merge_tool_meta(state, index, call_id, name)
            if created:
                state.init_tool_input_buffer(index)
            _ensure_tool_meta_defaults(meta, index, call_id, name)
            for sse_event in _emit_tool_start_if_needed(
                state,
                index,
                meta,
                require_complete_meta=False,
            ):
                yield sse_event
            final_args = _extract_final_arguments(payload)
            if index in state.started_tool_blocks:
                rendered_final = _render_tool_input_json(final_args)
                if rendered_final and not state.tool_input_buffers.get(index):
                    for sse_event in _append_tool_partial_and_maybe_emit(
                        state, index, rendered_final
                    ):
                        yield sse_event
            state.finalize_tool_input(index, raw_override=final_args)
            state.completed_blocks.add(index)
            yield _emit_content_block_stop(index)
            continue

        if event_type == "response.output_item.done":
            item = payload.get("item", {})
            if item.get("type") == "web_search_call":
                call_id = item.get("id") if isinstance(item.get("id"), str) else None
                if call_id:
                    action = item.get("action")
                    if isinstance(action, dict):
                        state.web_search_calls[call_id] = action
                    for sse_event in _emit_web_search_for_call(
                        state,
                        call_id,
                        state.web_search_calls.get(call_id, {}),
                        key_payload=payload,
                    ):
                        yield sse_event
                continue
            if item.get("type") == "function_call":
                state.saw_tool_call = True
                state.saw_function_call = True
                call_id = (
                    item.get("call_id")
                    if isinstance(item.get("call_id"), str)
                    else None
                )
                if call_id is None and isinstance(item.get("id"), str):
                    call_id = item.get("id")
                name = item.get("name") if isinstance(item.get("name"), str) else None
                index, created = _bind_tool_block(state, payload, call_id)
                if index in state.completed_blocks:
                    continue
                meta = _merge_tool_meta(state, index, call_id, name)
                if created:
                    state.init_tool_input_buffer(index)
                _ensure_tool_meta_defaults(meta, index, call_id, name)
                for sse_event in _emit_tool_start_if_needed(
                    state,
                    index,
                    meta,
                    require_complete_meta=False,
                ):
                    yield sse_event
                final_args = None
                if isinstance(item.get("arguments"), str):
                    final_args = item.get("arguments")
                elif isinstance(item.get("arguments"), (dict, list)):
                    final_args = item.get("arguments")
                if index in state.started_tool_blocks:
                    rendered_final = _render_tool_input_json(final_args)
                    if rendered_final and not state.tool_input_buffers.get(index):
                        for sse_event in _append_tool_partial_and_maybe_emit(
                            state, index, rendered_final
                        ):
                            yield sse_event
                state.finalize_tool_input(index, raw_override=final_args)
                state.completed_blocks.add(index)
                yield _emit_content_block_stop(index)
            continue

        if event_type == "response.completed":
            response = _response_from_event(payload) or payload
            for call_id, action in list(state.web_search_calls.items()):
                for sse_event in _emit_web_search_for_call(
                    state,
                    call_id,
                    action,
                    emit_empty_results=True,
                ):
                    yield sse_event
            stop_reason = derive_stop_reason(response)
            if stop_reason == "end_turn" and state.saw_tool_call:
                stop_reason = "tool_use"
            usage = response.get("usage") or payload.get("usage")
            normalized_usage = normalize_openai_usage(
                usage if isinstance(usage, dict) else None
            )
            state.last_usage = normalized_usage
            payload: Dict[str, Any] = {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": normalized_usage,
            }
            yield format_sse("message_delta", payload)
            yield format_sse(
                "message_stop",
                {
                    "type": "message_stop",
                    "usage": normalized_usage,
                },
            )
            continue

        # Unknown event types are ignored to keep stream resilient.
