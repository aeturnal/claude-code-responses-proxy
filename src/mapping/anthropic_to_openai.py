"""Map Anthropic Messages requests to OpenAI Responses requests."""

from __future__ import annotations

import json
from typing import List, Literal, Optional, Union, cast

from src.config import resolve_openai_model
from src.schema.anthropic import (
    Message,
    MessagesRequest,
    ServerToolUseBlock,
    TextBlock,
    ToolChoiceSpecific,
    ToolReferenceBlock,
    ToolResultBlock,
    ToolUseBlock,
    WebSearchToolResultBlock,
)
from src.schema.openai import (
    FunctionTool,
    FunctionCallItem,
    FunctionCallOutputItem,
    InputItem,
    InputMessageItem,
    InputTextItem,
    OpenAIResponsesRequest,
    ResponseTool,
    ToolChoice as OpenAIToolChoice,
    ToolChoiceFunction,
    ToolChoiceWebSearch,
    WebSearchTool,
    WebSearchToolFilters,
    WebSearchToolUserLocation,
)


def _system_to_instructions(
    system: Optional[Union[str, List[TextBlock]]],
) -> Optional[str]:
    if system is None:
        return None
    if isinstance(system, str):
        return system
    instructions: List[str] = []
    for block in system:
        if not isinstance(block, TextBlock):
            raise ValueError(
                f"Unsupported system block type: {getattr(block, 'type', None)}"
            )
        instructions.append(block.text)
    return "\n".join(instructions)


def _safe_json_dumps(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def _tool_result_to_text(block: ToolResultBlock) -> str:
    if isinstance(block.content, str):
        return block.content
    if isinstance(block.content, dict):
        return _safe_json_dumps(block.content)
    texts: List[str] = []
    for item in block.content:
        if isinstance(item, TextBlock):
            texts.append(item.text)
            continue
        if isinstance(item, ToolReferenceBlock):
            payload = (
                item.model_dump(exclude_none=True)
                if hasattr(item, "model_dump")
                else item.dict(exclude_none=True)
            )
            texts.append(_safe_json_dumps(payload))
            continue
        if isinstance(item, dict):
            texts.append(_safe_json_dumps(item))
            continue
        texts.append(_safe_json_dumps(item))
    return "\n".join(texts)


def _tool_use_to_arguments(block: ToolUseBlock) -> str:
    try:
        return json.dumps(block.input, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(block.input), ensure_ascii=False)


def _server_tool_use_to_text(block: ServerToolUseBlock) -> str:
    try:
        rendered_input = json.dumps(block.input, ensure_ascii=False)
    except TypeError:
        rendered_input = str(block.input)
    return f"[server_tool_use:{block.name}] {rendered_input}"


def _web_search_result_to_text(block: WebSearchToolResultBlock) -> str:
    if isinstance(block.content, dict):
        try:
            rendered = json.dumps(block.content, ensure_ascii=False)
        except TypeError:
            rendered = str(block.content)
        return f"[web_search_result:{block.tool_use_id}] {rendered}"
    lines: List[str] = []
    for item in block.content:
        title = item.title or ""
        if title:
            lines.append(f"- {title} ({item.url})")
        else:
            lines.append(f"- {item.url}")
    if not lines:
        return f"[web_search_result:{block.tool_use_id}]"
    return "\n".join(lines)


def _normalize_tool_parameters(schema: Optional[dict]) -> dict:
    if not schema:
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    if normalized.get("type") == "object":
        if "properties" not in normalized or normalized.get("properties") is None:
            normalized["properties"] = {}
    return normalized


MessageRole = Literal["user", "system", "developer", "assistant"]


def _role_for_message(role: str) -> MessageRole:
    return cast(MessageRole, role)


def _flush_text_items(role: MessageRole, items: List[InputTextItem]) -> List[InputItem]:
    if not items:
        return []
    output_items: List[InputItem] = []
    output_items.append(InputMessageItem(role=role, content=items))
    return output_items


def _message_to_input_items(message: Message) -> List[InputItem]:
    role = _role_for_message(message.role)
    if isinstance(message.content, str):
        output_items: List[InputItem] = []
        output_items.append(
            InputMessageItem(role=role, content=[InputTextItem(text=message.content)])
        )
        return output_items

    output_items: List[InputItem] = []
    buffered_text: List[InputTextItem] = []

    for block in message.content:
        if isinstance(block, TextBlock):
            buffered_text.append(InputTextItem(text=block.text))
            continue
        if isinstance(block, ToolUseBlock):
            output_items.extend(_flush_text_items(role, buffered_text))
            buffered_text = []
            output_items.append(
                FunctionCallItem(
                    call_id=block.id,
                    name=block.name,
                    arguments=_tool_use_to_arguments(block),
                )
            )
            continue
        if isinstance(block, ToolResultBlock):
            output_items.extend(_flush_text_items(role, buffered_text))
            buffered_text = []
            output_items.append(
                FunctionCallOutputItem(
                    call_id=block.tool_use_id,
                    output=_tool_result_to_text(block),
                )
            )
            continue
        if isinstance(block, ServerToolUseBlock):
            buffered_text.append(InputTextItem(text=_server_tool_use_to_text(block)))
            continue
        if isinstance(block, WebSearchToolResultBlock):
            buffered_text.append(InputTextItem(text=_web_search_result_to_text(block)))
            continue
        raise ValueError(
            f"Unsupported content block type: {getattr(block, 'type', None)}"
        )

    output_items.extend(_flush_text_items(role, buffered_text))
    return output_items


def map_anthropic_request_to_openai(request: MessagesRequest) -> OpenAIResponsesRequest:
    """Convert Anthropic Messages request into OpenAI Responses request."""

    instructions = _system_to_instructions(request.system)
    input_items: List[InputItem] = []
    for message in request.messages:
        input_items.extend(_message_to_input_items(message))
    tools: Optional[List[ResponseTool]] = None
    include: Optional[List[str]] = None
    max_tool_calls: Optional[int] = None
    if request.tools:
        tools = []
        web_search_tools: List[WebSearchTool] = []
        for tool in request.tools:
            tool_type = tool.type or ""
            normalized_name = tool.name.lower()
            schema_candidate = (
                tool.input_schema if tool.input_schema is not None else tool.parameters
            )
            is_web_search = tool_type.startswith("web_search_") or (
                normalized_name == "web_search" and not schema_candidate
            )
            if is_web_search:
                filters = None
                if tool.allowed_domains:
                    filters = WebSearchToolFilters(allowed_domains=tool.allowed_domains)
                user_location = None
                if tool.user_location:
                    user_location = WebSearchToolUserLocation(**tool.user_location)
                web_tool = WebSearchTool(
                    filters=filters,
                    user_location=user_location,
                )
                web_search_tools.append(web_tool)
                continue
            tools.append(
                FunctionTool(
                    name=tool.name,
                    description=tool.description,
                    parameters=_normalize_tool_parameters(schema_candidate),
                    strict=tool.strict if tool.strict is not None else False,
                )
            )
        if web_search_tools:
            include = ["web_search_call.action.sources"]
            if not tools and len(web_search_tools) == 1:
                web_tool = web_search_tools[0]
                if request.tools:
                    for tool in request.tools:
                        if tool.max_uses is not None:
                            max_tool_calls = tool.max_uses
                            break
            tools.extend(web_search_tools)

    tool_choice: Optional[OpenAIToolChoice] = None
    if request.tool_choice is not None:
        if isinstance(request.tool_choice, str):
            tool_choice = request.tool_choice
        elif isinstance(request.tool_choice, ToolChoiceSpecific):
            if request.tool_choice.name.lower() == "web_search":
                tool_choice = ToolChoiceWebSearch()
            else:
                tool_choice = ToolChoiceFunction(name=request.tool_choice.name)

    max_output_tokens: Optional[int] = None
    if request.max_tokens is not None and request.max_tokens >= 16:
        max_output_tokens = request.max_tokens

    payload = OpenAIResponsesRequest(
        model=resolve_openai_model(request.model),
        instructions=instructions,
        input=input_items,
        tools=tools,
        tool_choice=tool_choice,
        max_output_tokens=max_output_tokens,
        max_tool_calls=max_tool_calls,
        include=include,
    )
    return payload
